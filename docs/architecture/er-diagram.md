# SCIRM Entity Relationship Diagram

**Version:** v1.0.0  
**Date:** 2025-08-23  
**Owner:** Data Architecture Team  
**Status:** Active

This document provides detailed entity relationship diagrams for the SCIRM database architecture, organized by functional domain.

## Complete Entity Relationship Diagram

```mermaid
erDiagram
    org ||--o{ user_account : has
    org ||--o{ supplier : owns
    org ||--o{ facility : manages
    org ||--o{ item : catalogs
    org ||--o{ purchase_order : creates
    org ||--o{ inventory_balance : tracks
    org ||--o{ risk_event : monitors
    org ||--o{ rag_collection : manages
    org ||--o{ agent_run : executes
    org ||--o{ cag_policy : enforces
    
    supplier ||--o{ facility : operates
    supplier ||--o{ purchase_order : receives
    supplier ||--o{ shipment : ships
    supplier ||--o{ risk_event : impacts
    
    purchase_order ||--o{ po_line : contains
    purchase_order ||--o{ shipment : fulfills
    
    item ||--o{ po_line : ordered
    item ||--o{ inventory_balance : stocked
    item ||--o{ risk_event : affects
    
    facility ||--o{ inventory_balance : stores
    facility ||--o{ shipment : origin_destination
    
    shipment ||--o{ shipment_event : tracks
    
    rag_collection ||--o{ rag_document : groups
    rag_document ||--o{ rag_chunk : splits
    rag_chunk ||--|| rag_embedding : has
    
    agent_run ||--o{ agent_step : contains
    agent_run ||--o{ rag_citation : retrieves
    agent_run ||--o{ cag_violation : triggers
    
    cag_policy ||--o{ cag_violation : enforces
    
    user_account ||--o{ purchase_order : creates
    user_account ||--o{ risk_event : reports
    user_account ||--o{ agent_run : initiates
    
    org {
        uuid org_id PK
        varchar org_name
        varchar org_type
        timestamptz created_at
        timestamptz updated_at
        boolean is_active
    }
    
    user_account {
        uuid user_id PK
        uuid org_id FK
        varchar email
        varchar role
        timestamptz created_at
        timestamptz last_login
        boolean is_active
    }
    
    supplier {
        uuid supplier_id PK
        uuid org_id FK
        varchar supplier_code
        varchar supplier_name
        varchar supplier_type
        char country_code
        decimal risk_score
        varchar certification_status
        timestamptz created_at
        timestamptz updated_at
    }
    
    facility {
        uuid facility_id PK
        uuid org_id FK
        uuid supplier_id FK
        varchar facility_code
        varchar facility_name
        varchar address_line1
        varchar city
        char country_code
        decimal latitude
        decimal longitude
        varchar facility_type
        timestamptz created_at
    }
    
    item {
        uuid item_id PK
        uuid org_id FK
        varchar item_code
        varchar item_name
        varchar item_category
        varchar unit_of_measure
        decimal unit_cost
        char currency_code
        boolean is_controlled_substance
        varchar regulatory_class
        timestamptz created_at
    }
    
    purchase_order {
        uuid po_id PK
        uuid org_id FK
        varchar po_number
        uuid supplier_id FK
        varchar po_status
        date order_date
        date requested_delivery_date
        date confirmed_delivery_date
        decimal total_amount
        char currency_code
        uuid created_by FK
        timestamptz created_at
    }
    
    po_line {
        uuid po_line_id PK
        uuid po_id FK
        integer line_number
        uuid item_id FK
        decimal quantity_ordered
        decimal unit_price
        decimal line_total
        decimal quantity_received
        timestamptz created_at
    }
    
    shipment {
        uuid shipment_id PK
        uuid org_id FK
        varchar shipment_number
        uuid po_id FK
        uuid supplier_id FK
        varchar carrier_name
        varchar tracking_number
        varchar shipment_status
        date planned_ship_date
        date actual_ship_date
        date planned_delivery_date
        date actual_delivery_date
        timestamptz created_at
    }
    
    shipment_event {
        uuid event_id PK
        uuid shipment_id FK
        timestamptz event_timestamp
        varchar event_type
        varchar event_location
        text event_description
        decimal latitude
        decimal longitude
        decimal temperature
        timestamptz created_at
    }
    
    inventory_balance {
        uuid balance_id PK
        uuid org_id FK
        uuid facility_id FK
        uuid item_id FK
        date balance_date
        decimal quantity_on_hand
        decimal quantity_allocated
        decimal quantity_available
        decimal unit_cost
        decimal total_value
        timestamptz created_at
    }
    
    risk_event {
        uuid risk_event_id PK
        uuid org_id FK
        varchar event_type
        varchar severity
        varchar event_title
        text event_description
        uuid affected_supplier_id FK
        uuid affected_item_id FK
        uuid affected_shipment_id FK
        date impact_start_date
        date impact_end_date
        decimal estimated_financial_impact
        varchar event_status
        timestamptz detected_at
        timestamptz resolved_at
        uuid created_by FK
        uuid assigned_to FK
    }
    
    rag_collection {
        uuid collection_id PK
        uuid org_id FK
        varchar collection_name
        varchar collection_type
        varchar embedding_model
        integer vector_dimensions
        jsonb governance_tags
        integer retention_days
        timestamptz created_at
    }
    
    rag_document {
        uuid document_id PK
        uuid collection_id FK
        varchar document_name
        varchar document_type
        text source_url
        varchar content_hash
        jsonb metadata
        integer document_size_bytes
        varchar processing_status
        timestamptz processed_at
        timestamptz created_at
    }
    
    rag_chunk {
        uuid chunk_id PK
        uuid document_id FK
        integer chunk_index
        text chunk_text
        jsonb chunk_metadata
        integer token_count
        timestamptz created_at
    }
    
    rag_embedding {
        uuid embedding_id PK
        uuid chunk_id FK
        vector embedding
        varchar embedding_model
        timestamptz created_at
    }
    
    rag_citation {
        uuid citation_id PK
        uuid agent_run_id FK
        uuid chunk_id FK
        decimal similarity_score
        integer rank_position
        boolean used_in_response
        timestamptz created_at
    }
    
    agent_run {
        uuid run_id PK
        uuid org_id FK
        uuid user_id FK
        varchar agent_type
        varchar run_status
        text input_prompt
        text output_response
        decimal confidence_score
        jsonb token_usage
        decimal cost_usd
        timestamptz started_at
        timestamptz completed_at
        text error_message
    }
    
    agent_step {
        uuid step_id PK
        uuid run_id FK
        integer step_number
        varchar step_type
        text step_description
        jsonb input_data
        jsonb output_data
        integer duration_ms
        timestamptz started_at
        timestamptz completed_at
    }
    
    cag_policy {
        uuid policy_id PK
        uuid org_id FK
        varchar policy_name
        varchar policy_type
        jsonb policy_rules
        varchar severity
        boolean is_active
        timestamptz created_at
        timestamptz updated_at
    }
    
    cag_violation {
        uuid violation_id PK
        uuid policy_id FK
        uuid agent_run_id FK
        varchar violation_type
        jsonb violation_details
        varchar severity
        boolean blocked_action
        text remediation_taken
        timestamptz detected_at
        timestamptz resolved_at
    }
```

## Domain-Specific ER Diagrams

### Supply Chain Core Domain

```mermaid
erDiagram
    org ||--o{ supplier : owns
    org ||--o{ item : catalogs
    org ||--o{ purchase_order : creates
    
    supplier ||--o{ facility : operates
    supplier ||--o{ purchase_order : receives
    supplier ||--o{ shipment : ships
    
    purchase_order ||--o{ po_line : contains
    purchase_order ||--o{ shipment : fulfills
    
    item ||--o{ po_line : ordered
    item ||--o{ inventory_balance : stocked
    
    facility ||--o{ inventory_balance : stores
    facility ||--o{ shipment : origin_destination
    
    shipment ||--o{ shipment_event : tracks
    
    supplier {
        uuid supplier_id PK
        uuid org_id FK
        varchar supplier_code
        varchar supplier_name
        varchar supplier_type
        decimal risk_score
    }
    
    purchase_order {
        uuid po_id PK
        uuid org_id FK
        uuid supplier_id FK
        varchar po_status
        date order_date
        decimal total_amount
    }
    
    shipment {
        uuid shipment_id PK
        uuid org_id FK
        uuid po_id FK
        varchar shipment_status
        date planned_delivery_date
        date actual_delivery_date
    }
```

### RAG & AI Domain

```mermaid
erDiagram
    org ||--o{ rag_collection : manages
    org ||--o{ agent_run : executes
    
    rag_collection ||--o{ rag_document : groups
    rag_document ||--o{ rag_chunk : splits
    rag_chunk ||--|| rag_embedding : has
    
    agent_run ||--o{ agent_step : contains
    agent_run ||--o{ rag_citation : retrieves
    
    rag_chunk ||--o{ rag_citation : cited
    
    rag_collection {
        uuid collection_id PK
        uuid org_id FK
        varchar collection_name
        varchar collection_type
        varchar embedding_model
        integer vector_dimensions
    }
    
    rag_embedding {
        uuid embedding_id PK
        uuid chunk_id FK
        vector embedding
        varchar embedding_model
    }
    
    agent_run {
        uuid run_id PK
        uuid org_id FK
        varchar agent_type
        varchar run_status
        decimal confidence_score
        decimal cost_usd
    }
    
    rag_citation {
        uuid citation_id PK
        uuid agent_run_id FK
        uuid chunk_id FK
        decimal similarity_score
        integer rank_position
    }
```

### Risk Management Domain

```mermaid
erDiagram
    org ||--o{ risk_event : monitors
    org ||--o{ cag_policy : enforces
    
    supplier ||--o{ risk_event : impacts
    item ||--o{ risk_event : affects
    shipment ||--o{ risk_event : delays
    
    agent_run ||--o{ cag_violation : triggers
    cag_policy ||--o{ cag_violation : enforces
    
    user_account ||--o{ risk_event : reports
    user_account ||--o{ risk_event : assigned
    
    risk_event {
        uuid risk_event_id PK
        uuid org_id FK
        varchar event_type
        varchar severity
        varchar event_status
        uuid affected_supplier_id FK
        uuid affected_item_id FK
        timestamptz detected_at
    }
    
    cag_policy {
        uuid policy_id PK
        uuid org_id FK
        varchar policy_name
        varchar policy_type
        jsonb policy_rules
        boolean is_active
    }
    
    cag_violation {
        uuid violation_id PK
        uuid policy_id FK
        uuid agent_run_id FK
        varchar violation_type
        varchar severity
        boolean blocked_action
    }
```

## Key Relationships & Constraints

### Primary Relationships

1. **Organization-Centric**: All entities are anchored to `org` for multi-tenancy
2. **Supplier Network**: Suppliers operate facilities and fulfill purchase orders
3. **Order Lifecycle**: Purchase orders contain lines, generate shipments, track events
4. **Knowledge Graph**: RAG collections group documents, split into chunks with embeddings
5. **AI Governance**: Agent runs generate citations and trigger policy violations

### Foreign Key Constraints

```sql
-- Core supply chain relationships
ALTER TABLE supplier ADD CONSTRAINT fk_supplier_org 
    FOREIGN KEY (org_id) REFERENCES org(org_id);
    
ALTER TABLE purchase_order ADD CONSTRAINT fk_po_supplier 
    FOREIGN KEY (supplier_id) REFERENCES supplier(supplier_id);
    
ALTER TABLE po_line ADD CONSTRAINT fk_po_line_po 
    FOREIGN KEY (po_id) REFERENCES purchase_order(po_id);
    
-- RAG relationships
ALTER TABLE rag_document ADD CONSTRAINT fk_rag_doc_collection 
    FOREIGN KEY (collection_id) REFERENCES rag_collection(collection_id);
    
ALTER TABLE rag_chunk ADD CONSTRAINT fk_rag_chunk_doc 
    FOREIGN KEY (document_id) REFERENCES rag_document(document_id);
    
ALTER TABLE rag_embedding ADD CONSTRAINT fk_rag_embedding_chunk 
    FOREIGN KEY (chunk_id) REFERENCES rag_chunk(chunk_id);
    
-- AI governance relationships
ALTER TABLE cag_violation ADD CONSTRAINT fk_violation_policy 
    FOREIGN KEY (policy_id) REFERENCES cag_policy(policy_id);
    
ALTER TABLE cag_violation ADD CONSTRAINT fk_violation_run 
    FOREIGN KEY (agent_run_id) REFERENCES agent_run(run_id);
```

### Unique Constraints

```sql
-- Business key uniqueness within tenant
ALTER TABLE supplier ADD CONSTRAINT uk_supplier_code 
    UNIQUE (org_id, supplier_code);
    
ALTER TABLE purchase_order ADD CONSTRAINT uk_po_number 
    UNIQUE (org_id, po_number);
    
ALTER TABLE rag_collection ADD CONSTRAINT uk_collection_name 
    UNIQUE (org_id, collection_name);
    
-- Prevent duplicate embeddings
ALTER TABLE rag_embedding ADD CONSTRAINT uk_embedding_chunk 
    UNIQUE (chunk_id);
```

---

## Changelog

### v1.0.0 (2025-08-23)
- Initial ER diagram documentation
- Complete entity relationship model
- Domain-specific diagrams for supply chain, RAG, and risk management
- Foreign key constraints and relationship definitions
- Multi-tenant data model with org-centric design
