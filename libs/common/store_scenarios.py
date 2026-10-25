"""Saved scenario definitions in both stores (mixed into MemoryStore and PostgresStore)."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

SCENARIO_PUBLIC = ("id", "name", "definition", "created_by", "created_at")


def _row(r: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for k in SCENARIO_PUBLIC:
        v = r.get(k)
        if isinstance(v, datetime):
            v = (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
        elif isinstance(v, uuid.UUID):
            v = str(v)
        elif k == "definition" and isinstance(v, str):
            v = json.loads(v)
        out[k] = v
    return out


class MemoryScenarios:
    def _scenarios(self) -> Dict[str, Dict[str, Any]]:
        if not hasattr(self, "scenario_rows"):
            self.scenario_rows: Dict[str, Dict[str, Any]] = {}
        return self.scenario_rows

    async def list_saved_scenarios(self, org: str) -> List[Dict[str, Any]]:
        rows = sorted((r for r in self._scenarios().values() if r["organization_id"] == org), key=lambda r: r["created_at"])
        return [_row(r) for r in rows]

    async def save_scenario(self, org: str, name: str, definition: Dict[str, Any], by: Optional[str]) -> Dict[str, Any]:
        row = {"id": str(uuid.uuid4()), "organization_id": org, "name": name, "definition": definition, "created_by": by,
               "created_at": datetime.now(timezone.utc)}
        self._scenarios()[row["id"]] = row
        return _row(row)

    async def get_saved_scenario(self, org: str, scenario_id: str) -> Optional[Dict[str, Any]]:
        row = self._scenarios().get(str(scenario_id))
        return _row(row) if row and row["organization_id"] == org else None

    async def delete_saved_scenario(self, org: str, scenario_id: str) -> bool:
        row = self._scenarios().get(str(scenario_id))
        if not row or row["organization_id"] != org:
            return False
        del self._scenarios()[row["id"]]
        return True


def _uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (TypeError, ValueError):
        return False


class PostgresScenarios:
    async def list_saved_scenarios(self, org: str) -> List[Dict[str, Any]]:
        return [_row(r) for r in await self._all(org, "SELECT * FROM saved_scenarios ORDER BY created_at")]

    async def save_scenario(self, org: str, name: str, definition: Dict[str, Any], by: Optional[str]) -> Dict[str, Any]:
        rows = await self._all(org, (
            "INSERT INTO saved_scenarios (organization_id, name, definition, created_by) "
            "VALUES (CAST(:org AS uuid), :n, CAST(:d AS jsonb), :by) RETURNING *"),
            {"org": org, "n": name, "d": json.dumps(definition), "by": by})
        return _row(rows[0])

    async def get_saved_scenario(self, org: str, scenario_id: str) -> Optional[Dict[str, Any]]:
        if not _uuid(scenario_id):
            return None
        rows = await self._all(org, "SELECT * FROM saved_scenarios WHERE id = CAST(:i AS uuid)", {"i": scenario_id})
        return _row(rows[0]) if rows else None

    async def delete_saved_scenario(self, org: str, scenario_id: str) -> bool:
        if not _uuid(scenario_id):
            return False
        return bool(await self._all(org, "DELETE FROM saved_scenarios WHERE id = CAST(:i AS uuid) RETURNING id",
                                    {"i": scenario_id}))
