# Runbook Template

This is a template for creating operational runbooks following SCIRM documentation standards.

## Usage

Copy this template and customize it for your specific operational procedures. Ensure clear step-by-step instructions for incident response and maintenance tasks.

## Template Structure

- **Service Overview**: Brief description of the service
- **Prerequisites**: Required access, tools, knowledge
- **Common Issues**: Frequent problems and solutions
- **Monitoring & Alerts**: Key metrics and alert thresholds
- **Troubleshooting Steps**: Systematic diagnostic procedures
- **Escalation Procedures**: When and how to escalate
- **Recovery Procedures**: Service restoration steps
- **Post-Incident**: Cleanup and documentation requirements

## Example Sections

### Service Health Check
```bash
# Check service status
kubectl get pods -n scirm-prod
curl -f https://api.scirm.com/health
```

### Common Alerts
- High memory usage: Check for memory leaks
- Database connection errors: Verify connection pool
- API latency spikes: Check downstream dependencies
