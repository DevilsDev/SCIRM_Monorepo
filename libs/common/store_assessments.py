"""Supplier assessments in both stores (mixed into MemoryStore and PostgresStore).

The portal's token is a random value shown once; only its SHA-256 is stored. Every portal
step re-checks, in the same statement that reads or writes, that the token is still live:
status 'sent' and not expired. Submitting, cancelling and re-sending all clear or replace
the hash, so an old link stops working at once.
"""

import hashlib
import json
import secrets
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

ASSESSMENT_SUMMARY = ("id", "supplier_id", "supplier_name", "template_name", "status", "recipient_email",
                      "recipient_name", "due_date", "token_expires_at", "submitted_at", "submitted_by_name",
                      "submitted_by_email", "score", "flags", "review_note", "reviewed_by", "reviewed_at", "sent_by",
                      "sent_at", "updated_at", "request_reason")
ASSESSMENT_DETAIL = ASSESSMENT_SUMMARY + ("questions", "answers")
TEMPLATE_PUBLIC = ("id", "name", "description", "questions", "created_by", "created_at")
LINK_PUBLIC = ("id", "supplier_id", "assessment_id", "name", "country_code", "city", "supplies", "reported_at")


def new_portal_token() -> Tuple[str, str]:
    """(token for the link, its SHA-256 to store)."""
    token = secrets.token_urlsafe(32)
    return token, portal_token_hash(token)


def portal_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _pick(row: Dict[str, Any], keys) -> Dict[str, Any]:
    return {k: _iso(row.get(k)) for k in keys}


class MemoryAssessments:
    """In-memory assessments, for tests and the dev store."""

    def _assessment_tables(self) -> Tuple[Dict[str, Dict], Dict[str, Dict], Dict[str, Dict]]:
        if not hasattr(self, "assessment_rows"):
            self.assessment_rows: Dict[str, Dict[str, Any]] = {}
            self.assessment_template_rows: Dict[str, Dict[str, Any]] = {}
            self.subtier_rows: Dict[str, Dict[str, Any]] = {}
        return self.assessment_rows, self.assessment_template_rows, self.subtier_rows

    def _own_assessment(self, org: str, assessment_id: str) -> Optional[Dict[str, Any]]:
        row = self._assessment_tables()[0].get(str(assessment_id))
        return row if row and row["organization_id"] == org else None

    def _with_supplier_name(self, row: Dict[str, Any]) -> Dict[str, Any]:
        supplier = self.suppliers.get(row["supplier_id"]) or {}
        return {**row, "supplier_name": supplier.get("name")}

    # templates
    async def list_assessment_templates(self, org: str) -> List[Dict[str, Any]]:
        rows = [t for t in self._assessment_tables()[1].values() if t["organization_id"] == org and not t["archived"]]
        return [_pick(t, TEMPLATE_PUBLIC) for t in sorted(rows, key=lambda t: t["created_at"])]

    async def get_assessment_template(self, org: str, template_id: str) -> Optional[Dict[str, Any]]:
        t = self._assessment_tables()[1].get(str(template_id))
        return _pick(t, TEMPLATE_PUBLIC) if t and t["organization_id"] == org and not t["archived"] else None

    async def create_assessment_template(self, org: str, name: str, description: str, questions: List[Dict[str, Any]],
                                         created_by: Optional[str]) -> Dict[str, Any]:
        row = {"id": str(uuid.uuid4()), "organization_id": org, "name": name, "description": description,
               "questions": questions, "archived": False, "created_by": created_by, "created_at": _now()}
        self._assessment_tables()[1][row["id"]] = row
        return _pick(row, TEMPLATE_PUBLIC)

    async def archive_assessment_template(self, org: str, template_id: str) -> bool:
        t = self._assessment_tables()[1].get(str(template_id))
        if not t or t["organization_id"] != org or t["archived"]:
            return False
        t["archived"] = True
        return True

    # assessments
    async def create_assessment(self, org: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        supplier = self.suppliers.get(str(fields["supplier_id"]))
        if not supplier or supplier.get("organization_id") != org:
            raise LookupError("supplier")
        now = _now()
        row = {"id": str(uuid.uuid4()), "organization_id": org, "status": "sent", "answers": {}, "flags": [],
               "score": None, "submitted_at": None, "submitted_by_name": None, "submitted_by_email": None,
               "review_note": None, "reviewed_by": None, "reviewed_at": None, "sent_at": now, "updated_at": now,
               "request_reason": None, **fields, "supplier_id": str(fields["supplier_id"])}
        self._assessment_tables()[0][row["id"]] = row
        return _pick(self._with_supplier_name(row), ASSESSMENT_SUMMARY)

    async def list_assessments(self, org: str, supplier_id: Optional[str] = None,
                               status: Optional[str] = None) -> List[Dict[str, Any]]:
        rows = [r for r in self._assessment_tables()[0].values() if r["organization_id"] == org
                and (supplier_id is None or r["supplier_id"] == supplier_id) and (status is None or r["status"] == status)]
        rows.sort(key=lambda r: r["sent_at"], reverse=True)
        return [_pick(self._with_supplier_name(r), ASSESSMENT_SUMMARY) for r in rows]

    async def get_assessment(self, org: str, assessment_id: str) -> Optional[Dict[str, Any]]:
        row = self._own_assessment(org, assessment_id)
        return _pick(self._with_supplier_name(row), ASSESSMENT_DETAIL) if row else None

    async def resend_assessment(self, org: str, assessment_id: str, token_hash: str,
                                expires_at: datetime) -> Optional[Dict[str, Any]]:
        row = self._own_assessment(org, assessment_id)
        if not row or row["status"] != "sent":
            return None
        row.update(token_hash=token_hash, token_expires_at=expires_at, sent_at=_now(), updated_at=_now())
        return _pick(self._with_supplier_name(row), ASSESSMENT_SUMMARY)

    async def cancel_assessment(self, org: str, assessment_id: str) -> Optional[Dict[str, Any]]:
        row = self._own_assessment(org, assessment_id)
        if not row or row["status"] != "sent":
            return None
        row.update(status="cancelled", token_hash=None, updated_at=_now())
        return _pick(self._with_supplier_name(row), ASSESSMENT_SUMMARY)

    async def review_assessment(self, org: str, assessment_id: str, note: str, by: str) -> Optional[Dict[str, Any]]:
        row = self._own_assessment(org, assessment_id)
        if not row or row["status"] != "submitted":
            return None
        row.update(status="reviewed", review_note=note or None, reviewed_by=by, reviewed_at=_now(), updated_at=_now())
        return _pick(self._with_supplier_name(row), ASSESSMENT_SUMMARY)

    async def list_subtier_links(self, org: str, supplier_id: Optional[str] = None) -> List[Dict[str, Any]]:
        rows = [link for link in self._assessment_tables()[2].values() if link["organization_id"] == org
                and (supplier_id is None or link["supplier_id"] == supplier_id)]
        rows.sort(key=lambda link: (link["reported_at"], link["name"]))
        return [_pick(link, LINK_PUBLIC) for link in rows]

    # the portal (before sign-in: the token is the only credential)
    def _live(self, token_hash: str) -> Optional[Dict[str, Any]]:
        for row in self._assessment_tables()[0].values():
            if row.get("token_hash") == token_hash and row["status"] == "sent" and row["token_expires_at"] > _now():
                return row
        return None

    async def assessment_by_token(self, token_hash: str) -> Optional[Tuple[str, str]]:
        row = self._live(token_hash)
        return (row["id"], row["organization_id"]) if row else None

    async def portal_assessment(self, org: str, assessment_id: str, token_hash: str) -> Optional[Dict[str, Any]]:
        row = self._live(token_hash)
        if not row or row["id"] != assessment_id or row["organization_id"] != org:
            return None
        return {**_pick(self._with_supplier_name(row), ("id", "supplier_name", "template_name", "due_date",
                                                        "token_expires_at", "questions", "answers", "recipient_name")),
                "organization_name": (self.orgs.get(org) or {}).get("name")}

    async def portal_save(self, org: str, assessment_id: str, token_hash: str, answers: Dict[str, Any]) -> bool:
        row = self._live(token_hash)
        if not row or row["id"] != assessment_id or row["organization_id"] != org:
            return False
        row.update(answers=answers, updated_at=_now())
        return True

    async def portal_submit(self, org: str, assessment_id: str, token_hash: str, answers: Dict[str, Any],
                            links: List[Dict[str, Any]], score: Optional[int], flags: List[Dict[str, Any]],
                            name: str, email: str) -> Optional[Dict[str, Any]]:
        row = self._live(token_hash)
        if not row or row["id"] != assessment_id or row["organization_id"] != org:
            return None
        now = _now()
        row.update(status="submitted", token_hash=None, answers=answers, score=score, flags=flags,
                   submitted_by_name=name, submitted_by_email=email, submitted_at=now, updated_at=now)
        for link in links:
            lid = str(uuid.uuid4())
            self._assessment_tables()[2][lid] = {"id": lid, "organization_id": org, "supplier_id": row["supplier_id"],
                                                 "assessment_id": row["id"], "reported_at": now, **link}
        return _pick(self._with_supplier_name(row), ASSESSMENT_SUMMARY)


_A = "a.id, a.supplier_id, s.name AS supplier_name, a.template_name, a.status, a.recipient_email, a.recipient_name, " \
     "a.due_date, a.token_expires_at, a.submitted_at, a.submitted_by_name, a.submitted_by_email, a.score, a.flags, " \
     "a.review_note, a.reviewed_by, a.reviewed_at, a.sent_by, a.sent_at, a.updated_at, a.request_reason"
_FROM = "FROM supplier_assessments a JOIN suppliers s ON s.id = a.supplier_id"
_LIVE = "a.token_hash = :h AND a.status = 'sent' AND a.token_expires_at > now()"


def _uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (TypeError, ValueError):
        return False


class PostgresAssessments:
    """Assessments in PostgreSQL, under row-level security (migration 025)."""

    async def _one_assessment(self, org: str, sql: str, params: Dict[str, Any],
                              keys=ASSESSMENT_SUMMARY) -> Optional[Dict[str, Any]]:
        rows = await self._all(org, sql, params)
        return _pick(rows[0], keys) if rows else None

    # templates
    async def list_assessment_templates(self, org: str) -> List[Dict[str, Any]]:
        rows = await self._all(org, "SELECT * FROM assessment_templates WHERE NOT archived ORDER BY created_at")
        return [_pick(r, TEMPLATE_PUBLIC) for r in rows]

    async def get_assessment_template(self, org: str, template_id: str) -> Optional[Dict[str, Any]]:
        if not _uuid(template_id):
            return None
        rows = await self._all(org, "SELECT * FROM assessment_templates WHERE id = CAST(:i AS uuid) AND NOT archived",
                               {"i": template_id})
        return _pick(rows[0], TEMPLATE_PUBLIC) if rows else None

    async def create_assessment_template(self, org: str, name: str, description: str, questions: List[Dict[str, Any]],
                                         created_by: Optional[str]) -> Dict[str, Any]:
        rows = await self._all(org, (
            "INSERT INTO assessment_templates (organization_id, name, description, questions, created_by) "
            "VALUES (CAST(:org AS uuid), :n, :d, CAST(:q AS jsonb), :by) RETURNING *"),
            {"org": org, "n": name, "d": description, "q": json.dumps(questions), "by": created_by})
        return _pick(rows[0], TEMPLATE_PUBLIC)

    async def archive_assessment_template(self, org: str, template_id: str) -> bool:
        if not _uuid(template_id):
            return False
        return bool(await self._all(org, (
            "UPDATE assessment_templates SET archived = true WHERE id = CAST(:i AS uuid) AND NOT archived RETURNING id"),
            {"i": template_id}))

    # assessments
    async def create_assessment(self, org: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        if not _uuid(fields["supplier_id"]) or not await self.get_supplier(org, str(fields["supplier_id"])):
            raise LookupError("supplier")
        rows = await self._all(org, (
            "WITH a AS (INSERT INTO supplier_assessments (organization_id, supplier_id, template_name, questions, "
            "recipient_email, recipient_name, due_date, token_hash, token_expires_at, sent_by, request_reason) VALUES "
            "(CAST(:org AS uuid), CAST(:s AS uuid), :t, CAST(:q AS jsonb), :e, :n, :due, :h, :x, :by, :why) RETURNING *) "
            f"SELECT {_A} FROM a JOIN suppliers s ON s.id = a.supplier_id"),
            {"org": org, "s": str(fields["supplier_id"]), "t": fields["template_name"],
             "q": json.dumps(fields["questions"]), "e": fields["recipient_email"], "n": fields.get("recipient_name") or "",
             "due": date.fromisoformat(fields["due_date"]) if fields.get("due_date") else None,
             "h": fields["token_hash"], "x": fields["token_expires_at"], "by": fields.get("sent_by"),
             "why": fields.get("request_reason")})
        return _pick(rows[0], ASSESSMENT_SUMMARY)

    async def list_assessments(self, org: str, supplier_id: Optional[str] = None,
                               status: Optional[str] = None) -> List[Dict[str, Any]]:
        if supplier_id is not None and not _uuid(supplier_id):
            return []
        rows = await self._all(org, (
            f"SELECT {_A} {_FROM} WHERE (CAST(:s AS uuid) IS NULL OR a.supplier_id = CAST(:s AS uuid)) "
            "AND (CAST(:st AS text) IS NULL OR a.status = :st) ORDER BY a.sent_at DESC LIMIT 1000"),
            {"s": supplier_id, "st": status})
        return [_pick(r, ASSESSMENT_SUMMARY) for r in rows]

    async def get_assessment(self, org: str, assessment_id: str) -> Optional[Dict[str, Any]]:
        if not _uuid(assessment_id):
            return None
        return await self._one_assessment(org, f"SELECT {_A}, a.questions, a.answers {_FROM} WHERE a.id = CAST(:i AS uuid)",
                                          {"i": assessment_id}, ASSESSMENT_DETAIL)

    async def _transition(self, org: str, assessment_id: str, sets: str, where: str,
                          params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not _uuid(assessment_id):
            return None
        return await self._one_assessment(org, (
            f"WITH a AS (UPDATE supplier_assessments SET {sets}, updated_at = now() "
            f"WHERE id = CAST(:i AS uuid) AND {where} RETURNING *) SELECT {_A} FROM a JOIN suppliers s ON s.id = a.supplier_id"),
            {**params, "i": assessment_id})

    async def resend_assessment(self, org: str, assessment_id: str, token_hash: str,
                                expires_at: datetime) -> Optional[Dict[str, Any]]:
        return await self._transition(org, assessment_id, "token_hash = :h, token_expires_at = :x, sent_at = now()",
                                      "status = 'sent'", {"h": token_hash, "x": expires_at})

    async def cancel_assessment(self, org: str, assessment_id: str) -> Optional[Dict[str, Any]]:
        return await self._transition(org, assessment_id, "status = 'cancelled', token_hash = NULL", "status = 'sent'", {})

    async def review_assessment(self, org: str, assessment_id: str, note: str, by: str) -> Optional[Dict[str, Any]]:
        return await self._transition(org, assessment_id, (
            "status = 'reviewed', review_note = :note, reviewed_by = :by, reviewed_at = now()"),
            "status = 'submitted'", {"note": note or None, "by": by})

    async def list_subtier_links(self, org: str, supplier_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if supplier_id is not None and not _uuid(supplier_id):
            return []
        rows = await self._all(org, (
            "SELECT * FROM supplier_subtier_links WHERE (CAST(:s AS uuid) IS NULL OR supplier_id = CAST(:s AS uuid)) "
            "ORDER BY reported_at, name LIMIT 5000"), {"s": supplier_id})
        return [_pick(r, LINK_PUBLIC) for r in rows]

    # the portal
    async def assessment_by_token(self, token_hash: str) -> Optional[Tuple[str, str]]:
        rows = await self._all(None, "SELECT * FROM scirm_assessment_by_token(:h)", {"h": token_hash})
        return (str(rows[0]["id"]), str(rows[0]["organization_id"])) if rows else None

    async def portal_assessment(self, org: str, assessment_id: str, token_hash: str) -> Optional[Dict[str, Any]]:
        rows = await self._all(org, (
            "SELECT a.id, s.name AS supplier_name, a.template_name, a.due_date, a.token_expires_at, a.questions, "
            "a.answers, a.recipient_name, o.name AS organization_name "
            f"{_FROM} JOIN organizations o ON o.id = a.organization_id WHERE a.id = CAST(:i AS uuid) AND {_LIVE}"),
            {"i": assessment_id, "h": token_hash})
        return _pick(rows[0], ("id", "supplier_name", "template_name", "due_date", "token_expires_at", "questions",
                               "answers", "recipient_name", "organization_name")) if rows else None

    async def portal_save(self, org: str, assessment_id: str, token_hash: str, answers: Dict[str, Any]) -> bool:
        return bool(await self._all(org, (
            "UPDATE supplier_assessments a SET answers = CAST(:ans AS jsonb), updated_at = now() "
            f"WHERE a.id = CAST(:i AS uuid) AND {_LIVE} RETURNING a.id"),
            {"i": assessment_id, "h": token_hash, "ans": json.dumps(answers)}))

    async def portal_submit(self, org: str, assessment_id: str, token_hash: str, answers: Dict[str, Any],
                            links: List[Dict[str, Any]], score: Optional[int], flags: List[Dict[str, Any]],
                            name: str, email: str) -> Optional[Dict[str, Any]]:
        """Lock the answers and record the sub-tier suppliers in one transaction; the token
        is cleared by the same UPDATE that checks it, so it works exactly once."""
        from sqlalchemy import text
        async with self._tx(org) as conn:
            result = await conn.execute(text(
                "UPDATE supplier_assessments a SET status = 'submitted', token_hash = NULL, "
                "answers = CAST(:ans AS jsonb), score = :score, flags = CAST(:flags AS jsonb), "
                "submitted_by_name = :name, submitted_by_email = :email, submitted_at = now(), updated_at = now() "
                f"WHERE a.id = CAST(:i AS uuid) AND {_LIVE} RETURNING a.id, a.supplier_id"),
                {"i": assessment_id, "h": token_hash, "ans": json.dumps(answers), "score": score,
                 "flags": json.dumps(flags), "name": name, "email": email})
            row = result.first()
            if not row:
                return None
            for link in links:
                await conn.execute(text(
                    "INSERT INTO supplier_subtier_links (organization_id, supplier_id, assessment_id, name, country_code, "
                    "city, supplies) VALUES (CAST(:org AS uuid), :s, :a, :n, :c, :city, :sup)"),
                    {"org": org, "s": row.supplier_id, "a": row.id, "n": link["name"], "c": link.get("country_code"),
                     "city": link.get("city"), "sup": link.get("supplies")})
        return await self.get_assessment(org, assessment_id)
