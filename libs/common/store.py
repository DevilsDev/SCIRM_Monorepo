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
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

SEVERITIES = ("low", "medium", "high", "critical")

_ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
_IS_DEV = _ENVIRONMENT in {"development", "dev", "local", "test"}


def _activity(signal: Dict[str, Any]) -> str:
    """Date of a signal's latest public activity. For a recall this is its publication;
    for a still-listed shortage, the last FDA update. Feeds and "last 12 months"
    filters use it so an ongoing shortage posted years ago is not hidden. Point-in-time
    logic (the back-test) uses published_at instead."""
    return signal.get("updated_at") or signal["published_at"]


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
        self.signals: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self.source_runs: Dict[str, Dict[str, Any]] = {}

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

    # --- audit --------------------------------------------------------------
    async def record_audit(self, org: Optional[str], entry: Dict[str, Any]) -> None:
        self.audit.append({**entry, "organization_id": org, "created_at": _now()})

    async def list_audit(self, org: str, limit: int = 100) -> List[Dict[str, Any]]:
        return [a for a in reversed(self.audit) if a.get("organization_id") == org][:limit]


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
        row.pop("search_doc", None)
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
                    "raw = EXCLUDED.raw, last_seen_at = now(), delisted_at = NULL "
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
