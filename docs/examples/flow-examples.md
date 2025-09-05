# Flow Diagram Examples

This document provides examples of flow diagrams using Mermaid for SCIRM documentation.

## Data Processing Flow

```plantuml
@startuml
rectangle "Data Input" as A
B  --> |Yes| C[Process Data]
B  --> |No| D[Error Handler]
C  -->  E[Transform Data]
E  -->  F[Store in Database]
D  -->  G[Log Error]
G  -->  H[Notify Admin]
note right of A : Color #48dbfb
note right of C : Color #ff9ff3
note right of F : Color #feca57
note right of D : Color #ff6b6b
@enduml
```

## User Authentication Flow

```plantuml
@startuml
left to right direction
rectangle "User Login" as A
B  -->  C{Valid?}
C  --> |Yes| D[Generate JWT]
C  --> |No| E[Return Error]
D  -->  F[Set Session]
F  -->  G[Redirect to Dashboard]
E  -->  H[Show Login Form]
note right of D : Color #48dbfb
note right of G : Color #ff9ff3
note right of E : Color #ff6b6b
@enduml
```

## Risk Assessment Flow

```plantuml
@startuml
rectangle "Risk Event Detected" as A
B  -->  C[AI Risk Analysis]
C  -->  D[Calculate Risk Score]
D  -->  E{High Risk?}
E  --> |Yes| F[Immediate Alert]
E  --> |No| G[Log for Monitoring]
F  -->  H[Notify Stakeholders]
G  -->  I[Update Dashboard]
note right of A : Color #feca57
note right of C : Color #ff9ff3
note right of F : Color #ff6b6b
note right of I : Color #48dbfb
@enduml
```
