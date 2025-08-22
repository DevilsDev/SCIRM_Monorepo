# Frequently Asked Questions

## General Questions

### What is SCIRM?
SCIRM (Supply Chain Intelligence & Risk Management) is an AI-powered platform that predicts, monitors, and mitigates supply chain risks in real-time using a multi-agent architecture.

### Which industries does SCIRM support?
SCIRM primarily targets pharmaceutical and healthcare supply chains but is extensible to manufacturing, retail, and electronics sectors.

### What makes SCIRM different from other supply chain tools?
- **Multi-Agent AI**: 5 specialized agents working in coordination
- **Sub-500ms Response**: Real-time risk assessment
- **Explainable AI**: Transparent reasoning with confidence scores
- **Enterprise Security**: Built-in SOC2, GDPR, HIPAA compliance

## Technical Questions

### What are the system requirements?
- **Deployment**: Kubernetes cluster (cloud or on-premises)
- **Resources**: Minimum 8 CPU cores, 32GB RAM per node
- **Storage**: 1TB+ for vector databases and logs
- **Network**: High-speed internet for external data feeds

### How does the AI make recommendations?
The system uses a multi-agent approach:
1. **Researcher Agent** retrieves relevant data
2. **Planner Agent** maintains context and planning
3. **Executor Agent** generates recommendations
4. **Reviewer Agent** validates and scores confidence
5. **Coordinator Agent** orchestrates the process

### What data sources does SCIRM integrate with?
- **Internal**: ERP, WMS/TMS, IoT sensors
- **External**: Weather APIs, logistics feeds, regulatory data
- **Custom**: API integrations for proprietary systems

## Security & Compliance

### How is data protected?
- **Encryption**: AES-256 at rest, TLS 1.3 in transit
- **Access Control**: RBAC with MFA required
- **Monitoring**: 24/7 SOC with automated threat response
- **Compliance**: SOC2, GDPR, HIPAA controls built-in

### What compliance certifications does SCIRM have?
- SOC 2 Type II (in progress)
- GDPR compliance by design
- HIPAA safeguards implementation
- FDA 21 CFR Part 11 readiness

### How is audit trail maintained?
- All actions logged with timestamps
- Immutable evidence collection
- Digital signatures for critical operations
- 7-year retention policy

## Support & Troubleshooting

### How do I get support?
- **Documentation**: Check this site first
- **Email**: support@scirm.dev
- **Emergency**: 24/7 hotline for critical issues
- **Training**: Available for enterprise customers

### What are the SLA commitments?
- **Uptime**: 99.9% availability
- **Response Time**: Sub-500ms for risk assessments
- **Support**: 4-hour response for critical issues
- **Recovery**: 1-hour RTO for system failures

### How do I report a security issue?
Email security@scirm.dev with:
- Detailed description of the issue
- Steps to reproduce (if applicable)
- Potential impact assessment
- Your contact information for follow-up
