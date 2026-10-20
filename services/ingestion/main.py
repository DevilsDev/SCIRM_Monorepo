"""
SCIRM Ingestion Service
Collects public supply-chain signals (FDA drug recalls and shortages, GDACS
disaster alerts), stores them, and matches them to a tenant's suppliers.

The service holds public records only. Callers send the suppliers to match, so
no tenant data is stored here. A source that fails is reported as failing; it is
never replaced with sample data.
"""

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from libs.common.monitoring import setup_monitoring
from libs.common.security import setup_cors
from libs.common.store import create_store
from libs.common.tenancy import tenant_org
from libs.common.store import text_hash
from libs.evidence import answer as evidence_answer
from libs.evidence import embeddings as evidence_embeddings
from libs.evidence import retrieval as evidence_retrieval
from libs.intel import matching, scan, scoring, sources

logger = structlog.get_logger()

INGESTION_INTERVAL = int(os.getenv("INGESTION_INTERVAL_MINUTES", "60"))
INGESTION_AUTO = os.getenv("INGESTION_AUTO", "false").lower() == "true"
LOOKBACK_DAYS = int(os.getenv("INGESTION_LOOKBACK_DAYS", "90"))
# A current-list source returning fewer than this share of its previous entries is
# treated as a failed fetch (e.g. FDA changed its page), not as mass delisting.
SNAPSHOT_MIN_RATIO = float(os.getenv("INGESTION_SNAPSHOT_MIN_RATIO", "0.5"))
MATCH_CANDIDATE_LIMIT = int(os.getenv("MATCH_CANDIDATE_LIMIT", "20000"))

store = create_store()
# Replaced in tests with a client on a mock transport.
http_client_factory = sources.http_client
# None means keyword-only retrieval. Tests inject a fake embedder here.
embedder = evidence_embeddings.get_embedder()
EMBED_PER_RUN = int(os.getenv("EMBED_PER_RUN", "5000"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_auto_ingest_loop()) if INGESTION_AUTO else None
    yield
    if task:
        task.cancel()
    await store.close()


app = FastAPI(title="SCIRM Ingestion Service", description="Public supply chain intelligence", version="2.0.0",
              lifespan=lifespan)
setup_cors(app)
setup_monitoring(app, service_name="ingestion")


class IngestResult(BaseModel):
    documents_ingested: int
    sources_queried: List[str]
    sources: Dict[str, Dict[str, Any]]
    timestamp: str


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)
    supplier: Dict[str, Any]
    k: int = Field(8, ge=1, le=20)


class ScanRequest(BaseModel):
    csv: str = Field(..., min_length=1, max_length=1_000_000)
    title: str = Field("Supplier risk scan", max_length=200)
    prepared_for: str = Field("", max_length=200)


class MatchRequest(BaseModel):
    suppliers: List[Dict[str, Any]] = Field(..., max_length=5000)
    since_days: Optional[int] = Field(None, ge=1, le=3650)
    min_confidence: float = Field(0.6, ge=0.0, le=1.0)
    include_exposure: bool = True
    limit_per_supplier: int = Field(50, ge=1, le=500)


@app.get("/health")
async def health():
    return {"status": "healthy", "agent": "ingestion", "sources": list(sources.SOURCES)}


@app.get("/ready")
async def ready():
    return {"status": "ready", "agent": "ingestion"}


async def run_ingestion(only: Optional[List[str]] = None) -> IngestResult:
    async with http_client_factory() as client:
        results = await sources.collect(client, LOOKBACK_DAYS, only=only)
    previous_runs = await store.list_source_runs()
    summary: Dict[str, Dict[str, Any]] = {}
    total_new = 0
    for result in results:
        new = await store.upsert_signals(result.signals) if result.status == "ok" else 0
        total_new += new
        retired = 0
        if result.status == "ok" and result.source in sources.SNAPSHOT_SOURCES:
            # A current list: whatever FDA no longer lists is resolved or lifted. Retire it,
            # unless the list shrank so much that the fetch itself is the likelier fault.
            before = int((previous_runs.get(result.source) or {}).get("signals_seen") or 0)
            if not result.signals or (before and len(result.signals) < before * SNAPSHOT_MIN_RATIO):
                result.status = "error"
                result.error = f"list shrank from {before} to {len(result.signals)} entries; nothing retired"
            else:
                retired = await store.retire_unseen(result.source, [s["external_id"] for s in result.signals])
        await store.record_source_run(result.source, result.status, result.error, len(result.signals), new)
        summary[result.source] = {"status": result.status, "error": result.error,
                                  "signals": len(result.signals), "new": new, "delisted": retired}
        log = logger.info if result.status == "ok" else logger.warning
        log("Source ingested", source=result.source, status=result.status, error=result.error,
            signals=len(result.signals), new=new, delisted=retired)
    await embed_pending()
    return IngestResult(documents_ingested=total_new, sources_queried=[r.source for r in results], sources=summary,
                        timestamp=datetime.now(timezone.utc).isoformat())


async def embed_pending(limit: Optional[int] = None) -> Dict[str, Any]:
    """Embed records that have no current vector for the configured model. A separate
    step: an embedding failure (e.g. throttling) never fails a source's ingestion run."""
    if embedder is None:
        return {"status": "disabled"}
    done = 0
    budget = limit or EMBED_PER_RUN
    try:
        while done < budget:
            pending = await store.signals_needing_embedding(embedder.model_id, limit=min(200, budget - done))
            if not pending:
                break
            texts = [evidence_embeddings.document_text(r) for r in pending]
            vectors = await embedder.embed_documents(texts)
            written = await store.set_embeddings([(r["id"], text_hash(r), v) for r, v in zip(pending, vectors)],
                                                 embedder.model_id)
            done += written
            if len(pending) < 200 or written == 0:  # last batch, or no progress (texts changed meanwhile)
                break
    except Exception as exc:
        logger.warning("Embedding step failed", error=type(exc).__name__, embedded=done)
        return {"status": "error", "error": type(exc).__name__, "embedded": done}
    logger.info("Embedding step", embedded=done)
    return {"status": "ok", "embedded": done}


async def _auto_ingest_loop() -> None:
    while True:
        try:
            await run_ingestion()
        except Exception as exc:  # keep the loop alive; the next run retries
            logger.error("Ingestion run failed", error=type(exc).__name__)
        await asyncio.sleep(INGESTION_INTERVAL * 60)


@app.post("/ingest", response_model=IngestResult)
async def trigger_ingestion(org_id: str = Depends(tenant_org)):
    """Run one ingestion cycle across all sources."""
    return await run_ingestion()


def _match_entry(m: Dict[str, Any]) -> Dict[str, Any]:
    return {**{k: m[k] for k in ("match_type", "confidence", "kind", "matched_on")}, "signal": _as_document(m["signal"])}


def _event_entry(group: List[Dict[str, Any]]) -> Dict[str, Any]:
    """One event: its most severe record, plus every record (product) it covers."""
    entry = _match_entry(group[0])
    if len(group) > 1:
        entry["records"] = [{"id": m["signal"].get("id"), "external_id": m["signal"].get("external_id"),
                             "product": str((m["signal"].get("raw") or {}).get("product_description") or "")[:200],
                             "severity": m["signal"]["severity"], "url": m["signal"].get("url")}
                            for m in group]
    return entry


def _as_document(signal: Dict[str, Any]) -> Dict[str, Any]:
    """A signal in the shape the intelligence feed has always returned, plus provenance."""
    return {
        "id": signal.get("id"),
        "source": signal["source"],
        "source_label": sources.SOURCE_LABELS.get(signal["source"], signal["source"]),
        "signal_type": signal["signal_type"],
        "title": signal["title"],
        "content": signal.get("summary") or "",
        "url": signal.get("url"),
        "severity": signal["severity"],
        "region": ", ".join(signal.get("country_codes") or []) or "Global",
        "entity_names": signal.get("entity_names") or [],
        "country_codes": signal.get("country_codes") or [],
        "published_at": signal.get("published_at"),
        "occurred_at": signal.get("occurred_at"),
        "updated_at": signal.get("updated_at"),
        "ingested_at": signal.get("first_seen_at"),
        "is_demo": False,
    }


@app.get("/documents")
async def list_documents(source: Optional[str] = None, limit: int = 50, since_days: int = 30,
                         org_id: str = Depends(tenant_org)):
    """Public signals with activity in the window (publication, or the last FDA update of a
    still-listed shortage), most recent activity first."""
    since = (datetime.now(timezone.utc).date() - timedelta(days=max(1, since_days))).isoformat()
    signals, total = await store.list_signals(source=source, since=since, limit=max(1, min(limit, 500)))
    return {"documents": [_as_document(s) for s in signals], "total": total}


@app.get("/sources")
async def list_sources(org_id: str = Depends(tenant_org)):
    """Each source with the outcome of its last run (never-run sources are listed as such)."""
    runs = await store.list_source_runs()
    status = {name: {"label": sources.SOURCE_LABELS[name], "status": "never_run", **runs.get(name, {})}
              for name in sources.SOURCES}
    _, total = await store.list_signals(limit=1)
    vectors = ({"status": "disabled"} if embedder is None
               else {"status": "on", "model": embedder.model_id, **await store.embedding_coverage(embedder.model_id)})
    return {"sources": status, "available": list(sources.SOURCES), "total_documents": total, "embeddings": vectors}


def _watch(incidents: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The back-tested Watch flag for a supplier (libs/intel/scoring.watch_from_matches)."""
    return scoring.watch_from_matches(incidents, datetime.now(timezone.utc).date())


@app.post("/match")
async def match_suppliers(request: MatchRequest, org_id: str = Depends(tenant_org)):
    """Public signals that concern the given suppliers.

    Incidents name the supplier; exposures only share its country (e.g. a disaster
    in a country where the supplier operates) and are labelled as such.
    """
    index = matching.supplier_index(request.suppliers)
    since = None
    if request.since_days:
        since = (datetime.now(timezone.utc).date() - timedelta(days=request.since_days)).isoformat()
    countries = index["countries"] if request.include_exposure else []
    candidates = await store.signal_candidates(index["keys"], countries, since=since, limit=MATCH_CANDIDATE_LIMIT)
    matches = matching.match_all(request.suppliers, candidates, min_confidence=0.0)
    out, totals = {}, {}
    for supplier_id, found in matches.items():
        kept = [m for m in found if m["kind"] == "exposure" or m["confidence"] >= request.min_confidence]
        incidents = [m for m in kept if m["kind"] == "incident"]
        exposures = [m for m in kept if m["kind"] == "exposure"]
        # Incidents are counted and listed per event: one FDA recall event is often a dozen
        # recall numbers (one per strength or pack), which would otherwise read as a dozen problems.
        events = matching.group_events(incidents)
        totals[supplier_id] = {"incidents": len(events), "incident_records": len(incidents),
                               "exposures": len(exposures), **_watch(incidents)}
        # The limit applies to each kind, so exposures never crowd out incidents.
        out[supplier_id] = ([_event_entry(group) for group in events[: request.limit_per_supplier]]
                            + [_match_entry(m) for m in exposures[: request.limit_per_supplier]])
    truncated = len(candidates) >= MATCH_CANDIDATE_LIMIT
    if truncated:
        logger.warning("Match candidates truncated", limit=MATCH_CANDIDATE_LIMIT, suppliers=len(request.suppliers))
    # Truncation drops the oldest activity first; callers should say counts may be incomplete.
    return {"matches": out, "totals": totals, "candidates_considered": len(candidates),
            "candidates_truncated": truncated}


@app.post("/evidence/ask")
async def ask(request: AskRequest, org_id: str = Depends(tenant_org)):
    """Answer a question about one supplier from public records, citing each record used.

    The question and supplier come from the caller and are not stored here."""
    supplier = {k: request.supplier.get(k) for k in ("id", "name", "country_code", "aliases")}
    retrieved = await evidence_retrieval.retrieve(store, request.question, supplier, k=request.k, embedder=embedder)
    count = 0 if retrieved["results"] else await evidence_retrieval.supplier_record_count(store, supplier)
    since = (datetime.now(timezone.utc).date() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    return await evidence_answer.compose(request.question, supplier, retrieved, count, coverage_since=since)


@app.post("/scan")
async def scan_suppliers(request: ScanRequest, org_id: str = Depends(tenant_org)):
    """Scan an uploaded supplier list against the public records. The list is processed in
    memory and not stored; the report (data and a self-contained HTML page) is returned."""
    suppliers, warnings = scan.parse_supplier_csv(request.csv)
    if not suppliers:
        raise HTTPException(status_code=400, detail="; ".join(warnings) or "No suppliers found in the file")
    since = (datetime.now(timezone.utc).date() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    report = await scan.run_scan(store, suppliers, coverage=(
        f"FDA recalls and warning letters ingested since {since}; current FDA shortage and import-alert lists"))
    return {"report": report, "warnings": warnings,
            "html": scan.render_html(report, title=request.title, prepared_for=request.prepared_for)}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("INGESTION_SERVICE_PORT", "8008"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
