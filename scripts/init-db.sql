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

CREATE TABLE IF NOT EXISTS suppliers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES organizations(id),
  supplier_code VARCHAR(100) NOT NULL,
  name VARCHAR(255) NOT NULL,
  supplier_type VARCHAR(50) DEFAULT 'general',
  country_code VARCHAR(3),
  region VARCHAR(100),
  risk_score FLOAT DEFAULT 50.0,
  risk_tier VARCHAR(20) DEFAULT 'medium',
  contact_name VARCHAR(255),
  contact_email VARCHAR(255),
  last_assessment_at TIMESTAMP,
  is_active BOOLEAN DEFAULT TRUE,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMP DEFAULT now(),
  updated_at TIMESTAMP DEFAULT now(),
  UNIQUE(organization_id, supplier_code)
);

CREATE TABLE IF NOT EXISTS agent_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID REFERENCES organizations(id),
  assessment_id UUID REFERENCES risk_assessments(id),
  agent_type VARCHAR(50) NOT NULL,
  status VARCHAR(20) DEFAULT 'running',
  input_summary TEXT,
  output_summary TEXT,
  confidence_score FLOAT,
  cost_usd FLOAT DEFAULT 0.0,
  error_message TEXT,
  started_at TIMESTAMP DEFAULT now(),
  completed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_steps (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL REFERENCES agent_runs(id),
  step_order INT NOT NULL,
  step_type VARCHAR(50) NOT NULL,
  tool_name VARCHAR(100),
  input_data JSONB DEFAULT '{}',
  output_data JSONB DEFAULT '{}',
  execution_time_ms INT,
  token_count INT,
  step_cost_usd FLOAT DEFAULT 0.0,
  created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rag_collections (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID REFERENCES organizations(id),
  collection_name VARCHAR(255) NOT NULL,
  collection_type VARCHAR(50) DEFAULT 'general',
  embedding_model VARCHAR(100) DEFAULT 'text-embedding-3-small',
  vector_dimensions INT DEFAULT 1536,
  document_count INT DEFAULT 0,
  created_at TIMESTAMP DEFAULT now(),
  updated_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rag_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  collection_id UUID NOT NULL REFERENCES rag_collections(id),
  document_name VARCHAR(500) NOT NULL,
  source_url VARCHAR(1000),
  content_hash VARCHAR(64),
  processing_status VARCHAR(20) DEFAULT 'pending',
  chunk_count INT DEFAULT 0,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rag_chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NOT NULL REFERENCES rag_documents(id),
  chunk_text TEXT NOT NULL,
  chunk_order INT NOT NULL,
  chunk_metadata JSONB DEFAULT '{}',
  created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS alerts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID REFERENCES organizations(id),
  risk_id UUID,
  alert_type VARCHAR(50) NOT NULL,
  severity VARCHAR(20) NOT NULL,
  title VARCHAR(500) NOT NULL,
  description TEXT DEFAULT '',
  status VARCHAR(20) DEFAULT 'active',
  acknowledged_by UUID,
  acknowledged_at TIMESTAMP,
  resolved_at TIMESTAMP,
  metadata JSONB DEFAULT '{}',
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


-- ============================================================
-- Seed Data: Suppliers
-- ============================================================

INSERT INTO suppliers (id, organization_id, supplier_code, name, supplier_type, country_code, region, risk_score, risk_tier, contact_name, contact_email)
VALUES
  ('c0000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000001', 'SUP-ALPHA', 'Supplier Alpha', 'api_manufacturer', 'US', 'North America', 35.0, 'low', 'John Smith', 'john@supplier-alpha.com'),
  ('c0000000-0000-0000-0000-000000000002', 'a0000000-0000-0000-0000-000000000001', 'SUP-BETA', 'Supplier Beta', 'excipient_supplier', 'DE', 'Europe', 62.0, 'medium', 'Hans Mueller', 'hans@supplier-beta.de'),
  ('c0000000-0000-0000-0000-000000000003', 'a0000000-0000-0000-0000-000000000001', 'SUP-GAMMA', 'Supplier Gamma', 'packaging', 'CN', 'Asia Pacific', 78.0, 'high', 'Wei Zhang', 'wei@supplier-gamma.cn'),
  ('c0000000-0000-0000-0000-000000000004', 'a0000000-0000-0000-0000-000000000002', 'SUP-DELTA', 'Supplier Delta', 'sensor_components', 'JP', 'Asia Pacific', 28.0, 'low', 'Yuki Tanaka', 'yuki@supplier-delta.jp'),
  ('c0000000-0000-0000-0000-000000000005', 'a0000000-0000-0000-0000-000000000002', 'SUP-EPSILON', 'Supplier Epsilon', 'biocompatible_materials', 'US', 'North America', 55.0, 'medium', 'Sarah Johnson', 'sarah@supplier-epsilon.com')
ON CONFLICT DO NOTHING;
