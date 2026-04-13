-- SCIRM Database Initialization Script
-- Creates the database and extensions, then seeds initial data.

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- Schema: Enums
-- ============================================================
DO $$ BEGIN
  CREATE TYPE assessment_status AS ENUM ('pending', 'processing', 'completed', 'failed');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE risk_severity AS ENUM ('low', 'medium', 'high', 'critical');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE approval_status AS ENUM ('approved', 'conditional', 'rejected');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ============================================================
-- Schema: Tables
-- ============================================================
CREATE TABLE IF NOT EXISTS organizations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(255) NOT NULL,
  industry VARCHAR(100) NOT NULL,
  supply_chain_profile JSONB DEFAULT '{}',
  risk_tolerance JSONB DEFAULT '{}',
  compliance_requirements TEXT[] DEFAULT '{}',
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP DEFAULT now(),
  updated_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email VARCHAR(255) UNIQUE NOT NULL,
  name VARCHAR(255) NOT NULL,
  hashed_password VARCHAR(255) NOT NULL,
  roles TEXT[] DEFAULT '{}',
  organization_id UUID REFERENCES organizations(id),
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP DEFAULT now(),
  updated_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS risk_assessments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id VARCHAR(64) UNIQUE NOT NULL,
  organization_id UUID REFERENCES organizations(id),
  user_id UUID REFERENCES users(id),
  status assessment_status DEFAULT 'pending',
  assessment_type VARCHAR(50) DEFAULT 'comprehensive',
  request_payload JSONB DEFAULT '{}',
  confidence_score FLOAT,
  reasoning_trail JSONB DEFAULT '[]',
  metadata JSONB DEFAULT '{}',
  error_message TEXT,
  started_at TIMESTAMP,
  completed_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS risks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  assessment_id UUID NOT NULL REFERENCES risk_assessments(id),
  title VARCHAR(500) NOT NULL,
  description TEXT NOT NULL,
  severity risk_severity NOT NULL,
  probability FLOAT NOT NULL,
  impact_score FLOAT NOT NULL,
  affected_entities TEXT[] DEFAULT '{}',
  risk_category VARCHAR(100) DEFAULT '',
  detected_at TIMESTAMP DEFAULT now(),
  predicted_occurrence VARCHAR(255),
  data_sources TEXT[] DEFAULT '{}',
  created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS recommendations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  assessment_id UUID NOT NULL REFERENCES risk_assessments(id),
  risk_id UUID REFERENCES risks(id),
  title VARCHAR(500) NOT NULL,
  description TEXT NOT NULL,
  action_type VARCHAR(50) DEFAULT 'preventive',
  priority VARCHAR(20) DEFAULT 'medium',
  estimated_cost FLOAT,
  estimated_impact FLOAT DEFAULT 5.0,
  timeline_days INT,
  resources_required TEXT[] DEFAULT '{}',
  success_probability FLOAT DEFAULT 0.5,
  created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS quality_reviews (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  assessment_id UUID UNIQUE NOT NULL REFERENCES risk_assessments(id),
  overall_quality_score FLOAT DEFAULT 0.0,
  approval_status approval_status DEFAULT 'conditional',
  validation_results JSONB DEFAULT '{}',
  compliance_check JSONB DEFAULT '{}',
  recommendations_review JSONB DEFAULT '{}',
  review_summary TEXT DEFAULT '',
  reasoning TEXT DEFAULT '',
  confidence_score FLOAT DEFAULT 0.0,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS quality_issues (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  review_id UUID NOT NULL REFERENCES quality_reviews(id),
  severity VARCHAR(20) DEFAULT 'medium',
  category VARCHAR(50) DEFAULT 'completeness',
  description TEXT DEFAULT '',
  affected_item_id VARCHAR(64) DEFAULT '',
  affected_item_type VARCHAR(20) DEFAULT 'risk',
  suggested_action TEXT DEFAULT '',
  created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID,
  action VARCHAR(100) NOT NULL,
  resource_type VARCHAR(50) NOT NULL,
  resource_id VARCHAR(64),
  details JSONB DEFAULT '{}',
  ip_address VARCHAR(45),
  created_at TIMESTAMP DEFAULT now()
);

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
