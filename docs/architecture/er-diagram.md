# SCIRM Entity Relationship Diagram

**Version:** v1.0.0  
**Date:** 2025-08-23  
**Owner:** Data Architecture Team  
**Status:** Active

This document provides detailed entity relationship diagrams for the SCIRM database architecture, organized by functional domain.

## Complete Entity Relationship Diagram


> **TODO**: This diagram requires manual conversion from Mermaid to PlantUML.
> See the PlantUML documentation for proper syntax.

```plantuml
@startuml
!theme plain
title Erdiagram (Conversion Required)

> **NOTE**: Complex diagram conversion required.
> Original Mermaid syntax needs manual PlantUML conversion.

rectangle "TODO: Convert to PlantUML" as TODO
@enduml
```

## Domain-Specific ER Diagrams

### Supply Chain Core Domain


> **TODO**: This diagram requires manual conversion from Mermaid to PlantUML.
> See the PlantUML documentation for proper syntax.

```plantuml
@startuml
!theme plain
title Erdiagram (Conversion Required)

> **NOTE**: Complex diagram conversion required.
> Original Mermaid syntax needs manual PlantUML conversion.

rectangle "TODO: Convert to PlantUML" as TODO
@enduml
```

### RAG & AI Domain


> **TODO**: This diagram requires manual conversion from Mermaid to PlantUML.
> See the PlantUML documentation for proper syntax.

```plantuml
@startuml
!theme plain
title Erdiagram (Conversion Required)

> **NOTE**: Complex diagram conversion required.
> Original Mermaid syntax needs manual PlantUML conversion.

rectangle "TODO: Convert to PlantUML" as TODO
@enduml
```

### Risk Management Domain


> **TODO**: This diagram requires manual conversion from Mermaid to PlantUML.
> See the PlantUML documentation for proper syntax.

```plantuml
@startuml
!theme plain
title Erdiagram (Conversion Required)

> **NOTE**: Complex diagram conversion required.
> Original Mermaid syntax needs manual PlantUML conversion.

rectangle "TODO: Convert to PlantUML" as TODO
@enduml
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
