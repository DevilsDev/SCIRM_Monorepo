# SCIRM documentation

SCIRM monitors a company's suppliers against public records (FDA recalls, warning
letters, import alerts and shortages, and GDACS disaster alerts) and answers questions
about them with citations to those records.

## Guides

- [Importing suppliers from SAP](sap-import.md): upload an LFA1 export; preview before anything is saved.
- [Bedrock (EU) setup](bedrock-setup.md): enable AI-written answers and vector search, EU-only.

## For developers and operators

- [Branching](development/branching.md)
- [Deployment runbook](operations/runbooks/deployment-runbook.md)
- Architecture decisions: [ADR-001](architecture/adr/ADR-001-multi-agent-swarm-architecture.md),
  [ADR-002](architecture/adr/ADR-002-rag-implementation-strategy.md),
  [ADR-003](architecture/adr/ADR-003-secure-github-pages-publishing.md)

Each service's API is described by its OpenAPI spec. The Documentation workflow
generates them and attaches them to every run as the `api-specs` artifact.
