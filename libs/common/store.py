"""
SCIRM tenant data store.

One interface, two backends:
- MemoryStore: in-process dicts (development and tests; data is lost on restart).
- PostgresStore: persistent, every call runs in a transaction with the tenant set
  via set_config('app.current_org_id', ..., true) so row-level security applies.
  The app must connect as an ordinary (non-superuser, non-owner) role.

Select with STORE_BACKEND=memory|postgres. Outside development, postgres is required.
All methods take the tenant org explicitly; nothing reads another tenant's rows
except refresh_candidates(), which iterates tenants one by one.
"""

import json
import os
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from libs.common import secret_box

SEVERITIES = ("low", "medium", "high", "critical")

_ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
_IS_DEV = _ENVIRONMENT in {"development", "dev", "local", "test"}


def _activity(signal: Dict[str, Any]) -> str:
    """Date of a signal's latest public activity. For a recall this is its publication;
    for a still-listed shortage, the last FDA update. Feeds and "last 12 months"
    filters use it so an ongoing shortage posted years ago is not hidden. Point-in-time
    logic (the back-test) uses published_at instead."""
    return signal.get("updated_at") or signal["published_at"]


def text_hash(signal: Dict[str, Any]) -> str:
    """Hash of the embedded text (title and summary); PostgreSQL computes the same with
    md5(title || chr(10) || summary)."""
    import hashlib
    return hashlib.md5(f"{signal.get('title') or ''}\n{signal.get('summary') or ''}".encode("utf-8")).hexdigest()


def _vector_literal(vector: List[float]) -> str:
    return "[" + ",".join(f"{float(x):.7g}" for x in vector) + "]"


def _cosine_distance(a: List[float], b: List[float]) -> float:
    import math
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return 1.0 - dot / (na * nb) if na and nb else 1.0


class EmailExists(Exception):
    """An account with this email already exists (in any organization)."""


class LastAdmin(Exception):
    """The change would leave the organization without an active admin."""


ROLES = ("admin", "analyst", "viewer", "auditor")
INVITATION_TTL_HOURS = int(os.getenv("INVITATION_TTL_HOURS", "168"))  # 7 days


def new_invitation_token() -> Tuple[str, str]:
    """(token for the invitee, SHA-256 hash to store). Only the hash is kept."""
    import hashlib
    import secrets
    token = secrets.token_urlsafe(32)
    return token, hashlib.sha256(token.encode()).hexdigest()


_INVITATION_STATUS_SQL = ("CASE WHEN accepted_at IS NOT NULL THEN 'accepted' WHEN revoked_at IS NOT NULL "
                          "THEN 'revoked' WHEN expires_at <= now() THEN 'expired' ELSE 'pending' END AS status")


def invitation_hash(token: str) -> str:
    import hashlib
    return hashlib.sha256((token or "").encode()).hexdigest()


def _member(user: Dict[str, Any]) -> Dict[str, Any]:
    """A user as shown to colleagues: no password hash, no MFA secret."""
    return {k: user.get(k) for k in ("id", "email", "name", "roles", "is_active", "mfa_enabled",
                                     "created_at", "last_login_at")}


def _invitation_status(inv: Dict[str, Any], now: str) -> str:
    if inv.get("accepted_at"):
        return "accepted"
    if inv.get("revoked_at"):
        return "revoked"
    return "expired" if str(inv["expires_at"]) <= now else "pending"


FEEDBACK_TARGETS = ("signal_match", "answer", "citation")
FEEDBACK_VERDICTS = {"signal_match": ("useful", "not_useful", "wrong_supplier"),
                     "answer": ("useful", "not_useful"),
                     "citation": ("incorrect",)}


def summarize_feedback(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Pilot gate metrics from feedback rows (target_type, target_id, verdict, user_id, context)."""
    def count(t, v=None):
        return sum(1 for r in rows if r["target_type"] == t and (v is None or r["verdict"] == v))

    def rate(a, b):
        return round(a / b, 3) if b else None

    matches = count("signal_match")
    answers = count("answer")
    rated_answers = {r["target_id"] for r in rows if r["target_type"] == "answer"}
    cited = sum(int((r.get("context") or {}).get("citations") or 0) for r in rows if r["target_type"] == "answer")
    wrong_citations = count("citation", "incorrect")
    # Citation ids are "<answer id>:<S#>"; only reports on rated answers share a denominator.
    wrong_in_rated = sum(1 for r in rows if r["target_type"] == "citation" and r["verdict"] == "incorrect"
                         and r["target_id"].rsplit(":", 1)[0] in rated_answers)
    return {
        "raters": len({r["user_id"] for r in rows}),
        "records": {"rated": matches, "useful": count("signal_match", "useful"),
                    "not_useful": count("signal_match", "not_useful"),
                    "wrong_supplier": count("signal_match", "wrong_supplier"),
                    "useful_rate": rate(count("signal_match", "useful"), matches),
                    "wrong_supplier_rate": rate(count("signal_match", "wrong_supplier"), matches)},
        "answers": {"rated": answers, "helpful": count("answer", "useful"), "not_helpful": count("answer", "not_useful"),
                    "helpful_rate": rate(count("answer", "useful"), answers)},
        # Estimated: an unreported citation is counted as correct.
        "citations": {"reported_incorrect": wrong_citations, "in_rated_answers": cited,
                      "reported_incorrect_in_rated_answers": wrong_in_rated,
                      "estimated_correct_rate": rate(cited - wrong_in_rated, cited)},
    }


def _now() -> str:
    return datetime.utcnow().isoformat()


def _severity(value: Any) -> str:
    return value if value in SEVERITIES else "medium"


# Demo tenants' suppliers (development and tests only).
DEMO_SUPPLIERS: List[Dict[str, Any]] = [
    {"id": "c0000000-0000-0000-0000-000000000001", "organization_id": "a0000000-0000-0000-0000-000000000001", "supplier_code": "SUP-ALPHA", "name": "Supplier Alpha", "supplier_type": "api_manufacturer", "country_code": "US", "region": "North America", "risk_score": 35.0, "risk_tier": "low", "contact_name": "John Smith", "contact_email": "john@supplier-alpha.com", "is_active": True},
    {"id": "c0000000-0000-0000-0000-000000000002", "organization_id": "a0000000-0000-0000-0000-000000000001", "supplier_code": "SUP-BETA", "name": "Supplier Beta", "supplier_type": "excipient_supplier", "country_code": "DE", "region": "Europe", "risk_score": 62.0, "risk_tier": "medium", "contact_name": "Hans Mueller", "contact_email": "hans@supplier-beta.de", "is_active": True},
    {"id": "c0000000-0000-0000-0000-000000000003", "organization_id": "a0000000-0000-0000-0000-000000000001", "supplier_code": "SUP-GAMMA", "name": "Supplier Gamma", "supplier_type": "packaging", "country_code": "CN", "region": "Asia Pacific", "risk_score": 78.0, "risk_tier": "high", "contact_name": "Wei Zhang", "contact_email": "wei@supplier-gamma.cn", "is_active": True},
    {"id": "c0000000-0000-0000-0000-000000000004", "organization_id": "a0000000-0000-0000-0000-000000000002", "supplier_code": "SUP-DELTA", "name": "Supplier Delta", "supplier_type": "sensor_components", "country_code": "JP", "region": "Asia Pacific", "risk_score": 28.0, "risk_tier": "low", "contact_name": "Yuki Tanaka", "contact_email": "yuki@supplier-delta.jp", "is_active": True},
    {"id": "c0000000-0000-0000-0000-000000000005", "organization_id": "a0000000-0000-0000-0000-000000000002", "supplier_code": "SUP-EPSILON", "name": "Supplier Epsilon", "supplier_type": "biocompatible_materials", "country_code": "US", "region": "North America", "risk_score": 55.0, "risk_tier": "medium", "contact_name": "Sarah Johnson", "contact_email": "sarah@supplier-epsilon.com", "is_active": True},
]
# Fictional demo suppliers: their scores are sample values, so they carry a demo note
# (shown as a Demo badge) like the real-name demo suppliers below.
for _s in DEMO_SUPPLIERS:
    _s["demo_note"] = "Fictional supplier for demonstration; its details and scores are sample values."
# Demo suppliers named after real companies, so the demo tenant shows real public
# records (FDA recalls and shortages) matched to them. The signals are genuine;
# the supplier relationships, contacts and scores are not.
_REAL_DEMO = [
    ("c0000000-0000-0000-0000-000000000101", "DEMO-FRESENIUS", "Fresenius Kabi USA, LLC", "api_manufacturer", "US", "North America"),
    ("c0000000-0000-0000-0000-000000000102", "DEMO-HOSPIRA", "Hospira, Inc.", "api_manufacturer", "US", "North America"),
    ("c0000000-0000-0000-0000-000000000103", "DEMO-SUNPHARMA", "Sun Pharmaceutical Industries, Inc.", "api_manufacturer", "IN", "South Asia"),
    ("c0000000-0000-0000-0000-000000000104", "DEMO-GLENMARK", "Glenmark Pharmaceuticals Inc., USA", "api_manufacturer", "IN", "South Asia"),
    ("c0000000-0000-0000-0000-000000000105", "DEMO-BAXTER", "Baxter Healthcare Corporation", "packaging", "US", "North America"),
    ("c0000000-0000-0000-0000-000000000106", "DEMO-GLAND", "Gland Pharma Limited", "api_manufacturer", "IN", "South Asia"),
]
DEMO_SUPPLIERS += [
    {"id": sid, "organization_id": "a0000000-0000-0000-0000-000000000001", "supplier_code": code, "name": name,
     "supplier_type": stype, "country_code": cc, "region": region, "risk_score": 50.0, "risk_tier": "medium",
     "is_active": True, "demo_note": "Real company name for demonstration; matched signals are public records."}
    for sid, code, name, stype, cc, region in _REAL_DEMO
]
DEMO_ORGS = [
    ("a0000000-0000-0000-0000-000000000001", "PharmaCorp International", "pharmaceutical"),
    ("a0000000-0000-0000-0000-000000000002", "MedTech Solutions", "medical_devices"),
    ("a0000000-0000-0000-0000-000000000003", "SCIRM Audit", "general"),
]


# ===========================================================================
# In-memory backend
# ===========================================================================

class MemoryStore:
    def __init__(self, seed_demo: bool = True):
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.manual_risks: Dict[str, Dict[str, Any]] = {}
        self.suppliers: Dict[str, Dict[str, Any]] = {s["id"]: dict(s) for s in DEMO_SUPPLIERS} if seed_demo else {}
        self.alerts: List[Dict[str, Any]] = []
        self.events: List[Dict[str, Any]] = []
        self.impacts: List[Dict[str, Any]] = []
        self.audit: List[Dict[str, Any]] = []
        self.orgs: Dict[str, Dict[str, Any]] = {}
        self.users: Dict[str, Dict[str, Any]] = {}
        self.invitations: Dict[str, Dict[str, Any]] = {}
        self.feedback: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
        self.signals: Dict[Tuple[str, str], Dict[str, Any]] = {}
        # (source, external_id) -> (vector, model, text hash)
        self.embeddings: Dict[Tuple[str, str], Tuple[List[float], str, str]] = {}
        self.source_runs: Dict[str, Dict[str, Any]] = {}
        self.erp_connections: Dict[Tuple[str, str], Dict[str, Any]] = {}

    async def close(self) -> None:
        return None

    # --- tasks --------------------------------------------------------------
    async def create_task(self, org: str, task_id: str, request: Dict[str, Any]) -> None:
        self.tasks[task_id] = {"status": "processing", "organization_id": org,
                               "started_at": _now(), "request": request}

    async def complete_task(self, org: str, task_id: str, result: Dict[str, Any]) -> None:
        task = self.tasks[task_id]
        task.update(status="completed", completed_at=_now(), result=result)

    async def fail_task(self, org: str, task_id: str, error: Optional[str] = None) -> None:
        task = self.tasks[task_id]
        task["status"] = "failed"
        if error:
            task["error"] = error

    async def get_task(self, org: str, task_id: str) -> Optional[Dict[str, Any]]:
        task = self.tasks.get(task_id)
        return task if task and task.get("organization_id") == org else None

    async def list_tasks(self, org: str, status: Optional[str] = None) -> List[Tuple[str, Dict[str, Any]]]:
        return [(tid, t) for tid, t in self.tasks.items()
                if t.get("organization_id") == org and (status is None or t.get("status") == status)]

    async def refresh_candidates(self) -> Dict[str, List[Dict[str, Any]]]:
        by_org: Dict[str, List[Dict[str, Any]]] = {}
        seen = set()
        for task in list(self.tasks.values()):
            org = task.get("organization_id")
            if org and task.get("status") == "completed" and task.get("request"):
                for entity in task["request"].get("entities", []):
                    eid = entity.get("id", "")
                    if eid and (org, eid) not in seen:
                        by_org.setdefault(org, []).append(entity)
                        seen.add((org, eid))
        return by_org

    def _completed(self, org: str) -> Iterable[Tuple[str, Dict[str, Any]]]:
        for tid, task in list(self.tasks.items()):
            if task.get("organization_id") == org and task.get("status") == "completed" and task.get("result"):
                yield tid, task

    # --- risks --------------------------------------------------------------
    async def assessment_risks(self, org: str) -> List[Dict[str, Any]]:
        risks: List[Dict[str, Any]] = []
        for _, task in self._completed(org):
            risks.extend(task["result"].get("risks", []))
        return risks

    async def list_risks(self, org: str, severity: Optional[str] = None,
                         limit: Optional[int] = None, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
        risks = [r for r in self.manual_risks.values() if r.get("organization_id") == org]
        risks += await self.assessment_risks(org)
        if severity:
            risks = [r for r in risks if r.get("severity") == severity]
        page = risks[offset:offset + limit] if limit is not None else risks[offset:]
        return page, len(risks)

    async def get_risk(self, org: str, risk_id: str) -> Optional[Dict[str, Any]]:
        risks, _ = await self.list_risks(org)
        return next((r for r in risks if r.get("id") == risk_id), None)

    async def create_risk(self, org: str, risk: Dict[str, Any]) -> Dict[str, Any]:
        risk = {**risk, "organization_id": org}
        self.manual_risks[risk["id"]] = risk
        return risk

    async def update_risk(self, org: str, risk_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        risk = await self.get_risk(org, risk_id)
        if risk is None:
            return None
        risk.update({k: v for k, v in updates.items() if k not in ("id", "organization_id")})
        return risk

    async def risk_history(self, org: str, limit: int) -> Tuple[List[Dict[str, Any]], int]:
        history = []
        for tid, task in self._completed(org):
            for risk in task["result"].get("risks", []):
                history.append({**risk, "assessment_task_id": tid, "assessment_completed_at": task.get("completed_at")})
        history.sort(key=lambda r: r.get("detected_at", ""), reverse=True)
        return history[:limit], len(history)

    async def recommendations_for_risk(self, org: str, risk_id: str) -> List[Dict[str, Any]]:
        for _, task in self._completed(org):
            matching = [r for r in task["result"].get("recommendations", []) if r.get("risk_id") == risk_id]
            if matching:
                return matching
        return []

    # --- suppliers ----------------------------------------------------------
    async def list_suppliers(self, org: str, risk_tier: Optional[str] = None,
                             limit: Optional[int] = None) -> Tuple[List[Dict[str, Any]], int]:
        suppliers = [s for s in self.suppliers.values() if s.get("organization_id") == org]
        if risk_tier:
            suppliers = [s for s in suppliers if s.get("risk_tier") == risk_tier]
        return (suppliers[:limit] if limit is not None else suppliers), len(suppliers)

    async def get_supplier(self, org: str, supplier_id: str) -> Optional[Dict[str, Any]]:
        supplier = self.suppliers.get(supplier_id)
        return supplier if supplier and supplier.get("organization_id") == org else None

    async def create_supplier(self, org: str, supplier: Dict[str, Any]) -> Dict[str, Any]:
        supplier = {**supplier, "id": str(uuid.uuid4()), "organization_id": org}
        self.suppliers[supplier["id"]] = supplier
        return supplier

    async def update_supplier(self, org: str, supplier_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        supplier = await self.get_supplier(org, supplier_id)
        if supplier is None:
            return None
        supplier.update({k: v for k, v in updates.items() if k not in ("id", "organization_id")})
        return supplier

    async def write_suppliers(self, org: str, creates: List[Dict[str, Any]],
                              updates: List[Tuple[str, Dict[str, Any]]]) -> int:
        """Create and update suppliers together: all of them, or none if any update target is missing."""
        if any([await self.get_supplier(org, sid) is None for sid, _ in updates]):
            raise KeyError("supplier not found")
        for sid, fields in updates:
            await self.update_supplier(org, sid, fields)
        for supplier in creates:
            await self.create_supplier(org, supplier)
        return len(creates) + len(updates)

    # --- alerts -------------------------------------------------------------
    async def add_alerts(self, org: str, alerts: List[Dict[str, Any]]) -> None:
        self.alerts.extend({**a, "organization_id": org} for a in alerts)

    async def list_alerts(self, org: str, status: Optional[str] = None, severity: Optional[str] = None,
                          limit: int = 50) -> Tuple[List[Dict[str, Any]], int]:
        alerts = [a for a in self.alerts if a.get("organization_id") == org]
        if status:
            alerts = [a for a in alerts if a.get("status") == status]
        if severity:
            alerts = [a for a in alerts if a.get("severity") == severity]
        return alerts[:limit], len(alerts)

    async def acknowledge_alert(self, org: str, alert_id: str) -> Optional[Dict[str, Any]]:
        for alert in self.alerts:
            if alert.get("id") == alert_id and alert.get("organization_id") == org:
                alert["status"] = "acknowledged"
                alert["acknowledged_at"] = _now()
                return alert
        return None

    # --- events -------------------------------------------------------------
    async def create_event(self, org: str, event: Dict[str, Any]) -> Dict[str, Any]:
        event = {**event, "organization_id": org}
        self.events.append(event)
        return event

    async def list_events(self, org: str, limit: int = 50) -> Tuple[List[Dict[str, Any]], int]:
        events = sorted((e for e in self.events if e.get("organization_id") == org),
                        key=lambda e: e.get("detected_at", ""), reverse=True)
        return events[:limit], len(events)

    async def add_impacts(self, org: str, impacts: List[Dict[str, Any]]) -> None:
        self.impacts.extend({**i, "organization_id": org} for i in impacts)

    async def event_impacts(self, org: str, event_id: str) -> List[Dict[str, Any]]:
        return [i for i in self.impacts if i.get("event_id") == event_id and i.get("organization_id") == org]

    # --- public signals (no tenant: public records) --------------------------
    async def upsert_signals(self, signals: List[Dict[str, Any]]) -> int:
        new = 0
        for sig in signals:
            key = (sig["source"], sig["external_id"])
            if key in self.signals:
                kept = {k: self.signals[key][k] for k in ("id", "first_seen_at")}
                self.signals[key] = {**sig, **kept, "last_seen_at": _now(), "delisted_at": None}
            else:
                self.signals[key] = {**sig, "id": str(uuid.uuid4()), "first_seen_at": _now(), "last_seen_at": _now()}
                new += 1
        return new

    async def list_signals(self, source: Optional[str] = None, since: Optional[str] = None,
                           limit: int = 50) -> Tuple[List[Dict[str, Any]], int]:
        found = [s for s in self.signals.values() if not s.get("delisted_at")
                 and (source is None or s["source"] == source) and (since is None or _activity(s) >= since)]
        found.sort(key=lambda s: (_activity(s), s["external_id"]), reverse=True)
        return found[:limit], len(found)

    async def signal_candidates(self, keys: List[str], countries: List[str], since: Optional[str] = None,
                                limit: int = 2000) -> List[Dict[str, Any]]:
        keys_set, countries_set = set(keys), set(countries)
        found = [s for s in self.signals.values()
                 if not s.get("delisted_at") and (since is None or _activity(s) >= since)
                 and (keys_set & set(s.get("entity_keys") or [])
                      or (s["signal_type"] == "disaster" and countries_set & set(s.get("country_codes") or [])))]
        found.sort(key=_activity, reverse=True)
        return found[:limit]

    async def search_signals(self, query_terms: List[str], keys: Optional[List[str]] = None,
                             limit: int = 50) -> List[Dict[str, Any]]:
        """Keyword search (any term), title matches weighing double. Development stand-in for
        the PostgreSQL full-text search; evaluation numbers come from PostgreSQL."""
        stems = [t.lower()[:5] for term in query_terms for t in re.findall(r"[a-z0-9]+", term.lower()) if len(t) > 2]
        if not stems:
            return []
        keys_set = set(keys or [])
        scored = []
        for sig in self.signals.values():
            if sig.get("delisted_at") or (keys is not None and not keys_set & set(sig.get("entity_keys") or [])):
                continue
            title = {w[:5] for w in re.findall(r"[a-z0-9]+", (sig.get("title") or "").lower())}
            summary = {w[:5] for w in re.findall(r"[a-z0-9]+", (sig.get("summary") or "").lower())}
            score = sum(2.0 * (st in title) + 1.0 * (st in summary) for st in stems)
            if score:
                scored.append({**sig, "rank": score})
        scored.sort(key=lambda x: (x["rank"], _activity(x)), reverse=True)
        return scored[:limit]

    async def signals_needing_embedding(self, model: str, limit: int = 500) -> List[Dict[str, Any]]:
        out = []
        for key, sig in self.signals.items():
            if sig.get("delisted_at"):
                continue
            stored = self.embeddings.get(key)
            if not stored or stored[1] != model or stored[2] != text_hash(sig):
                out.append({"id": sig["id"], "title": sig["title"], "summary": sig.get("summary") or "",
                            "_key": key})
        out.sort(key=lambda r: _activity(self.signals[r["_key"]]), reverse=True)
        return out[:limit]

    async def set_embeddings(self, items: List[Tuple[str, str, List[float]]], model: str) -> int:
        """items: (signal id, hash of the text embedded, vector). Skipped if the text changed since."""
        by_id = {sig["id"]: key for key, sig in self.signals.items()}
        written = 0
        for signal_id, digest, vector in items:
            key = by_id.get(signal_id)
            if key and text_hash(self.signals[key]) == digest:
                self.embeddings[key] = (list(vector), model, digest)
                written += 1
        return written

    async def vector_search(self, vector: List[float], model: str, keys: List[str],
                            limit: int = 50) -> List[Dict[str, Any]]:
        keys_set, scored = set(keys), []
        for key, sig in self.signals.items():
            stored = self.embeddings.get(key)
            if (sig.get("delisted_at") or not stored or stored[1] != model or stored[2] != text_hash(sig)
                    or not keys_set & set(sig.get("entity_keys") or [])):
                continue
            scored.append({**sig, "distance": _cosine_distance(vector, stored[0])})
        scored.sort(key=lambda r: r["distance"])
        return scored[:limit]

    async def embedding_coverage(self, model: str) -> Dict[str, int]:
        active = [(k, s) for k, s in self.signals.items() if not s.get("delisted_at")]
        embedded = sum(1 for k, s in active if (e := self.embeddings.get(k)) and e[1] == model and e[2] == text_hash(s))
        return {"embedded": embedded, "total": len(active)}

    async def retire_unseen(self, source: str, seen_ids: Iterable[str]) -> int:
        """Mark this source's active signals that a full run did not see as delisted."""
        seen, retired = set(seen_ids), 0
        for (src, external_id), sig in self.signals.items():
            if src == source and external_id not in seen and not sig.get("delisted_at"):
                sig["delisted_at"] = _now()
                retired += 1
        return retired

    async def record_source_run(self, source: str, status: str, error: Optional[str], seen: int, new: int) -> None:
        previous = self.source_runs.get(source, {})
        self.source_runs[source] = {"source": source, "status": status, "error": error, "signals_seen": seen,
                                    "signals_new": new, "last_run_at": _now(),
                                    "last_success_at": _now() if status == "ok" else previous.get("last_success_at")}

    async def list_source_runs(self) -> Dict[str, Dict[str, Any]]:
        return dict(self.source_runs)

    # --- accounts -----------------------------------------------------------
    def _user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        email = (email or "").lower()
        return next((u for u in self.users.values() if u["email"] == email), None)

    async def find_login_user(self, email: str) -> Optional[Dict[str, Any]]:
        user = self._user_by_email(email)
        return await self._with_mfa_secret(dict(user)) if user else None

    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        user = self.users.get(str(user_id))
        return await self._with_mfa_secret({k: v for k, v in user.items() if k != "hashed_password"}) if user else None

    async def _with_mfa_secret(self, user: Dict[str, Any]) -> Dict[str, Any]:
        return await _open_mfa_secret(self, user)

    async def create_organization(self, name: str, industry: str = "general") -> str:
        org = str(uuid.uuid4())
        self.orgs[org] = {"id": org, "name": name, "industry": industry}
        return org

    async def create_user(self, org: str, email: str, name: str, hashed_password: str,
                          roles: List[str]) -> Dict[str, Any]:
        if self._user_by_email(email):
            raise EmailExists(email)
        user = {"id": str(uuid.uuid4()), "organization_id": org, "email": email.lower(), "name": name,
                "hashed_password": hashed_password, "roles": list(roles), "is_active": True,
                "mfa_secret": None, "mfa_enabled": False, "created_at": _now(), "last_login_at": None}
        self.users[user["id"]] = user
        return _member(user)

    async def list_members(self, org: str) -> List[Dict[str, Any]]:
        return [_member(u) for u in self.users.values() if u["organization_id"] == org]

    async def update_member(self, org: str, user_id: str, roles: Optional[List[str]] = None,
                            is_active: Optional[bool] = None) -> Optional[Dict[str, Any]]:
        user = self.users.get(str(user_id))
        if not user or user["organization_id"] != org:
            return None
        new_roles = list(roles) if roles is not None else user["roles"]
        new_active = user["is_active"] if is_active is None else bool(is_active)
        # Only a change that takes away an active admin can leave the organization without one.
        removes_admin = user["is_active"] and "admin" in user["roles"] and not (new_active and "admin" in new_roles)
        others = [u for u in self.users.values() if u["organization_id"] == org and u["is_active"]
                  and "admin" in u["roles"] and u["id"] != user["id"]]
        if removes_admin and not others:
            raise LastAdmin(org)
        user.update(roles=new_roles, is_active=new_active)
        return _member(user)

    async def create_invitation(self, org: str, email: str, roles: List[str], invited_by: Optional[str],
                                ttl_hours: int = INVITATION_TTL_HOURS) -> Tuple[Dict[str, Any], str]:
        if self._user_by_email(email):
            raise EmailExists(email)
        from datetime import timedelta
        token, digest = new_invitation_token()
        inv = {"id": str(uuid.uuid4()), "organization_id": org, "email": email.lower(), "roles": list(roles),
               "token_hash": digest, "invited_by": invited_by, "created_at": _now(),
               "expires_at": (datetime.utcnow() + timedelta(hours=ttl_hours)).isoformat(),
               "accepted_at": None, "revoked_at": None}
        self.invitations[inv["id"]] = inv
        return self._invitation_view(inv), token

    def _invitation_view(self, inv: Dict[str, Any]) -> Dict[str, Any]:
        view = {k: inv.get(k) for k in ("id", "email", "roles", "invited_by", "created_at", "expires_at",
                                        "accepted_at", "revoked_at")}
        return {**view, "status": _invitation_status(inv, _now())}

    async def list_invitations(self, org: str) -> List[Dict[str, Any]]:
        found = [self._invitation_view(i) for i in self.invitations.values() if i["organization_id"] == org]
        return sorted(found, key=lambda i: i["created_at"], reverse=True)

    async def revoke_invitation(self, org: str, invitation_id: str) -> bool:
        inv = self.invitations.get(str(invitation_id))
        if not inv or inv["organization_id"] != org or inv["accepted_at"] or inv["revoked_at"]:
            return False
        inv["revoked_at"] = _now()
        return True

    def _live_invitation(self, token: str) -> Optional[Dict[str, Any]]:
        digest = invitation_hash(token)
        inv = next((i for i in self.invitations.values() if i["token_hash"] == digest), None)
        return inv if inv and _invitation_status(inv, _now()) == "pending" else None

    async def lookup_invitation(self, token: str) -> Optional[Dict[str, Any]]:
        inv = self._live_invitation(token)
        if not inv:
            return None
        org = self.orgs.get(inv["organization_id"], {})
        return {"id": inv["id"], "organization_id": inv["organization_id"],
                "organization_name": org.get("name", ""), "email": inv["email"], "roles": inv["roles"],
                "expires_at": inv["expires_at"]}

    async def accept_invitation(self, token: str, name: str, hashed_password: str) -> Optional[Dict[str, Any]]:
        inv = self._live_invitation(token)
        if not inv:
            return None
        if self._user_by_email(inv["email"]):
            raise EmailExists(inv["email"])
        inv["accepted_at"] = _now()
        user = await self.create_user(inv["organization_id"], inv["email"], name, hashed_password, inv["roles"])
        return {"user_id": user["id"], "organization_id": inv["organization_id"], "email": inv["email"],
                "roles": inv["roles"]}

    async def set_mfa_secret(self, org: str, user_id: str, secret: Optional[str]) -> bool:
        user = self.users.get(str(user_id))
        if not user or user["organization_id"] != org:
            return False
        user.update(mfa_secret=secret_box.encrypt(secret, user["id"]) if secret else None, mfa_enabled=bool(secret))
        return True

    async def record_login(self, org: str, user_id: str) -> None:
        user = self.users.get(str(user_id))
        if user and user["organization_id"] == org:
            user["last_login_at"] = _now()

    # --- feedback -----------------------------------------------------------
    async def record_feedback(self, org: str, user_id: str, item: Dict[str, Any]) -> Dict[str, Any]:
        key = (org, str(user_id), item["target_type"], item["target_id"])
        existing = self.feedback.get(key)
        row = {**item, "organization_id": org, "user_id": str(user_id),
               "created_at": existing["created_at"] if existing else _now(), "updated_at": _now()}
        self.feedback[key] = row
        return {k: row.get(k) for k in ("target_type", "target_id", "supplier_id", "verdict", "reason", "updated_at")}

    async def my_feedback_for_supplier(self, org: str, user_id: str, supplier_id: str) -> Dict[str, str]:
        """This user's ratings of records matched to one supplier: {target_id: verdict}."""
        return {k[3]: v["verdict"] for k, v in self.feedback.items()
                if k[0] == org and k[1] == str(user_id) and k[2] == "signal_match" and v.get("supplier_id") == supplier_id}

    async def feedback_summary(self, org: str, since: Optional[datetime] = None) -> Dict[str, Any]:
        cutoff = since.replace(tzinfo=None).isoformat() if since else None
        rows = [r for k, r in self.feedback.items() if k[0] == org and (cutoff is None or r["updated_at"] >= cutoff)]
        return summarize_feedback(rows)

    # --- ERP connections ------------------------------------------------------
    async def get_erp_connection(self, org: str, system: str, with_password: bool = False) -> Optional[Dict[str, Any]]:
        """The tenant's connection without its password, or with it decrypted
        (with_password, for the service that calls SAP; never for an API response)."""
        row = self.erp_connections.get((org, system))
        if row is None:
            return None
        out = _erp_public(row)
        if with_password:
            password, stale = _erp_open(org, row)
            if stale:  # sealed with the previous key
                row["password_enc"] = secret_box.encrypt(password, _erp_bound(system, org, row["id"]))
            out["password"] = password
        return out

    async def save_erp_connection(self, org: str, system: str, fields: Dict[str, Any], password: Optional[str],
                                  actor: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Create or replace the connection. password=None keeps the stored one; None is
        returned when there is none to keep."""
        row = self.erp_connections.get((org, system))
        if row is None and not password:
            return None
        if row is None:
            row = {"id": str(uuid.uuid4()), "organization_id": org, "system": system, "created_by": actor,
                   "created_at": _now(), "last_test": None, "last_import": None}
        changed = {k: fields.get(k) for k in ("base_url", "sap_client", "username")}
        if password or any(row.get(k) != v for k, v in changed.items()):
            row["last_test"] = None  # a test of other settings no longer says anything
        row.update(changed, updated_at=_now())
        if password:
            row["password_enc"] = secret_box.encrypt(password, _erp_bound(system, org, row["id"]))
        self.erp_connections[(org, system)] = row
        return _erp_public(row)

    async def delete_erp_connection(self, org: str, system: str) -> bool:
        return self.erp_connections.pop((org, system), None) is not None

    async def record_erp_result(self, org: str, system: str, kind: str, result: Dict[str, Any]) -> None:
        row = self.erp_connections.get((org, system))
        if row is not None and kind in ("last_test", "last_import"):
            row[kind] = {**result, "at": _now()}

    # --- audit --------------------------------------------------------------
    async def record_audit(self, org: Optional[str], entry: Dict[str, Any]) -> None:
        self.audit.append({**entry, "organization_id": org, "created_at": _now()})

    async def list_audit(self, org: str, limit: int = 100) -> List[Dict[str, Any]]:
        return [a for a in reversed(self.audit) if a.get("organization_id") == org][:limit]


# --- ERP connections (shared) ---------------------------------------------------

_ERP_PUBLIC = ("id", "system", "base_url", "sap_client", "username", "last_test", "last_import", "created_by",
               "created_at", "updated_at")


def _erp_bound(system: str, org: str, connection_id: str) -> str:
    # The "erp:" prefix keeps these ciphertexts apart from MFA seeds, which are bound to a user id.
    return f"erp:{system}:{org}:{connection_id}"


def _erp_public(row: Dict[str, Any]) -> Dict[str, Any]:
    """A connection as the API shows it: everything except the password."""
    out = {k: row.get(k) for k in _ERP_PUBLIC}
    for k in ("last_test", "last_import"):
        if isinstance(out[k], str):
            out[k] = json.loads(out[k])
    return {**_jsonable(out), "has_password": bool(row.get("password_enc"))}


def _erp_open(org: str, row: Dict[str, Any]) -> Tuple[str, bool]:
    return secret_box.decrypt(row["password_enc"], _erp_bound(row["system"], org, str(row["id"])),
                              allow_plaintext=False)


async def _open_mfa_secret(store: Any, user: Dict[str, Any]) -> Dict[str, Any]:
    """Decrypt a user's TOTP seed for the caller. A legacy plaintext seed, or one sealed
    with the previous key, is re-encrypted with the current key on the way."""
    stored = user.get("mfa_secret")
    if not stored:
        return user
    plaintext, stale = secret_box.decrypt(stored, str(user["id"]))
    if stale:
        await store.set_mfa_secret(str(user["organization_id"]), str(user["id"]), plaintext)
    return {**user, "mfa_secret": plaintext}


# ===========================================================================
# PostgreSQL backend
# ===========================================================================

_SUPPLIER_COLUMNS = ("supplier_code", "name", "supplier_type", "country_code", "region", "risk_score",
                     "risk_tier", "contact_name", "contact_email", "is_active", "tier_level")
_RISK_COLUMNS = ("title", "description", "severity", "probability", "impact_score", "affected_entities",
                 "risk_category", "detected_at", "predicted_occurrence", "data_sources", "status", "owner")
_EVENT_COLUMNS = ("event_type", "title", "description", "severity", "affected_region",
                  "location_lat", "location_lng", "source_url", "status", "detected_at")


def _is_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError):
        return False


def _ts(value: Any) -> Optional[datetime]:
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _day(value: Any) -> Optional[date]:
    """ISO date string -> date (asyncpg will not cast strings to date parameters)."""
    return date.fromisoformat(value[:10]) if isinstance(value, str) and value else None


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def _jsonable(row: Dict[str, Any]) -> Dict[str, Any]:
    return {k: (str(v) if isinstance(v, uuid.UUID) else _iso(v)) for k, v in row.items()}


class PostgresStore:
    def __init__(self, database_url: str):
        from sqlalchemy.ext.asyncio import create_async_engine
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if os.getenv("DB_POOL", "").lower() == "null":
            # No pooling: for tests, where each request may run on a different event loop.
            from sqlalchemy.pool import NullPool
            self.engine = create_async_engine(database_url, poolclass=NullPool)
        else:
            self.engine = create_async_engine(
                database_url,
                pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
                max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
                pool_pre_ping=True,
            )

    async def close(self) -> None:
        await self.engine.dispose()

    def _tx(self, org: Optional[str]):
        """Transaction scoped to one tenant. set_config(..., true) is transaction-local,
        so a pooled connection never carries one tenant's id into the next request."""
        from sqlalchemy import text
        store = self

        class _Tx:
            async def __aenter__(self):
                self._cm = store.engine.begin()
                conn = await self._cm.__aenter__()
                await conn.execute(text("SELECT set_config('app.current_org_id', :org, true)"), {"org": org or ""})
                return conn

            async def __aexit__(self, *exc):
                return await self._cm.__aexit__(*exc)

        return _Tx()

    async def _all(self, org: Optional[str], sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        from sqlalchemy import text
        async with self._tx(org) as conn:
            result = await conn.execute(text(sql), params or {})
            return [dict(r._mapping) for r in result]

    async def _exec(self, org: Optional[str], statements: List[Tuple[str, Dict[str, Any]]]) -> None:
        from sqlalchemy import text
        async with self._tx(org) as conn:
            for sql, params in statements:
                await conn.execute(text(sql), params)

    async def _ensure_org(self, org: str) -> None:
        # organizations has no RLS: an org row must exist for tenant foreign keys.
        await self._exec(org, [(
            "INSERT INTO organizations (id, name, industry) VALUES (CAST(:org AS uuid), :name, 'general') "
            "ON CONFLICT (id) DO NOTHING", {"org": org, "name": f"Organization {org[:8]}"})])

    # --- tasks --------------------------------------------------------------
    async def create_task(self, org: str, task_id: str, request: Dict[str, Any]) -> None:
        await self._ensure_org(org)
        await self._exec(org, [(
            "INSERT INTO risk_assessments (task_id, organization_id, status, assessment_type, request_payload, started_at) "
            "VALUES (:task_id, CAST(:org AS uuid), 'processing', :atype, CAST(:req AS json), now())",
            {"task_id": task_id, "org": org, "atype": request.get("assessment_type") or "comprehensive",
             "req": json.dumps(request)})])

    async def complete_task(self, org: str, task_id: str, result: Dict[str, Any]) -> None:
        rows = await self._all(org, "SELECT id FROM risk_assessments WHERE task_id = :t", {"t": task_id})
        if not rows:
            return
        aid = str(rows[0]["id"])
        statements: List[Tuple[str, Dict[str, Any]]] = [(
            "UPDATE risk_assessments SET status = 'completed', completed_at = now(), result = CAST(:result AS jsonb), "
            "confidence_score = :conf, reasoning_trail = CAST(:trail AS json), metadata = CAST(:meta AS json) "
            "WHERE id = CAST(:aid AS uuid)",
            {"aid": aid, "result": json.dumps(result), "conf": result.get("confidence_score"),
             "trail": json.dumps(result.get("reasoning_trail", [])), "meta": json.dumps(result.get("metadata", {}))})]
        risk_ids = set()
        for risk in result.get("risks", []):
            rid = risk.get("id") if _is_uuid(risk.get("id")) else str(uuid.uuid4())
            risk_ids.add(rid)
            statements.append(self._insert_risk_sql(org, {**risk, "id": rid}, aid))
        for rec in result.get("recommendations", []):
            rec_risk = rec.get("risk_id") if rec.get("risk_id") in risk_ids else None
            known = {"id", "risk_id", "title", "description", "action_type", "priority", "estimated_cost",
                     "estimated_impact", "timeline_days", "resources_required", "success_probability"}
            statements.append((
                "INSERT INTO recommendations (id, assessment_id, risk_id, title, description, action_type, priority, "
                "estimated_cost, estimated_impact, timeline_days, resources_required, success_probability, details) "
                "VALUES (CAST(:id AS uuid), CAST(:aid AS uuid), CAST(:rid AS uuid), :title, :description, :atype, :priority, "
                ":cost, :impact, :days, :resources, :success, CAST(:details AS jsonb))",
                {"id": rec["id"] if _is_uuid(rec.get("id")) else str(uuid.uuid4()), "aid": aid, "rid": rec_risk,
                 "title": rec.get("title", ""), "description": rec.get("description", ""),
                 "atype": rec.get("action_type", "preventive"), "priority": rec.get("priority", "medium"),
                 "cost": rec.get("estimated_cost"), "impact": rec.get("estimated_impact", 5.0),
                 "days": rec.get("timeline_days"), "resources": list(rec.get("resources_required") or []),
                 "success": rec.get("success_probability", 0.5),
                 "details": json.dumps({k: v for k, v in rec.items() if k not in known} | {"risk_ref": rec.get("risk_id")})}))
        await self._exec(org, statements)

    def _insert_risk_sql(self, org: str, risk: Dict[str, Any], assessment_id: Optional[str]) -> Tuple[str, Dict[str, Any]]:
        details = {k: v for k, v in risk.items() if k not in _RISK_COLUMNS and k not in ("id", "organization_id")}
        return (
            "INSERT INTO risks (id, assessment_id, organization_id, title, description, severity, probability, "
            "impact_score, affected_entities, risk_category, detected_at, predicted_occurrence, data_sources, "
            "status, owner, details) VALUES (CAST(:id AS uuid), CAST(:aid AS uuid), CAST(:org AS uuid), :title, "
            ":description, CAST(:severity AS risk_severity), :probability, :impact, :entities, :category, "
            "COALESCE(:detected, now()), :predicted, :sources, :status, :owner, CAST(:details AS jsonb))",
            {"id": risk["id"], "aid": assessment_id, "org": org, "title": risk.get("title") or "Untitled risk",
             "description": risk.get("description") or "", "severity": _severity(risk.get("severity")),
             "probability": float(risk.get("probability", 0.5)), "impact": float(risk.get("impact_score", 5.0)),
             "entities": [str(e) for e in risk.get("affected_entities") or []],
             "category": risk.get("risk_category") or "", "detected": _ts(risk.get("detected_at")),
             "predicted": None if risk.get("predicted_occurrence") is None else str(risk.get("predicted_occurrence")),
             "sources": [str(s) for s in risk.get("data_sources") or []],
             "status": risk.get("status") or "open", "owner": risk.get("owner"),
             "details": json.dumps(details, default=str)})

    async def fail_task(self, org: str, task_id: str, error: Optional[str] = None) -> None:
        await self._exec(org, [("UPDATE risk_assessments SET status = 'failed', error_message = :err WHERE task_id = :t",
                                {"t": task_id, "err": error})])

    def _task_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": row["status"], "organization_id": str(row["organization_id"]),
                "started_at": _iso(row["started_at"]), "completed_at": _iso(row["completed_at"]),
                "error": row["error_message"], "request": row["request_payload"], "result": row["result"]}

    async def get_task(self, org: str, task_id: str) -> Optional[Dict[str, Any]]:
        rows = await self._all(org, "SELECT * FROM risk_assessments WHERE task_id = :t", {"t": task_id})
        return self._task_row(rows[0]) if rows else None

    async def list_tasks(self, org: str, status: Optional[str] = None) -> List[Tuple[str, Dict[str, Any]]]:
        rows = await self._all(org, "SELECT * FROM risk_assessments WHERE (CAST(:s AS text) IS NULL OR status::text = :s) "
                                    "ORDER BY created_at", {"s": status})
        return [(r["task_id"], self._task_row(r)) for r in rows]

    async def refresh_candidates(self) -> Dict[str, List[Dict[str, Any]]]:
        orgs = await self._all(None, "SELECT id FROM organizations")
        by_org: Dict[str, List[Dict[str, Any]]] = {}
        for o in orgs:
            org = str(o["id"])
            seen = set()
            for _, task in await self.list_tasks(org, "completed"):
                for entity in (task.get("request") or {}).get("entities", []):
                    eid = entity.get("id", "")
                    if eid and eid not in seen:
                        by_org.setdefault(org, []).append(entity)
                        seen.add(eid)
        return by_org

    # --- risks --------------------------------------------------------------
    def _risk_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        details = row.pop("details", None) or {}
        row.pop("assessment_id", None)
        row.pop("created_at", None)
        row.pop("updated_at", None)
        out = _jsonable(row)
        out["severity"] = str(row["severity"])
        out["affected_entities"] = list(row.get("affected_entities") or [])
        out["data_sources"] = list(row.get("data_sources") or [])
        return {**details, **out}

    async def assessment_risks(self, org: str) -> List[Dict[str, Any]]:
        rows = await self._all(org, "SELECT * FROM risks WHERE assessment_id IS NOT NULL ORDER BY created_at")
        return [self._risk_row(r) for r in rows]

    async def list_risks(self, org: str, severity: Optional[str] = None,
                         limit: Optional[int] = None, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
        where = "WHERE (CAST(:sev AS text) IS NULL OR severity::text = :sev)"
        params = {"sev": severity, "limit": limit, "offset": offset}
        rows = await self._all(org, f"SELECT * FROM risks {where} ORDER BY (assessment_id IS NOT NULL), created_at "
                                    "LIMIT :limit OFFSET :offset", params)
        total = (await self._all(org, f"SELECT count(*) AS n FROM risks {where}", params))[0]["n"]
        return [self._risk_row(r) for r in rows], total

    async def get_risk(self, org: str, risk_id: str) -> Optional[Dict[str, Any]]:
        if not _is_uuid(risk_id):
            return None
        rows = await self._all(org, "SELECT * FROM risks WHERE id = CAST(:id AS uuid)", {"id": risk_id})
        return self._risk_row(rows[0]) if rows else None

    async def create_risk(self, org: str, risk: Dict[str, Any]) -> Dict[str, Any]:
        await self._ensure_org(org)
        await self._exec(org, [self._insert_risk_sql(org, risk, None)])
        return await self.get_risk(org, risk["id"])

    async def update_risk(self, org: str, risk_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        current = await self.get_risk(org, risk_id)
        if current is None:
            return None
        merged = {**current, **{k: v for k, v in updates.items() if k not in ("id", "organization_id")}}
        details = {k: v for k, v in merged.items() if k not in _RISK_COLUMNS and k not in ("id", "organization_id")}
        await self._exec(org, [(
            "UPDATE risks SET title = :title, description = :description, severity = CAST(:severity AS risk_severity), "
            "probability = :probability, impact_score = :impact, affected_entities = :entities, risk_category = :category, "
            "predicted_occurrence = :predicted, data_sources = :sources, status = :status, owner = :owner, "
            "details = CAST(:details AS jsonb), updated_at = now() WHERE id = CAST(:id AS uuid)",
            {"id": risk_id, "title": merged.get("title") or "Untitled risk", "description": merged.get("description") or "",
             "severity": _severity(merged.get("severity")), "probability": float(merged.get("probability", 0.5)),
             "impact": float(merged.get("impact_score", 5.0)),
             "entities": [str(e) for e in merged.get("affected_entities") or []],
             "category": merged.get("risk_category") or "",
             "predicted": None if merged.get("predicted_occurrence") is None else str(merged["predicted_occurrence"]),
             "sources": [str(s) for s in merged.get("data_sources") or []], "status": merged.get("status") or "open",
             "owner": merged.get("owner"), "details": json.dumps(details, default=str)})])
        return await self.get_risk(org, risk_id)

    async def risk_history(self, org: str, limit: int) -> Tuple[List[Dict[str, Any]], int]:
        rows = await self._all(org, "SELECT r.*, a.task_id AS _task, a.completed_at AS _completed FROM risks r "
                                    "JOIN risk_assessments a ON a.id = r.assessment_id ORDER BY r.detected_at DESC")
        history = []
        for row in rows:
            task, completed = row.pop("_task"), row.pop("_completed")
            history.append({**self._risk_row(row), "assessment_task_id": task, "assessment_completed_at": _iso(completed)})
        return history[:limit], len(history)

    async def recommendations_for_risk(self, org: str, risk_id: str) -> List[Dict[str, Any]]:
        if not _is_uuid(risk_id):
            return []
        rows = await self._all(org, "SELECT * FROM recommendations WHERE risk_id = CAST(:id AS uuid) ORDER BY created_at",
                               {"id": risk_id})
        out = []
        for row in rows:
            details = row.pop("details", None) or {}
            row.pop("assessment_id", None)
            item = _jsonable(row)
            item["resources_required"] = list(row.get("resources_required") or [])
            item.update({k: v for k, v in details.items() if k != "risk_ref"})
            out.append(item)
        return out

    # --- suppliers ----------------------------------------------------------
    def _supplier_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        extra = row.pop("metadata", None) or {}
        for key in ("created_at", "updated_at", "last_assessment_at", "composite_risk_score",
                    "risk_dimensions_summary", "parent_supplier_id"):
            row.pop(key, None)
        return {**extra, **_jsonable(row)}

    async def list_suppliers(self, org: str, risk_tier: Optional[str] = None,
                             limit: Optional[int] = None) -> Tuple[List[Dict[str, Any]], int]:
        where = "WHERE (CAST(:tier AS text) IS NULL OR risk_tier = :tier)"
        params = {"tier": risk_tier, "limit": limit}
        rows = await self._all(org, f"SELECT * FROM suppliers {where} ORDER BY created_at, supplier_code LIMIT :limit", params)
        total = (await self._all(org, f"SELECT count(*) AS n FROM suppliers {where}", params))[0]["n"]
        return [self._supplier_row(r) for r in rows], total

    async def get_supplier(self, org: str, supplier_id: str) -> Optional[Dict[str, Any]]:
        if not _is_uuid(supplier_id):
            return None
        rows = await self._all(org, "SELECT * FROM suppliers WHERE id = CAST(:id AS uuid)", {"id": supplier_id})
        return self._supplier_row(rows[0]) if rows else None

    def _supplier_params(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "supplier_code": str(data.get("supplier_code") or f"SUP-{uuid.uuid4().hex[:8].upper()}"),
            "name": data.get("name") or "Unnamed supplier",
            "supplier_type": data.get("supplier_type") or "general",
            "country_code": (data.get("country_code") or None) and str(data["country_code"])[:3],
            "region": data.get("region"),
            "risk_score": float(data.get("risk_score", 50.0) or 50.0),
            "risk_tier": data.get("risk_tier") or "medium",
            "contact_name": data.get("contact_name"),
            "contact_email": data.get("contact_email"),
            "is_active": bool(data.get("is_active", True)),
            "tier_level": int(data.get("tier_level", 1) or 1),
            "metadata": json.dumps({k: v for k, v in data.items()
                                    if k not in _SUPPLIER_COLUMNS and k not in ("id", "organization_id")}, default=str),
        }

    async def create_supplier(self, org: str, supplier: Dict[str, Any], supplier_id: Optional[str] = None) -> Dict[str, Any]:
        await self._ensure_org(org)
        sid = supplier_id or str(uuid.uuid4())
        params = {**self._supplier_params(supplier), "id": sid, "org": org}
        await self._exec(org, [(
            "INSERT INTO suppliers (id, organization_id, supplier_code, name, supplier_type, country_code, region, "
            "risk_score, risk_tier, contact_name, contact_email, is_active, tier_level, metadata) VALUES "
            "(CAST(:id AS uuid), CAST(:org AS uuid), :supplier_code, :name, :supplier_type, :country_code, :region, "
            ":risk_score, :risk_tier, :contact_name, :contact_email, :is_active, :tier_level, CAST(:metadata AS json))",
            params)])
        return await self.get_supplier(org, sid)

    async def update_supplier(self, org: str, supplier_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        current = await self.get_supplier(org, supplier_id)
        if current is None:
            return None
        merged = {**current, **{k: v for k, v in updates.items() if k not in ("id", "organization_id")}}
        params = {**self._supplier_params(merged), "id": supplier_id}
        await self._exec(org, [(
            "UPDATE suppliers SET supplier_code = :supplier_code, name = :name, supplier_type = :supplier_type, "
            "country_code = :country_code, region = :region, risk_score = :risk_score, risk_tier = :risk_tier, "
            "contact_name = :contact_name, contact_email = :contact_email, is_active = :is_active, "
            "tier_level = :tier_level, metadata = CAST(:metadata AS json), updated_at = now() "
            "WHERE id = CAST(:id AS uuid)", params)])
        return await self.get_supplier(org, supplier_id)

    async def write_suppliers(self, org: str, creates: List[Dict[str, Any]],
                              updates: List[Tuple[str, Dict[str, Any]]]) -> int:
        """Create and update suppliers in one transaction: all of them, or none."""
        from sqlalchemy import text
        if creates:
            await self._ensure_org(org)
        async with self._tx(org) as conn:
            for sid, fields in updates:
                rows = [dict(r._mapping) for r in await conn.execute(
                    text("SELECT * FROM suppliers WHERE id = CAST(:id AS uuid) FOR UPDATE"), {"id": sid})]
                if not rows:
                    raise KeyError("supplier not found")
                current = self._supplier_row(rows[0])
                merged = {**current, **{k: v for k, v in fields.items() if k not in ("id", "organization_id")}}
                await conn.execute(text(
                    "UPDATE suppliers SET supplier_code = :supplier_code, name = :name, supplier_type = :supplier_type, "
                    "country_code = :country_code, region = :region, risk_score = :risk_score, risk_tier = :risk_tier, "
                    "contact_name = :contact_name, contact_email = :contact_email, is_active = :is_active, "
                    "tier_level = :tier_level, metadata = CAST(:metadata AS json), updated_at = now() "
                    "WHERE id = CAST(:id AS uuid)"), {**self._supplier_params(merged), "id": sid})
            for supplier in creates:
                await conn.execute(text(
                    "INSERT INTO suppliers (id, organization_id, supplier_code, name, supplier_type, country_code, region, "
                    "risk_score, risk_tier, contact_name, contact_email, is_active, tier_level, metadata) VALUES "
                    "(CAST(:id AS uuid), CAST(:org AS uuid), :supplier_code, :name, :supplier_type, :country_code, :region, "
                    ":risk_score, :risk_tier, :contact_name, :contact_email, :is_active, :tier_level, CAST(:metadata AS json))"),
                    {**self._supplier_params(supplier), "id": str(uuid.uuid4()), "org": org})
        return len(creates) + len(updates)

    # --- alerts -------------------------------------------------------------
    async def add_alerts(self, org: str, alerts: List[Dict[str, Any]]) -> None:
        if not alerts:
            return
        await self._ensure_org(org)
        known = {"id", "organization_id", "risk_id", "alert_type", "severity", "title", "description", "status", "created_at"}
        await self._exec(org, [(
            "INSERT INTO alerts (id, organization_id, risk_id, alert_type, severity, title, description, status, metadata, created_at) "
            "VALUES (CAST(:id AS uuid), CAST(:org AS uuid), CAST(:risk_id AS uuid), :atype, :severity, :title, :description, "
            ":status, CAST(:meta AS json), COALESCE(:created, now()))",
            {"id": a["id"], "org": org, "risk_id": a.get("risk_id") if _is_uuid(a.get("risk_id")) else None,
             "atype": a.get("alert_type", "risk_detected"), "severity": a.get("severity", "medium"),
             "title": a.get("title", ""), "description": a.get("description", ""), "status": a.get("status", "active"),
             "created": _ts(a.get("created_at")),
             "meta": json.dumps({**(a.get("metadata") or {}), **{k: v for k, v in a.items() if k not in known | {"metadata"}}},
                                default=str)}) for a in alerts])

    def _alert_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        out = _jsonable(row)
        for key in ("acknowledged_by", "resolved_at"):
            if out.get(key) is None:
                out.pop(key, None)
        return out

    async def list_alerts(self, org: str, status: Optional[str] = None, severity: Optional[str] = None,
                          limit: int = 50) -> Tuple[List[Dict[str, Any]], int]:
        where = "WHERE (CAST(:st AS text) IS NULL OR status = :st) AND (CAST(:sev AS text) IS NULL OR severity = :sev)"
        params = {"st": status, "sev": severity, "limit": limit}
        rows = await self._all(org, f"SELECT * FROM alerts {where} ORDER BY created_at LIMIT :limit", params)
        total = (await self._all(org, f"SELECT count(*) AS n FROM alerts {where}", params))[0]["n"]
        return [self._alert_row(r) for r in rows], total

    async def acknowledge_alert(self, org: str, alert_id: str) -> Optional[Dict[str, Any]]:
        if not _is_uuid(alert_id):
            return None
        rows = await self._all(org, "UPDATE alerts SET status = 'acknowledged', acknowledged_at = now() "
                                    "WHERE id = CAST(:id AS uuid) RETURNING *", {"id": alert_id})
        return self._alert_row(rows[0]) if rows else None

    # --- events -------------------------------------------------------------
    def _event_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        extra = row.pop("metadata", None) or {}
        return {**extra, **_jsonable(row)}

    async def create_event(self, org: str, event: Dict[str, Any]) -> Dict[str, Any]:
        await self._ensure_org(org)
        extra = {k: v for k, v in event.items() if k not in _EVENT_COLUMNS and k not in ("id", "organization_id")}
        await self._exec(org, [(
            "INSERT INTO risk_events (id, organization_id, event_type, title, description, severity, affected_region, "
            "location_lat, location_lng, source_url, status, detected_at, metadata) VALUES (CAST(:id AS uuid), "
            "CAST(:org AS uuid), :etype, :title, :description, :severity, :region, :lat, :lng, :url, :status, "
            "COALESCE(:detected, now()), CAST(:meta AS json))",
            {"id": event["id"], "org": org, "etype": str(event.get("event_type") or "other")[:50],
             "title": event.get("title") or "Untitled event", "description": event.get("description") or "",
             "severity": event.get("severity") or "medium", "region": event.get("affected_region"),
             "lat": event.get("location_lat"), "lng": event.get("location_lng"), "url": event.get("source_url"),
             "status": event.get("status") or "active", "detected": _ts(event.get("detected_at")),
             "meta": json.dumps(extra, default=str)})])
        rows = await self._all(org, "SELECT * FROM risk_events WHERE id = CAST(:id AS uuid)", {"id": event["id"]})
        return self._event_row(rows[0])

    async def list_events(self, org: str, limit: int = 50) -> Tuple[List[Dict[str, Any]], int]:
        rows = await self._all(org, "SELECT * FROM risk_events ORDER BY detected_at DESC LIMIT :limit", {"limit": limit})
        total = (await self._all(org, "SELECT count(*) AS n FROM risk_events"))[0]["n"]
        return [self._event_row(r) for r in rows], total

    async def add_impacts(self, org: str, impacts: List[Dict[str, Any]]) -> None:
        if not impacts:
            return
        known = {"id", "event_id", "impacted_entity_type", "impacted_entity_id", "impact_severity",
                 "estimated_disruption_days", "estimated_financial_impact", "impact_path", "tier_distance"}
        await self._exec(org, [(
            "INSERT INTO event_impacts (id, event_id, impacted_entity_type, impacted_entity_id, impact_severity, "
            "estimated_disruption_days, estimated_financial_impact, impact_path, tier_distance, details) VALUES "
            "(CAST(:id AS uuid), CAST(:event AS uuid), :etype, CAST(:entity AS uuid), :severity, :days, :money, "
            "CAST(:path AS json), :tier, CAST(:details AS jsonb))",
            {"id": i["id"], "event": i["event_id"], "etype": i.get("impacted_entity_type", "supplier"),
             "entity": i["impacted_entity_id"], "severity": i.get("impact_severity", "medium"),
             "days": i.get("estimated_disruption_days"), "money": i.get("estimated_financial_impact"),
             "path": json.dumps(i.get("impact_path", [])), "tier": i.get("tier_distance", 0),
             "details": json.dumps({k: v for k, v in i.items() if k not in known and k != "organization_id"}, default=str)})
            for i in impacts])

    async def event_impacts(self, org: str, event_id: str) -> List[Dict[str, Any]]:
        if not _is_uuid(event_id):
            return []
        rows = await self._all(org, "SELECT * FROM event_impacts WHERE event_id = CAST(:id AS uuid) ORDER BY tier_distance",
                               {"id": event_id})
        out = []
        for row in rows:
            details = row.pop("details", None) or {}
            row.pop("created_at", None)
            out.append({**details, **_jsonable(row), "organization_id": org})
        return out

    # --- public signals (no tenant: public records, no RLS) -----------------
    _SIGNAL_FIELDS = ("source", "external_id", "signal_type", "title", "summary", "severity", "entity_names",
                      "entity_keys", "country_codes", "occurred_at", "published_at", "updated_at", "url")

    @staticmethod
    def _signal_row(row: Dict[str, Any]) -> Dict[str, Any]:
        for k in ("search_doc", "embedding", "embedding_text_hash"):
            row.pop(k, None)
        out = _jsonable(row)
        for k in ("occurred_at", "published_at", "updated_at"):
            if isinstance(out.get(k), date):
                out[k] = out[k].isoformat()
        for k in ("entity_names", "entity_keys", "country_codes"):
            out[k] = list(out.get(k) or [])
        if isinstance(out.get("raw"), str):  # asyncpg returns jsonb as text
            out["raw"] = json.loads(out["raw"])
        return out

    async def upsert_signals(self, signals: List[Dict[str, Any]]) -> int:
        from sqlalchemy import text
        day = _day
        new = 0
        async with self._tx(None) as conn:
            for sig in signals:
                row = {**{k: sig.get(k) for k in self._SIGNAL_FIELDS},
                       "summary": sig.get("summary") or "",
                       "entity_names": list(sig.get("entity_names") or []),
                       "entity_keys": list(sig.get("entity_keys") or []),
                       "country_codes": list(sig.get("country_codes") or []),
                       "occurred_at": day(sig.get("occurred_at")), "published_at": day(sig["published_at"]),
                       "updated_at": day(sig.get("updated_at")), "raw": json.dumps(sig.get("raw") or {}, default=str)}
                result = await conn.execute(text(
                    "INSERT INTO public_signals (source, external_id, signal_type, title, summary, severity, entity_names, "
                    "entity_keys, country_codes, occurred_at, published_at, updated_at, url, raw) VALUES (:source, "
                    ":external_id, :signal_type, :title, :summary, :severity, :entity_names, :entity_keys, :country_codes, "
                    ":occurred_at, :published_at, :updated_at, :url, CAST(:raw AS jsonb)) "
                    "ON CONFLICT (source, external_id) DO UPDATE SET signal_type = EXCLUDED.signal_type, "
                    "title = EXCLUDED.title, summary = EXCLUDED.summary, severity = EXCLUDED.severity, "
                    "entity_names = EXCLUDED.entity_names, entity_keys = EXCLUDED.entity_keys, "
                    "country_codes = EXCLUDED.country_codes, occurred_at = EXCLUDED.occurred_at, "
                    "published_at = EXCLUDED.published_at, updated_at = EXCLUDED.updated_at, url = EXCLUDED.url, "
                    "raw = EXCLUDED.raw, last_seen_at = now(), delisted_at = NULL, "
                    # A changed text invalidates its embedding (it is re-embedded later).
                    "embedding = CASE WHEN md5(EXCLUDED.title || chr(10) || EXCLUDED.summary) "
                    "  = public_signals.embedding_text_hash THEN public_signals.embedding END, "
                    "embedding_model = CASE WHEN md5(EXCLUDED.title || chr(10) || EXCLUDED.summary) "
                    "  = public_signals.embedding_text_hash THEN public_signals.embedding_model END, "
                    "embedding_text_hash = CASE WHEN md5(EXCLUDED.title || chr(10) || EXCLUDED.summary) "
                    "  = public_signals.embedding_text_hash THEN public_signals.embedding_text_hash END "
                    "RETURNING (xmax = 0) AS inserted"), row)
                new += int(bool(result.scalar()))
        return new

    async def list_signals(self, source: Optional[str] = None, since: Optional[str] = None,
                           limit: int = 50) -> Tuple[List[Dict[str, Any]], int]:
        where = ("WHERE delisted_at IS NULL AND (CAST(:source AS text) IS NULL OR source = :source) "
                 "AND (CAST(:since AS date) IS NULL OR COALESCE(updated_at, published_at) >= CAST(:since AS date))")
        params = {"source": source, "since": _day(since), "limit": limit}
        rows = await self._all(None, f"SELECT * FROM public_signals {where} "
                                     f"ORDER BY COALESCE(updated_at, published_at) DESC, external_id DESC LIMIT :limit", params)
        total = (await self._all(None, f"SELECT count(*) AS n FROM public_signals {where}", params))[0]["n"]
        return [self._signal_row(r) for r in rows], total

    async def signal_candidates(self, keys: List[str], countries: List[str], since: Optional[str] = None,
                                limit: int = 2000) -> List[Dict[str, Any]]:
        rows = await self._all(None, (
            "SELECT * FROM public_signals WHERE delisted_at IS NULL AND (CAST(:since AS date) IS NULL "
            "OR COALESCE(updated_at, published_at) >= CAST(:since AS date)) "
            "AND (entity_keys && CAST(:keys AS text[]) "
            "OR (signal_type = 'disaster' AND country_codes && CAST(:countries AS varchar(3)[]))) "
            "ORDER BY COALESCE(updated_at, published_at) DESC LIMIT :limit"),
            {"keys": list(keys), "countries": list(countries), "since": _day(since), "limit": limit})
        return [self._signal_row(r) for r in rows]

    async def search_signals(self, query_terms: List[str], keys: Optional[List[str]] = None,
                             limit: int = 50) -> List[Dict[str, Any]]:
        """Full-text search: active signals matching any term, ranked by ts_rank_cd (titles
        weighted above summaries). websearch_to_tsquery never raises on user text."""
        terms = [t.replace('"', " ").strip() for t in query_terms if t and t.strip()]
        if not terms:
            return []
        query = " or ".join(f'"{t}"' if " " in t else t for t in terms)
        rows = await self._all(None, (
            "SELECT s.*, ts_rank_cd(s.search_doc, q) AS rank "
            "FROM public_signals s, websearch_to_tsquery('english', :q) q "
            "WHERE s.delisted_at IS NULL AND s.search_doc @@ q "
            "AND (CAST(:keys AS text[]) IS NULL OR s.entity_keys && CAST(:keys AS text[])) "
            "ORDER BY rank DESC, COALESCE(s.updated_at, s.published_at) DESC LIMIT :limit"),
            {"q": query, "keys": list(keys) if keys is not None else None, "limit": limit})
        return [self._signal_row(r) for r in rows]

    async def signals_needing_embedding(self, model: str, limit: int = 500) -> List[Dict[str, Any]]:
        rows = await self._all(None, (
            "SELECT id, title, summary FROM public_signals WHERE delisted_at IS NULL AND ("
            "embedding IS NULL OR embedding_model IS DISTINCT FROM :model "
            "OR embedding_text_hash IS DISTINCT FROM md5(title || chr(10) || summary)) "
            "ORDER BY COALESCE(updated_at, published_at) DESC LIMIT :limit"), {"model": model, "limit": limit})
        return [{"id": str(r["id"]), "title": r["title"], "summary": r["summary"] or ""} for r in rows]

    async def set_embeddings(self, items: List[Tuple[str, str, List[float]]], model: str) -> int:
        """items: (signal id, hash of the text embedded, vector). A row whose text changed
        since it was read keeps no vector: it is picked up again on the next pass."""
        from sqlalchemy import text
        written = 0
        async with self._tx(None) as conn:
            for signal_id, digest, vector in items:
                result = await conn.execute(text(
                    "UPDATE public_signals SET embedding = CAST(:v AS vector), embedding_model = :m, "
                    "embedding_text_hash = :h WHERE id = CAST(:id AS uuid) "
                    "AND md5(title || chr(10) || summary) = :h"),
                    {"v": _vector_literal(vector), "m": model, "h": digest, "id": signal_id})
                written += result.rowcount or 0
        return written

    async def vector_search(self, vector: List[float], model: str, keys: List[str],
                            limit: int = 50) -> List[Dict[str, Any]]:
        """Nearest records among one supplier's. The supplier's rows are taken first
        (MATERIALIZED) and compared exactly: filtering after an approximate index search
        would often leave a small supplier with no results at all."""
        rows = await self._all(None, (
            "WITH scoped AS MATERIALIZED (SELECT * FROM public_signals WHERE delisted_at IS NULL "
            "AND embedding IS NOT NULL AND embedding_model = :m "
            "AND embedding_text_hash = md5(title || chr(10) || summary) "
            "AND entity_keys && CAST(:keys AS text[])) "
            "SELECT *, embedding <=> CAST(:v AS vector) AS distance FROM scoped ORDER BY distance LIMIT :limit"),
            {"v": _vector_literal(vector), "m": model, "keys": list(keys), "limit": limit})
        return [self._signal_row(r) for r in rows]

    async def embedding_coverage(self, model: str) -> Dict[str, int]:
        [row] = await self._all(None, (
            "SELECT count(*) FILTER (WHERE embedding IS NOT NULL AND embedding_model = :m "
            "AND embedding_text_hash = md5(title || chr(10) || summary)) AS embedded, count(*) AS total "
            "FROM public_signals WHERE delisted_at IS NULL"), {"m": model})
        return {"embedded": int(row["embedded"]), "total": int(row["total"])}

    async def retire_unseen(self, source: str, seen_ids: Iterable[str]) -> int:
        """Mark this source's active signals that a full run did not see as delisted."""
        rows = await self._all(None, (
            "UPDATE public_signals SET delisted_at = now() WHERE source = :source AND delisted_at IS NULL "
            "AND NOT (external_id = ANY(CAST(:ids AS text[]))) RETURNING id"),
            {"source": source, "ids": list(seen_ids)})
        return len(rows)

    async def record_source_run(self, source: str, status: str, error: Optional[str], seen: int, new: int) -> None:
        await self._exec(None, [(
            "INSERT INTO public_sources (source, status, error, signals_seen, signals_new, last_run_at, last_success_at) "
            "VALUES (:source, :status, :error, :seen, :new, now(), CASE WHEN CAST(:ok AS boolean) THEN now() END) "
            "ON CONFLICT (source) DO UPDATE SET status = EXCLUDED.status, error = EXCLUDED.error, "
            "signals_seen = EXCLUDED.signals_seen, signals_new = EXCLUDED.signals_new, last_run_at = now(), "
            "last_success_at = COALESCE(EXCLUDED.last_success_at, public_sources.last_success_at)",
            {"source": source, "status": status, "error": error, "seen": seen, "new": new, "ok": status == "ok"})])

    async def list_source_runs(self) -> Dict[str, Dict[str, Any]]:
        return {r["source"]: _jsonable(r) for r in await self._all(None, "SELECT * FROM public_sources")}

    # --- accounts -----------------------------------------------------------
    @staticmethod
    def _account(row: Dict[str, Any]) -> Dict[str, Any]:
        out = _jsonable(row)
        out["roles"] = list(out.get("roles") or [])
        return out

    async def find_login_user(self, email: str) -> Optional[Dict[str, Any]]:
        rows = await self._all(None, "SELECT * FROM scirm_login_lookup(:e)", {"e": (email or "").lower()})
        return await _open_mfa_secret(self, self._account(rows[0])) if rows else None

    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        if not _is_uuid(user_id):
            return None
        rows = await self._all(None, "SELECT * FROM scirm_user_by_id(CAST(:i AS uuid))", {"i": str(user_id)})
        return await _open_mfa_secret(self, self._account(rows[0])) if rows else None

    async def create_organization(self, name: str, industry: str = "general") -> str:
        org = str(uuid.uuid4())
        await self._exec(org, [("INSERT INTO organizations (id, name, industry) VALUES (CAST(:id AS uuid), :n, :i)",
                                {"id": org, "n": name, "i": industry})])
        return org

    _MEMBER_COLUMNS = "id, email, name, roles::text[] AS roles, is_active, mfa_enabled, created_at, last_login_at"

    async def create_user(self, org: str, email: str, name: str, hashed_password: str,
                          roles: List[str]) -> Dict[str, Any]:
        if await self.find_login_user(email):
            raise EmailExists(email)
        from sqlalchemy.exc import IntegrityError
        try:
            rows = await self._all(org, (
                "INSERT INTO users (email, name, hashed_password, roles, organization_id, is_active) "
                "VALUES (:e, :n, :h, CAST(:r AS varchar[]), CAST(:org AS uuid), true) "
                f"RETURNING {self._MEMBER_COLUMNS}"),
                {"e": email.lower(), "n": name, "h": hashed_password, "r": list(roles), "org": org})
        except IntegrityError:
            raise EmailExists(email)
        return self._account(rows[0])

    async def list_members(self, org: str) -> List[Dict[str, Any]]:
        rows = await self._all(org, f"SELECT {self._MEMBER_COLUMNS} FROM users ORDER BY created_at, email")
        return [self._account(r) for r in rows]

    async def update_member(self, org: str, user_id: str, roles: Optional[List[str]] = None,
                            is_active: Optional[bool] = None) -> Optional[Dict[str, Any]]:
        if not _is_uuid(user_id):
            return None
        from sqlalchemy import text
        async with self._tx(org) as conn:
            # Lock the organization's active admins so two admins demoting each other at
            # the same moment cannot leave it with none.
            admins = [dict(r._mapping) for r in await conn.execute(text(
                "SELECT id FROM users WHERE is_active AND 'admin' = ANY(roles) FOR UPDATE"))]
            current = [dict(r._mapping) for r in await conn.execute(text(
                "SELECT roles::text[] AS roles, is_active FROM users WHERE id = CAST(:i AS uuid) FOR UPDATE"),
                {"i": user_id})]
            if not current:
                return None
            old_roles = list(current[0]["roles"] or [])
            new_roles = list(roles) if roles is not None else old_roles
            new_active = current[0]["is_active"] if is_active is None else bool(is_active)
            # Only a change that takes away an active admin can leave the organization without one.
            removes_admin = current[0]["is_active"] and "admin" in old_roles and not (new_active and "admin" in new_roles)
            others = [a for a in admins if str(a["id"]) != str(user_id)]
            if removes_admin and not others:
                raise LastAdmin(org)
            result = await conn.execute(text(
                "UPDATE users SET roles = CAST(:r AS varchar[]), is_active = :a, updated_at = now() "
                f"WHERE id = CAST(:i AS uuid) RETURNING {self._MEMBER_COLUMNS}"),
                {"r": new_roles, "a": new_active, "i": user_id})
            row = result.first()
            return self._account(dict(row._mapping)) if row else None

    async def create_invitation(self, org: str, email: str, roles: List[str], invited_by: Optional[str],
                                ttl_hours: int = INVITATION_TTL_HOURS) -> Tuple[Dict[str, Any], str]:
        if await self.find_login_user(email):
            raise EmailExists(email)
        token, digest = new_invitation_token()
        rows = await self._all(org, (
            "INSERT INTO invitations (organization_id, email, roles, token_hash, invited_by, expires_at) "
            "VALUES (CAST(:org AS uuid), :e, CAST(:r AS text[]), :h, CAST(:by AS uuid), "
            "now() + make_interval(hours => :ttl)) "
            "RETURNING id, email, roles, invited_by, created_at, expires_at, accepted_at, revoked_at, "
            f"{_INVITATION_STATUS_SQL}"),
            {"org": org, "e": email.lower(), "r": list(roles), "h": digest,
             "by": invited_by if _is_uuid(invited_by) else None, "ttl": int(ttl_hours)})
        return self._invitation_row(rows[0]), token

    @staticmethod
    def _invitation_row(row: Dict[str, Any]) -> Dict[str, Any]:
        out = _jsonable(row)
        out["roles"] = list(out.get("roles") or [])
        for k in ("created_at", "expires_at", "accepted_at", "revoked_at"):
            if out.get(k) is not None and not isinstance(out[k], str):
                out[k] = out[k].isoformat()
        return out

    async def list_invitations(self, org: str) -> List[Dict[str, Any]]:
        rows = await self._all(org, (
            "SELECT id, email, roles, invited_by, created_at, expires_at, accepted_at, revoked_at, "
            f"{_INVITATION_STATUS_SQL} FROM invitations ORDER BY created_at DESC"))
        return [self._invitation_row(r) for r in rows]

    async def revoke_invitation(self, org: str, invitation_id: str) -> bool:
        if not _is_uuid(invitation_id):
            return False
        rows = await self._all(org, (
            "UPDATE invitations SET revoked_at = now() WHERE id = CAST(:i AS uuid) "
            "AND accepted_at IS NULL AND revoked_at IS NULL RETURNING id"), {"i": invitation_id})
        return bool(rows)

    async def lookup_invitation(self, token: str) -> Optional[Dict[str, Any]]:
        rows = await self._all(None, "SELECT * FROM scirm_invitation_lookup(:h)", {"h": invitation_hash(token)})
        return self._account(rows[0]) if rows else None

    async def accept_invitation(self, token: str, name: str, hashed_password: str) -> Optional[Dict[str, Any]]:
        from sqlalchemy.exc import IntegrityError
        try:
            rows = await self._all(None, "SELECT * FROM scirm_accept_invitation(:h, :n, :p)",
                                   {"h": invitation_hash(token), "n": name, "p": hashed_password})
        except IntegrityError:
            raise EmailExists("")
        return self._account(rows[0]) if rows else None

    async def set_mfa_secret(self, org: str, user_id: str, secret: Optional[str]) -> bool:
        if not _is_uuid(user_id):
            return False
        rows = await self._all(org, (
            "UPDATE users SET mfa_secret = :s, mfa_enabled = :on, updated_at = now() "
            "WHERE id = CAST(:i AS uuid) RETURNING id"),
            {"s": secret_box.encrypt(secret, user_id) if secret else None, "on": bool(secret), "i": user_id})
        return bool(rows)

    async def record_login(self, org: str, user_id: str) -> None:
        if _is_uuid(user_id):
            await self._exec(org, [("UPDATE users SET last_login_at = now() WHERE id = CAST(:i AS uuid)",
                                    {"i": user_id})])

    # --- feedback -----------------------------------------------------------
    async def record_feedback(self, org: str, user_id: str, item: Dict[str, Any]) -> Dict[str, Any]:
        await self._ensure_org(org)
        rows = await self._all(org, (
            "INSERT INTO feedback (organization_id, user_id, target_type, target_id, supplier_id, verdict, reason, context) "
            "VALUES (CAST(:org AS uuid), :u, :t, :tid, :sid, :v, :r, CAST(:ctx AS jsonb)) "
            "ON CONFLICT (organization_id, user_id, target_type, target_id) DO UPDATE SET "
            "verdict = EXCLUDED.verdict, reason = EXCLUDED.reason, supplier_id = EXCLUDED.supplier_id, "
            "context = EXCLUDED.context, updated_at = now() "
            "RETURNING target_type, target_id, supplier_id, verdict, reason, updated_at"),
            {"org": org, "u": str(user_id), "t": item["target_type"], "tid": item["target_id"],
             "sid": item.get("supplier_id"), "v": item["verdict"], "r": item.get("reason"),
             "ctx": json.dumps(item.get("context") or {})})
        return _jsonable(rows[0])

    async def my_feedback_for_supplier(self, org: str, user_id: str, supplier_id: str) -> Dict[str, str]:
        rows = await self._all(org, (
            "SELECT target_id, verdict FROM feedback WHERE user_id = :u AND target_type = 'signal_match' "
            "AND supplier_id = :sid"), {"u": str(user_id), "sid": supplier_id})
        return {r["target_id"]: r["verdict"] for r in rows}

    async def feedback_summary(self, org: str, since: Optional[datetime] = None) -> Dict[str, Any]:
        if since is not None and since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        rows = await self._all(org, (
            "SELECT target_type, target_id, verdict, user_id, context FROM feedback "
            "WHERE (CAST(:since AS timestamptz) IS NULL OR updated_at >= CAST(:since AS timestamptz))"),
            {"since": since})
        for r in rows:
            if isinstance(r.get("context"), str):
                r["context"] = json.loads(r["context"])
        return summarize_feedback(rows)

    # --- ERP connections ------------------------------------------------------
    @staticmethod
    async def _erp_row(conn: Any, system: str) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text
        result = await conn.execute(text("SELECT * FROM erp_connections WHERE system = :s"), {"s": system})
        row = result.first()
        return dict(row._mapping) if row else None

    async def get_erp_connection(self, org: str, system: str, with_password: bool = False) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text
        async with self._tx(org) as conn:
            row = await self._erp_row(conn, system)
            if row is None:
                return None
            out = _erp_public(row)
            if with_password:
                password, stale = _erp_open(org, row)
                if stale:  # sealed with the previous key
                    await conn.execute(text("UPDATE erp_connections SET password_enc = :p WHERE id = :i"),
                                       {"p": secret_box.encrypt(password, _erp_bound(system, org, str(row["id"]))),
                                        "i": row["id"]})
                out["password"] = password
            return out

    async def save_erp_connection(self, org: str, system: str, fields: Dict[str, Any], password: Optional[str],
                                  actor: Optional[str] = None) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text
        await self._ensure_org(org)
        async with self._tx(org) as conn:
            row = await self._erp_row(conn, system)
            if row is None and not password:
                return None
            params = {"u": fields.get("base_url"), "c": fields.get("sap_client"), "n": fields.get("username")}
            if row is None:
                connection_id = str(uuid.uuid4())
                result = await conn.execute(text(
                    "INSERT INTO erp_connections (id, organization_id, system, base_url, sap_client, username, "
                    "password_enc, created_by) VALUES (CAST(:i AS uuid), CAST(:org AS uuid), :s, :u, :c, :n, :p, :a) "
                    "RETURNING *"),
                    {**params, "i": connection_id, "org": org, "s": system, "a": actor,
                     "p": secret_box.encrypt(password, _erp_bound(system, org, connection_id))})
            else:
                connection_id = str(row["id"])
                reset = bool(password) or any(row.get(k) != fields.get(k) for k in ("base_url", "sap_client", "username"))
                result = await conn.execute(text(
                    "UPDATE erp_connections SET base_url = :u, sap_client = :c, username = :n, "
                    "password_enc = COALESCE(:p, password_enc), "
                    "last_test = CASE WHEN :reset THEN NULL ELSE last_test END, updated_at = now() "
                    "WHERE id = CAST(:i AS uuid) RETURNING *"),
                    {**params, "i": connection_id, "reset": reset,
                     "p": secret_box.encrypt(password, _erp_bound(system, org, connection_id)) if password else None})
            return _erp_public(dict(result.first()._mapping))

    async def delete_erp_connection(self, org: str, system: str) -> bool:
        rows = await self._all(org, "DELETE FROM erp_connections WHERE system = :s RETURNING id", {"s": system})
        return bool(rows)

    async def record_erp_result(self, org: str, system: str, kind: str, result: Dict[str, Any]) -> None:
        if kind not in ("last_test", "last_import"):
            return
        await self._exec(org, [(
            f"UPDATE erp_connections SET {kind} = CAST(:r AS jsonb) WHERE system = :s",
            {"r": json.dumps({**result, "at": _now()}), "s": system})])

    # --- audit --------------------------------------------------------------
    async def record_audit(self, org: Optional[str], entry: Dict[str, Any]) -> None:
        await self._exec(org, [(
            "INSERT INTO audit_logs (organization_id, user_id, actor_type, actor, action, resource_type, resource_id, "
            "details, ip_address, status_code) VALUES (CAST(:org AS uuid), CAST(:uid AS uuid), :atype, :actor, :action, "
            ":rtype, :rid, CAST(:details AS json), :ip, :status)",
            {"org": org or None, "uid": entry.get("user_id") if _is_uuid(entry.get("user_id")) else None,
             "atype": entry.get("actor_type", "user"), "actor": entry.get("actor"), "action": entry["action"],
             "rtype": entry.get("resource_type", "unknown"), "rid": (entry.get("resource_id") or None) and str(entry["resource_id"])[:64],
             "details": json.dumps(entry.get("details", {}), default=str), "ip": entry.get("ip_address"),
             "status": entry.get("status_code")})])

    async def list_audit(self, org: str, limit: int = 100) -> List[Dict[str, Any]]:
        rows = await self._all(org, "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT :limit", {"limit": limit})
        return [_jsonable(r) for r in rows]

    # --- development seed ---------------------------------------------------
    async def seed_demo(self) -> None:
        """Idempotently create the demo tenants and their suppliers (development only)."""
        for org, name, industry in DEMO_ORGS:
            await self._exec(org, [(
                "INSERT INTO organizations (id, name, industry) VALUES (CAST(:id AS uuid), :name, :industry) "
                "ON CONFLICT (id) DO NOTHING", {"id": org, "name": name, "industry": industry})])
        for supplier in DEMO_SUPPLIERS:
            org = supplier["organization_id"]
            if await self.get_supplier(org, supplier["id"]) is None:
                await self.create_supplier(org, supplier, supplier_id=supplier["id"])


def create_store():
    """Build the store selected by STORE_BACKEND (memory|postgres)."""
    backend = os.getenv("STORE_BACKEND", "memory").lower()
    if backend == "postgres":
        url = os.getenv("DATABASE_URL", "")
        if not url:
            raise RuntimeError("STORE_BACKEND=postgres requires DATABASE_URL")
        return PostgresStore(url)
    if backend != "memory":
        raise RuntimeError(f"Unknown STORE_BACKEND {backend!r}")
    if not _IS_DEV:
        raise RuntimeError(f"STORE_BACKEND=memory loses all data on restart and is not allowed when "
                           f"ENVIRONMENT={_ENVIRONMENT!r}; set STORE_BACKEND=postgres.")
    return MemoryStore()
