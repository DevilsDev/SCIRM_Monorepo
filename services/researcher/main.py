"""
SCIRM Researcher Agent
RAG-powered data retrieval using Weaviate vector search and LLM-based
synthesis of supply chain intelligence from multiple data sources.
"""

import json
import os
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from libs.common.monitoring import setup_monitoring, track_agent_task
from libs.common.security import setup_cors
from libs.common import llm as llm_client

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WEAVIATE_URL = os.getenv("WEAVIATE_URL", "http://localhost:8080")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Weaviate client (lazy init)
_weaviate_client = None
_weaviate_available = False

COLLECTION_NAME = "SupplyChainData"


# ---------------------------------------------------------------------------
# Weaviate helpers
# ---------------------------------------------------------------------------

def _get_weaviate_client():
    global _weaviate_client, _weaviate_available
    if _weaviate_client is not None:
        return _weaviate_client
    try:
        import weaviate
        _weaviate_client = weaviate.Client(url=WEAVIATE_URL)
        _weaviate_available = _weaviate_client.is_ready()
        if _weaviate_available:
            logger.info("Weaviate connected", url=WEAVIATE_URL)
        return _weaviate_client
    except Exception as exc:
        logger.warning("Weaviate unavailable, using fallback", error=str(exc))
        _weaviate_available = False
        return None


def _ensure_schema():
    """Create the Weaviate collection if it doesn't exist."""
    client = _get_weaviate_client()
    if not client or not _weaviate_available:
        return

    if client.schema.contains({"class": COLLECTION_NAME}):
        return

    schema = {
        "class": COLLECTION_NAME,
        "description": "Supply chain risk intelligence documents",
        "vectorizer": "text2vec-openai",
        "moduleConfig": {
            "text2vec-openai": {"model": "ada", "modelVersion": "002", "type": "text"}
        },
        "properties": [
            {"name": "source", "dataType": ["text"], "description": "Data source category"},
            {"name": "content", "dataType": ["text"], "description": "Document content"},
            {"name": "risk_level", "dataType": ["text"], "description": "Assessed risk level"},
            {"name": "category", "dataType": ["text"], "description": "Risk category"},
            {"name": "region", "dataType": ["text"], "description": "Geographic region"},
            {"name": "confidence", "dataType": ["number"], "description": "Confidence score"},
            {"name": "timestamp", "dataType": ["date"], "description": "Data timestamp"},
        ],
    }
    try:
        client.schema.create_class(schema)
        logger.info("Weaviate schema created", collection=COLLECTION_NAME)
    except Exception as exc:
        logger.warning("Schema creation failed", error=str(exc))


async def _vector_search(query: str, limit: int = 10, source_filter: Optional[List[str]] = None) -> List[Dict]:
    """Run semantic similarity search in Weaviate."""
    client = _get_weaviate_client()
    if not client or not _weaviate_available:
        return []

    try:
        builder = (
            client.query
            .get(COLLECTION_NAME, ["source", "content", "risk_level", "category", "region", "confidence"])
            .with_near_text({"concepts": [query]})
            .with_limit(limit)
            .with_additional(["certainty", "id"])
        )

        if source_filter:
            where_filter = {
                "operator": "Or",
                "operands": [
                    {"path": ["source"], "operator": "Equal", "valueText": s}
                    for s in source_filter
                ],
            }
            builder = builder.with_where(where_filter)

        result = builder.do()
        hits = result.get("data", {}).get("Get", {}).get(COLLECTION_NAME, [])
        return [
            {
                "source": h.get("source", ""),
                "content": h.get("content", ""),
                "risk_level": h.get("risk_level", "medium"),
                "category": h.get("category", ""),
                "region": h.get("region", ""),
                "confidence": h.get("confidence", 0.5),
                "certainty": h.get("_additional", {}).get("certainty", 0),
            }
            for h in hits
        ]
    except Exception as exc:
        logger.warning("Vector search failed", error=str(exc))
        return []


async def _ingest_document(doc: Dict[str, Any]) -> bool:
    """Ingest a single document into Weaviate."""
    client = _get_weaviate_client()
    if not client or not _weaviate_available:
        return False

    try:
        client.data_object.create(
            data_object={
                "source": doc.get("source", "unknown"),
                "content": doc.get("content", ""),
                "risk_level": doc.get("risk_level", "medium"),
                "category": doc.get("category", "general"),
                "region": doc.get("region", "global"),
                "confidence": doc.get("confidence", 0.5),
                "timestamp": doc.get("timestamp", datetime.utcnow().isoformat()),
            },
            class_name=COLLECTION_NAME,
        )
        return True
    except Exception as exc:
        logger.warning("Document ingestion failed", error=str(exc))
        return False


# ---------------------------------------------------------------------------
# Built-in knowledge base (used when Weaviate has no data or is unavailable)
# ---------------------------------------------------------------------------

SUPPLY_CHAIN_KNOWLEDGE = [
    {
        "source": "regulatory",
        "content": "FDA has increased scrutiny on pharmaceutical supply chain transparency. New requirements for drug supply chain traceability under DSCSA are being enforced.",
        "risk_level": "high",
        "category": "regulatory",
        "region": "usa",
        "confidence": 0.85,
    },
    {
        "source": "logistics",
        "content": "Global shipping delays continue to affect pharmaceutical cold chain logistics. Average transit times have increased 15-20% on major trade lanes.",
        "risk_level": "high",
        "category": "logistics",
        "region": "global",
        "confidence": 0.80,
    },
    {
        "source": "weather",
        "content": "Hurricane season forecasts predict above-average activity in the Atlantic basin, potentially disrupting Gulf Coast manufacturing and port operations.",
        "risk_level": "medium",
        "category": "supplier",
        "region": "usa",
        "confidence": 0.70,
    },
    {
        "source": "news",
        "content": "Geopolitical tensions in East Asia raise concerns about semiconductor and API supply continuity for medical device and pharmaceutical manufacturers.",
        "risk_level": "critical",
        "category": "supplier",
        "region": "asia",
        "confidence": 0.75,
    },
    {
        "source": "regulatory",
        "content": "EMA is implementing new GMP Annex 1 requirements for sterile manufacturing. Compliance deadline approaching for pharmaceutical producers.",
        "risk_level": "high",
        "category": "regulatory",
        "region": "europe",
        "confidence": 0.90,
    },
    {
        "source": "logistics",
        "content": "Port congestion in major Asian hubs has eased slightly but remains above pre-pandemic levels. Container availability improving for refrigerated cargo.",
        "risk_level": "medium",
        "category": "logistics",
        "region": "asia",
        "confidence": 0.75,
    },
    {
        "source": "news",
        "content": "Raw material costs for pharmaceutical excipients have risen 8-12% year-over-year, driven by energy costs and supply constraints.",
        "risk_level": "medium",
        "category": "financial",
        "region": "global",
        "confidence": 0.80,
    },
    {
        "source": "weather",
        "content": "Drought conditions in Southern Europe may affect agricultural supply chains and water-intensive pharmaceutical manufacturing processes.",
        "risk_level": "medium",
        "category": "quality",
        "region": "europe",
        "confidence": 0.65,
    },
]


def _search_knowledge_base(
    query: str,
    data_sources: List[str],
    entities: List[Dict],
    limit: int = 10,
) -> List[Dict]:
    """Keyword-based fallback search against the built-in knowledge base."""
    query_lower = query.lower()
    entity_names = [e.get("name", "").lower() for e in entities]
    entity_locations = [e.get("location", "").lower() for e in entities if e.get("location")]

    scored = []
    for doc in SUPPLY_CHAIN_KNOWLEDGE:
        # Filter by requested data sources
        if data_sources and doc["source"] not in data_sources:
            continue

        score = 0.0
        content_lower = doc["content"].lower()

        # Query term matching
        for word in query_lower.split():
            if len(word) > 3 and word in content_lower:
                score += 0.15

        # Entity relevance
        for name in entity_names:
            if name in content_lower:
                score += 0.25
        for loc in entity_locations:
            if loc in content_lower or loc in doc.get("region", ""):
                score += 0.20

        # Source relevance boost
        if doc["source"] in data_sources:
            score += 0.10

        score = min(score + doc["confidence"] * 0.3, 1.0)
        scored.append({**doc, "relevance_score": round(score, 3)})

    scored.sort(key=lambda x: x["relevance_score"], reverse=True)
    return scored[:limit]


# ---------------------------------------------------------------------------
# LLM-powered synthesis
# ---------------------------------------------------------------------------

async def _synthesize_findings(
    query: str,
    raw_results: List[Dict],
    entities: List[Dict],
    context: Dict[str, Any],
) -> List[Dict]:
    """Use LLM to synthesize raw search results into structured findings."""
    if not llm_client.is_configured() or not raw_results:
        # Return raw results as findings without LLM synthesis
        return [
            {
                "id": str(uuid.uuid4()),
                "source": r.get("source", "unknown"),
                "data": r.get("content", ""),
                "risk_level": r.get("risk_level", "medium"),
                "type": r.get("category", "general"),
                "key_insights": [r.get("content", "")[:100]],
                "confidence": r.get("confidence", 0.5),
            }
            for r in raw_results
        ]

    entities_desc = ", ".join(
        f"{e.get('name', 'unknown')} ({e.get('type', '')})" for e in entities[:10]
    )
    org_industry = context.get("metadata", {}).get("industry", context.get("industry", "general"))

    prompt = f"""Analyze these supply chain intelligence results and synthesize findings.

Query: {query}
Industry: {org_industry}
Entities under assessment: {entities_desc}

Raw intelligence data:
{json.dumps(raw_results[:15], indent=2, default=str)}

For each distinct risk or insight found, produce a JSON object.
Return a JSON object with key "findings" containing an array. Each finding:
{{
  "source": "<data source category>",
  "data": "<concise summary of the finding, 1-2 sentences>",
  "risk_level": "low|medium|high|critical",
  "type": "<risk category: supplier|logistics|regulatory|quality|financial>",
  "key_insights": ["<insight 1>", "<insight 2>"],
  "confidence": <0.0-1.0>
}}

Merge duplicate/overlapping results. Prioritize findings most relevant to the entities.
Return 3-8 findings, ordered by risk_level (critical first)."""

    try:
        result = await llm_client.generate_json(prompt)
        findings = result.get("findings", [])
        for f in findings:
            f["id"] = str(uuid.uuid4())
        return findings
    except Exception as exc:
        logger.warning("LLM synthesis failed, using raw results", error=str(exc))
        return [
            {
                "id": str(uuid.uuid4()),
                "source": r.get("source", "unknown"),
                "data": r.get("content", ""),
                "risk_level": r.get("risk_level", "medium"),
                "type": r.get("category", "general"),
                "key_insights": [r.get("content", "")[:100]],
                "confidence": r.get("confidence", 0.5),
            }
            for r in raw_results
        ]


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------

class ResearchRequest(BaseModel):
    query: str
    data_sources: List[str] = ["weather", "logistics", "news", "regulatory"]
    entities: List[Dict[str, Any]] = []
    context: Dict[str, Any] = {}
    max_results: int = Field(default=10, ge=1, le=50)


class IngestRequest(BaseModel):
    documents: List[Dict[str, Any]]


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_schema()
    logger.info("Researcher agent started", weaviate=WEAVIATE_URL, weaviate_available=_weaviate_available)
    yield
    logger.info("Researcher agent stopped")


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="SCIRM Researcher Agent",
    description="RAG-powered supply chain intelligence retrieval and synthesis",
    version="1.0.0",
    lifespan=lifespan,
)

setup_cors(app)
setup_monitoring(app, service_name="researcher")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    weaviate_status = "healthy" if _weaviate_available else "unavailable"
    llm_status = "configured" if llm_client.is_configured() else "not_configured"
    return {
        "status": "healthy",
        "agent": "researcher",
        "weaviate": weaviate_status,
        "llm": llm_status,
    }


@app.get("/ready")
async def ready():
    return {"status": "ready", "agent": "researcher"}


@app.post("/research")
@track_agent_task("researcher", "research")
async def research(request: ResearchRequest):
    """
    Primary research endpoint.
    1. Search Weaviate for semantically relevant documents
    2. Fall back to built-in knowledge base if Weaviate is empty/unavailable
    3. Use LLM to synthesize findings (if configured)
    """
    # Step 1: Try vector search
    vector_results = await _vector_search(
        query=request.query,
        limit=request.max_results,
        source_filter=request.data_sources if request.data_sources else None,
    )

    # Step 2: Fall back to knowledge base if vector search returned nothing
    if not vector_results:
        vector_results = _search_knowledge_base(
            query=request.query,
            data_sources=request.data_sources,
            entities=request.entities,
            limit=request.max_results,
        )

    data_sources_used = list({r.get("source", "unknown") for r in vector_results})

    # Step 3: LLM synthesis
    findings = await _synthesize_findings(
        query=request.query,
        raw_results=vector_results,
        entities=request.entities,
        context=request.context,
    )

    # Confidence: average of finding confidences, weighted by result count
    confidences = [f.get("confidence", 0.5) for f in findings]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    coverage_factor = min(len(findings) / 5, 1.0)  # 5+ findings = full coverage
    overall_confidence = round(avg_confidence * 0.7 + coverage_factor * 0.3, 3)

    return {
        "research_results": vector_results,
        "findings": findings,
        "confidence_score": overall_confidence,
        "data_sources_used": data_sources_used,
        "reasoning": f"Retrieved {len(vector_results)} results from {len(data_sources_used)} sources, synthesized into {len(findings)} findings.",
        "metadata": {
            "query": request.query,
            "vector_search_used": _weaviate_available and len(vector_results) > 0,
            "llm_synthesis_used": llm_client.is_configured(),
            "results_count": len(vector_results),
            "findings_count": len(findings),
            "research_timestamp": datetime.utcnow().isoformat(),
        },
    }


@app.post("/ingest")
async def ingest(request: IngestRequest):
    """Ingest documents into the Weaviate vector store."""
    if not _weaviate_available:
        raise HTTPException(status_code=503, detail="Weaviate is not available for ingestion")

    ingested = 0
    for doc in request.documents:
        if await _ingest_document(doc):
            ingested += 1

    return {
        "ingested": ingested,
        "total": len(request.documents),
        "status": "completed",
    }


@app.get("/sources")
async def list_sources():
    """List available data source categories."""
    return {
        "sources": ["weather", "logistics", "news", "regulatory"],
        "knowledge_base_size": len(SUPPLY_CHAIN_KNOWLEDGE),
        "weaviate_available": _weaviate_available,
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("RESEARCHER_SERVICE_PORT", "8003"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
