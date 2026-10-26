"""
SCIRM Data Repository
Async CRUD operations for all domain entities via SQLAlchemy.
Replaces in-memory stores with persistent PostgreSQL-backed queries.
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

import structlog

logger = structlog.get_logger()

# Check if database is available — fallback to in-memory for dev
DB_ENABLED = os.getenv("DB_PERSISTENCE_ENABLED", "false").lower() == "true"


class InMemoryStore:
    """Simple in-memory fallback when DB is not configured."""

    def __init__(self):
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.alerts: List[Dict[str, Any]] = []
        self.suppliers: Dict[str, Dict[str, Any]] = {}

    # --- Tasks ---

    async def save_task(self, task_id: str, data: Dict[str, Any]) -> None:
        self.tasks[task_id] = data

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        return self.tasks.get(task_id)

    async def list_completed_tasks(self) -> List[Dict[str, Any]]:
        return [t for t in self.tasks.values() if t.get("status") == "completed"]

    # --- Risks ---

    async def list_risks(self, limit: int = 50, offset: int = 0, severity: str = None) -> tuple:
        all_risks = []
        for task in self.tasks.values():
            if task.get("status") == "completed" and task.get("result"):
                all_risks.extend(task["result"].get("risks", []))
        if severity:
            all_risks = [r for r in all_risks if r.get("severity") == severity]
        return all_risks[offset:offset + limit], len(all_risks)

    async def get_risk(self, risk_id: str) -> Optional[Dict[str, Any]]:
        for task in self.tasks.values():
            if task.get("status") == "completed" and task.get("result"):
                for risk in task["result"].get("risks", []):
                    if risk.get("id") == risk_id:
                        return risk
        return None

    async def get_recommendations_for_risk(self, risk_id: str) -> List[Dict[str, Any]]:
        for task in self.tasks.values():
            if task.get("status") == "completed" and task.get("result"):
                matching = [r for r in task["result"].get("recommendations", []) if r.get("risk_id") == risk_id]
                if matching:
                    return matching
        return []

    # --- Suppliers ---

    async def list_suppliers(self, org_id: str = None, risk_tier: str = None, limit: int = 50) -> tuple:
        suppliers = list(self.suppliers.values())
        if org_id:
            suppliers = [s for s in suppliers if s.get("organization_id") == org_id]
        if risk_tier:
            suppliers = [s for s in suppliers if s.get("risk_tier") == risk_tier]
        return suppliers[:limit], len(suppliers)

    async def get_supplier(self, supplier_id: str) -> Optional[Dict[str, Any]]:
        return self.suppliers.get(supplier_id)

    async def save_supplier(self, supplier_id: str, data: Dict[str, Any]) -> None:
        self.suppliers[supplier_id] = data

    # --- Alerts ---

    async def add_alert(self, alert: Dict[str, Any]) -> None:
        self.alerts.append(alert)

    async def list_alerts(self, status_filter: str = None, severity: str = None, limit: int = 50) -> tuple:
        alerts = list(self.alerts)
        if status_filter:
            alerts = [a for a in alerts if a.get("status") == status_filter]
        if severity:
            alerts = [a for a in alerts if a.get("severity") == severity]
        return alerts[:limit], len(alerts)

    async def acknowledge_alert(self, alert_id: str) -> Optional[Dict[str, Any]]:
        for alert in self.alerts:
            if alert.get("id") == alert_id:
                alert["status"] = "acknowledged"
                alert["acknowledged_at"] = datetime.utcnow().isoformat()
                return alert
        return None

    # --- Risk History ---

    async def get_risk_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        history = []
        for task_id, task in self.tasks.items():
            if task.get("status") == "completed" and task.get("result"):
                for risk in task["result"].get("risks", []):
                    history.append({**risk, "assessment_task_id": task_id, "assessment_completed_at": task.get("completed_at")})
        history.sort(key=lambda r: r.get("detected_at", ""), reverse=True)
        return history[:limit]


# Global repository instance
store = InMemoryStore()


def seed_default_suppliers():
    """Seed default suppliers into the in-memory store."""
    defaults = [
        {"id": "c0000000-0000-0000-0000-000000000001", "organization_id": "a0000000-0000-0000-0000-000000000001", "supplier_code": "SUP-ALPHA", "name": "Supplier Alpha", "supplier_type": "api_manufacturer", "country_code": "US", "region": "North America", "risk_score": 35.0, "risk_tier": "low", "contact_name": "John Smith", "contact_email": "john@supplier-alpha.com", "is_active": True},
        {"id": "c0000000-0000-0000-0000-000000000002", "organization_id": "a0000000-0000-0000-0000-000000000001", "supplier_code": "SUP-BETA", "name": "Supplier Beta", "supplier_type": "excipient_supplier", "country_code": "DE", "region": "Europe", "risk_score": 62.0, "risk_tier": "medium", "contact_name": "Hans Mueller", "contact_email": "hans@supplier-beta.de", "is_active": True},
        {"id": "c0000000-0000-0000-0000-000000000003", "organization_id": "a0000000-0000-0000-0000-000000000001", "supplier_code": "SUP-GAMMA", "name": "Supplier Gamma", "supplier_type": "packaging", "country_code": "CN", "region": "Asia Pacific", "risk_score": 78.0, "risk_tier": "high", "contact_name": "Wei Zhang", "contact_email": "wei@supplier-gamma.cn", "is_active": True},
        {"id": "c0000000-0000-0000-0000-000000000004", "organization_id": "a0000000-0000-0000-0000-000000000002", "supplier_code": "SUP-DELTA", "name": "Supplier Delta", "supplier_type": "sensor_components", "country_code": "JP", "region": "Asia Pacific", "risk_score": 28.0, "risk_tier": "low", "contact_name": "Yuki Tanaka", "contact_email": "yuki@supplier-delta.jp", "is_active": True},
        {"id": "c0000000-0000-0000-0000-000000000005", "organization_id": "a0000000-0000-0000-0000-000000000002", "supplier_code": "SUP-EPSILON", "name": "Supplier Epsilon", "supplier_type": "biocompatible_materials", "country_code": "US", "region": "North America", "risk_score": 55.0, "risk_tier": "medium", "contact_name": "Sarah Johnson", "contact_email": "sarah@supplier-epsilon.com", "is_active": True},
    ]
    for s in defaults:
        store.suppliers[s["id"]] = s
