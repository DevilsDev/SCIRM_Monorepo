"""The AI run log, action policies and action proposals in both stores (mixed into
MemoryStore and PostgresStore). The run log is append-only. A proposal is decided once:
claim_proposal moves it out of "pending" in one statement, so two people approving at the
same moment cannot run it twice."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

RUN_PUBLIC = ("id", "kind", "actor", "actor_type", "status", "method", "degraded", "input", "output", "llm",
              "latency_ms", "created_at")
RUN_SUMMARY = ("id", "kind", "actor", "actor_type", "status", "method", "degraded", "input", "llm", "latency_ms",
               "created_at")
PROPOSAL_PUBLIC = ("id", "action", "params", "summary", "proposed_by", "proposed_via", "status", "decided_by",
                   "decided_at", "decision_note", "result", "created_at")


def _iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, str) and value[:1] in "{[":
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _pick(row: Dict[str, Any], keys) -> Dict[str, Any]:
    return {k: _iso(row.get(k)) for k in keys}


def _uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (TypeError, ValueError):
        return False


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryAI:
    def _ai(self) -> Dict[str, Any]:
        if not hasattr(self, "ai_tables"):
            self.ai_tables = {"runs": [], "policies": {}, "proposals": {}}
        return self.ai_tables

    async def record_ai_run(self, org: str, run: Dict[str, Any]) -> str:
        row = {"id": str(uuid.uuid4()), "organization_id": org, "actor_type": "user", "degraded": False, "input": {},
               "output": {}, "llm": None, "method": None, "latency_ms": None, "created_at": _now(), **run}
        self._ai()["runs"].append(row)
        return row["id"]

    async def list_ai_runs(self, org: str, kind: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        rows = [r for r in reversed(self._ai()["runs"]) if r["organization_id"] == org and (kind is None or r["kind"] == kind)]
        return [_pick(r, RUN_SUMMARY) for r in rows[:limit]]

    async def get_ai_run(self, org: str, run_id: str) -> Optional[Dict[str, Any]]:
        row = next((r for r in self._ai()["runs"] if r["id"] == str(run_id) and r["organization_id"] == org), None)
        return _pick(row, RUN_PUBLIC) if row else None

    async def get_action_policy(self, org: str) -> Dict[str, str]:
        return {action: p["mode"] for (o, action), p in self._ai()["policies"].items() if o == org}

    async def set_action_policy(self, org: str, action: str, mode: str, by: Optional[str]) -> None:
        self._ai()["policies"][(org, action)] = {"mode": mode, "updated_by": by, "updated_at": _now()}

    async def create_proposal(self, org: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        row = {"id": str(uuid.uuid4()), "organization_id": org, "status": "pending", "decided_by": None,
               "decided_at": None, "decision_note": None, "result": None, "created_at": _now(), **fields}
        self._ai()["proposals"][row["id"]] = row
        return _pick(row, PROPOSAL_PUBLIC)

    async def list_proposals(self, org: str, status: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        rows = [p for p in self._ai()["proposals"].values() if p["organization_id"] == org
                and (status is None or p["status"] == status)]
        rows.sort(key=lambda p: (p["status"] != "pending", -p["created_at"].timestamp()))
        return [_pick(p, PROPOSAL_PUBLIC) for p in rows[:limit]]

    async def get_proposal(self, org: str, proposal_id: str) -> Optional[Dict[str, Any]]:
        row = self._ai()["proposals"].get(str(proposal_id))
        return _pick(row, PROPOSAL_PUBLIC) if row and row["organization_id"] == org else None

    async def claim_proposal(self, org: str, proposal_id: str, by: str) -> Optional[Dict[str, Any]]:
        row = self._ai()["proposals"].get(str(proposal_id))
        if not row or row["organization_id"] != org or row["status"] != "pending" or row["decided_by"]:
            return None
        row.update(decided_by=by, decided_at=_now())
        return _pick(row, PROPOSAL_PUBLIC)

    async def finish_proposal(self, org: str, proposal_id: str, status: str, result: Optional[Dict[str, Any]],
                              note: Optional[str]) -> Optional[Dict[str, Any]]:
        row = self._ai()["proposals"].get(str(proposal_id))
        if not row or row["organization_id"] != org:
            return None
        row.update(status=status, result=result, decision_note=note)
        return _pick(row, PROPOSAL_PUBLIC)


class PostgresAI:
    async def record_ai_run(self, org: str, run: Dict[str, Any]) -> str:
        rows = await self._all(org, (
            "INSERT INTO ai_runs (organization_id, kind, actor, actor_type, status, method, degraded, input, output, "
            "llm, latency_ms) VALUES (CAST(:org AS uuid), :kind, :actor, :atype, :status, :method, :degraded, "
            "CAST(:input AS jsonb), CAST(:output AS jsonb), CAST(:llm AS jsonb), :latency) RETURNING id"),
            {"org": org, "kind": run["kind"], "actor": run.get("actor"), "atype": run.get("actor_type", "user"),
             "status": run["status"], "method": run.get("method"), "degraded": bool(run.get("degraded")),
             "input": json.dumps(run.get("input") or {}, default=str),
             "output": json.dumps(run.get("output") or {}, default=str),
             "llm": json.dumps(run["llm"], default=str) if run.get("llm") else None, "latency": run.get("latency_ms")})
        return str(rows[0]["id"])

    async def list_ai_runs(self, org: str, kind: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        rows = await self._all(org, (
            f"SELECT {', '.join(RUN_SUMMARY)} FROM ai_runs WHERE (CAST(:k AS text) IS NULL OR kind = :k) "
            "ORDER BY seq DESC LIMIT :limit"), {"k": kind, "limit": limit})
        return [_pick(r, RUN_SUMMARY) for r in rows]

    async def get_ai_run(self, org: str, run_id: str) -> Optional[Dict[str, Any]]:
        if not _uuid(run_id):
            return None
        rows = await self._all(org, "SELECT * FROM ai_runs WHERE id = CAST(:i AS uuid)", {"i": run_id})
        return _pick(rows[0], RUN_PUBLIC) if rows else None

    async def get_action_policy(self, org: str) -> Dict[str, str]:
        rows = await self._all(org, "SELECT action, mode FROM action_policies")
        return {r["action"]: r["mode"] for r in rows}

    async def set_action_policy(self, org: str, action: str, mode: str, by: Optional[str]) -> None:
        await self._exec(org, [(
            "INSERT INTO action_policies (organization_id, action, mode, updated_by) VALUES (CAST(:org AS uuid), :a, :m, :by) "
            "ON CONFLICT (organization_id, action) DO UPDATE SET mode = EXCLUDED.mode, updated_by = EXCLUDED.updated_by, "
            "updated_at = now()", {"org": org, "a": action, "m": mode, "by": by})])

    async def create_proposal(self, org: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        rows = await self._all(org, (
            "INSERT INTO action_proposals (organization_id, action, params, summary, proposed_by, proposed_via) "
            "VALUES (CAST(:org AS uuid), :a, CAST(:p AS jsonb), :s, :by, :via) RETURNING *"),
            {"org": org, "a": fields["action"], "p": json.dumps(fields.get("params") or {}, default=str),
             "s": fields["summary"][:500], "by": fields["proposed_by"], "via": fields["proposed_via"]})
        return _pick(rows[0], PROPOSAL_PUBLIC)

    async def list_proposals(self, org: str, status: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        rows = await self._all(org, (
            "SELECT * FROM action_proposals WHERE (CAST(:s AS text) IS NULL OR status = :s) "
            "ORDER BY (status <> 'pending'), created_at DESC LIMIT :limit"), {"s": status, "limit": limit})
        return [_pick(r, PROPOSAL_PUBLIC) for r in rows]

    async def get_proposal(self, org: str, proposal_id: str) -> Optional[Dict[str, Any]]:
        if not _uuid(proposal_id):
            return None
        rows = await self._all(org, "SELECT * FROM action_proposals WHERE id = CAST(:i AS uuid)", {"i": proposal_id})
        return _pick(rows[0], PROPOSAL_PUBLIC) if rows else None

    async def claim_proposal(self, org: str, proposal_id: str, by: str) -> Optional[Dict[str, Any]]:
        if not _uuid(proposal_id):
            return None
        rows = await self._all(org, (
            "UPDATE action_proposals SET decided_by = :by, decided_at = now() "
            "WHERE id = CAST(:i AS uuid) AND status = 'pending' AND decided_by IS NULL RETURNING *"),
            {"i": proposal_id, "by": by})
        return _pick(rows[0], PROPOSAL_PUBLIC) if rows else None

    async def finish_proposal(self, org: str, proposal_id: str, status: str, result: Optional[Dict[str, Any]],
                              note: Optional[str]) -> Optional[Dict[str, Any]]:
        if not _uuid(proposal_id):
            return None
        rows = await self._all(org, (
            "UPDATE action_proposals SET status = :s, result = CAST(:r AS jsonb), decision_note = :n "
            "WHERE id = CAST(:i AS uuid) RETURNING *"),
            {"i": proposal_id, "s": status, "r": json.dumps(result, default=str) if result is not None else None,
             "n": note})
        return _pick(rows[0], PROPOSAL_PUBLIC) if rows else None
