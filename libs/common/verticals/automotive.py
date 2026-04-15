AUTOMOTIVE_VERTICAL = {
    "name": "Automotive",
    "compliance_rules": ["IATF 16949", "ISO 26262 Functional Safety", "REACH/RoHS", "TISAX (Information Security)", "VDA 6.3 Process Audit"],
    "mandatory_certifications": ["IATF 16949", "ISO 14001", "ISO 45001"],
    "risk_weights": {"operational": 0.25, "financial": 0.20, "geopolitical": 0.15, "catastrophic": 0.15, "regulatory": 0.10, "cyber": 0.10, "esg": 0.05},
    "risk_thresholds": {"critical": 75, "high": 55, "medium": 35},
    "kpis": ["PPM defect rate", "On-time delivery to line", "Tooling availability", "JIT compliance rate", "Recall exposure"],
    "recommendation_templates": {
        "supplier": ["Dual-source critical components", "Implement supplier scorecards", "Conduct VDA 6.3 audits"],
        "logistics": ["Establish JIT buffer stock", "Add GPS tracking for in-transit", "Qualify regional warehousing"],
    },
}
