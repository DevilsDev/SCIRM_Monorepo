"""
SCIRM Discovery Agent
LLM-powered sub-tier supplier discovery and relationship mapping.
"""

import json
import os
import sys
import uuid
from datetime import datetime
from typing import Any, Dict, List

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from libs.common.monitoring import setup_monitoring
from libs.common.security import setup_cors
from libs.common import llm as llm_client

logger = structlog.get_logger()

app = FastAPI(
    title="SCIRM Discovery Agent",
    description="Sub-tier supplier discovery and relationship mapping",
    version="1.0.0",
)

setup_cors(app)
setup_monitoring(app, service_name="discovery")

# In-memory relationship store (production uses DB)
_relationships: List[Dict[str, Any]] = []
_discovered_suppliers: Dict[str, Dict[str, Any]] = {}

# Built-in sub-tier knowledge for development
KNOWN_SUBTIERS = {
    "Supplier Alpha": [
        {"name": "Alpha Raw Materials Co", "type": "raw_material_source", "country": "BR", "region": "South America", "tier": 2},
        {"name": "Alpha Chemical Processing", "type": "sub_supplier", "country": "IN", "region": "South Asia", "tier": 2},
    ],
    "Supplier Beta": [
        {"name": "Beta Polymer Labs", "type": "sub_supplier", "country": "CH", "region": "Europe", "tier": 2},
        {"name": "Beta Logistics GmbH", "type": "logistics_provider", "country": "DE", "region": "Europe", "tier": 2},
        {"name": "Rhine Chemical AG", "type": "raw_material_source", "country": "DE", "region": "Europe", "tier": 3},
    ],
    "Supplier Gamma": [
        {"name": "Shenzhen Packaging Materials", "type": "sub_supplier", "country": "CN", "region": "Asia Pacific", "tier": 2},
        {"name": "Guangzhou Printing Co", "type": "sub_supplier", "country": "CN", "region": "Asia Pacific", "tier": 2},
        {"name": "Yangtze Paper Mill", "type": "raw_material_source", "country": "CN", "region": "Asia Pacific", "tier": 3},
    ],
    "Supplier Delta": [
        {"name": "Tokyo Sensor Corp", "type": "sub_supplier", "country": "JP", "region": "Asia Pacific", "tier": 2},
        {"name": "Osaka Silicon Foundry", "type": "raw_material_source", "country": "JP", "region": "Asia Pacific", "tier": 3},
    ],
    "Supplier Epsilon": [
        {"name": "BioMat Research Inc", "type": "sub_supplier", "country": "US", "region": "North America", "tier": 2},
    ],
}


class DiscoverRequest(BaseModel):
    supplier_name: str
    supplier_id: str = ""
    supplier_context: Dict[str, Any] = {}
    max_depth: int = 3


class DiscoverResponse(BaseModel):
    supplier_name: str
    discovered_subtiers: List[Dict[str, Any]]
    relationships: List[Dict[str, Any]]
    total_discovered: int
    max_depth_reached: int
    discovery_method: str
    # Every returned sub-tier is a hypothesis until a supplier or document confirms it.
    verification_status: str = "unconfirmed"
    notice: str = ("Sub-tier suppliers are suggestions, not verified relationships. "
                   "Confirm them through a supplier assessment before relying on them.")


@app.get("/health")
async def health():
    return {"status": "healthy", "agent": "discovery", "llm_configured": llm_client.is_configured()}


@app.get("/ready")
async def ready():
    return {"status": "ready", "agent": "discovery"}


@app.post("/discover", response_model=DiscoverResponse)
async def discover_subtiers(request: DiscoverRequest):
    """Discover sub-tier suppliers for a given supplier."""
    discovered = []
    relationships = []

    # Try LLM-powered discovery
    if llm_client.is_configured():
        try:
            prompt = f"""Identify likely sub-tier suppliers for this supply chain entity.

Supplier: {request.supplier_name}
Type: {request.supplier_context.get('supplier_type', 'unknown')}
Country: {request.supplier_context.get('country_code', 'unknown')}
Region: {request.supplier_context.get('region', 'unknown')}
Industry context: pharmaceutical/healthcare supply chain

Return a JSON object with key "subtiers" as an array. Each subtier:
{{
  "name": "<likely sub-supplier company name>",
  "type": "sub_supplier|raw_material_source|logistics_provider",
  "country": "<2-letter country code>",
  "region": "<geographic region>",
  "tier": <2 or 3>,
  "confidence": <0.0-1.0>,
  "reasoning": "<why this supplier is likely in the chain>"
}}

Generate 2-5 realistic sub-tier suppliers based on industry knowledge."""

            result = await llm_client.generate_json(prompt)
            llm_subtiers = result.get("subtiers", [])
            for st in llm_subtiers:
                sub_id = str(uuid.uuid4())
                st["id"] = sub_id
                # The model infers plausible suppliers from general knowledge; it has
                # no evidence these companies supply this one. Cap confidence and label.
                st["discovered_by"] = "llm_suggestion"
                st["verification_status"] = "unconfirmed"
                st["confidence"] = min(float(st.get("confidence", 0.3)), 0.5)
                discovered.append(st)
                relationships.append({
                    "id": str(uuid.uuid4()),
                    "source_supplier_id": request.supplier_id or request.supplier_name,
                    "target_supplier_id": sub_id,
                    "target_supplier_name": st["name"],
                    "relationship_type": st.get("type", "sub_supplier"),
                    "tier_level": st.get("tier", 2),
                    "confidence_score": st["confidence"],
                    "discovered_by": "llm_suggestion",
                    "verification_status": "unconfirmed",
                })

            if discovered:
                return DiscoverResponse(
                    supplier_name=request.supplier_name,
                    discovered_subtiers=discovered,
                    relationships=relationships,
                    total_discovered=len(discovered),
                    max_depth_reached=max(s.get("tier", 2) for s in discovered),
                    discovery_method="llm_suggestion",
                )
        except Exception as exc:
            logger.warning("LLM discovery failed, using knowledge base", error=str(exc))

    # Fallback to known sub-tier data
    known = KNOWN_SUBTIERS.get(request.supplier_name, [])
    for st in known:
        sub_id = str(uuid.uuid4())
        discovered.append({
            **st,
            "id": sub_id,
            "discovered_by": "knowledge_base",
            "verification_status": "unconfirmed",
            "confidence": 0.6,
        })
        relationships.append({
            "id": str(uuid.uuid4()),
            "source_supplier_id": request.supplier_id or request.supplier_name,
            "target_supplier_id": sub_id,
            "target_supplier_name": st["name"],
            "relationship_type": st.get("type", "sub_supplier"),
            "tier_level": st.get("tier", 2),
            "confidence_score": 0.6,
            "discovered_by": "knowledge_base",
            "verification_status": "unconfirmed",
        })

    # Store discovered data
    for d in discovered:
        _discovered_suppliers[d["id"]] = d
    _relationships.extend(relationships)

    return DiscoverResponse(
        supplier_name=request.supplier_name,
        discovered_subtiers=discovered,
        relationships=relationships,
        total_discovered=len(discovered),
        max_depth_reached=max((s.get("tier", 2) for s in discovered), default=1),
        # Report what produced these results, not what is configured.
        discovery_method="knowledge_base" if discovered else "none",
    )


@app.get("/relationships")
async def list_relationships():
    """List all discovered relationships."""
    return {"relationships": _relationships, "total": len(_relationships)}


@app.get("/discovered-suppliers")
async def list_discovered():
    """List all discovered sub-tier suppliers."""
    return {"suppliers": list(_discovered_suppliers.values()), "total": len(_discovered_suppliers)}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("DISCOVERY_SERVICE_PORT", "8007"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
