# SCIRM Platform Deployment Runbook

## Overview
This runbook provides step-by-step procedures for deploying and operating the SCIRM AI-powered supply chain risk management platform.

## Prerequisites

### Required Tools
- `kubectl` (v1.24+)
- `docker` (v20.10+)
- `helm` (v3.8+) - optional
- `make` - for automation
- `git` - for version control

### Access Requirements
- Kubernetes cluster admin access
- Docker registry push permissions
- GitHub repository access
- Cloud provider credentials (AWS/Azure/GCP)

## Deployment Procedures

### 1. Initial Setup

```bash
# Clone repository
git clone <repository-url>
cd SCIRM_Monorepo

# Initialize project
make init

# Set up environment
make setup-env
```

### 2. Development Environment

```bash
# Start local development
make dev

# Check service health
make health

# Run tests
make test
```

### 3. Staging Deployment

```bash
# Build and deploy to staging
make deploy-staging

# Monitor deployment
kubectl get pods -n scirm-staging -w

# Check logs
kubectl logs -f deployment/coordinator -n scirm-staging
```

### 4. Production Deployment

```bash
# Deploy to production
make deploy-prod

# Verify deployment
kubectl get services -n scirm-production
kubectl get ingress -n scirm-production
```

## Operational Procedures

### Health Monitoring

#### Service Health Checks
```bash
# Check all services
make health

# Individual service check
curl -f http://api-gateway/health
```

#### Database Health
```bash
# Check PostgreSQL
kubectl exec -n scirm-staging deployment/postgres -- pg_isready

# Check Redis
kubectl exec -n scirm-staging deployment/redis -- redis-cli ping
```

#### Vector Database Health
```bash
# Check Weaviate
curl http://weaviate:8080/v1/.well-known/ready
```

### Scaling Procedures

#### Horizontal Pod Autoscaling
```bash
# Enable HPA for coordinator
kubectl autoscale deployment coordinator --cpu-percent=70 --min=2 --max=10 -n scirm-staging

# Check HPA status
kubectl get hpa -n scirm-staging
```

#### Manual Scaling
```bash
# Scale coordinator to 5 replicas
kubectl scale deployment coordinator --replicas=5 -n scirm-staging

# Scale all agent services
for service in coordinator planner researcher executor reviewer; do
  kubectl scale deployment $service --replicas=3 -n scirm-staging
done
```

### Backup Procedures

#### Database Backup
```bash
# Create database backup
kubectl exec -n scirm-staging deployment/postgres -- pg_dump -U scirm scirm_staging > backup-$(date +%Y%m%d).sql

# Restore from backup
kubectl exec -i -n scirm-staging deployment/postgres -- psql -U scirm scirm_staging < backup-20240120.sql
```

#### Vector Database Backup
```bash
# Backup Weaviate data
kubectl exec -n scirm-staging deployment/weaviate -- tar -czf /tmp/weaviate-backup.tar.gz /var/lib/weaviate
kubectl cp scirm-staging/weaviate-pod:/tmp/weaviate-backup.tar.gz ./weaviate-backup-$(date +%Y%m%d).tar.gz
```

### Update Procedures

#### Rolling Updates
```bash
# Update coordinator image
kubectl set image deployment/coordinator coordinator=scirm/coordinator:v1.1.0 -n scirm-staging

# Monitor rollout
kubectl rollout status deployment/coordinator -n scirm-staging

# Rollback if needed
kubectl rollout undo deployment/coordinator -n scirm-staging
```

#### Configuration Updates
```bash
# Update ConfigMap
kubectl patch configmap scirm-config -n scirm-staging --patch '{"data":{"log-level":"DEBUG"}}'

# Restart deployments to pick up changes
kubectl rollout restart deployment/coordinator -n scirm-staging
```

## Troubleshooting

### Common Issues

#### Pod Startup Failures
```bash
# Check pod status
kubectl describe pod <pod-name> -n scirm-staging

# Check logs
kubectl logs <pod-name> -n scirm-staging --previous

# Check events
kubectl get events -n scirm-staging --sort-by=.metadata.creationTimestamp
```

#### Database Connection Issues
```bash
# Test database connectivity
kubectl exec -n scirm-staging deployment/coordinator -- python -c "
import asyncpg
import asyncio
import os

async def test_db():
    try:
        conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
        result = await conn.fetchval('SELECT 1')
        print(f'Database connection successful: {result}')
        await conn.close()
    except Exception as e:
        print(f'Database connection failed: {e}')

asyncio.run(test_db())
"
```

#### High Memory Usage
```bash
# Check resource usage
kubectl top pods -n scirm-staging

# Increase memory limits
kubectl patch deployment coordinator -n scirm-staging --patch '{"spec":{"template":{"spec":{"containers":[{"name":"coordinator","resources":{"limits":{"memory":"1Gi"}}}]}}}}'
```

### Performance Issues

#### High Response Times
1. Check Prometheus metrics
2. Scale up replicas
3. Optimize database queries
4. Review AI model performance

#### Agent Execution Failures
1. Check agent logs
2. Verify API key configurations
3. Monitor external service availability
4. Review rate limiting

### Security Incidents

#### Suspected Breach
1. Isolate affected services
2. Review audit logs
3. Rotate secrets
4. Notify security team

#### Certificate Expiry
```bash
# Check certificate expiry
kubectl get certificates -n scirm-staging

# Renew certificates
kubectl delete certificate <cert-name> -n scirm-staging
# Certificate will be automatically renewed
```

## Monitoring and Alerting

### Key Metrics to Monitor
- Service availability (uptime > 99.9%)
- Response times (< 500ms p95)
- Error rates (< 1%)
- Resource utilization (CPU < 80%, Memory < 80%)
- Agent execution success rates (> 95%)

### Alert Escalation
1. **Critical**: Page on-call engineer immediately
2. **High**: Notify team within 15 minutes
3. **Medium**: Create ticket for next business day
4. **Low**: Weekly review

## Disaster Recovery

### RTO/RPO Targets
- **RTO**: 4 hours
- **RPO**: 1 hour

### Recovery Procedures
1. Assess damage scope
2. Restore from backups
3. Verify data integrity
4. Resume operations
5. Post-incident review

## Compliance Procedures

### Audit Trail Maintenance
```bash
# Export audit logs
kubectl exec -n scirm-staging deployment/postgres -- psql -U scirm -c "
COPY (SELECT * FROM audit.activity_log WHERE timestamp >= NOW() - INTERVAL '30 days') 
TO '/tmp/audit_export.csv' WITH CSV HEADER;
"
```

### Data Retention
- Audit logs: 7 years
- Application data: Per organization policy
- Backups: 90 days

## Emergency Contacts

- **On-call Engineer**: +1-XXX-XXX-XXXX
- **DevOps Team**: devops@company.com
- **Security Team**: security@company.com
- **Compliance Officer**: compliance@company.com

## Change Management

### Deployment Windows
- **Staging**: Anytime
- **Production**: Tuesday/Thursday 2-4 AM UTC

### Approval Process
1. Code review (2 approvals)
2. Security review (for security changes)
3. Change advisory board (for major changes)
4. Deployment approval

## Documentation Updates

This runbook should be updated:
- After each major deployment
- When new procedures are added
- After incident resolution
- Quarterly review cycle

---

**Last Updated**: 2024-01-20  
**Version**: 1.0  
**Owner**: DevOps Team
