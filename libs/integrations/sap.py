"""
SAP ERP Integration Adapter
Connects to SAP S/4HANA or SAP ECC via OData/RFC APIs.
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
import structlog

from .base import ERPAdapter

logger = structlog.get_logger()

# SAP Configuration
SAP_BASE_URL = os.getenv("SAP_BASE_URL", "")
SAP_CLIENT = os.getenv("SAP_CLIENT", "100")
SAP_USERNAME = os.getenv("SAP_USERNAME", "")
SAP_PASSWORD = os.getenv("SAP_PASSWORD", "")


class SAPAdapter(ERPAdapter):
    """SAP S/4HANA adapter using OData v4 APIs."""

    def __init__(self):
        super().__init__({
            "base_url": SAP_BASE_URL,
            "client": SAP_CLIENT,
            "username": SAP_USERNAME,
        })
        self._client: Optional[httpx.AsyncClient] = None

    async def connect(self) -> bool:
        if not SAP_BASE_URL or not SAP_USERNAME:
            logger.info("SAP not configured — using mock data")
            self.connected = False
            return False

        self._client = httpx.AsyncClient(
            base_url=SAP_BASE_URL,
            auth=(SAP_USERNAME, SAP_PASSWORD),
            headers={"sap-client": SAP_CLIENT, "Accept": "application/json"},
            timeout=30.0,
        )

        try:
            resp = await self._client.get("/sap/opu/odata/sap/API_BUSINESS_PARTNER/A_Supplier?$top=1")
            self.connected = resp.status_code == 200
        except Exception as exc:
            logger.warning("SAP connection failed", error=str(exc))
            self.connected = False

        return self.connected

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
        self.connected = False

    async def get_suppliers(self, org_id: str) -> List[Dict[str, Any]]:
        if not self.connected:
            return self._mock_suppliers()

        resp = await self._client.get(
            "/sap/opu/odata/sap/API_BUSINESS_PARTNER/A_Supplier",
            params={"$top": 100, "$select": "Supplier,SupplierName,Country,Region"},
        )
        resp.raise_for_status()
        results = resp.json().get("d", {}).get("results", [])

        return [
            {
                "supplier_code": r.get("Supplier", ""),
                "name": r.get("SupplierName", ""),
                "country_code": r.get("Country", ""),
                "region": r.get("Region", ""),
                "source": "sap",
            }
            for r in results
        ]

    async def get_purchase_orders(self, org_id: str, since: Optional[datetime] = None) -> List[Dict[str, Any]]:
        if not self.connected:
            return self._mock_purchase_orders()

        params = {"$top": 200, "$select": "PurchaseOrder,Supplier,PurchaseOrderDate,NetAmount,Currency"}
        if since:
            params["$filter"] = f"PurchaseOrderDate ge datetime'{since.strftime('%Y-%m-%dT%H:%M:%S')}'"

        resp = await self._client.get("/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrder", params=params)
        resp.raise_for_status()
        results = resp.json().get("d", {}).get("results", [])

        return [
            {
                "po_number": r.get("PurchaseOrder", ""),
                "supplier_code": r.get("Supplier", ""),
                "order_date": r.get("PurchaseOrderDate", ""),
                "amount": float(r.get("NetAmount", 0)),
                "currency": r.get("Currency", "USD"),
                "source": "sap",
            }
            for r in results
        ]

    async def get_inventory(self, org_id: str) -> List[Dict[str, Any]]:
        if not self.connected:
            return self._mock_inventory()
        return []

    async def get_shipments(self, org_id: str, since: Optional[datetime] = None) -> List[Dict[str, Any]]:
        if not self.connected:
            return self._mock_shipments()
        return []

    # --- Mock data for development ---

    def _mock_suppliers(self) -> List[Dict[str, Any]]:
        return [
            {"supplier_code": "SAP-1001", "name": "Global Pharma Ingredients", "country_code": "DE", "region": "Europe", "source": "sap_mock"},
            {"supplier_code": "SAP-1002", "name": "Pacific Chemical Corp", "country_code": "JP", "region": "Asia Pacific", "source": "sap_mock"},
            {"supplier_code": "SAP-1003", "name": "American Excipients Ltd", "country_code": "US", "region": "North America", "source": "sap_mock"},
        ]

    def _mock_purchase_orders(self) -> List[Dict[str, Any]]:
        return [
            {"po_number": "PO-4500001", "supplier_code": "SAP-1001", "order_date": "2026-03-15", "amount": 125000.0, "currency": "EUR", "source": "sap_mock"},
            {"po_number": "PO-4500002", "supplier_code": "SAP-1002", "order_date": "2026-04-01", "amount": 89000.0, "currency": "USD", "source": "sap_mock"},
        ]

    def _mock_inventory(self) -> List[Dict[str, Any]]:
        return [
            {"material": "API-Compound-X", "plant": "DE01", "quantity": 5200, "unit": "KG", "source": "sap_mock"},
            {"material": "Excipient-Y", "plant": "US01", "quantity": 12400, "unit": "KG", "source": "sap_mock"},
        ]

    def _mock_shipments(self) -> List[Dict[str, Any]]:
        return [
            {"shipment_id": "SHP-80001", "supplier_code": "SAP-1001", "status": "in_transit", "eta": "2026-04-18", "source": "sap_mock"},
        ]
