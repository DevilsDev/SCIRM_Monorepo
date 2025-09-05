# Agent Sequence Diagrams

## Overview

This document provides detailed sequence diagrams for SCIRM's multi-agent orchestration, including the golden path for successful risk assessment and three critical failure scenarios. These diagrams illustrate the interaction patterns between agents, data stores, and external systems.

## Agent Architecture Overview

| Agent | Role | Primary Function | Response Time Target |
|-------|------|------------------|---------------------|
| Coordinator | Meta-agent | Orchestrate workflow, manage state | < 50ms |
| Planner | Context-aware | Analyze query, plan execution | < 200ms |
| Researcher | RAG-powered | Retrieve relevant knowledge | < 300ms |
| Executor | Action-oriented | Generate recommendations | < 400ms |
| Reviewer | Quality assurance | Validate outputs, check compliance | < 100ms |

## Golden Path: Successful Risk Assessment

```mermaid
sequenceDiagram
    participant U as User
    participant C as Coordinator
    participant P as Planner
    participant R as Researcher
    participant E as Executor
    participant V as Reviewer
    participant DB as Database
    participant RAG as RAG Store
    participant CAG as CAG Engine
    
    U->>C: "Assess risk for Supplier ABC shipment delay"
    
    Note over C: Initialize agent run
    C->>DB: Create agent_run record
    C->>P: Plan risk assessment workflow
    
    Note over P: Analyze query context
    P->>DB: Query supplier history
    P->>CAG: Check planning policies
    P->>C: Return execution plan
    
    Note over C: Coordinate research phase
    C->>R: Research supplier risk factors
    R->>RAG: Vector search: "supplier ABC delays"
    RAG-->>R: Relevant documents + citations
    R->>DB: Log research telemetry
    R->>C: Return risk intelligence
    
    Note over C: Generate recommendations
    C->>E: Execute risk mitigation plan
    E->>DB: Query alternative suppliers
    E->>CAG: Check vendor compliance policies
    E->>C: Return recommendations
    
    Note over C: Quality validation
    C->>V: Review output quality
    V->>CAG: Check confidence thresholds
    V->>CAG: Validate PII protection
    V->>DB: Log review metrics
    V->>C: Approve output
    
    Note over C: Finalize response
    C->>DB: Update agent_run status
    C->>U: "Risk: HIGH. Recommend Supplier XYZ. Confidence: 0.85"
    
    Note over U,CAG: Total execution time: ~450ms
```

## Failure Scenario 1: RAG Search Timeout

```mermaid
sequenceDiagram
    participant U as User
    participant C as Coordinator
    participant P as Planner
    participant R as Researcher
    participant E as Executor
    participant V as Reviewer
    participant DB as Database
    participant RAG as RAG Store
    participant CAG as CAG Engine
    
    U->>C: "Assess risk for critical pharmaceutical shipment"
    
    C->>DB: Create agent_run record
    C->>P: Plan risk assessment workflow
    P->>C: Return execution plan
    
    C->>R: Research pharmaceutical regulations
    R->>RAG: Vector search with 5s timeout
    
    Note over RAG: Database overloaded
    RAG--xR: Timeout after 5 seconds
    
    Note over R: Fallback to cached results
    R->>DB: Query cached search results
    R->>C: Return limited intelligence + warning
    
    Note over C: Proceed with degraded data
    C->>E: Execute with fallback data
    E->>CAG: Check confidence policies
    CAG-->>E: Confidence below threshold (0.4)
    
    C->>V: Review low-confidence output
    V->>CAG: Flag for human review
    V->>C: Require manual validation
    
    C->>DB: Log degraded performance
    C->>U: "Partial assessment available. Human review required. Confidence: 0.4"
    
    Note over U,CAG: Graceful degradation in 6.2s
```

## Failure Scenario 2: CAG Policy Violation

```mermaid
sequenceDiagram
    participant U as User
    participant C as Coordinator
    participant P as Planner
    participant R as Researcher
    participant E as Executor
    participant V as Reviewer
    participant DB as Database
    participant RAG as RAG Store
    participant CAG as CAG Engine
    participant SEC as Security Team
    
    U->>C: "Find suppliers in restricted country X"
    
    C->>DB: Create agent_run record
    C->>P: Plan supplier search workflow
    P->>CAG: Check planning policies
    
    Note over CAG: Detect restricted country policy
    CAG->>DB: Log policy violation
    CAG->>SEC: Alert security team
    CAG--xP: Block request - Policy violation
    
    P->>C: Return policy violation error
    
    Note over C: Handle policy violation
    C->>V: Review violation details
    V->>DB: Log compliance event
    V->>C: Confirm violation handling
    
    C->>DB: Update agent_run with violation
    C->>U: "Request blocked: Violates vendor compliance policy"
    
    Note over SEC: Immediate security alert
    SEC->>DB: Review violation details
    SEC->>SEC: Investigate potential threat
    
    Note over U,CAG: Security-first blocking in 150ms
```

## Failure Scenario 3: Database Connection Failure

```mermaid
sequenceDiagram
    participant U as User
    participant C as Coordinator
    participant P as Planner
    participant R as Researcher
    participant E as Executor
    participant V as Reviewer
    participant DB as Database
    participant RAG as RAG Store
    participant CAG as CAG Engine
    participant CACHE as Redis Cache
    
    U->>C: "Get supplier risk scores for dashboard"
    
    C->>DB: Create agent_run record
    
    Note over DB: Database connection lost
    DB--xC: Connection timeout
    
    Note over C: Circuit breaker activated
    C->>CACHE: Check cached data
    CACHE-->>C: Stale supplier data (2h old)
    
    C->>P: Plan with cached context
    P->>CACHE: Use cached policies
    P->>C: Return limited plan
    
    C->>R: Research with cache only
    R->>CACHE: Query cached embeddings
    R->>C: Return cached results + staleness warning
    
    C->>E: Execute with stale data
    E->>CACHE: Generate recommendations
    E->>C: Return results with data age warning
    
    C->>V: Review cache-based output
    V->>CACHE: Log review to cache
    V->>C: Approve with staleness flag
    
    C->>CACHE: Store response in cache
    C->>U: "Risk scores available (data 2h old). Database reconnecting..."
    
    Note over C: Background DB reconnection
    C->>DB: Retry connection (async)
    
    Note over U,CAG: Resilient operation with 800ms delay
```

## Performance Characteristics

### Execution Time Breakdown

| Phase | Golden Path | RAG Timeout | Policy Violation | DB Failure |
|-------|-------------|-------------|------------------|------------|
| Planning | 150ms | 150ms | 100ms | 200ms |
| Research | 250ms | 5000ms | N/A | 300ms |
| Execution | 300ms | 400ms | N/A | 350ms |
| Review | 80ms | 120ms | 50ms | 100ms |
| **Total** | **780ms** | **5670ms** | **150ms** | **950ms** |

### Error Recovery Strategies

```mermaid
graph TD
    A[Agent Error] --> B{Error Type}
    
    B -->|Timeout| C[Circuit Breaker]
    B -->|Policy Violation| D[Security Block]
    B -->|Resource Limit| E[Throttling]
    B -->|Data Corruption| F[Fallback Data]
    
    C --> G[Use Cache]
    C --> H[Reduce Scope]
    
    D --> I[Log Violation]
    D --> J[Alert Security]
    
    E --> K[Queue Request]
    E --> L[Scale Resources]
    
    F --> M[Validate Backup]
    F --> N[Manual Review]
    
    G --> O[Degraded Response]
    H --> O
    I --> P[Blocked Response]
    J --> P
    K --> Q[Delayed Response]
    L --> Q
    M --> R[Backup Response]
    N --> R
```

## Agent Communication Patterns

### Message Types

| Message Type | Source → Target | Purpose | Timeout |
|--------------|-----------------|---------|---------|
| Plan Request | Coordinator → Planner | Initiate workflow planning | 5s |
| Research Query | Coordinator → Researcher | Request knowledge retrieval | 10s |
| Execute Task | Coordinator → Executor | Generate recommendations | 15s |
| Review Output | Coordinator → Reviewer | Validate quality/compliance | 3s |
| Policy Check | Any → CAG Engine | Verify compliance | 1s |

### State Management

```
Agent Run Lifecycle:
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ INITIALIZED │───→│  PLANNING   │───→│ RESEARCHING │
└─────────────┘    └─────────────┘    └─────────────┘
                                              │
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  COMPLETED  │←───│  REVIEWING  │←───│  EXECUTING  │
└─────────────┘    └─────────────┘    └─────────────┘
       │                   │                   │
       ▼                   ▼                   ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   SUCCESS   │    │   FAILED    │    │   BLOCKED   │
└─────────────┘    └─────────────┘    └─────────────┘
```

## Monitoring & Observability

### Key Metrics per Sequence

| Metric | Golden Path Target | Failure Threshold | Alert Level |
|--------|-------------------|-------------------|-------------|
| End-to-end Latency | < 1s | > 5s | Critical |
| Agent Step Success Rate | > 99% | < 95% | Warning |
| CAG Policy Violations | < 0.1% | > 1% | Critical |
| Cache Hit Rate | > 80% | < 50% | Warning |
| Circuit Breaker Trips | < 5/hour | > 20/hour | Critical |

### Distributed Tracing

```
Trace Example (Golden Path):
span_id: abc123 | coordinator.orchestrate | 780ms
  ├─ span_id: def456 | planner.analyze_query | 150ms
  ├─ span_id: ghi789 | researcher.vector_search | 250ms
  │  └─ span_id: jkl012 | rag.similarity_search | 200ms
  ├─ span_id: mno345 | executor.generate_recommendations | 300ms
  │  └─ span_id: pqr678 | cag.check_vendor_policy | 25ms
  └─ span_id: stu901 | reviewer.validate_output | 80ms
     └─ span_id: vwx234 | cag.check_confidence | 15ms
```

---

**Related Documentation:**
- [Performance Architecture](performance.md)
- [CAG Policies](../security/cag-policies.md)
- [Database Architecture](database.md)
- [Observability Metrics](../observability/metrics.md)
