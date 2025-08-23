# SCIRM Documentation

Welcome to the SCIRM (Supply Chain Intelligence & Risk Management) documentation portal.

## Quick Navigation

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } **Getting Started**

    ---

    New to SCIRM? Start here for an overview and quick introduction.

    [:octicons-arrow-right-24: Platform Overview](intro/overview.md)
    [:octicons-arrow-right-24: Getting Started Guide](intro/getting-started.md)

-   :material-cog:{ .lg .middle } **Architecture**

    ---

    Technical system design and multi-agent architecture details.

    [:octicons-arrow-right-24: System Overview](architecture/system-overview.md)
    [:octicons-arrow-right-24: Multi-Agent Architecture](architecture/agents.md)

-   :material-file-document:{ .lg .middle } **Product Documentation**

    ---

    Business requirements, design documents, and governance.

    [:octicons-arrow-right-24: Product Requirements (PRD)](product/prd.md)
    [:octicons-arrow-right-24: Product Design (PDD)](product/pdd.md)
    [:octicons-arrow-right-24: Anti-Patterns & Governance](product/anti-patterns.md)

-   :material-shield-check:{ .lg .middle } **Security & Compliance**

    ---

    Security principles, compliance frameworks, and best practices.

    [:octicons-arrow-right-24: Security Overview](security/security-overview.md)
    [:octicons-arrow-right-24: Architecture Decisions](architecture/adr/index.md)

</div>

## What is SCIRM?

SCIRM is an AI-powered platform that provides intelligent, real-time supply chain risk management through a coordinated swarm of specialized AI agents. The platform delivers sub-500ms risk assessments with explainable recommendations, helping organizations proactively identify and mitigate supply chain disruptions.

### Key Capabilities

- **Real-Time Risk Assessment**: Sub-500ms response times for critical supply chain alerts
- **Explainable AI**: All recommendations include reasoning trails and confidence scores  
- **Multi-Agent Intelligence**: Five specialized AI agents working in coordination
- **Enterprise Security**: SOC2, GDPR, HIPAA compliance with comprehensive audit trails
- **Industry Focus**: Initially targeting pharmaceutical & healthcare with extensibility

### Platform Architecture

SCIRM implements a multi-agent swarm architecture:

1. **Coordinator Agent** - Orchestrates workflow and agent collaboration
2. **Planner Agent (CAG)** - Maintains organizational context and priorities  
3. **Researcher Agent (RAG)** - Fetches and ranks real-time data from multiple sources
4. **Executor Agent** - Generates actionable risk mitigation recommendations
5. **Quality Reviewer Agent** - Validates outputs and assigns confidence scores

## Documentation Sections

### :material-play-circle: Introduction
- [Platform Overview](intro/overview.md) - What is SCIRM and why use it
- [Getting Started](intro/getting-started.md) - Quick introduction to key concepts

### :material-file-document: Product Documentation  
- [Product Requirements Document (PRD)](product/prd.md) - Business goals and feature requirements
- [Product Design Document (PDD)](product/pdd.md) - Technical implementation details
- [Anti-Patterns & Governance](product/anti-patterns.md) - Governance guardrails and what to avoid

### :material-sitemap: Architecture
- [System Overview](architecture/system-overview.md) - High-level system architecture and data flows
- [Multi-Agent Architecture](architecture/agents.md) - Detailed AI agent specifications
- [Architecture Decision Records](architecture/adr/index.md) - Design decisions and technical rationale

### :material-shield-check: Security & Compliance
- [Security Overview](security/security-overview.md) - Security principles and compliance frameworks

### :material-map: Planning & Development
- [Roadmap](roadmap/README.md) - Development roadmap and future plans
- [Changelog](changelog/README.md) - Release notes and version history

### :material-help-circle: Support
- [Support Resources](support/README.md) - FAQ, troubleshooting, and getting help

## Performance Metrics

- **Response Time**: <500ms for risk assessments
- **Prediction Accuracy**: 85%+ across all risk categories
- **System Availability**: 99.9% uptime SLA
- **Concurrent Users**: 10,000+ simultaneous requests supported

## Technology Stack

- **AI/ML**: Python, FastAPI, LangChain, LangGraph, GPT-4/Claude
- **Data**: Vector databases, Elasticsearch, real-time streaming
- **Frontend**: React/Next.js with modern UI components
- **Infrastructure**: Kubernetes, cloud-native deployment
- **Monitoring**: Prometheus, Grafana, comprehensive observability

---

*Documentation automatically updated with each release. For technical support, see [Support Resources](support/README.md).*

