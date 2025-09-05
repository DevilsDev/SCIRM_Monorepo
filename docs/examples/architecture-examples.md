# Architecture Diagram Examples

This document provides examples of architecture diagrams using Mermaid for SCIRM documentation.

## High-Level System Architecture

```plantuml
@startuml
package "Frontend Layer" {
rectangle "React Dashboard" as A
rectangle "Mobile App" as B
}
package "API Layer" {
rectangle "API Gateway" as C
rectangle "Authentication Service" as D
}
package "Business Logic" {
rectangle "Agent Coordinator" as E
rectangle "Risk Engine" as F
rectangle "Data Processor" as G
}
package "Data Layer" {
rectangle "PostgreSQL" as H
rectangle "Vector Store" as I
rectangle "Analytics DB" as J
}
A  -->  C
B  -->  C
C  -->  D
C  -->  E
E  -->  F
E  -->  G
F  -->  H
G  -->  I
G  -->  J
note right of A : Color #48dbfb
note right of C : Color #ff6b6b
note right of E : Color #ff9ff3
note right of H : Color #feca57
@enduml
```

## Microservices Architecture

```plantuml
@startuml
left to right direction
rectangle "Load Balancer" as A
B  -->  C[User Service]
B  -->  D[Supply Chain Service]
B  -->  E[Risk Service]
B  -->  F[AI Agent Service]
C  -->  G[User DB]
D  -->  H[Supply Chain DB]
E  -->  I[Risk DB]
F  -->  J[Vector DB]
note right of B : Color #ff6b6b
note right of F : Color #ff9ff3
@enduml
```
