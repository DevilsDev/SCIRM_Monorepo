"""
Microsoft Dynamics 365 Integration Adapter
Connects to Dynamics 365 Supply Chain Management via Dataverse/OData APIs.
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
import structlog

from .base import ERPAdapter

logger = structlog.get_logger()

DYNAMICS_BASE_URL = os.getenv("DYNAMICS_BASE_URL", "")
DYNAMICS_TENANT_ID = os.getenv("DYNAMICS_TENANT_ID", "")
DYNAMICS_CLIENT_ID = os.getenv("DYNAMICS_CLIENT_ID", "")
DYNAMICS_CLIENT_SECRET = os.getenv("DYNAMICS_CLIENT_SECRET", "")


class DynamicsAdapter(ERPAdapter):
    """Microsoft Dynamics 365 adapter using Dataverse OData APIs."""

    def __init__(self):
        super().__init__({"base_url": DYNAMICS_BASE_URL, "tenant_id": DYNAMICS_TENANT_ID})
        self._client: Optional[httpx.AsyncClient] = None
        self._access_token: Optional[str] = None

    async def _get_token(self) -> str:
        """Acquire OAuth2 token from Azure AD for Dynamics API."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://login.microsoftonline.com/{DYNAMICS_TENANT_ID}/oauth2/v2.0/token",
                data={
                    "client_id": DYNAMICS_CLIENT_ID,
                    "client_secret": DYNAMICS_CLIENT_SECRET,
                    "scope": f"{DYNAMICS_BASE_URL}/.default",
                    "grant_type": "client_credentials",
                },
            )
            resp.raise_for_status()
            return resp.json()["access_token"]

    async def connect(self) -> bool:
        if not DYNAMICS_BASE_URL or not DYNAMICS_CLIENT_ID:
            logger.info("Dynamics 365 not configured — using mock data")
            self.connected = False
            return False

        try:
            self._access_token = await self._get_token()
            self._client = httpx.AsyncClient(
                base_url=DYNAMICS_BASE_URL,
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Accept": "application/json",
                    "OData-MaxVersion": "4.0",
                },
                timeout=30.0,
            )
            resp = await self._client.get("/api/data/v9.2/accounts?$top=1")
            self.connected = resp.status_code == 200
        except Exception as exc:
            logger.warning("Dynamics connection failed", error=str(exc))
            self.connected = False

        return self.connected

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
        self.connected = False

    async def get_suppliers(self, org_id: str) -> List[Dict[str, Any]]:
        if not self.connected:
            return [
                {"supplier_code": "DYN-3001", "name": "Precision Polymers LLC", "country_code": "US", "region": "North America", "source": "dynamics_mock"},
                {"supplier_code": "DYN-3002", "name": "Nordic Packaging Solutions", "country_code": "SE", "region": "Europe", "source": "dynamics_mock"},
            ]

        resp = await self._client.get(
            "/api/data/v9.2/msdyn_vendors",
            params={"$select": "msdyn_vendornumber,msdyn_name,msdyn_countryregionid", "$top": 100},
        )
        resp.raise_for_status()
        items = resp.json().get("value", [])
        return [
            {
                "supplier_code": v.get("msdyn_vendornumber", ""),
                "name": v.get("msdyn_name", ""),
                "country_code": v.get("msdyn_countryregionid", ""),
                "source": "dynamics",
            }
            for v in items
        ]

    async def get_purchase_orders(self, org_id: str, since: Optional[datetime] = None) -> List[Dict[str, Any]]:
        if not self.connected:
            return [
                {"po_number": "DYN-PO-9001", "supplier_code": "DYN-3001", "order_date": "2026-04-05", "amount": 42000.0, "currency": "USD", "source": "dynamics_mock"},
            ]
        return []

    async def get_inventory(self, org_id: str) -> List[Dict[str, Any]]:
        if not self.connected:
            return [
                {"material": "Industrial-Polymer-Z", "warehouse": "WH-Central", "quantity": 8900, "unit": "KG", "source": "dynamics_mock"},
            ]
        return []

    async def get_shipments(self, org_id: str, since: Optional[datetime] = None) -> List[Dict[str, Any]]:
        if not self.connected:
            return [
                {"shipment_id": "DYN-SHP-001", "supplier_code": "DYN-3002", "status": "in_transit", "eta": "2026-04-20", "source": "dynamics_mock"},
            ]
        return []
