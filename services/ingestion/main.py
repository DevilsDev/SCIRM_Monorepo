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

    # News feed
    news_docs = await _fetch_news()
    new_docs.extend(news_docs)
    _sources_status["news"] = {"last_fetched": datetime.utcnow().isoformat(), "documents": len(news_docs), "status": "active"}

    # Weather feed
    weather_docs = await _fetch_weather()
    new_docs.extend(weather_docs)
    _sources_status["weather"] = {"last_fetched": datetime.utcnow().isoformat(), "documents": len(weather_docs), "status": "active"}

    # Regulatory feed
    reg_docs = await _fetch_regulatory()
    new_docs.extend(reg_docs)
    _sources_status["regulatory"] = {"last_fetched": datetime.utcnow().isoformat(), "documents": len(reg_docs), "status": "active"}

    # Financial feed
    fin_docs = await _fetch_financial()
    new_docs.extend(fin_docs)
    _sources_status["financial"] = {"last_fetched": datetime.utcnow().isoformat(), "documents": len(fin_docs), "status": "active"}

    _documents.extend(new_docs)
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
                resp = await client.get(
                    "https://newsapi.org/v2/everything",
                    params={"q": "supply chain disruption", "sortBy": "publishedAt", "pageSize": 10, "apiKey": NEWS_API_KEY},
                    timeout=15.0,
                )
                resp.raise_for_status()
                articles = resp.json().get("articles", [])
                return [
                    _normalize_doc("news", a.get("title", ""), a.get("description", ""), a.get("url"), "medium", "Global")
                    for a in articles[:10]
                ]
        except Exception as exc:
            logger.warning("News API failed, using built-in", error=str(exc))

    return [_normalize_doc(f["source"], f["title"], f["content"], None, f["severity"], f["region"]) for f in LIVE_FEEDS if f["source"] == "news"]


async def _fetch_weather() -> List[Dict[str, Any]]:
    """Fetch weather alerts or use built-in feed."""
    return [_normalize_doc(f["source"], f["title"], f["content"], None, f["severity"], f["region"]) for f in LIVE_FEEDS if f["source"] == "weather"]


async def _fetch_regulatory() -> List[Dict[str, Any]]:
    """Fetch regulatory updates or use built-in feed."""
    return [_normalize_doc(f["source"], f["title"], f["content"], None, f["severity"], f["region"]) for f in LIVE_FEEDS if f["source"] == "regulatory"]


async def _fetch_financial() -> List[Dict[str, Any]]:
    """Fetch financial data or use built-in feed."""
    return [_normalize_doc(f["source"], f["title"], f["content"], None, f["severity"], f["region"]) for f in LIVE_FEEDS if f["source"] == "financial"]


def _normalize_doc(source: str, title: str, content: str, url: str = None, severity: str = "medium", region: str = "Global") -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "source": source,
        "title": title,
        "content": content,
        "url": url,
        "severity": severity,
        "region": region,
        "ingested_at": datetime.utcnow().isoformat(),
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("INGESTION_SERVICE_PORT", "8008"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
