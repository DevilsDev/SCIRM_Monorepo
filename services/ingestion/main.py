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
from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from libs.common.monitoring import setup_monitoring
from libs.common.security import setup_cors
from libs.common.store import create_store
from libs.common.tenancy import tenant_org
from libs.intel import matching, sources

logger = structlog.get_logger()

INGESTION_INTERVAL = int(os.getenv("INGESTION_INTERVAL_MINUTES", "60"))
INGESTION_AUTO = os.getenv("INGESTION_AUTO", "false").lower() == "true"
LOOKBACK_DAYS = int(os.getenv("INGESTION_LOOKBACK_DAYS", "90"))

store = create_store()
# Replaced in tests with a client on a mock transport.
http_client_factory = sources.http_client


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
    summary: Dict[str, Dict[str, Any]] = {}
    total_new = 0
    for result in results:
        new = await store.upsert_signals(result.signals) if result.status == "ok" else 0
        total_new += new
        await store.record_source_run(result.source, result.status, result.error, len(result.signals), new)
        summary[result.source] = {"status": result.status, "error": result.error,
                                  "signals": len(result.signals), "new": new}
        log = logger.info if result.status == "ok" else logger.warning
        log("Source ingested", source=result.source, status=result.status, error=result.error,
            signals=len(result.signals), new=new)
    return IngestResult(documents_ingested=total_new, sources_queried=[r.source for r in results], sources=summary,
                        timestamp=datetime.now(timezone.utc).isoformat())


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
    """Recent public signals, newest by publication date first."""
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
    return {"sources": status, "available": list(sources.SOURCES), "total_documents": total}


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
    candidates = await store.signal_candidates(index["keys"], countries, since=since)
    matches = matching.match_all(request.suppliers, candidates, min_confidence=0.0)
    out = {}
    for supplier_id, found in matches.items():
        kept = [m for m in found if m["kind"] == "exposure" or m["confidence"] >= request.min_confidence]
        out[supplier_id] = [{**{k: m[k] for k in ("match_type", "confidence", "kind", "matched_on")},
                             "signal": _as_document(m["signal"])} for m in kept[: request.limit_per_supplier]]
    return {"matches": out, "candidates_considered": len(candidates)}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("INGESTION_SERVICE_PORT", "8008"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
