"""
Oracle ERP Cloud Integration Adapter
Connects to Oracle Fusion Cloud ERP via REST APIs.
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
import structlog

from .base import ERPAdapter

logger = structlog.get_logger()

ORACLE_BASE_URL = os.getenv("ORACLE_ERP_BASE_URL", "")
ORACLE_USERNAME = os.getenv("ORACLE_ERP_USERNAME", "")
ORACLE_PASSWORD = os.getenv("ORACLE_ERP_PASSWORD", "")


class OracleAdapter(ERPAdapter):
    """Oracle Fusion Cloud ERP adapter using REST APIs."""

    def __init__(self):
        super().__init__({"base_url": ORACLE_BASE_URL, "username": ORACLE_USERNAME})
        self._client: Optional[httpx.AsyncClient] = None

    async def connect(self) -> bool:
        if not ORACLE_BASE_URL or not ORACLE_USERNAME:
            logger.info("Oracle ERP not configured — using mock data")
            self.connected = False
            return False

        self._client = httpx.AsyncClient(
            base_url=ORACLE_BASE_URL,
            auth=(ORACLE_USERNAME, ORACLE_PASSWORD),
            headers={"Accept": "application/json"},
            timeout=30.0,
        )

        try:
            resp = await self._client.get("/fscmRestApi/resources/latest/suppliers?limit=1")
            self.connected = resp.status_code == 200
        except Exception as exc:
            logger.warning("Oracle connection failed", error=str(exc))
            self.connected = False

        return self.connected

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
        self.connected = False

    async def get_suppliers(self, org_id: str) -> List[Dict[str, Any]]:
        if not self.connected:
            return [
                {"supplier_code": "ORA-2001", "name": "MedDevice Components Inc", "country_code": "US", "region": "North America", "source": "oracle_mock"},
                {"supplier_code": "ORA-2002", "name": "BioSynth Materials AG", "country_code": "CH", "region": "Europe", "source": "oracle_mock"},
            ]

        resp = await self._client.get("/fscmRestApi/resources/latest/suppliers", params={"limit": 100})
        resp.raise_for_status()
        items = resp.json().get("items", [])
        return [
            {
                "supplier_code": s.get("SupplierNumber", ""),
                "name": s.get("Supplier", ""),
                "country_code": s.get("Country", ""),
                "source": "oracle",
            }
            for s in items
        ]

    async def get_purchase_orders(self, org_id: str, since: Optional[datetime] = None) -> List[Dict[str, Any]]:
        if not self.connected:
            return [
                {"po_number": "ORA-PO-7001", "supplier_code": "ORA-2001", "order_date": "2026-03-20", "amount": 67500.0, "currency": "USD", "source": "oracle_mock"},
            ]
        return []

    async def get_inventory(self, org_id: str) -> List[Dict[str, Any]]:
        if not self.connected:
            return [
                {"material": "Sensor-Module-A", "warehouse": "WH-East", "quantity": 3400, "unit": "PCS", "source": "oracle_mock"},
            ]
        return []

    async def get_shipments(self, org_id: str, since: Optional[datetime] = None) -> List[Dict[str, Any]]:
        if not self.connected:
            return [
                {"shipment_id": "ORA-SHP-001", "supplier_code": "ORA-2002", "status": "delivered", "eta": "2026-04-10", "source": "oracle_mock"},
            ]
        return []
