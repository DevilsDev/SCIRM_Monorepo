ELECTRONICS_VERTICAL = {
    "name": "Electronics & Semiconductors",
    "compliance_rules": ["IPC Standards", "REACH/RoHS/WEEE", "Conflict Minerals (Dodd-Frank 1502)", "Export Control (EAR/ITAR)", "UL/CE Certification"],
    "mandatory_certifications": ["ISO 9001", "IPC-A-610", "UL Listed"],
    "risk_weights": {"geopolitical": 0.25, "operational": 0.20, "financial": 0.15, "catastrophic": 0.15, "cyber": 0.10, "regulatory": 0.10, "esg": 0.05},
    "risk_thresholds": {"critical": 70, "high": 50, "medium": 30},
    "kpis": ["Lead time variability", "Component obsolescence rate", "Counterfeit detection rate", "Yield rate", "Design-to-production cycle"],
    "recommendation_templates": {
        "supplier": ["Qualify last-time-buy alternatives", "Add authorized distributor network", "Implement component lifecycle monitoring"],
        "quality": ["Deploy incoming inspection X-ray", "Add traceability marking", "Implement counterfeit prevention program"],
    },
}
