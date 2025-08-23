# SCIRM Data Flow Architecture

**Version:** v1.0.0  
**Date:** 2025-08-23  
**Owner:** Data Architecture Team  
**Status:** Active

This document details the data flow architecture for SCIRM, showing how data moves through the system from ingestion to AI processing to analytics output.

## High-Level Data Flow

```mermaid
flowchart LR
    A[External Data Sources] --> B[Data Ingestion Layer]
    B --> C[OLTP Database<br/>Postgres/AlloyDB]
    C -->|CDC Pipeline| D[Analytics Warehouse<br/>BigQuery]
    C -->|Document Processing| E[RAG Vector Store<br/>pgvector]
    E -->|Semantic Search| F[AI Agent Swarm]
    F -->|Telemetry| G[CAG Policy Engine]
    F -->|Results| H[Dashboards & APIs]
    G -->|Violations| I[Audit & Compliance]
    D -->|BI Queries| H
    
    subgraph "Data Sources"
        A1[ERP Systems]
        A2[IoT Sensors]
        A3[Supplier APIs]
        A4[Weather/News]
        A1 --> A
        A2 --> A
        A3 --> A
        A4 --> A
    end
    
    subgraph "Processing Layer"
        B1[ETL Pipelines]
        B2[Data Validation]
        B3[Deduplication]
        B --> B1
        B1 --> B2
        B2 --> B3
        B3 --> C
    end
    
    subgraph "AI Layer"
        F1[Coordinator Agent]
        F2[Researcher Agent]
        F3[Executor Agent]
        F --> F1
        F1 --> F2
        F2 --> F3
    end
    
    style C fill:#ff6b6b
    style E fill:#48dbfb
    style D fill:#feca57
    style F fill:#ff9ff3
    style G fill:#54a0ff
```

## Detailed Data Flow by Domain

### Supply Chain Transaction Flow

```mermaid
flowchart TD
    A[ERP Purchase Order] --> B[API Gateway]
    B --> C[Data Validation]
    C --> D[OLTP: purchase_order table]
    D --> E[OLTP: po_line table]
    
    F[Supplier Shipment Notice] --> B
    B --> G[Shipment Processing]
    G --> H[OLTP: shipment table]
    H --> I[OLTP: shipment_event table]
    
    J[IoT Tracking Data] --> K[Real-time Stream]
    K --> L[Event Processing]
    L --> I
    
    D --> M[CDC Pipeline]
    H --> M
    M --> N[BigQuery: fact_orders]
    M --> O[BigQuery: fact_shipments]
    
    style D fill:#ff6b6b
    style H fill:#ff6b6b
    style N fill:#feca57
    style O fill:#feca57
```

### RAG Knowledge Processing Flow

```mermaid
flowchart TD
    A[Document Upload] --> B[Document Parser]
    B --> C[Text Extraction]
    C --> D[Chunking Strategy]
    D --> E[OLTP: rag_chunk table]
    
    E --> F[Embedding Generation]
    F --> G[OpenAI API]
    G --> H[Vector Storage]
    H --> I[OLTP: rag_embedding table]
    
    J[Agent Query] --> K[Vector Search]
    K --> I
    I --> L[Similarity Matching]
    L --> M[Retrieved Chunks]
    M --> N[Agent Context]
    
    N --> O[OLTP: rag_citation table]
    
    style E fill:#ff6b6b
    style I fill:#48dbfb
    style O fill:#ff6b6b
```

### AI Agent Execution Flow

```mermaid
flowchart TD
    A[User Request] --> B[Coordinator Agent]
    B --> C[OLTP: agent_run table]
    C --> D[Task Planning]
    D --> E[OLTP: agent_step table]
    
    E --> F[Researcher Agent]
    F --> G[RAG Retrieval]
    G --> H[Context Assembly]
    
    H --> I[Executor Agent]
    I --> J[LLM Processing]
    J --> K[Response Generation]
    
    K --> L[Reviewer Agent]
    L --> M[Quality Check]
    M --> N[CAG Policy Check]
    
    N --> O{Policy Violation?}
    O -->|Yes| P[OLTP: cag_violation table]
    O -->|No| Q[Final Response]
    
    P --> R[Block/Log Action]
    Q --> S[User Interface]
    
    C --> T[Telemetry Collection]
    T --> U[Cost Tracking]
    U --> V[BigQuery: fact_agent_costs]
    
    style C fill:#ff6b6b
    style P fill:#ff6b6b
    style V fill:#feca57
```

## Data Processing Patterns

### Change Data Capture (CDC) Pipeline

```mermaid
sequenceDiagram
    participant OLTP as OLTP Database
    participant CDC as CDC Service
    participant BQ as BigQuery
    participant Monitor as Monitoring
    
    OLTP->>CDC: Row Change Event
    CDC->>CDC: Transform Data
    CDC->>BQ: Upsert Fact Table
    BQ-->>CDC: Acknowledgment
    CDC->>Monitor: Log Success/Failure
    
    Note over CDC,BQ: Batch processing every 5 minutes
    Note over OLTP,CDC: Debezium connector for real-time CDC
```

### Real-time Risk Event Processing

```mermaid
sequenceDiagram
    participant External as External API
    participant Stream as Kafka Stream
    participant Processor as Risk Processor
    participant OLTP as OLTP Database
    participant Alert as Alert Service
    
    External->>Stream: Risk Event Data
    Stream->>Processor: Event Message
    Processor->>Processor: Risk Scoring
    Processor->>OLTP: Insert risk_event
    OLTP->>Alert: Trigger Notification
    Alert->>Alert: Send to Users
```

### Vector Embedding Pipeline

```mermaid
sequenceDiagram
    participant Upload as Document Upload
    participant Parser as Document Parser
    participant Chunker as Text Chunker
    participant Embedder as Embedding Service
    participant Vector as Vector Store
    
    Upload->>Parser: PDF/DOCX File
    Parser->>Chunker: Extracted Text
    Chunker->>Embedder: Text Chunks
    Embedder->>Embedder: Generate Embeddings
    Embedder->>Vector: Store Vectors
    Vector-->>Embedder: Confirmation
```

## Data Quality & Governance Flow

### Data Lineage Tracking

```mermaid
flowchart LR
    A[Source System] --> B[Ingestion Job]
    B --> C[Transformation]
    C --> D[Target Table]
    
    B --> E[Lineage Tracker]
    C --> E
    D --> E
    E --> F[OLTP: data_lineage table]
    
    F --> G[Lineage API]
    G --> H[Data Catalog UI]
    
    style F fill:#ff6b6b
    style H fill:#54a0ff
```

### PII Data Handling Flow

```mermaid
flowchart TD
    A[PII Data Input] --> B[PII Detection]
    B --> C{Contains PII?}
    C -->|Yes| D[KMS Encryption]
    C -->|No| E[Standard Processing]
    
    D --> F[OLTP: pii_contact table]
    E --> G[Standard Tables]
    
    H[Data Access Request] --> I[Decrypt with KMS]
    I --> F
    F --> J[Decrypted PII]
    
    style F fill:#ff6b6b
    style D fill:#54a0ff
    style I fill:#54a0ff
```

## Performance Optimization Patterns

### Read Replica Strategy

```mermaid
flowchart LR
    A[Write Operations] --> B[Primary Database]
    B --> C[Async Replication]
    C --> D[Read Replica 1]
    C --> E[Read Replica 2]
    
    F[Analytics Queries] --> D
    G[Agent RAG Queries] --> E
    H[Dashboard Queries] --> D
    
    style B fill:#ff6b6b
    style D fill:#48dbfb
    style E fill:#48dbfb
```

### Caching Strategy

```mermaid
flowchart TD
    A[API Request] --> B{Cache Hit?}
    B -->|Yes| C[Return Cached Data]
    B -->|No| D[Query Database]
    D --> E[Update Cache]
    E --> F[Return Fresh Data]
    
    G[Cache Invalidation] --> H[TTL Expiry]
    G --> I[Data Change Event]
    H --> J[Remove from Cache]
    I --> J
    
    style B fill:#feca57
    style E fill:#feca57
```

## Monitoring & Observability Flow

### Data Pipeline Monitoring

```mermaid
flowchart LR
    A[Data Pipeline] --> B[Metrics Collection]
    B --> C[Prometheus]
    C --> D[Grafana Dashboard]
    
    A --> E[Log Collection]
    E --> F[Elasticsearch]
    F --> G[Kibana]
    
    A --> H[Trace Collection]
    H --> I[Jaeger]
    
    C --> J[Alert Manager]
    J --> K[PagerDuty/Slack]
    
    style C fill:#ff9ff3
    style F fill:#48dbfb
    style I fill:#feca57
```

### Data Quality Monitoring

```mermaid
flowchart TD
    A[Data Ingestion] --> B[Quality Checks]
    B --> C{Quality Pass?}
    C -->|Yes| D[Continue Processing]
    C -->|No| E[Quarantine Data]
    
    E --> F[Data Quality Alert]
    F --> G[Data Team Notification]
    
    B --> H[Quality Metrics]
    H --> I[Quality Dashboard]
    
    style E fill:#ff6b6b
    style I fill:#54a0ff
```

## Disaster Recovery Flow

### Backup & Recovery Strategy

```mermaid
sequenceDiagram
    participant Primary as Primary DB
    participant Backup as Backup Service
    participant Storage as Cloud Storage
    participant Recovery as Recovery Process
    
    Primary->>Backup: Continuous WAL Shipping
    Backup->>Storage: Store WAL Files
    
    Note over Primary,Storage: Point-in-Time Recovery Available
    
    Recovery->>Storage: Retrieve WAL Files
    Storage-->>Recovery: WAL Data
    Recovery->>Recovery: Restore to Point-in-Time
    Recovery->>Primary: New Primary Instance
```

---

## Data Flow Metrics & SLAs

### Processing Latencies
- **OLTP Writes**: < 50ms p95
- **CDC Pipeline**: < 5 minutes end-to-end
- **Vector Search**: < 200ms p95
- **Agent Execution**: < 30 seconds p95

### Data Freshness SLAs
- **Real-time Events**: < 1 minute
- **Analytics Data**: < 15 minutes
- **RAG Embeddings**: < 1 hour
- **Risk Assessments**: < 5 minutes

### Throughput Targets
- **Transactions/sec**: 1,000 TPS sustained
- **Documents/hour**: 10,000 processed
- **Agent Runs/minute**: 100 concurrent
- **API Requests/sec**: 5,000 RPS

---

## Changelog

### v1.0.0 (2025-08-23)
- Initial data flow architecture documentation
- High-level and detailed flow diagrams
- Processing patterns for CDC, real-time events, and vector embeddings
- Data quality and governance flows
- Performance optimization patterns
- Monitoring and disaster recovery flows
- SLA definitions and metrics
