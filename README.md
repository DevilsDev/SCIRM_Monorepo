# SCIRM: AI-Powered Supply Chain Risk Management Platform

[![CI](https://github.com/DevilsDev/SCIRM_Monorepo/workflows/CI/badge.svg)](https://github.com/DevilsDev/SCIRM_Monorepo/actions)
[![Documentation](https://github.com/DevilsDev/SCIRM_Monorepo/workflows/Documentation/badge.svg)](https://devilsdev.github.io/SCIRM_Monorepo/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Overview

SCIRM is an intelligent agent swarm system that proactively predicts, monitors, and mitigates supply chain risks through real-time data analysis and AI-driven recommendations. The platform integrates Context-Augmented Generation (CAG) for organizational insights and Retrieval-Augmented Generation (RAG) for live data processing.

### Key Features
- **Multi-Agent Swarm Architecture**: Coordinated AI agents for specialized risk management tasks
- **Real-Time Risk Prediction**: Sub-500ms response times for critical supply chain alerts
- **Explainable AI**: All recommendations include reasoning trails and confidence scores
- **Industry Focus**: Initially targeting pharmaceutical & healthcare with extensibility
- **Compliance Ready**: SOC2, GDPR, HIPAA alignment with audit trails

## Agent Swarm Architecture

- **Coordinator Agent**: Orchestrates agent collaboration and monitors task state
- **Planner Agent (CAG)**: Maintains organizational context and priorities
- **Researcher Agent (RAG)**: Fetches and ranks real-time data from multiple sources
- **Executor Agent**: Generates actionable risk mitigation recommendations
- **Quality Reviewer Agent**: Validates outputs and assigns confidence scores

## Technology Stack

- **Backend/AI**: Python, FastAPI, LangChain, LangGraph, GPT-4/Claude
- **Vector DB**: Pinecone/Weaviate for embeddings, Elasticsearch for search
- **Frontend**: React/Next.js, Tailwind CSS, Chart.js/D3.js
- **Infrastructure**: Docker, Kubernetes, AWS/Azure/GCP
- **Monitoring**: Prometheus, Grafana, structured logging

## Repository Structure

```
SCIRM_Monorepo/
├── apps/                    # Frontend and API gateway
│   ├── frontend/           # React dashboard
│   └── api-gateway/        # FastAPI gateway
├── services/               # Agent microservices
│   ├── coordinator/        # Meta-agent orchestration
│   ├── planner/           # CAG context agent
│   ├── researcher/        # RAG data agent
│   ├── executor/          # Action recommendation agent
│   └── reviewer/          # Quality validation agent
├── libs/                  # Shared libraries
│   ├── common/           # Utilities and types
│   ├── rag/              # RAG implementation
│   └── cag/              # CAG implementation
├── data/                 # Fixtures and seeds
├── infra/                # Infrastructure as Code
├── ops/                  # CI/CD and monitoring
├── docs/                 # MkDocs documentation
└── tests/                # Integration tests
```

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- Docker & Docker Compose
- Make

### Development Setup

```bash
# Clone repository
git clone https://github.com/DevilsDev/SCIRM_Monorepo.git
cd SCIRM_Monorepo

# Install dependencies
make install

# Start development environment
make dev

# Run tests
make test

# Build documentation
make docs
```

### Environment Configuration

```bash
# Copy environment template
cp .env.example .env

# Configure required variables
# - OpenAI/Anthropic API keys
# - Vector database credentials
# - External data source APIs
```

## Data Sources

### Internal Systems
- ERP systems (SAP, Oracle)
- Warehouse Management Systems (WMS)
- Transportation Management Systems (TMS)
- IoT sensor networks

### External Sources
- Weather and climate data
- Logistics and shipping APIs
- Regulatory and compliance feeds
- Market and economic indicators

## Risk Management Capabilities

- **Supplier Risk Assessment**: Financial stability, geopolitical factors
- **Logistics Disruption Prediction**: Weather, traffic, port congestion
- **Regulatory Compliance Monitoring**: FDA, EMA, customs requirements
- **Demand Forecasting**: Market trends, seasonal patterns
- **Quality Control**: Product recalls, contamination risks

## Monitoring & Observability

- **Performance Metrics**: Response times, throughput, error rates
- **Business Metrics**: Risk prediction accuracy, mitigation effectiveness
- **System Health**: Service availability, resource utilization
- **Audit Trails**: Decision logs, data lineage, compliance reports

## Security & Compliance

- **Authentication**: OAuth2/JWT with RBAC
- **Data Protection**: TLS encryption, secrets management
- **Compliance**: SOC2, GDPR, HIPAA frameworks
- **Audit Logging**: Immutable decision trails

## Documentation

- [Architecture Overview](https://devilsdev.github.io/SCIRM_Monorepo/architecture/)
- [API Reference](https://devilsdev.github.io/SCIRM_Monorepo/api/)
- [Deployment Guide](https://devilsdev.github.io/SCIRM_Monorepo/deployment/)
- [User Manual](https://devilsdev.github.io/SCIRM_Monorepo/user-guide/)

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- **Documentation**: [https://devilsdev.github.io/SCIRM_Monorepo/](https://devilsdev.github.io/SCIRM_Monorepo/)
- **Issues**: [GitHub Issues](https://github.com/DevilsDev/SCIRM_Monorepo/issues)
- **Discussions**: [GitHub Discussions](https://github.com/DevilsDev/SCIRM_Monorepo/discussions)