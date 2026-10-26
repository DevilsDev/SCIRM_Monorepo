"""War-room incidents in both stores (mixed into MemoryStore and PostgresStore).

Every change is written with its timeline entries in the same transaction, so the
timeline always tells what happened. The timeline is append-only."""

import json
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

INCIDENT_PUBLIC = ("id", "title", "summary", "severity", "status", "owner_email", "signal_id", "signal", "resolution",
                   "opened_by", "created_at", "updated_at", "resolved_at")
TASK_PUBLIC = ("id", "incident_id", "title", "assignee_email", "due_date", "status", "created_by", "created_at",
               "done_by", "done_at")
ENTRY_PUBLIC = ("id", "kind", "text", "actor", "created_at")
INCIDENT_EDITABLE = ("title", "summary", "severity", "status", "owner_email", "resolution")
Entries = List[Tuple[str, str]]


def _iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, str) and value[:1] in "{[":
        try:
            return json.loads(value)  # jsonb returned as text
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


class MemoryWarRoom:
    def _war(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        if not hasattr(self, "war_tables"):
            self.war_tables = {"incidents": {}, "suppliers": {}, "tasks": {}, "timeline": {}}
        return self.war_tables

    def _own_incident(self, org: str, incident_id: str) -> Optional[Dict[str, Any]]:
        row = self._war()["incidents"].get(str(incident_id))
        return row if row and row["organization_id"] == org else None

    def _log(self, org: str, incident_id: str, entries: Entries, actor: Optional[str]) -> None:
        for kind, text in entries:
            eid = str(uuid.uuid4())
            self._war()["timeline"][eid] = {"id": eid, "organization_id": org, "incident_id": incident_id,
                                            "kind": kind, "text": text[:4000], "actor": actor, "created_at": _now()}

    async def get_public_signal(self, signal_id: str) -> Optional[Dict[str, Any]]:
        return next((s for s in self.signals.values() if str(s.get("id")) == str(signal_id)), None)

    async def create_incident(self, org: str, fields: Dict[str, Any], suppliers: List[Tuple[str, str]],
                              entries: Entries, actor: Optional[str]) -> str:
        now = _now()
        row = {"id": str(uuid.uuid4()), "organization_id": org, "summary": "", "severity": "medium", "status": "open",
               "owner_email": None, "signal_id": None, "signal": None, "resolution": None, "opened_by": actor,
               "created_at": now, "updated_at": now, "resolved_at": None, **fields}
        self._war()["incidents"][row["id"]] = row
        for supplier_id, reason in suppliers:
            await self.add_incident_supplier(org, row["id"], supplier_id, reason, [], actor)
        self._log(org, row["id"], entries, actor)
        return row["id"]

    async def list_incidents(self, org: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        war = self._war()
        rows = [r for r in war["incidents"].values() if r["organization_id"] == org and (status is None or r["status"] == status)]
        rows.sort(key=lambda r: (r["status"] == "resolved", -r["updated_at"].timestamp()))
        out = []
        for r in rows:
            out.append({**_pick(r, INCIDENT_PUBLIC),
                        "supplier_count": sum(1 for s in war["suppliers"].values() if s["incident_id"] == r["id"]),
                        "open_tasks": sum(1 for t in war["tasks"].values() if t["incident_id"] == r["id"] and t["status"] == "open")})
        return out

    async def get_incident(self, org: str, incident_id: str) -> Optional[Dict[str, Any]]:
        row = self._own_incident(org, incident_id)
        if not row:
            return None
        war = self._war()
        suppliers = []
        for link in sorted((s for s in war["suppliers"].values() if s["incident_id"] == row["id"]), key=lambda s: s["added_at"]):
            supplier = self.suppliers.get(link["supplier_id"])
            if supplier:
                suppliers.append({**supplier, "reason": link["reason"], "added_at": _iso(link["added_at"])})
        tasks = sorted((t for t in war["tasks"].values() if t["incident_id"] == row["id"]), key=lambda t: t["created_at"])
        timeline = sorted((e for e in war["timeline"].values() if e["incident_id"] == row["id"]), key=lambda e: e["created_at"])
        return {"incident": _pick(row, INCIDENT_PUBLIC), "suppliers": suppliers,
                "tasks": [_pick(t, TASK_PUBLIC) for t in tasks], "timeline": [_pick(e, ENTRY_PUBLIC) for e in timeline]}

    async def update_incident(self, org: str, incident_id: str, changes: Dict[str, Any], entries: Entries,
                              actor: Optional[str]) -> bool:
        row = self._own_incident(org, incident_id)
        if not row:
            return False
        row.update({k: v for k, v in changes.items() if k in INCIDENT_EDITABLE}, updated_at=_now())
        if "status" in changes:
            row["resolved_at"] = _now() if changes["status"] == "resolved" else None
        self._log(org, row["id"], entries, actor)
        return True

    async def add_incident_supplier(self, org: str, incident_id: str, supplier_id: str, reason: str, entries: Entries,
                                    actor: Optional[str]) -> bool:
        row, supplier = self._own_incident(org, incident_id), self.suppliers.get(str(supplier_id))
        if not row or not supplier or supplier.get("organization_id") != org:
            raise LookupError("incident or supplier")
        war = self._war()
        if any(s["incident_id"] == row["id"] and s["supplier_id"] == str(supplier_id) for s in war["suppliers"].values()):
            return False
        lid = str(uuid.uuid4())
        war["suppliers"][lid] = {"id": lid, "organization_id": org, "incident_id": row["id"], "supplier_id": str(supplier_id),
                                 "reason": reason[:300], "added_by": actor, "added_at": _now()}
        row["updated_at"] = _now()
        self._log(org, row["id"], entries, actor)
        return True

    async def remove_incident_supplier(self, org: str, incident_id: str, supplier_id: str, entries: Entries,
                                       actor: Optional[str]) -> bool:
        row = self._own_incident(org, incident_id)
        war = self._war()
        link = next((k for k, s in war["suppliers"].items()
                     if row and s["incident_id"] == row["id"] and s["supplier_id"] == str(supplier_id)), None)
        if not link:
            return False
        del war["suppliers"][link]
        row["updated_at"] = _now()
        self._log(org, row["id"], entries, actor)
        return True

    async def add_incident_task(self, org: str, incident_id: str, fields: Dict[str, Any], entries: Entries,
                                actor: Optional[str]) -> Optional[Dict[str, Any]]:
        row = self._own_incident(org, incident_id)
        if not row:
            return None
        task = {"id": str(uuid.uuid4()), "organization_id": org, "incident_id": row["id"], "status": "open",
                "created_by": actor, "created_at": _now(), "done_by": None, "done_at": None,
                "assignee_email": None, "due_date": None, **fields}
        self._war()["tasks"][task["id"]] = task
        row["updated_at"] = _now()
        self._log(org, row["id"], entries, actor)
        return _pick(task, TASK_PUBLIC)

    async def set_incident_task_status(self, org: str, incident_id: str, task_id: str, status: str, entries: Entries,
                                       actor: Optional[str]) -> Optional[Dict[str, Any]]:
        row, task = self._own_incident(org, incident_id), self._war()["tasks"].get(str(task_id))
        if not row or not task or task["incident_id"] != row["id"]:
            return None
        if task["status"] != status:
            task.update(status=status, done_by=actor if status == "done" else None,
                        done_at=_now() if status == "done" else None)
            row["updated_at"] = _now()
            self._log(org, row["id"], entries, actor)
        return _pick(task, TASK_PUBLIC)

    async def add_incident_note(self, org: str, incident_id: str, entries: Entries, actor: Optional[str]) -> bool:
        return await self.update_incident(org, incident_id, {}, entries, actor)


class PostgresWarRoom:
    async def _log_in(self, conn, org: str, incident_id: str, entries: Entries, actor: Optional[str]) -> None:
        from sqlalchemy import text
        for kind, body in entries:
            await conn.execute(text(
                "INSERT INTO incident_timeline (organization_id, incident_id, kind, text, actor) "
                "VALUES (CAST(:org AS uuid), CAST(:i AS uuid), :k, :t, :a)"),
                {"org": org, "i": incident_id, "k": kind, "t": body[:4000], "a": actor})

    async def _touch(self, conn, incident_id: str) -> None:
        from sqlalchemy import text
        await conn.execute(text("UPDATE incidents SET updated_at = now() WHERE id = CAST(:i AS uuid)"), {"i": incident_id})

    async def get_public_signal(self, signal_id: str) -> Optional[Dict[str, Any]]:
        if not _uuid(signal_id):
            return None
        rows = await self._all(None, "SELECT * FROM public_signals WHERE id = CAST(:i AS uuid)", {"i": signal_id})
        return self._signal_row(rows[0]) if rows else None

    async def create_incident(self, org: str, fields: Dict[str, Any], suppliers: List[Tuple[str, str]],
                              entries: Entries, actor: Optional[str]) -> str:
        from sqlalchemy import text
        async with self._tx(org) as conn:
            result = await conn.execute(text(
                "INSERT INTO incidents (organization_id, title, summary, severity, owner_email, signal_id, signal, opened_by) "
                "VALUES (CAST(:org AS uuid), :title, :summary, :severity, :owner, CAST(:sid AS uuid), CAST(:sig AS jsonb), :by) "
                "RETURNING id"),
                {"org": org, "title": fields["title"], "summary": fields.get("summary") or "",
                 "severity": fields.get("severity") or "medium", "owner": fields.get("owner_email"),
                 "sid": fields.get("signal_id"), "sig": json.dumps(fields["signal"]) if fields.get("signal") else None,
                 "by": actor})
            incident_id = str(result.scalar())
            for supplier_id, reason in suppliers:
                await conn.execute(text(
                    "INSERT INTO incident_suppliers (organization_id, incident_id, supplier_id, reason, added_by) "
                    "VALUES (CAST(:org AS uuid), CAST(:i AS uuid), CAST(:s AS uuid), :r, :by) ON CONFLICT DO NOTHING"),
                    {"org": org, "i": incident_id, "s": supplier_id, "r": reason[:300], "by": actor})
            await self._log_in(conn, org, incident_id, entries, actor)
        return incident_id

    async def list_incidents(self, org: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        rows = await self._all(org, (
            "SELECT i.*, (SELECT count(*) FROM incident_suppliers s WHERE s.incident_id = i.id) AS supplier_count, "
            "(SELECT count(*) FROM incident_tasks t WHERE t.incident_id = i.id AND t.status = 'open') AS open_tasks "
            "FROM incidents i WHERE (CAST(:st AS text) IS NULL OR i.status = :st) "
            "ORDER BY (i.status = 'resolved'), i.updated_at DESC LIMIT 500"), {"st": status})
        return [{**_pick(r, INCIDENT_PUBLIC), "supplier_count": r["supplier_count"], "open_tasks": r["open_tasks"]}
                for r in rows]

    async def get_incident(self, org: str, incident_id: str) -> Optional[Dict[str, Any]]:
        if not _uuid(incident_id):
            return None
        rows = await self._all(org, "SELECT * FROM incidents WHERE id = CAST(:i AS uuid)", {"i": incident_id})
        if not rows:
            return None
        suppliers = await self._all(org, (
            "SELECT s.*, l.reason AS link_reason, l.added_at AS link_added_at FROM incident_suppliers l "
            "JOIN suppliers s ON s.id = l.supplier_id WHERE l.incident_id = CAST(:i AS uuid) ORDER BY l.added_at"),
            {"i": incident_id})
        tasks = await self._all(org, "SELECT * FROM incident_tasks WHERE incident_id = CAST(:i AS uuid) ORDER BY created_at",
                                {"i": incident_id})
        timeline = await self._all(org, (
            "SELECT * FROM incident_timeline WHERE incident_id = CAST(:i AS uuid) ORDER BY seq"), {"i": incident_id})
        out_suppliers = []
        for s in suppliers:
            reason, added = s.pop("link_reason"), s.pop("link_added_at")
            out_suppliers.append({**self._supplier_row(s), "reason": reason, "added_at": _iso(added)})
        return {"incident": _pick(rows[0], INCIDENT_PUBLIC), "suppliers": out_suppliers,
                "tasks": [_pick(t, TASK_PUBLIC) for t in tasks], "timeline": [_pick(e, ENTRY_PUBLIC) for e in timeline]}

    async def update_incident(self, org: str, incident_id: str, changes: Dict[str, Any], entries: Entries,
                              actor: Optional[str]) -> bool:
        from sqlalchemy import text
        if not _uuid(incident_id):
            return False
        sets = [k for k in INCIDENT_EDITABLE if k in changes]
        assignments = ", ".join([f"{k} = :{k}" for k in sets] + ["updated_at = now()"])
        if "status" in changes:
            assignments += ", resolved_at = CASE WHEN :status = 'resolved' THEN now() ELSE NULL END"
        async with self._tx(org) as conn:
            result = await conn.execute(text(f"UPDATE incidents SET {assignments} WHERE id = CAST(:i AS uuid) RETURNING id"),
                                        {**{k: changes[k] for k in sets}, "i": incident_id})
            if not result.first():
                return False
            await self._log_in(conn, org, incident_id, entries, actor)
        return True

    async def add_incident_note(self, org: str, incident_id: str, entries: Entries, actor: Optional[str]) -> bool:
        return await self.update_incident(org, incident_id, {}, entries, actor)

    async def add_incident_supplier(self, org: str, incident_id: str, supplier_id: str, reason: str, entries: Entries,
                                    actor: Optional[str]) -> bool:
        from sqlalchemy import text
        if not (_uuid(incident_id) and _uuid(supplier_id)) or not await self.get_supplier(org, supplier_id):
            raise LookupError("supplier")
        async with self._tx(org) as conn:
            if not (await conn.execute(text("SELECT 1 FROM incidents WHERE id = CAST(:i AS uuid)"), {"i": incident_id})).first():
                raise LookupError("incident")
            result = await conn.execute(text(
                "INSERT INTO incident_suppliers (organization_id, incident_id, supplier_id, reason, added_by) "
                "VALUES (CAST(:org AS uuid), CAST(:i AS uuid), CAST(:s AS uuid), :r, :by) ON CONFLICT DO NOTHING RETURNING id"),
                {"org": org, "i": incident_id, "s": supplier_id, "r": reason[:300], "by": actor})
            if not result.first():
                return False
            await self._touch(conn, incident_id)
            await self._log_in(conn, org, incident_id, entries, actor)
        return True

    async def remove_incident_supplier(self, org: str, incident_id: str, supplier_id: str, entries: Entries,
                                       actor: Optional[str]) -> bool:
        from sqlalchemy import text
        if not (_uuid(incident_id) and _uuid(supplier_id)):
            return False
        async with self._tx(org) as conn:
            result = await conn.execute(text(
                "DELETE FROM incident_suppliers WHERE incident_id = CAST(:i AS uuid) AND supplier_id = CAST(:s AS uuid) "
                "RETURNING id"), {"i": incident_id, "s": supplier_id})
            if not result.first():
                return False
            await self._touch(conn, incident_id)
            await self._log_in(conn, org, incident_id, entries, actor)
        return True

    async def add_incident_task(self, org: str, incident_id: str, fields: Dict[str, Any], entries: Entries,
                                actor: Optional[str]) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text
        if not _uuid(incident_id):
            return None
        async with self._tx(org) as conn:
            if not (await conn.execute(text("SELECT 1 FROM incidents WHERE id = CAST(:i AS uuid)"), {"i": incident_id})).first():
                return None
            result = await conn.execute(text(
                "INSERT INTO incident_tasks (organization_id, incident_id, title, assignee_email, due_date, created_by) "
                "VALUES (CAST(:org AS uuid), CAST(:i AS uuid), :t, :a, :d, :by) RETURNING *"),
                {"org": org, "i": incident_id, "t": fields["title"], "a": fields.get("assignee_email"),
                 "d": date.fromisoformat(fields["due_date"]) if fields.get("due_date") else None, "by": actor})
            task = dict(result.first()._mapping)
            await self._touch(conn, incident_id)
            await self._log_in(conn, org, incident_id, entries, actor)
        return _pick(task, TASK_PUBLIC)

    async def set_incident_task_status(self, org: str, incident_id: str, task_id: str, status: str, entries: Entries,
                                       actor: Optional[str]) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text
        if not (_uuid(incident_id) and _uuid(task_id)):
            return None
        async with self._tx(org) as conn:
            current = (await conn.execute(text(
                "SELECT * FROM incident_tasks WHERE id = CAST(:t AS uuid) AND incident_id = CAST(:i AS uuid) FOR UPDATE"),
                {"t": task_id, "i": incident_id})).first()
            if not current:
                return None
            if current.status == status:
                return _pick(dict(current._mapping), TASK_PUBLIC)
            result = await conn.execute(text(
                "UPDATE incident_tasks SET status = :s, done_by = CASE WHEN :s = 'done' THEN :by END, "
                "done_at = CASE WHEN :s = 'done' THEN now() END WHERE id = CAST(:t AS uuid) RETURNING *"),
                {"s": status, "by": actor, "t": task_id})
            task = dict(result.first()._mapping)
            await self._touch(conn, incident_id)
            await self._log_in(conn, org, incident_id, entries, actor)
        return _pick(task, TASK_PUBLIC)
