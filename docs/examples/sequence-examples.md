# Sequence Diagram Examples

This document provides examples of sequence diagrams using Mermaid for SCIRM documentation.

## API Request Sequence

```plantuml
@startuml
participant "Client" as Client
participant "Gateway" as Gateway
participant "Auth" as Auth
participant "Service" as Service
participant "Database" as Database
Client -> Gateway: API Request
Gateway -> Auth: Validate Token
Auth --> Gateway: Token Valid
Gateway -> Service: Forward Request
Service -> Database: Query Data
Database --> Service: Return Data
Service --> Gateway: Response
Gateway --> Client: Final Response
@enduml
```

## Agent Execution Sequence

```plantuml
@startuml
participant "User" as User
participant "Coordinator" as Coordinator
participant "Researcher" as Researcher
participant "Executor" as Executor
participant "Database" as Database
User -> Coordinator: Risk Assessment Request
Coordinator -> Researcher: Gather Context
Researcher -> Database: Query Historical Data
Database --> Researcher: Return Data
Researcher --> Coordinator: Context Package
Coordinator -> Executor: Execute Analysis
Executor --> Coordinator: Analysis Results
Coordinator --> User: Risk Assessment
@enduml
```

## Error Handling Sequence

```plantuml
@startuml
participant "Client" as Client
participant "Service" as Service
participant "Database" as Database
participant "Logger" as Logger
Client -> Service: Request
Service -> Database: Query
Database --> Service: Error Response
Service -> Logger: Log Error
Service --> Client: Error Message
Logger -> Logger: Store Error Details
@enduml
```
