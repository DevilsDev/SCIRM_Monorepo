"""
A fake SAP S/4HANA OData V2 server for tests (an httpx transport).

Entity and property names are SAP's published API model (API_BUSINESS_PARTNER and
API_PURCHASEORDER_PROCESS_SRV, as generated in SAP Cloud SDK's VDM packages), written
out here independently of libs/integrations/sap_odata.py, so a wrong field name in the
connector fails these tests. Each entity type also lists unrelated properties, as the
real $metadata does. Supports $metadata, $top/$skip, $inlinecount and nested results
for $expand. It does not evaluate $filter or $select: it records them for assertions.

This is not SAP. It checks that SCIRM reads SAP's documented shapes; the first real
customer connection is still the real test.
"""

import json
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlsplit

import httpx

BP = "/sap/opu/odata/sap/API_BUSINESS_PARTNER"
PO = "/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV"

ENTITY_TYPES = {
    BP: {
        "A_BusinessPartner": ["BusinessPartner", "Customer", "Supplier", "BusinessPartnerCategory",
                              "BusinessPartnerFullName", "BusinessPartnerName", "OrganizationBPName1",
                              "OrganizationBPName2", "OrganizationBPName3", "OrganizationBPName4",
                              "BusinessPartnerIsBlocked", "IsMarkedForArchiving", "SearchTerm1"],
        "A_BusinessPartnerAddress": ["BusinessPartner", "AddressID", "ValidityStartDate", "ValidityEndDate",
                                     "CityName", "Country", "PostalCode", "StreetName", "Region"],
        "A_Supplier": ["Supplier", "AuthorizationGroup", "PaymentIsBlockedForSupplier", "PostingIsBlocked",
                       "PurchasingIsBlocked", "SupplierAccountGroup", "SupplierFullName", "SupplierName",
                       "VATRegistration", "DeletionIndicator", "SupplierProcurementBlock"],
    },
    PO: {
        "A_PurchaseOrder": ["PurchaseOrder", "CompanyCode", "PurchaseOrderType", "PurchasingDocumentDeletionCode",
                            "Supplier", "PurchasingOrganization", "PurchaseOrderDate", "DocumentCurrency"],
        "A_PurchaseOrderItem": ["PurchaseOrder", "PurchaseOrderItem", "PurchasingDocumentDeletionCode", "Plant",
                                "OrderQuantity", "PurchaseOrderQuantityUnit", "DocumentCurrency", "NetPriceAmount",
                                "NetPriceQuantity", "IsCompletelyDelivered", "IsFinallyInvoiced"],
    },
}


def date_ms(iso: str) -> str:
    from datetime import datetime, timezone
    d = datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)
    return f"/Date({int(d.timestamp() * 1000)})/"


def metadata(service: str, net_amount: bool = True, drop: Optional[Dict[str, str]] = None) -> bytes:
    namespace = service.rsplit("/", 1)[-1]
    types, sets = [], []
    for entity, props in ENTITY_TYPES[service].items():
        props = list(props)
        if entity == "A_PurchaseOrderItem" and net_amount:
            props.append("NetAmount")
        if drop and drop.get(entity) in props:
            props.remove(drop[entity])
        body = "".join(f'<Property Name="{p}" Type="Edm.String"/>' for p in props)
        types.append(f'<EntityType Name="{entity}Type"><Key><PropertyRef Name="{props[0]}"/></Key>{body}</EntityType>')
        sets.append(f'<EntitySet Name="{entity}" EntityType="{namespace}.{entity}Type"/>')
    return (f'<?xml version="1.0" encoding="utf-8"?><edmx:Edmx Version="1.0" '
            f'xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx"><edmx:DataServices>'
            f'<Schema Namespace="{namespace}" xmlns="http://schemas.microsoft.com/ado/2008/09/edm">'
            f'{"".join(types)}<EntityContainer Name="{namespace}_Entities">{"".join(sets)}</EntityContainer>'
            f'</Schema></edmx:DataServices></edmx:Edmx>').encode()


def partner(bp: str, supplier: str, name1: str, country: str = "DE", city: str = "Berlin", *, name2: str = "",
            posting_block: bool = False, purchasing_block: bool = False, deleted: bool = False,
            vat: str = "", addresses: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """An A_BusinessPartner as the service returns it with to_Supplier and
    to_BusinessPartnerAddress expanded."""
    return {
        "__metadata": {"type": "API_BUSINESS_PARTNER.A_BusinessPartnerType"},
        "BusinessPartner": bp, "Supplier": supplier, "BusinessPartnerFullName": f"{name1} {name2}".strip(),
        "OrganizationBPName1": name1, "OrganizationBPName2": name2, "OrganizationBPName3": "",
        "OrganizationBPName4": "",
        "to_Supplier": {"Supplier": supplier, "SupplierName": name1, "PostingIsBlocked": posting_block,
                        "PurchasingIsBlocked": purchasing_block, "DeletionIndicator": deleted,
                        "VATRegistration": vat},
        "to_BusinessPartnerAddress": {"results": addresses if addresses is not None else [
            {"AddressID": "1", "Country": country, "CityName": city,
             "ValidityStartDate": "/Date(946684800000+0000)/", "ValidityEndDate": "/Date(253402214400000+0000)/"}]},
    }


def order(number: str, supplier: str, day: str, items: List[Dict[str, Any]], currency: str = "EUR",
          deletion: str = "") -> Dict[str, Any]:
    return {"PurchaseOrder": number, "Supplier": supplier, "PurchaseOrderDate": date_ms(day),
            "DocumentCurrency": currency, "PurchasingDocumentDeletionCode": deletion,
            "to_PurchaseOrderItem": {"results": [
                {"PurchaseOrder": number, "PurchaseOrderItem": f"{(i + 1) * 10:05d}", "DocumentCurrency": currency,
                 "PurchasingDocumentDeletionCode": "", "Plant": "1010", "NetPriceQuantity": "1", **it}
                for i, it in enumerate(items)]}}


class FakeSap(httpx.AsyncBaseTransport):
    def __init__(self, partners=(), orders=(), *, net_amount: bool = True, drop: Optional[Dict[str, str]] = None,
                 status: Optional[Dict[str, int]] = None, fail_after_pages: Optional[int] = None,
                 short_by: int = 0, redirect: bool = False, body_bytes: Optional[int] = None):
        self.data = {f"{BP}/A_BusinessPartner": list(partners), f"{PO}/A_PurchaseOrder": list(orders)}
        self.net_amount, self.drop, self.status = net_amount, drop, status or {}
        self.fail_after_pages, self.short_by, self.redirect, self.body_bytes = fail_after_pages, short_by, redirect, body_bytes
        self.requests: List[httpx.Request] = []
        self.pages = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if self.redirect:
            return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data/"})
        for prefix, code in self.status.items():
            if path.startswith(prefix):
                return httpx.Response(code, text="<html>SAP logon page with internal details</html>")
        if self.body_bytes:
            return httpx.Response(200, content=b"x" * self.body_bytes)
        service = BP if path.startswith(BP) else PO if path.startswith(PO) else None
        if service is None:
            return httpx.Response(404)
        if path.endswith("/$metadata"):
            return httpx.Response(200, content=metadata(service, self.net_amount, self.drop),
                                  headers={"Content-Type": "application/xml"})
        rows = self.data.get(path)
        if rows is None:
            return httpx.Response(404)
        query = {k: v[0] for k, v in parse_qs(urlsplit(str(request.url)).query).items()}
        self.pages += 1
        if self.fail_after_pages is not None and self.pages > self.fail_after_pages:
            return httpx.Response(500, text="internal")
        skip, top = int(query.get("$skip", 0)), int(query.get("$top", 1000))
        page = rows[skip:skip + top]
        if not net_amount_allowed(self.net_amount, query):
            return httpx.Response(400, text="Property NetAmount not found")
        body: Dict[str, Any] = {"results": page}
        if query.get("$inlinecount") == "allpages":
            body["__count"] = str(len(rows) + self.short_by)
        return httpx.Response(200, content=json.dumps({"d": body}).encode(),
                              headers={"Content-Type": "application/json"})

    def queries(self, entity: str) -> List[Dict[str, str]]:
        return [{k: v[0] for k, v in parse_qs(urlsplit(str(r.url)).query).items()}
                for r in self.requests if r.url.path.endswith(f"/{entity}")]


def net_amount_allowed(net_amount: bool, query: Dict[str, str]) -> bool:
    # Like SAP: selecting a property the release does not have is an error.
    return net_amount or "NetAmount" not in query.get("$select", "")
