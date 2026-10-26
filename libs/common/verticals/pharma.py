PHARMA_VERTICAL = {
    "name": "Pharmaceutical & Healthcare",
    "compliance_rules": ["FDA 21 CFR Part 11", "EMA GMP Annex 1", "ICH Q7 API Guidelines", "HIPAA", "WHO Prequalification", "GDP (Good Distribution Practice)", "Drug Supply Chain Security Act (DSCSA)"],
    "mandatory_certifications": ["GMP", "ISO 13485", "FDA registered", "EMA authorized"],
    "risk_weights": {"regulatory": 0.25, "operational": 0.20, "esg": 0.10, "cyber": 0.10, "financial": 0.15, "geopolitical": 0.10, "catastrophic": 0.10},
    "risk_thresholds": {"critical": 80, "high": 60, "medium": 40},
    "kpis": ["Batch release on-time rate", "Regulatory audit pass rate", "API supply continuity", "Cold chain compliance", "Serialization accuracy"],
    "recommendation_templates": {
        "regulatory": ["Conduct FDA pre-approval inspection readiness", "Update GMP documentation", "Implement DSCSA serialization"],
        "quality": ["Add incoming material testing", "Implement statistical process control", "Qualify backup API supplier"],
        "logistics": ["Establish GDP-compliant cold chain routes", "Add temperature monitoring IoT", "Qualify secondary distribution center"],
    },
}
