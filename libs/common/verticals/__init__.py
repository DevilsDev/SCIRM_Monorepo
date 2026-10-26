"""
SCIRM Industry Vertical Templates
Configurable risk rubrics, compliance rules, and recommendation templates per industry.
"""

from typing import Any, Dict

from .pharma import PHARMA_VERTICAL
from .automotive import AUTOMOTIVE_VERTICAL
from .electronics import ELECTRONICS_VERTICAL
from .food_beverage import FOOD_BEVERAGE_VERTICAL
from .energy import ENERGY_VERTICAL

VERTICALS: Dict[str, Dict[str, Any]] = {
    "pharmaceutical": PHARMA_VERTICAL,
    "healthcare": PHARMA_VERTICAL,  # Shares pharma vertical
    "automotive": AUTOMOTIVE_VERTICAL,
    "electronics": ELECTRONICS_VERTICAL,
    "food_beverage": FOOD_BEVERAGE_VERTICAL,
    "energy": ENERGY_VERTICAL,
}


def get_vertical(industry: str) -> Dict[str, Any]:
    """Get vertical configuration for an industry. Falls back to general."""
    return VERTICALS.get(industry, {
        "name": "General",
        "compliance_rules": ["Business continuity", "Stakeholder impact", "Cost-benefit analysis"],
        "risk_weights": {"operational": 0.25, "financial": 0.25, "regulatory": 0.15, "geopolitical": 0.15, "esg": 0.10, "cyber": 0.05, "catastrophic": 0.05},
        "kpis": ["On-time delivery", "Supplier defect rate", "Cost variance"],
    })
