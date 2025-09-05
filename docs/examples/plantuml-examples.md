# PlantUML Examples for SCIRM Documentation

This page provides copy-pasteable PlantUML examples for common diagram types in SCIRM documentation.

## Flow Diagrams

### Basic Architecture Flow

```plantuml
@startuml
left to right direction
rectangle "React Dashboard" as UI
rectangle "API Gateway" as API
rectangle "Agent Coordinator" as COORD
rectangle "Vector Database" as VDB

UI --> API : HTTP/REST
API --> COORD : Internal API
COORD --> VDB : Query/Store
@enduml
```

### Supply Chain Flow

```plantuml
@startuml
left to right direction
rectangle "Supplier Data" as SUP
rectangle "Risk Engine" as RISK
rectangle "Alert System" as ALERT
rectangle "Dashboard" as DASH

SUP --> RISK : Real-time feeds
RISK --> ALERT : Risk detected
RISK --> DASH : Risk scores
ALERT --> DASH : Notifications
@enduml
```

## Sequence Diagrams

### Agent Orchestration

```plantuml
@startuml
actor User
participant "Coordinator" as C
participant "Planner" as P
participant "Researcher (RAG)" as R
participant "Executor" as E

User -> C: Ask question
C -> P: Plan task
P --> C: Task plan
C -> R: Retrieve context
R --> C: Context + citations
C -> E: Execute with context
E --> C: Recommendations
C --> User: Results + explanations
@enduml
```

### Risk Assessment Flow

```plantuml
@startuml
participant "Data Ingestion" as DI
participant "Risk Engine" as RE
participant "CAG Policies" as CAG
participant "Alert Manager" as AM
participant "Dashboard" as DASH

DI -> RE: Supply chain data
RE -> CAG: Validate output
CAG --> RE: Policy check result
alt Policy violation
    RE -> AM: Critical alert
    AM -> DASH: Immediate notification
else Normal flow
    RE -> DASH: Risk update
end
@enduml
```

## Entity Relationship Diagrams

### Core Data Model

```plantuml
@startuml
entity Supplier {
  * supplier_id : UUID
  --
  name : VARCHAR
  country : VARCHAR
  risk_score : DECIMAL
}

entity Item {
  * item_id : UUID
  --
  name : VARCHAR
  category : VARCHAR
  supplier_id : UUID
}

entity RiskEvent {
  * event_id : UUID
  --
  event_type : VARCHAR
  severity : VARCHAR
  detected_at : TIMESTAMP
  supplier_id : UUID
}

Supplier ||--o{ Item : provides
Supplier ||--o{ RiskEvent : experiences
@enduml
```

## Component Diagrams

### Multi-Agent Architecture

```plantuml
@startuml
package "SCIRM Platform" {
  component "API Gateway" as API
  component "Agent Coordinator" as COORD
  
  package "AI Agents" {
    component "Planner Agent" as PLAN
    component "Researcher Agent" as RESEARCH
    component "Executor Agent" as EXEC
    component "Reviewer Agent" as REVIEW
  }
  
  package "Data Layer" {
    database "PostgreSQL" as PG
    database "Vector Store" as VECTOR
    database "Time Series" as TS
  }
}

API --> COORD
COORD --> PLAN
COORD --> RESEARCH
COORD --> EXEC
COORD --> REVIEW

RESEARCH --> VECTOR
EXEC --> PG
REVIEW --> TS
@enduml
```

## Deployment Diagrams

### Infrastructure Overview

```plantuml
@startuml
node "Load Balancer" as LB
node "Kubernetes Cluster" as K8S {
  component "API Pods" as API
  component "Agent Pods" as AGENTS
  component "Worker Pods" as WORKERS
}

database "PostgreSQL\n(Primary)" as PG1
database "PostgreSQL\n(Replica)" as PG2
database "Vector DB\n(Pinecone)" as VDB

cloud "External APIs" as EXT

LB --> API
API --> AGENTS
AGENTS --> WORKERS
WORKERS --> PG1
PG1 --> PG2 : Replication
AGENTS --> VDB
WORKERS --> EXT
@enduml
```

## Styling Guidelines

### Color Schemes

Use consistent colors for component types:

```plantuml
@startuml
rectangle "Frontend" as FE #lightblue
rectangle "API Layer" as API #lightgreen
rectangle "Business Logic" as BL #lightyellow
rectangle "Database" as DB #lightcoral

FE --> API
API --> BL
BL --> DB
@enduml
```

### Notes and Documentation

Add explanatory notes to complex diagrams:

```plantuml
@startuml
rectangle "Risk Engine" as RE
rectangle "Alert System" as AS

RE --> AS
note right of AS : Sends notifications\nvia Slack, email,\nand dashboard
note left of RE : Processes 10K+\nevents per minute
@enduml
```

## Best Practices

1. **Direction**: Use `left to right direction` for wide architecture diagrams
2. **Grouping**: Use `package` or `node` to group related components
3. **Naming**: Use descriptive aliases (`as ALIAS`) for readability
4. **Documentation**: Add notes for complex interactions
5. **Consistency**: Use the same component names across diagrams

## Conversion from Mermaid

If converting from Mermaid:
- `graph LR` → `@startuml` + `left to right direction`
- `A-->B` → `A --> B`
- `subgraph "X"` → `package "X" { ... }`
- `style A fill:#color` → Add as note or use PlantUML skinparam
