# Sequence Diagram Examples

This document provides examples of sequence diagrams using Mermaid for SCIRM documentation.

## API Request Sequence

```mermaid
sequenceDiagram
    participant Client
    participant Gateway
    participant Auth
    participant Service
    participant Database
    
    Client->>Gateway: API Request
    Gateway->>Auth: Validate Token
    Auth-->>Gateway: Token Valid
    Gateway->>Service: Forward Request
    Service->>Database: Query Data
    Database-->>Service: Return Data
    Service-->>Gateway: Response
    Gateway-->>Client: Final Response
```

## Agent Execution Sequence

```mermaid
sequenceDiagram
    participant User
    participant Coordinator
    participant Researcher
    participant Executor
    participant Database
    
    User->>Coordinator: Risk Assessment Request
    Coordinator->>Researcher: Gather Context
    Researcher->>Database: Query Historical Data
    Database-->>Researcher: Return Data
    Researcher-->>Coordinator: Context Package
    Coordinator->>Executor: Execute Analysis
    Executor-->>Coordinator: Analysis Results
    Coordinator-->>User: Risk Assessment
```

## Error Handling Sequence

```mermaid
sequenceDiagram
    participant Client
    participant Service
    participant Database
    participant Logger
    
    Client->>Service: Request
    Service->>Database: Query
    Database-->>Service: Error Response
    Service->>Logger: Log Error
    Service-->>Client: Error Message
    Logger->>Logger: Store Error Details
```
