"""
ERP Integration Manager
Manages connections to all configured ERP systems and provides unified sync.
"""

import os
from typing import Any, Dict, List

import structlog

from .sap import SAPAdapter
from .oracle import OracleAdapter
from .dynamics import DynamicsAdapter
from .base import ERPAdapter

logger = structlog.get_logger()

# Adapters that are not connected return built-in sample records. Those are only
# included when explicitly enabled (default: development only) and are always
# tagged is_demo, so they can never be mistaken for, or merged into, real ERP data.
_ENV = os.getenv("ENVIRONMENT", "development").lower()
ERP_DEMO_DATA = os.getenv("ERP_DEMO_DATA", "true" if _ENV in {"development", "dev", "local", "test"} else "false").lower() == "true"


def _tag_demo(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{**r, "is_demo": True} for r in records]


class ERPManager:
    """Manages all ERP adapters and provides unified data access."""

    def __init__(self):
        self.adapters: Dict[str, ERPAdapter] = {
            "sap": SAPAdapter(),
            "oracle": OracleAdapter(),
            "dynamics": DynamicsAdapter(),
        }

    async def connect_all(self) -> Dict[str, bool]:
        """Attempt to connect to all configured ERP systems."""
        results = {}
        for name, adapter in self.adapters.items():
            try:
                results[name] = await adapter.connect()
            except Exception as exc:
                logger.warning(f"Failed to connect to {name}", error=str(exc))
                results[name] = False
        return results

    async def disconnect_all(self) -> None:
        for adapter in self.adapters.values():
            try:
                await adapter.disconnect()
            except Exception:
                pass

    async def sync_suppliers(self, org_id: str) -> List[Dict[str, Any]]:
        """Fetch suppliers from all connected ERP systems."""
        all_suppliers = []
        for name, adapter in self.adapters.items():
            if not adapter.connected and not ERP_DEMO_DATA:
                continue
            try:
                suppliers = await adapter.get_suppliers(org_id)
                all_suppliers.extend(suppliers if adapter.connected else _tag_demo(suppliers))
                logger.info(f"Fetched {len(suppliers)} suppliers from {name}")
            except Exception as exc:
                logger.warning(f"Failed to fetch suppliers from {name}", error=str(exc))
        return all_suppliers

    async def sync_all(self, org_id: str) -> Dict[str, Any]:
        """Full sync from all ERP systems."""
        results = {}
        for name, adapter in self.adapters.items():
            if not adapter.connected and not ERP_DEMO_DATA:
                results[name] = {"status": "not_connected"}
                continue
            try:
                synced = await adapter.sync_all(org_id)
                if not adapter.connected:
                    synced = {k: _tag_demo(v) if isinstance(v, list) else v for k, v in synced.items()}
                    synced["status"] = "demo"
                else:
                    synced["status"] = "connected"
                results[name] = synced
            except Exception as exc:
                logger.warning(f"Sync failed for {name}", error=str(exc))
                results[name] = {"error": str(exc)}
        return results

    def health_check(self) -> Dict[str, Any]:
        return {
            name: adapter.health_check()
            for name, adapter in self.adapters.items()
        }


# Global instance
erp_manager = ERPManager()
