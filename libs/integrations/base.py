"""
Base adapter interface for all ERP integrations.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()


class ERPAdapter(ABC):
    """Abstract base class for ERP system integrations."""

    def __init__(self, config: Dict[str, str]):
        self.config = config
        self.connected = False
        self.last_sync_at: Optional[datetime] = None

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to the ERP system."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the ERP system."""
        ...

    @abstractmethod
    async def get_suppliers(self, org_id: str) -> List[Dict[str, Any]]:
        """Fetch supplier list from ERP."""
        ...

    @abstractmethod
    async def get_purchase_orders(self, org_id: str, since: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Fetch purchase orders from ERP."""
        ...

    @abstractmethod
    async def get_inventory(self, org_id: str) -> List[Dict[str, Any]]:
        """Fetch inventory/stock levels from ERP."""
        ...

    @abstractmethod
    async def get_shipments(self, org_id: str, since: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Fetch shipment/logistics data from ERP."""
        ...

    async def sync_all(self, org_id: str) -> Dict[str, Any]:
        """Full sync — fetch all data types from ERP."""
        results = {
            "suppliers": await self.get_suppliers(org_id),
            "purchase_orders": await self.get_purchase_orders(org_id),
            "inventory": await self.get_inventory(org_id),
            "shipments": await self.get_shipments(org_id),
            "synced_at": datetime.utcnow().isoformat(),
        }
        self.last_sync_at = datetime.utcnow()
        logger.info("ERP sync completed", adapter=self.__class__.__name__, org_id=org_id)
        return results

    def health_check(self) -> Dict[str, Any]:
        return {
            "adapter": self.__class__.__name__,
            "connected": self.connected,
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
        }
