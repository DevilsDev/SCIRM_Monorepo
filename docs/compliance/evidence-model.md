# Evidence Model

SCIRM implements a comprehensive evidence model to support compliance, auditing, and operational transparency.

## Evidence Types

### Deployment Evidence
Captures all deployment activities with complete metadata:
- Deployment target and environment
- Source code commit information
- Security scan results
- Approval workflows and timestamps
- Rollback procedures and capabilities

### Security Evidence
Documents security controls and their effectiveness:
- Access control implementations
- Encryption status and key management
- Vulnerability scan results
- Incident response activities
- Compliance control testing

### Operational Evidence
Tracks day-to-day platform operations:
- Performance metrics and SLA compliance
- Error rates and resolution times
- Capacity planning and scaling events
- Maintenance windows and updates
- User activity and access patterns

## Evidence Schema

### Standard Fields
All evidence records include:
```json
{
  "evidence_id": "unique-identifier",
  "timestamp": "ISO-8601-datetime",
  "evidence_type": "deployment|security|operational",
  "source": "system-or-process-name",
  "classification": "public|internal|confidential|restricted"
}
```

### Deployment Evidence Schema
```json
{
  "deployment_target": "firebase-hosting|kubernetes|etc",
  "branch": "source-branch-name",
  "commit_sha": "git-commit-hash",
  "workflow_run_url": "github-actions-url",
  "site_url": "deployed-site-url",
  "security_scans": {
    "status": "passed|failed",
    "vulnerabilities": "count-by-severity"
  },
  "approvals": [
    {
      "approver": "user-identifier",
      "timestamp": "approval-time",
      "type": "security|technical|business"
    }
  ]
}
```

## Storage and Retention

### Evidence Storage
- **Location**: `/compliance/artifacts/` directory
- **Format**: JSON with standardized schema
- **Naming**: `{type}-{timestamp}-{identifier}.json`
- **Access**: Restricted to compliance and audit teams

### Retention Policy
- **Active Evidence**: 3 years online storage
- **Archived Evidence**: 7 years cold storage
- **Legal Hold**: Indefinite retention during litigation
- **Destruction**: Secure deletion after retention period

## Compliance Mapping

### SOC 2 Controls
- **CC6.1**: Access controls → deployment approvals
- **CC6.2**: Authentication → security evidence
- **CC7.1**: Monitoring → operational evidence
- **CC8.1**: Change management → deployment evidence

### GDPR Requirements
- **Article 5**: Data processing principles → operational evidence
- **Article 25**: Privacy by design → security evidence
- **Article 32**: Security measures → security evidence
- **Article 33**: Breach notification → incident evidence

### HIPAA Safeguards
- **Administrative**: Policies and procedures → operational evidence
- **Physical**: Facility controls → security evidence
- **Technical**: Access controls → security evidence

## Automated Evidence Collection

Evidence is automatically collected through:
- GitHub Actions workflows
- Security scanning tools
- Monitoring and alerting systems
- Access control systems
- Application logging

## Manual Evidence Requirements

Certain evidence must be manually collected:
- Executive approvals for major changes
- Third-party audit results
- Legal and regulatory correspondence
- Customer security questionnaires
- Vendor security assessments

## Evidence Validation

### Automated Validation
- Schema compliance checking
- Digital signature verification
- Timestamp validation
- Cross-reference verification

### Manual Validation
- Quarterly evidence reviews
- Annual compliance audits
- Third-party assessments
- Regulatory examinations
