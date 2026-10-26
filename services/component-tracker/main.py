"""
SCIRM Component Tracker
BOM (Bill of Materials) tracking with inherited supplier risk.
"""

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

logger = structlog.get_logger()

app = FastAPI(title="SCIRM Component Tracker", description="BOM and component risk tracking", version="1.0.0")
setup_cors(app)
setup_monitoring(app, service_name="component-tracker")

# Built-in component catalog
COMPONENTS = [
    {"id": "comp-001", "name": "API Compound X", "part_number": "API-X-500", "category": "active_ingredient", "criticality": "critical", "suppliers": ["Supplier Alpha"], "risk_score": 35},
    {"id": "comp-002", "name": "Excipient Y Powder", "part_number": "EXC-Y-100", "category": "excipient", "criticality": "high", "suppliers": ["Supplier Beta"], "risk_score": 62},
    {"id": "comp-003", "name": "Blister Pack Film", "part_number": "PKG-BL-200", "category": "packaging", "criticality": "medium", "suppliers": ["Supplier Gamma"], "risk_score": 78},
    {"id": "comp-004", "name": "Capsule Shell Type A", "part_number": "CAP-A-300", "category": "packaging", "criticality": "high", "suppliers": ["Supplier Alpha", "Supplier Beta"], "risk_score": 48},
    {"id": "comp-005", "name": "Temperature Sensor Module", "part_number": "SEN-T-100", "category": "monitoring", "criticality": "medium", "suppliers": ["Supplier Delta"], "risk_score": 28},
    {"id": "comp-006", "name": "Biocompatible Coating", "part_number": "BIO-C-50", "category": "material", "criticality": "critical", "suppliers": ["Supplier Epsilon"], "risk_score": 55},
    {"id": "comp-007", "name": "Sterile Vial 10mL", "part_number": "VIAL-10-S", "category": "packaging", "criticality": "critical", "suppliers": ["Supplier Gamma"], "risk_score": 78},
    {"id": "comp-008", "name": "Label Stock Pharma Grade", "part_number": "LBL-PG-100", "category": "packaging", "criticality": "low", "suppliers": ["Supplier Gamma"], "risk_score": 78},
]

# BOM hierarchy: product → components
BOM_TREE = {
    "PROD-001": {
        "name": "CardioSafe Tablet 50mg",
        "category": "finished_product",
        "children": [
            {"component_id": "comp-001", "quantity": 0.05, "is_critical": True},
            {"component_id": "comp-002", "quantity": 0.45, "is_critical": True},
            {"component_id": "comp-004", "quantity": 1, "is_critical": True},
            {"component_id": "comp-008", "quantity": 1, "is_critical": False},
        ],
    },
    "PROD-002": {
        "name": "ImmunoBoost Injection 5mL",
        "category": "finished_product",
        "children": [
            {"component_id": "comp-001", "quantity": 0.02, "is_critical": True},
            {"component_id": "comp-006", "quantity": 0.01, "is_critical": True},
            {"component_id": "comp-007", "quantity": 1, "is_critical": True},
            {"component_id": "comp-005", "quantity": 1, "is_critical": False},
            {"component_id": "comp-008", "quantity": 1, "is_critical": False},
        ],
    },
    "PROD-003": {
        "name": "DermaCare Patch",
        "category": "finished_product",
        "children": [
            {"component_id": "comp-006", "quantity": 0.1, "is_critical": True},
            {"component_id": "comp-003", "quantity": 1, "is_critical": True},
            {"component_id": "comp-008", "quantity": 1, "is_critical": False},
        ],
    },
}

_comp_map = {c["id"]: c for c in COMPONENTS}


@app.get("/health")
async def health():
    return {"status": "healthy", "agent": "component-tracker", "components": len(COMPONENTS), "products": len(BOM_TREE)}


@app.get("/ready")
async def ready():
    return {"status": "ready", "agent": "component-tracker"}


@app.get("/components")
async def list_components(category: str = None, criticality: str = None):
    """List all tracked components."""
    comps = COMPONENTS
    if category:
        comps = [c for c in comps if c["category"] == category]
    if criticality:
        comps = [c for c in comps if c["criticality"] == criticality]
    return {"components": comps, "total": len(comps)}


@app.get("/components/{component_id}")
async def get_component(component_id: str):
    comp = _comp_map.get(component_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Component not found")
    return comp


@app.get("/products")
async def list_products():
    """List all products with their BOM summary."""
    products = []
    for prod_id, prod in BOM_TREE.items():
        children = prod["children"]
        risk_scores = [_comp_map.get(c["component_id"], {}).get("risk_score", 50) for c in children if c["is_critical"]]
        max_risk = max(risk_scores) if risk_scores else 0
        avg_risk = sum(risk_scores) / len(risk_scores) if risk_scores else 0
        products.append({
            "id": prod_id,
            "name": prod["name"],
            "category": prod["category"],
            "component_count": len(children),
            "critical_components": sum(1 for c in children if c["is_critical"]),
            "max_component_risk": max_risk,
            "avg_component_risk": round(avg_risk, 1),
        })
    return {"products": products, "total": len(products)}


@app.get("/products/{product_id}/bom")
async def get_bom(product_id: str):
    """Get full BOM tree for a product."""
    prod = BOM_TREE.get(product_id)
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")

    bom_items = []
    for child in prod["children"]:
        comp = _comp_map.get(child["component_id"], {})
        bom_items.append({
            **comp,
            "quantity": child["quantity"],
            "is_critical": child["is_critical"],
        })

    return {
        "product_id": product_id,
        "product_name": prod["name"],
        "bom": bom_items,
        "total_components": len(bom_items),
    }


@app.get("/impact-analysis/{component_id}")
async def component_impact(component_id: str):
    """Analyze which products are affected if a component is unavailable."""
    comp = _comp_map.get(component_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Component not found")

    affected_products = []
    for prod_id, prod in BOM_TREE.items():
        for child in prod["children"]:
            if child["component_id"] == component_id:
                affected_products.append({
                    "product_id": prod_id,
                    "product_name": prod["name"],
                    "is_critical_in_product": child["is_critical"],
                    "quantity_needed": child["quantity"],
                })

    return {
        "component": comp,
        "affected_products": affected_products,
        "total_affected": len(affected_products),
        "critical_impact": any(p["is_critical_in_product"] for p in affected_products),
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("COMPONENT_TRACKER_PORT", "8012"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
