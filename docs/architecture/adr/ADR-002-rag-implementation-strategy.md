# ADR-002: RAG Implementation Strategy for Supply Chain Data

**Status**: Accepted  
**Date**: 2025-08-21  
**Categories**: Data & Retrieval, Architecture, Performance & Scalability  
**DRI**: @EngineerLead  

---

## Context & Problem Statement

SCIRM needs to process and retrieve information from diverse supply chain data sources (ERP, IoT sensors, weather APIs, regulatory feeds) while maintaining data freshness, relevance ranking, and compliance with data governance policies.

## Decision

Implement a hybrid RAG (Retrieval-Augmented Generation) system with:
- **Vector Database**: Pinecone for semantic search with 1536-dim embeddings
- **Traditional Search**: Elasticsearch for structured queries and filters
- **Data Pipeline**: Real-time ingestion with staleness budgets
- **Embedding Strategy**: Domain-specific embeddings for supply chain terminology

## Alternatives Considered

### Option A: Pure Vector Search
**Pros**: 
- Excellent semantic matching
- Handles unstructured data well
**Cons**: 
- Poor performance on exact matches
- Expensive for large datasets

### Option B: Traditional Search Only
**Pros**: 
- Fast exact matching
- Lower cost
**Cons**: 
- Poor semantic understanding
- Requires extensive query engineering

### Option C: Knowledge Graph Approach
**Pros**: 
- Rich relationship modeling
- Excellent for complex queries
**Cons**: 
- Complex schema management
- Slow for large-scale retrieval

## Consequences

**Positive**:
- Best-of-both-worlds search capabilities
- Scalable to enterprise data volumes
- Maintains data lineage and freshness

**Negative**:
- Dual system complexity
- Higher infrastructure costs
- Embedding model maintenance overhead

---

## Google SD&D Required Fields

### Rollout Plan & Guardrails
- **Rollout Strategy**: Canary deployment with 10% traffic, gradual increase over 2 weeks
- **Success Criteria**: <200ms retrieval time, >90% relevance score, zero data leaks
- **Rollback Plan**: Fallback to cached responses with degraded functionality
- **Monitoring**: Query performance, embedding quality, data freshness metrics

### Test & Quality Impact
- **Unit Tests**: Embedding generation, vector similarity, query parsing
- **Integration Tests**: End-to-end retrieval workflows, data pipeline validation
- **E2E Tests**: Complete RAG scenarios with supply chain use cases
- **New Quality Gates**: Retrieval relevance >90%, data freshness <1 hour

### Privacy/Security Impact
- **Data Flows**: Encrypted embeddings, anonymized query logs, no PII in vectors
- **Access Controls**: Role-based data access, query audit trails
- **Threat Model**: Embedding inference attacks, query injection, data exfiltration
- **Compliance**: GDPR right-to-deletion support, SOC2 data handling

### Observability & SLOs
- **Metrics**: Query latency, relevance scores, cache hit rates, embedding drift
- **Alerts**: Retrieval failures, data staleness, relevance degradation
- **SLO Impact**: 200ms P95 retrieval time, 99.5% availability
- **Dashboards**: RAG performance dashboard, data freshness monitoring

### Cost/Performance Considerations
- **Cost Impact**: $2000/month for Pinecone, $500/month for Elasticsearch
- **Performance Impact**: 150ms average retrieval time, 95% cache hit rate
- **Resource Usage**: 4GB RAM for embedding service, 100GB vector storage
- **Rate Limits**: 1000 queries/minute per API key

### Dependencies & Migration
- **Dependencies**: Pinecone, Elasticsearch, OpenAI embeddings, Redis cache
- **API Changes**: New retrieval endpoints, enhanced query parameters
- **Migration Plan**: Parallel deployment with gradual traffic shifting
- **Deprecation**: Legacy search endpoints sunset in 6 months

---

## Evidence & Compliance Links

- **Compliance Evidence**: `/compliance/artifacts/2025-08-21-0800/data-governance/`
- **Security Scans**: Data access pattern analysis, embedding security validation
- **Test Results**: RAG performance benchmarks, relevance scoring results
- **Performance Benchmarks**: Sub-200ms retrieval achieved in testing

---

## Related ADRs

- [ADR-001: Multi-Agent Swarm Architecture](./ADR-001-multi-agent-swarm-architecture.md)
- [ADR-004: Data Governance Framework](./ADR-004-data-governance-framework.md)

---

*This ADR follows Google Software Design & Development practices and SCIRM compliance requirements.*
