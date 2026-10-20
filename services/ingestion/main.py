"""
SCIRM Ingestion Service
Real-time data collection from news, weather, regulatory, and financial feeds.
Normalizes, embeds, and stores intelligence documents.
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List

import httpx
import structlog
from fastapi import FastAPI
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from libs.common.monitoring import setup_monitoring
from libs.common.security import setup_cors

logger = structlog.get_logger()

INGESTION_INTERVAL = int(os.getenv("INGESTION_INTERVAL_MINUTES", "30"))
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
WEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")

app = FastAPI(title="SCIRM Ingestion Service", description="Real-time supply chain intelligence ingestion", version="1.0.0")
setup_cors(app)
setup_monitoring(app, service_name="ingestion")

# Intelligence document store
_documents: List[Dict[str, Any]] = []
_sources_status: Dict[str, Dict[str, Any]] = {}

# Built-in intelligence feeds (always available, simulates real-time data)
LIVE_FEEDS = [
    {"source": "news", "title": "Semiconductor shortage deepens in Asia Pacific", "content": "Major chip manufacturers report 15% capacity reduction due to equipment supply constraints. Lead times extended to 26 weeks for automotive-grade semiconductors.", "severity": "high", "region": "Asia Pacific", "category": "supplier"},
    {"source": "news", "title": "New EU supply chain due diligence regulation enacted", "content": "European Parliament approves Corporate Sustainability Due Diligence Directive requiring companies to identify and mitigate human rights and environmental impacts across supply chains.", "severity": "medium", "region": "Europe", "category": "regulatory"},
    {"source": "weather", "title": "Hurricane season forecast: above-average activity", "content": "NOAA predicts 17-25 named storms for 2026 Atlantic hurricane season, with 8-13 hurricanes. Gulf Coast manufacturing and port operations at elevated risk June-November.", "severity": "high", "region": "North America", "category": "catastrophic"},
    {"source": "regulatory", "title": "FDA updates DSCSA enforcement timeline", "content": "FDA announces phased enforcement of Drug Supply Chain Security Act serialization requirements. Full compliance deadline moved to November 2026 with interim milestones.", "severity": "medium", "region": "North America", "category": "regulatory"},
    {"source": "financial", "title": "Raw material prices surge 12% quarter-over-quarter", "content": "Chemical and pharmaceutical excipient prices continue upward trend driven by energy costs. API manufacturing costs in India up 8%, European producers face margin pressure.", "severity": "medium", "region": "Global", "category": "financial"},
    {"source": "news", "title": "Red Sea shipping disruptions continue into Q2", "content": "Houthi attacks on commercial vessels force continued rerouting via Cape of Good Hope. Transit times for Asia-Europe routes increased by 10-14 days, adding $1M+ per voyage.", "severity": "critical", "region": "Middle East", "category": "logistics"},
    {"source": "regulatory", "title": "EMA releases new GMP Annex 1 guidance", "content": "European Medicines Agency publishes updated sterile manufacturing guidelines. Pharmaceutical companies have 12 months to implement changes to cleanroom operations.", "severity": "medium", "region": "Europe", "category": "regulatory"},
    {"source": "weather", "title": "Monsoon season impacts Indian API manufacturing", "content": "Heavy monsoon rainfall disrupts logistics in Maharashtra and Gujarat pharmaceutical clusters. API shipment delays of 5-10 days expected through September.", "severity": "high", "region": "South Asia", "category": "logistics"},
    {"source": "financial", "title": "Major pharma supplier credit downgrade", "content": "Moody's downgrades key excipient supplier from Baa2 to Baa3 citing declining margins and debt-to-equity concerns. Affects 15% of global excipient supply.", "severity": "high", "region": "Global", "category": "financial"},
    {"source": "news", "title": "Cybersecurity breach at logistics provider", "content": "Major third-party logistics provider confirms ransomware attack affecting tracking and warehouse management systems. Recovery timeline estimated at 2-3 weeks.", "severity": "critical", "region": "North America", "category": "cyber"},
]


class IngestResult(BaseModel):
    documents_ingested: int
    sources_queried: List[str]
    timestamp: str


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "agent": "ingestion",
        "documents_stored": len(_documents),
        "sources": list(_sources_status.keys()),
    }


@app.get("/ready")
async def ready():
    return {"status": "ready", "agent": "ingestion"}


@app.post("/ingest")
async def trigger_ingestion():
    """Trigger a manual ingestion cycle from all configured sources."""
    new_docs = []

    for source, fetch in (("news", _fetch_news), ("weather", _fetch_weather),
                          ("regulatory", _fetch_regulatory), ("financial", _fetch_financial)):
        docs = await fetch()
        added = _store_new(docs)
        new_docs.extend(added)
        demo = bool(docs) and all(d.get("is_demo") for d in docs)
        _sources_status[source] = {
            "last_fetched": datetime.utcnow().isoformat(),
            "documents": len(added),
            # "demo" = built-in sample items, not a live feed. Never report it as active.
            "status": "demo" if demo else "live",
        }

    logger.info("Ingestion cycle complete", total_new=len(new_docs), total_stored=len(_documents))

    return IngestResult(
        documents_ingested=len(new_docs),
        sources_queried=["news", "weather", "regulatory", "financial"],
        timestamp=datetime.utcnow().isoformat(),
    )


@app.get("/documents")
async def list_documents(source: str = None, limit: int = 50, since_hours: int = 24):
    """List ingested intelligence documents."""
    cutoff = (datetime.utcnow() - timedelta(hours=since_hours)).isoformat()
    docs = _documents
    if source:
        docs = [d for d in docs if d.get("source") == source]
    docs = [d for d in docs if d.get("ingested_at", "") >= cutoff]
    docs.sort(key=lambda d: d.get("ingested_at", ""), reverse=True)
    return {"documents": docs[:limit], "total": len(docs)}


@app.get("/sources")
async def list_sources():
    """List all data sources and their status."""
    return {
        "sources": _sources_status,
        "available": ["news", "weather", "regulatory", "financial"],
        "total_documents": len(_documents),
    }


# --- Feed collectors ---

async def _fetch_news() -> List[Dict[str, Any]]:
    """Fetch from news API or use built-in feed."""
    if NEWS_API_KEY:
        try:
            async with httpx.AsyncClient() as client:
                # Key in a header, not the URL: httpx error messages include the URL.
                resp = await client.get(
                    "https://newsapi.org/v2/everything",
                    params={"q": "supply chain disruption", "sortBy": "publishedAt", "pageSize": 10},
                    headers={"X-Api-Key": NEWS_API_KEY},
                    timeout=15.0,
                )
                resp.raise_for_status()
                articles = resp.json().get("articles", [])
                return [
                    _normalize_doc("news", a.get("title", ""), a.get("description", ""), a.get("url"), "medium",
                                   "Global", published_at=a.get("publishedAt"))
                    for a in articles[:10]
                ]
        except Exception as exc:
            logger.warning("News API failed, using built-in sample items", error=type(exc).__name__)

    return [_normalize_doc(f["source"], f["title"], f["content"], None, f["severity"], f["region"], is_demo=True) for f in LIVE_FEEDS if f["source"] == "news"]


async def _fetch_weather() -> List[Dict[str, Any]]:
    """Fetch weather alerts or use built-in feed."""
    return [_normalize_doc(f["source"], f["title"], f["content"], None, f["severity"], f["region"], is_demo=True) for f in LIVE_FEEDS if f["source"] == "weather"]


async def _fetch_regulatory() -> List[Dict[str, Any]]:
    """Fetch regulatory updates or use built-in feed."""
    return [_normalize_doc(f["source"], f["title"], f["content"], None, f["severity"], f["region"], is_demo=True) for f in LIVE_FEEDS if f["source"] == "regulatory"]


async def _fetch_financial() -> List[Dict[str, Any]]:
    """Fetch financial data or use built-in feed."""
    return [_normalize_doc(f["source"], f["title"], f["content"], None, f["severity"], f["region"], is_demo=True) for f in LIVE_FEEDS if f["source"] == "financial"]


def _normalize_doc(source: str, title: str, content: str, url: str = None, severity: str = "medium",
                   region: str = "Global", is_demo: bool = False, published_at: str = None) -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "source": source,
        "title": title,
        "content": content,
        "url": url,
        "severity": severity,
        "region": region,
        "ingested_at": datetime.utcnow().isoformat(),
        "published_at": published_at,
        # Built-in sample items: shown for demos, never presented as live intelligence.
        "is_demo": is_demo,
    }


def _store_new(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Store documents not already stored (by source + url/title), so repeated ingest
    runs don't re-add the same item with a fresh timestamp and make it look new."""
    seen = {(d["source"], d.get("url") or d["title"]) for d in _documents}
    added = [d for d in docs if (d["source"], d.get("url") or d["title"]) not in seen]
    _documents.extend(added)
    return added


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("INGESTION_SERVICE_PORT", "8008"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
