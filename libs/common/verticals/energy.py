ENERGY_VERTICAL = {
    "name": "Energy & Utilities",
    "compliance_rules": ["NERC CIP", "IEC 62443 (Industrial Cybersecurity)", "EPA Regulations", "OSHA Process Safety", "DOE Order 413.3B", "Nuclear Regulatory Commission (NRC)"],
    "mandatory_certifications": ["ISO 55001 (Asset Management)", "ISO 50001 (Energy Management)", "API Standards"],
    "risk_weights": {"catastrophic": 0.25, "cyber": 0.20, "operational": 0.20, "regulatory": 0.15, "esg": 0.10, "financial": 0.05, "geopolitical": 0.05},
    "risk_thresholds": {"critical": 65, "high": 45, "medium": 25},
    "kpis": ["Grid reliability index", "Safety incident rate", "Emissions compliance", "Asset availability", "Cybersecurity incident rate"],
    "recommendation_templates": {
        "cyber": ["Implement NERC CIP compliance program", "Deploy OT/IT network segmentation", "Add SCADA monitoring"],
        "operational": ["Establish redundant supply routes", "Implement predictive maintenance", "Add emergency response drills"],
    },
}
