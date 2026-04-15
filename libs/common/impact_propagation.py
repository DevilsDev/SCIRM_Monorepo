"""
SCIRM Impact Propagation Engine
BFS graph traversal to calculate cascading impact through supplier relationships.
"""

import uuid
from collections import deque
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()

# Impact attenuation: each tier reduces severity by this factor
TIER_ATTENUATION = 0.6
SEVERITY_SCORES = {"critical": 1.0, "high": 0.75, "medium": 0.5, "low": 0.25}
SEVERITY_LABELS = [(0.75, "critical"), (0.5, "high"), (0.25, "medium"), (0.0, "low")]


def severity_from_score(score: float) -> str:
    for threshold, label in SEVERITY_LABELS:
        if score >= threshold:
            return label
    return "low"


def propagate_impact(
    event_id: str,
    initial_severity: str,
    directly_affected_supplier_ids: List[str],
    supplier_graph: Dict[str, List[Dict[str, Any]]],
    supplier_info: Dict[str, Dict[str, Any]],
    max_tier: int = 5,
) -> List[Dict[str, Any]]:
    """
    BFS propagation of impact through the supplier relationship graph.

    Args:
        event_id: The triggering risk event ID
        initial_severity: critical/high/medium/low
        directly_affected_supplier_ids: Supplier IDs directly hit by the event
        supplier_graph: Adjacency list {supplier_id: [{target_id, relationship_type, tier_level}]}
        supplier_info: {supplier_id: {name, risk_score, ...}}
        max_tier: Maximum depth of propagation

    Returns:
        List of EventImpact dicts
    """
    impacts = []
    visited = set()
    queue = deque()

    base_severity_score = SEVERITY_SCORES.get(initial_severity, 0.5)

    # Seed with directly affected suppliers (tier 0)
    for sid in directly_affected_supplier_ids:
        if sid not in visited:
            queue.append((sid, 0, base_severity_score, [sid]))
            visited.add(sid)

    while queue:
        current_id, tier, severity_score, path = queue.popleft()

        if tier > max_tier:
            continue

        # Calculate financial impact based on supplier risk score and tier
        info = supplier_info.get(current_id, {})
        risk_score = info.get("risk_score", 50)
        financial_multiplier = risk_score / 100 * severity_score
        estimated_financial = financial_multiplier * 100000  # Base $100k per unit
        disruption_days = int(15 * severity_score * (1 + tier * 0.5))

        impacts.append({
            "id": str(uuid.uuid4()),
            "event_id": event_id,
            "impacted_entity_type": "supplier",
            "impacted_entity_id": current_id,
            "impacted_entity_name": info.get("name", f"Supplier {current_id[:8]}"),
            "impact_severity": severity_from_score(severity_score),
            "severity_score": round(severity_score, 3),
            "estimated_disruption_days": disruption_days,
            "estimated_financial_impact": round(estimated_financial, 2),
            "impact_path": path,
            "tier_distance": tier,
        })

        # Propagate to connected suppliers with attenuation
        for edge in supplier_graph.get(current_id, []):
            target_id = edge.get("target_id")
            if target_id and target_id not in visited:
                next_severity = severity_score * TIER_ATTENUATION
                if next_severity >= 0.1:  # Stop propagating negligible impact
                    visited.add(target_id)
                    queue.append((target_id, tier + 1, next_severity, path + [target_id]))

    logger.info(
        "Impact propagation complete",
        event_id=event_id,
        initial_severity=initial_severity,
        directly_affected=len(directly_affected_supplier_ids),
        total_impacted=len(impacts),
        max_tier_reached=max(i["tier_distance"] for i in impacts) if impacts else 0,
    )

    return impacts
