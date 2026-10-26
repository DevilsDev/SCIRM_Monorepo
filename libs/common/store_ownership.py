"""Supplier ownership links to GLEIF (mixed into MemoryStore and PostgresStore).

One row per supplier that a person linked to an LEI, with the last GLEIF answer (snapshot)
for the entity and its parents. See alembic/versions/033_supplier_ownership.py."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

PUBLIC = ("supplier_id", "lei", "snapshot", "confirmed_by", "confirmed_at", "refreshed_at")


def _iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _pick(row: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: _iso(row.get(k)) for k in PUBLIC}
    if isinstance(out["snapshot"], str):
        out["snapshot"] = json.loads(out["snapshot"])
    return out


def _uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (TypeError, ValueError):
        return False


class MemoryOwnership:
    def _own(self) -> Dict[str, Dict[str, Any]]:
        if not hasattr(self, "ownership_rows"):
            self.ownership_rows = {}
        return self.ownership_rows

    async def get_ownership(self, org: str, supplier_id: str) -> Optional[Dict[str, Any]]:
        row = self._own().get(str(supplier_id))
        return _pick(row) if row and row["organization_id"] == org else None

    async def list_ownership(self, org: str) -> List[Dict[str, Any]]:
        return [_pick(r) for r in self._own().values() if r["organization_id"] == org
                and (self.suppliers.get(r["supplier_id"]) or {}).get("organization_id") == org]

    async def set_ownership(self, org: str, supplier_id: str, lei: str, snapshot: Dict[str, Any],
                            actor: str) -> Dict[str, Any]:
        supplier = self.suppliers.get(str(supplier_id))
        if not supplier or supplier.get("organization_id") != org:
            raise LookupError("supplier")
        now = datetime.now(timezone.utc)
        row = {"supplier_id": str(supplier_id), "organization_id": org, "lei": lei, "snapshot": snapshot,
               "confirmed_by": actor, "confirmed_at": now, "refreshed_at": now}
        self._own()[str(supplier_id)] = row
        return _pick(row)

    async def refresh_ownership(self, org: str, supplier_id: str, snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        row = self._own().get(str(supplier_id))
        if not row or row["organization_id"] != org:
            return None
        row.update(snapshot=snapshot, refreshed_at=datetime.now(timezone.utc))
        return _pick(row)

    async def remove_ownership(self, org: str, supplier_id: str) -> bool:
        row = self._own().get(str(supplier_id))
        if not row or row["organization_id"] != org:
            return False
        del self._own()[str(supplier_id)]
        return True


class PostgresOwnership:
    async def get_ownership(self, org: str, supplier_id: str) -> Optional[Dict[str, Any]]:
        if not _uuid(supplier_id):
            return None
        rows = await self._all(org, "SELECT * FROM supplier_ownership WHERE supplier_id = CAST(:s AS uuid)",
                               {"s": str(supplier_id)})
        return _pick(rows[0]) if rows else None

    async def list_ownership(self, org: str) -> List[Dict[str, Any]]:
        return [_pick(r) for r in await self._all(org, "SELECT * FROM supplier_ownership ORDER BY confirmed_at")]

    async def set_ownership(self, org: str, supplier_id: str, lei: str, snapshot: Dict[str, Any],
                            actor: str) -> Dict[str, Any]:
        if not _uuid(supplier_id) or not await self.get_supplier(org, str(supplier_id)):
            raise LookupError("supplier")
        rows = await self._all(org, (
            "INSERT INTO supplier_ownership (supplier_id, organization_id, lei, snapshot, confirmed_by) "
            "VALUES (CAST(:s AS uuid), CAST(:org AS uuid), :lei, CAST(:snap AS jsonb), :by) "
            "ON CONFLICT (supplier_id) DO UPDATE SET lei = :lei, snapshot = CAST(:snap AS jsonb), confirmed_by = :by, "
            "confirmed_at = now(), refreshed_at = now() RETURNING *"),
            {"s": str(supplier_id), "org": org, "lei": lei, "snap": json.dumps(snapshot), "by": actor})
        return _pick(rows[0])

    async def refresh_ownership(self, org: str, supplier_id: str, snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not _uuid(supplier_id):
            return None
        rows = await self._all(org, (
            "UPDATE supplier_ownership SET snapshot = CAST(:snap AS jsonb), refreshed_at = now() "
            "WHERE supplier_id = CAST(:s AS uuid) RETURNING *"), {"s": str(supplier_id), "snap": json.dumps(snapshot)})
        return _pick(rows[0]) if rows else None

    async def remove_ownership(self, org: str, supplier_id: str) -> bool:
        if not _uuid(supplier_id):
            return False
        rows = await self._all(org, "DELETE FROM supplier_ownership WHERE supplier_id = CAST(:s AS uuid) RETURNING supplier_id",
                               {"s": str(supplier_id)})
        return bool(rows)
