-- SCIRM Database Initialization Script
-- Creates the database and extensions, then seeds initial data.

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- Seed Data: Organizations
-- ============================================================

INSERT INTO organizations (id, name, industry, supply_chain_profile, risk_tolerance, compliance_requirements)
VALUES
  (
    'a0000000-0000-0000-0000-000000000001',
    'PharmaCorp International',
    'pharmaceutical',
    '{
      "primary_suppliers": ["supplier-alpha", "supplier-beta", "supplier-gamma"],
      "critical_materials": ["api-compound-x", "excipient-y", "packaging-z"],
      "manufacturing_sites": ["usa-east", "europe-central", "asia-pacific"],
      "distribution_channels": ["retail", "hospital", "online", "government"]
    }',
    '{"financial": 0.3, "operational": 0.2, "regulatory": 0.1, "reputational": 0.15}',
    ARRAY['FDA', 'EMA', 'GMP', 'GDP', 'HIPAA', 'SOC2']
  ),
  (
    'a0000000-0000-0000-0000-000000000002',
    'MedTech Solutions',
    'healthcare',
    '{
      "primary_suppliers": ["supplier-delta", "supplier-epsilon"],
      "critical_materials": ["sensor-components", "biocompatible-materials"],
      "manufacturing_sites": ["usa-west", "europe-north"],
      "distribution_channels": ["hospital", "clinic", "online"]
    }',
    '{"financial": 0.35, "operational": 0.25, "regulatory": 0.1, "reputational": 0.2}',
    ARRAY['FDA', 'HIPAA', 'ISO-13485', 'CE-Mark']
  ),
  (
    'a0000000-0000-0000-0000-000000000003',
    'Global Manufacturing Co',
    'manufacturing',
    '{
      "primary_suppliers": ["supplier-zeta", "supplier-eta", "supplier-theta"],
      "critical_materials": ["steel-alloy", "electronic-components", "polymers"],
      "manufacturing_sites": ["usa-central", "asia-east", "south-america"],
      "distribution_channels": ["wholesale", "retail", "direct"]
    }',
    '{"financial": 0.4, "operational": 0.3, "regulatory": 0.2, "reputational": 0.25}',
    ARRAY['ISO-9001', 'SOC2']
  )
ON CONFLICT DO NOTHING;


-- ============================================================
-- Seed Data: Users (password = "scirm-dev-2026" hashed with bcrypt)
-- ============================================================

INSERT INTO users (id, email, name, hashed_password, roles, organization_id)
VALUES
  (
    'b0000000-0000-0000-0000-000000000001',
    'sarah.chen@pharmacorp.com',
    'Sarah Chen',
    '$2b$12$LJ3m5ZQxPxE5tQxKqG5pXOqEwQG1jNqIvHO.QJ5fNqXL5Z4J5X5bK',
    ARRAY['admin', 'analyst'],
    'a0000000-0000-0000-0000-000000000001'
  ),
  (
    'b0000000-0000-0000-0000-000000000002',
    'marcus.rodriguez@pharmacorp.com',
    'Marcus Rodriguez',
    '$2b$12$LJ3m5ZQxPxE5tQxKqG5pXOqEwQG1jNqIvHO.QJ5fNqXL5Z4J5X5bK',
    ARRAY['analyst'],
    'a0000000-0000-0000-0000-000000000001'
  ),
  (
    'b0000000-0000-0000-0000-000000000003',
    'lisa.park@medtech.com',
    'Lisa Park',
    '$2b$12$LJ3m5ZQxPxE5tQxKqG5pXOqEwQG1jNqIvHO.QJ5fNqXL5Z4J5X5bK',
    ARRAY['admin', 'analyst'],
    'a0000000-0000-0000-0000-000000000002'
  ),
  (
    'b0000000-0000-0000-0000-000000000004',
    'auditor@scirm.dev',
    'SCIRM Auditor',
    '$2b$12$LJ3m5ZQxPxE5tQxKqG5pXOqEwQG1jNqIvHO.QJ5fNqXL5Z4J5X5bK',
    ARRAY['auditor', 'viewer'],
    NULL
  )
ON CONFLICT DO NOTHING;
