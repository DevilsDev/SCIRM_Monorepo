"""Due diligence records in both stores (mixed into MemoryStore and PostgresStore).

Risks and measures are written together with their history entries (dd_events) in one
transaction. Nothing here is ever deleted: the documentation is kept for seven years (LkSG
section 10(1)); the history is append-only."""

import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

RISK_PUBLIC = ("id", "supplier_id", "area", "description", "likelihood", "severity", "rating_reason", "source",
               "source_ref", "status", "assessed_by", "assessed_at", "created_at")
MEASURE_PUBLIC = ("id", "supplier_id", "risk_id", "kind", "description", "owner_email", "due_date", "status",
                  "effectiveness", "effectiveness_note", "created_by", "created_at", "updated_at")
EVENT_PUBLIC = ("id", "supplier_id", "risk_id", "measure_id", "kind", "text", "actor", "created_at")
RISK_EDITABLE = ("description", "likelihood", "severity", "rating_reason", "status")
MEASURE_EDITABLE = ("description", "owner_email", "due_date", "status", "effectiveness", "effectiveness_note")
# (kind, text) entries written to the history with a change.
Entries = List[Tuple[str, str]]


def _iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
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


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class MemoryDueDiligence:
    def _dd(self) -> Dict[str, Dict[str, Any]]:
        if not hasattr(self, "dd_tables"):
            self.dd_tables = {"settings": {}, "risks": {}, "measures": {}, "events": {}}
            self.dd_seq = 0
        return self.dd_tables

    def _dd_supplier(self, org: str, supplier_id: str) -> bool:
        supplier = self.suppliers.get(str(supplier_id))
        return bool(supplier and supplier.get("organization_id") == org)

    def _dd_own(self, table: str, org: str, row_id: str) -> Optional[Dict[str, Any]]:
        row = self._dd()[table].get(str(row_id))
        return row if row and row["organization_id"] == org else None

    def _dd_log(self, org: str, supplier_id: str, entries: Entries, actor: Optional[str], risk_id: Optional[str] = None,
                measure_id: Optional[str] = None) -> List[Dict[str, Any]]:
        out = []
        for kind, body in entries:
            self._dd()
            self.dd_seq += 1
            row = {"id": str(uuid.uuid4()), "seq": self.dd_seq, "organization_id": org, "supplier_id": str(supplier_id),
                   "risk_id": risk_id, "measure_id": measure_id, "kind": kind, "text": body[:4000], "actor": actor,
                   "created_at": _now()}
            self._dd()["events"][row["id"]] = row
            out.append(_pick(row, EVENT_PUBLIC))
        return out

    async def get_dd_settings(self, org: str) -> Dict[str, Any]:
        row = self._dd()["settings"].get(org)
        return {"review_months": row["review_months"] if row else 12}

    async def set_dd_settings(self, org: str, review_months: int, actor: Optional[str]) -> Dict[str, Any]:
        self._dd()["settings"][org] = {"review_months": review_months, "updated_by": actor, "updated_at": _now()}
        return {"review_months": review_months}

    async def list_dd_risks(self, org: str, supplier_id: Optional[str] = None) -> List[Dict[str, Any]]:
        rows = [r for r in self._dd()["risks"].values()
                if r["organization_id"] == org and (supplier_id is None or r["supplier_id"] == str(supplier_id))]
        return [_pick(r, RISK_PUBLIC) for r in sorted(rows, key=lambda r: r["created_at"])]

    async def add_dd_risk(self, org: str, supplier_id: str, fields: Dict[str, Any], entries: Entries,
                          actor: Optional[str]) -> Dict[str, Any]:
        if not self._dd_supplier(org, supplier_id):
            raise LookupError("supplier")
        now = _now()
        row = {"id": str(uuid.uuid4()), "organization_id": org, "supplier_id": str(supplier_id), "status": "open",
               "source_ref": None, "assessed_by": actor, "assessed_at": now, "created_at": now, **fields}
        self._dd()["risks"][row["id"]] = row
        self._dd_log(org, supplier_id, entries, actor, risk_id=row["id"])
        return _pick(row, RISK_PUBLIC)

    async def update_dd_risk(self, org: str, risk_id: str, changes: Dict[str, Any], entries: Entries,
                             actor: Optional[str]) -> Optional[Dict[str, Any]]:
        row = self._dd_own("risks", org, risk_id)
        if not row:
            return None
        row.update({k: v for k, v in changes.items() if k in RISK_EDITABLE})
        if {"likelihood", "severity", "rating_reason"} & set(changes):
            row.update(assessed_by=actor, assessed_at=_now())
        self._dd_log(org, row["supplier_id"], entries, actor, risk_id=row["id"])
        return _pick(row, RISK_PUBLIC)

    async def list_dd_measures(self, org: str, supplier_id: Optional[str] = None) -> List[Dict[str, Any]]:
        rows = [m for m in self._dd()["measures"].values()
                if m["organization_id"] == org and (supplier_id is None or m["supplier_id"] == str(supplier_id))]
        return [_pick(m, MEASURE_PUBLIC) for m in sorted(rows, key=lambda m: m["created_at"])]

    async def add_dd_measure(self, org: str, supplier_id: str, fields: Dict[str, Any], entries: Entries,
                             actor: Optional[str]) -> Dict[str, Any]:
        if not self._dd_supplier(org, supplier_id):
            raise LookupError("supplier")
        risk_id = fields.get("risk_id")
        if risk_id:
            risk = self._dd_own("risks", org, risk_id)
            if not risk or risk["supplier_id"] != str(supplier_id):
                raise LookupError("risk")
        now = _now()
        row = {"id": str(uuid.uuid4()), "organization_id": org, "supplier_id": str(supplier_id), "risk_id": None,
               "owner_email": None, "due_date": None, "status": "planned", "effectiveness": "not_reviewed",
               "effectiveness_note": None, "created_by": actor, "created_at": now, "updated_at": now, **fields}
        self._dd()["measures"][row["id"]] = row
        self._dd_log(org, supplier_id, entries, actor, risk_id=row["risk_id"], measure_id=row["id"])
        return _pick(row, MEASURE_PUBLIC)

    async def update_dd_measure(self, org: str, measure_id: str, changes: Dict[str, Any], entries: Entries,
                                actor: Optional[str]) -> Optional[Dict[str, Any]]:
        row = self._dd_own("measures", org, measure_id)
        if not row:
            return None
        row.update({k: v for k, v in changes.items() if k in MEASURE_EDITABLE}, updated_at=_now())
        self._dd_log(org, row["supplier_id"], entries, actor, risk_id=row["risk_id"], measure_id=row["id"])
        return _pick(row, MEASURE_PUBLIC)

    async def add_dd_review(self, org: str, supplier_id: str, text: str, actor: Optional[str]) -> Dict[str, Any]:
        if not self._dd_supplier(org, supplier_id):
            raise LookupError("supplier")
        return self._dd_log(org, supplier_id, [("analysis_reviewed", text)], actor)[0]

    async def list_dd_events(self, org: str, supplier_id: Optional[str] = None, since: Optional[datetime] = None,
                             until: Optional[datetime] = None) -> List[Dict[str, Any]]:
        rows = [e for e in self._dd()["events"].values() if e["organization_id"] == org
                and (supplier_id is None or e["supplier_id"] == str(supplier_id))
                and (since is None or e["created_at"] >= since) and (until is None or e["created_at"] < until)]
        return [_pick(e, EVENT_PUBLIC) for e in sorted(rows, key=lambda e: e["seq"])]

    async def dd_last_reviews(self, org: str) -> Dict[str, datetime]:
        out: Dict[str, datetime] = {}
        for e in self._dd()["events"].values():
            if e["organization_id"] == org and e["kind"] == "analysis_reviewed":
                if e["supplier_id"] not in out or e["created_at"] > out[e["supplier_id"]]:
                    out[e["supplier_id"]] = e["created_at"]
        return out

    async def dd_change_facts(self, org: str) -> List[Dict[str, Any]]:
        """Dated facts about suppliers that may change their risk situation: a war-room
        incident they were added to, a questionnaire they submitted."""
        facts = []
        war = self._war()
        for link in war["suppliers"].values():
            incident = war["incidents"].get(link["incident_id"])
            if link["organization_id"] == org and incident:
                facts.append({"supplier_id": link["supplier_id"], "at": link["added_at"],
                              "text": f"War-room incident: {incident['title']}"})
        for a in self._assessment_tables()[0].values():
            if a["organization_id"] == org and a.get("submitted_at"):
                facts.append({"supplier_id": a["supplier_id"], "at": a["submitted_at"],
                              "text": f"Questionnaire submitted: {a['template_name']}"})
        return facts


class PostgresDueDiligence:
    async def _dd_log_in(self, conn, org: str, supplier_id: str, entries: Entries, actor: Optional[str],
                         risk_id: Optional[str] = None, measure_id: Optional[str] = None) -> List[Dict[str, Any]]:
        from sqlalchemy import text
        out = []
        for kind, body in entries:
            result = await conn.execute(text(
                "INSERT INTO dd_events (organization_id, supplier_id, risk_id, measure_id, kind, text, actor) "
                "VALUES (CAST(:org AS uuid), CAST(:s AS uuid), CAST(:r AS uuid), CAST(:m AS uuid), :k, :t, :a) "
                "RETURNING *"),
                {"org": org, "s": str(supplier_id), "r": risk_id, "m": measure_id, "k": kind, "t": body[:4000],
                 "a": actor})
            out.append(_pick(dict(result.first()._mapping), EVENT_PUBLIC))
        return out

    async def get_dd_settings(self, org: str) -> Dict[str, Any]:
        rows = await self._all(org, "SELECT review_months FROM dd_settings")
        return {"review_months": rows[0]["review_months"] if rows else 12}

    async def set_dd_settings(self, org: str, review_months: int, actor: Optional[str]) -> Dict[str, Any]:
        await self._all(org, (
            "INSERT INTO dd_settings (organization_id, review_months, updated_by) VALUES (CAST(:org AS uuid), :m, :by) "
            "ON CONFLICT (organization_id) DO UPDATE SET review_months = :m, updated_by = :by, updated_at = now() "
            "RETURNING review_months"), {"org": org, "m": review_months, "by": actor})
        return {"review_months": review_months}

    async def list_dd_risks(self, org: str, supplier_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if supplier_id is not None and not _uuid(supplier_id):
            return []
        rows = await self._all(org, (
            "SELECT * FROM dd_risks WHERE (CAST(:s AS uuid) IS NULL OR supplier_id = CAST(:s AS uuid)) "
            "ORDER BY created_at"), {"s": supplier_id})
        return [_pick(r, RISK_PUBLIC) for r in rows]

    async def add_dd_risk(self, org: str, supplier_id: str, fields: Dict[str, Any], entries: Entries,
                          actor: Optional[str]) -> Dict[str, Any]:
        from sqlalchemy import text
        if not _uuid(supplier_id) or not await self.get_supplier(org, str(supplier_id)):
            raise LookupError("supplier")
        async with self._tx(org) as conn:
            result = await conn.execute(text(
                "INSERT INTO dd_risks (organization_id, supplier_id, area, description, likelihood, severity, "
                "rating_reason, source, source_ref, assessed_by) VALUES (CAST(:org AS uuid), CAST(:s AS uuid), :area, "
                ":d, :l, :sev, :why, :src, :ref, :by) RETURNING *"),
                {"org": org, "s": str(supplier_id), "area": fields["area"], "d": fields["description"],
                 "l": fields["likelihood"], "sev": fields["severity"], "why": fields["rating_reason"],
                 "src": fields["source"], "ref": fields.get("source_ref"), "by": actor})
            row = dict(result.first()._mapping)
            await self._dd_log_in(conn, org, str(supplier_id), entries, actor, risk_id=str(row["id"]))
        return _pick(row, RISK_PUBLIC)

    async def update_dd_risk(self, org: str, risk_id: str, changes: Dict[str, Any], entries: Entries,
                             actor: Optional[str]) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text
        if not _uuid(risk_id):
            return None
        sets = [k for k in RISK_EDITABLE if k in changes]
        assignments = [f"{k} = :{k}" for k in sets]
        if {"likelihood", "severity", "rating_reason"} & set(changes):
            assignments += ["assessed_by = :by", "assessed_at = now()"]
        async with self._tx(org) as conn:
            sql = (f"UPDATE dd_risks SET {', '.join(assignments)} WHERE id = CAST(:i AS uuid) RETURNING *" if assignments
                   else "SELECT * FROM dd_risks WHERE id = CAST(:i AS uuid)")
            found = (await conn.execute(text(sql), {**{k: changes[k] for k in sets}, "i": risk_id, "by": actor})).first()
            if not found:
                return None
            row = dict(found._mapping)
            await self._dd_log_in(conn, org, str(row["supplier_id"]), entries, actor, risk_id=str(row["id"]))
        return _pick(row, RISK_PUBLIC)

    async def list_dd_measures(self, org: str, supplier_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if supplier_id is not None and not _uuid(supplier_id):
            return []
        rows = await self._all(org, (
            "SELECT * FROM dd_measures WHERE (CAST(:s AS uuid) IS NULL OR supplier_id = CAST(:s AS uuid)) "
            "ORDER BY created_at"), {"s": supplier_id})
        return [_pick(r, MEASURE_PUBLIC) for r in rows]

    async def add_dd_measure(self, org: str, supplier_id: str, fields: Dict[str, Any], entries: Entries,
                             actor: Optional[str]) -> Dict[str, Any]:
        from sqlalchemy import text
        if not _uuid(supplier_id) or not await self.get_supplier(org, str(supplier_id)):
            raise LookupError("supplier")
        risk_id = fields.get("risk_id")
        if risk_id is not None and not _uuid(risk_id):
            raise LookupError("risk")
        async with self._tx(org) as conn:
            if risk_id and not (await conn.execute(text(
                    "SELECT 1 FROM dd_risks WHERE id = CAST(:r AS uuid) AND supplier_id = CAST(:s AS uuid)"),
                    {"r": risk_id, "s": str(supplier_id)})).first():
                raise LookupError("risk")
            result = await conn.execute(text(
                "INSERT INTO dd_measures (organization_id, supplier_id, risk_id, kind, description, owner_email, "
                "due_date, created_by) VALUES (CAST(:org AS uuid), CAST(:s AS uuid), CAST(:r AS uuid), :k, :d, :o, "
                ":due, :by) RETURNING *"),
                {"org": org, "s": str(supplier_id), "r": risk_id, "k": fields["kind"], "d": fields["description"],
                 "o": fields.get("owner_email"),
                 "due": date.fromisoformat(fields["due_date"]) if fields.get("due_date") else None, "by": actor})
            row = dict(result.first()._mapping)
            await self._dd_log_in(conn, org, str(supplier_id), entries, actor, risk_id=risk_id,
                                  measure_id=str(row["id"]))
        return _pick(row, MEASURE_PUBLIC)

    async def update_dd_measure(self, org: str, measure_id: str, changes: Dict[str, Any], entries: Entries,
                                actor: Optional[str]) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text
        if not _uuid(measure_id):
            return None
        sets = [k for k in MEASURE_EDITABLE if k in changes]
        values = {k: (date.fromisoformat(changes[k]) if k == "due_date" and changes[k] else changes[k]) for k in sets}
        assignments = ", ".join([f"{k} = :{k}" for k in sets] + ["updated_at = now()"])
        async with self._tx(org) as conn:
            found = (await conn.execute(text(
                f"UPDATE dd_measures SET {assignments} WHERE id = CAST(:i AS uuid) RETURNING *"),
                {**values, "i": measure_id})).first()
            if not found:
                return None
            row = dict(found._mapping)
            await self._dd_log_in(conn, org, str(row["supplier_id"]), entries, actor,
                                  risk_id=str(row["risk_id"]) if row["risk_id"] else None, measure_id=str(row["id"]))
        return _pick(row, MEASURE_PUBLIC)

    async def add_dd_review(self, org: str, supplier_id: str, text: str, actor: Optional[str]) -> Dict[str, Any]:
        if not _uuid(supplier_id) or not await self.get_supplier(org, str(supplier_id)):
            raise LookupError("supplier")
        async with self._tx(org) as conn:
            return (await self._dd_log_in(conn, org, str(supplier_id), [("analysis_reviewed", text)], actor))[0]

    async def list_dd_events(self, org: str, supplier_id: Optional[str] = None, since: Optional[datetime] = None,
                             until: Optional[datetime] = None) -> List[Dict[str, Any]]:
        if supplier_id is not None and not _uuid(supplier_id):
            return []
        rows = await self._all(org, (
            "SELECT * FROM dd_events WHERE (CAST(:s AS uuid) IS NULL OR supplier_id = CAST(:s AS uuid)) "
            "AND (CAST(:a AS timestamptz) IS NULL OR created_at >= CAST(:a AS timestamptz)) "
            "AND (CAST(:b AS timestamptz) IS NULL OR created_at < CAST(:b AS timestamptz)) ORDER BY seq"),
            {"s": supplier_id, "a": since, "b": until})
        return [_pick(r, EVENT_PUBLIC) for r in rows]

    async def dd_last_reviews(self, org: str) -> Dict[str, datetime]:
        rows = await self._all(org, (
            "SELECT supplier_id, max(created_at) AS at FROM dd_events WHERE kind = 'analysis_reviewed' "
            "GROUP BY supplier_id"))
        return {str(r["supplier_id"]): _aware(r["at"]) for r in rows}

    async def dd_change_facts(self, org: str) -> List[Dict[str, Any]]:
        rows = await self._all(org, (
            "SELECT l.supplier_id, l.added_at AS at, 'War-room incident: ' || i.title AS text "
            "FROM incident_suppliers l JOIN incidents i ON i.id = l.incident_id "
            "UNION ALL SELECT a.supplier_id, a.submitted_at, 'Questionnaire submitted: ' || a.template_name "
            "FROM supplier_assessments a WHERE a.submitted_at IS NOT NULL"))
        return [{"supplier_id": str(r["supplier_id"]), "at": _aware(r["at"]), "text": r["text"]} for r in rows]
