FOOD_BEVERAGE_VERTICAL = {
    "name": "Food & Beverage",
    "compliance_rules": ["FDA FSMA", "HACCP", "GFSI Standards (BRC/SQF/FSSC 22000)", "EU Food Safety Regulation", "Allergen Management", "Organic/Non-GMO Certification"],
    "mandatory_certifications": ["FSSC 22000", "BRC", "HACCP", "Organic (USDA/EU)"],
    "risk_weights": {"operational": 0.25, "regulatory": 0.20, "esg": 0.15, "catastrophic": 0.15, "financial": 0.10, "geopolitical": 0.10, "cyber": 0.05},
    "risk_thresholds": {"critical": 70, "high": 50, "medium": 30},
    "kpis": ["Food safety incident rate", "Shelf life compliance", "Allergen control accuracy", "Traceability recall speed", "Supplier audit score"],
    "recommendation_templates": {
        "quality": ["Implement HACCP critical control points", "Add allergen testing protocols", "Deploy blockchain traceability"],
        "regulatory": ["Update FSMA preventive controls", "Conduct GFSI gap assessment", "Implement supplier food safety audits"],
    },
}
