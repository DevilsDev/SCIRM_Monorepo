# SCIRM# Compliance Evidence & Artifacts

## Overview
This directory contains automated evidence capture for all deployments and governance activities, supporting SOC2, GDPR, HIPAA, and FDA compliance requirements.

## Evidence Schema

### Deployment Evidence
Every deployment generates a JSON evidence file with the following schema:
```json
{
  "deployment_id": "firebase-auth-20250822-081239",
  "timestamp": "2025-08-22T08:12:39Z",
  "commit_sha": "abc123def456...",
  "branch": "main",
  "workflow_url": "https://github.com/org/repo/actions/runs/123456",
  "deployment_type": "firebase-auth|firebase-static|netlify",
  "artifacts": ["functions", "hosting", "storage"],
  "security_scan": {
    "status": "passed",
    "vulnerabilities": 0,
    "scan_url": "https://github.com/org/repo/security/code-scanning"
  },
  "compliance_check": {
    "status": "passed",
    "controls_verified": ["access_control", "data_encryption", "audit_logging"],
    "evidence_links": ["https://..."]
  },
  "approvals": [
    {
      "reviewer": "@SecurityLead",
      "timestamp": "2025-08-22T08:10:00Z",
      "approval_type": "security_review"
    }
  ]
}
```

### Governance Evidence
ADR and governance activities generate evidence:
```json
{
  "activity_id": "adr-20250822-001",
  "timestamp": "2025-08-22T08:12:39Z",
  "activity_type": "adr_creation|weekly_digest|compliance_review",
  "participants": ["@Architect", "@ComplianceOfficer"],
  "decisions": [
    {
      "decision_id": "ADR-001",
      "title": "Authentication Architecture",
      "status": "approved",
      "impact_assessment": "high"
    }
  ],
  "compliance_impact": "Updated security controls documentation"
}
```

## File Naming Convention
```
{deployment_type}-{timestamp}-{commit_short}.json

Examples:
- firebase-auth-20250822-081239-abc123d.json
- firebase-static-20250822-081240-abc123d.json
- netlify-20250822-081241-abc123d.json
- governance-weekly-20250822-081242.json
```

## Retention Policy
- **Active Evidence**: Keep all files for current year
- **Archive**: Move previous year files to cold storage
- **Legal Hold**: Preserve evidence for ongoing audits
- **Deletion**: After 7 years (unless legal hold)

## Compliance Mapping

### SOC2 Type II
- **CC6.1**: Logical access controls → deployment approvals
- **CC6.2**: Authentication management → auth evidence
- **CC6.3**: Authorization → RBAC evidence
- **CC7.1**: System monitoring → deployment logs

### GDPR Article 32
- **Technical measures**: Security scan evidence
- **Organizational measures**: Approval workflows
- **Documentation**: Complete audit trail

### HIPAA 164.312
- **Access control**: Authentication evidence
- **Audit controls**: Deployment logging
- **Integrity**: Code signing verification
- **Transmission security**: TLS enforcement evidence

### FDA 21 CFR Part 11
- **Electronic signatures**: Git commit signatures
- **Audit trail**: Complete deployment history
- **System validation**: Security scan results
- **Access controls**: RBAC evidence

## Automated Evidence Capture

### GitHub Actions Integration
All deployment workflows automatically generate evidence:
```yaml
- name: Capture Evidence
  run: |
    cat > evidence.json << EOF
    {
      "deployment_id": "${{ github.run_id }}",
      "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
      "commit_sha": "${{ github.sha }}",
      "branch": "${{ github.ref_name }}",
      "workflow_url": "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"
    }
    EOF
    
- name: Commit Evidence
  run: |
    git add compliance/artifacts/
    git commit -m "Evidence: ${{ github.workflow }} deployment"
    git push
```

## Manual Evidence Requirements

### Security Reviews
When manual security reviews are required:
1. Create evidence file with reviewer information
2. Include links to review documentation
3. Document any exceptions or waivers
4. Obtain required approvals before deployment

### Compliance Audits
During compliance audits:
1. Provide evidence files for requested time period
2. Generate summary reports from JSON data
3. Demonstrate continuous monitoring
4. Show remediation of any findings

## Monitoring & Alerting

### Evidence Completeness
- **Missing Evidence**: Alert if deployment completes without evidence file
- **Schema Validation**: Verify all evidence files match required schema
- **Approval Gaps**: Flag deployments without required approvals

### Compliance Metrics
- **Deployment Success Rate**: % of deployments with complete evidence
- **Security Scan Pass Rate**: % of scans with no critical vulnerabilities
- **Approval Timeliness**: Average time from PR to approval
- **Evidence Retention**: % of evidence files within retention policy

## Access Controls
- **Read Access**: Compliance team, auditors, security team
- **Write Access**: Automated systems only (GitHub Actions)
- **Admin Access**: Compliance officer for retention management
- **Audit Access**: External auditors with time-limited access

## Tools & Integration

### Evidence Analysis
```bash
# Generate compliance report
python scripts/compliance-report.py --start-date 2025-01-01 --end-date 2025-12-31

# Validate evidence completeness
python scripts/validate-evidence.py --directory compliance/artifacts/

# Export for audit
python scripts/export-audit.py --auditor "External Audit Firm" --format pdf
```

### Automated Validation
```yaml
# .github/workflows/validate-evidence.yml
- name: Validate Evidence Schema
  run: |
    for file in compliance/artifacts/*.json; do
      jsonschema -i "$file" evidence-schema.json
    done
```

## Support & Contacts
- **Compliance Officer**: @ComplianceOfficer
- **Security Lead**: @SecurityLead
- **DevOps Team**: @SRELead

## 📁 Directory Structure

```
compliance/artifacts/
├── YYYY-MM-DD-HHMM/                  # Timestamped evidence directories
│   ├── firebase-deploy.json          # Firebase deployment evidence
│   ├── security-scan-results.json    # Security scanning evidence
│   ├── adr-validation.json           # ADR compliance validation
│   └── quality-gate-results.json     # CI/CD quality gate results
├── firebase-setup-validation.json    # Firebase setup validation evidence
└── compliance-reports/               # Generated compliance reports
    ├── monthly-security-report.json
    ├── quarterly-audit-summary.json
    └── annual-compliance-review.json
```

## 🔒 Security & Access Control

- **Access**: Restricted to @ComplianceOfficer, @SecurityLead, @SRELead
- **Retention**: Evidence retained for 7 years per SOC2/HIPAA requirements
- **Encryption**: All evidence encrypted at rest in Git repository
- **Audit Trail**: All changes tracked via Git commits with signed commits required

## 📋 Evidence Types

### 1. Deployment Evidence (`firebase-deploy.json`)
```json
{
  "deployment_id": "github-run-id",
  "timestamp": "ISO-8601-timestamp",
  "commit_sha": "git-commit-hash",
  "deployer": "github-actor",
  "security_controls": {
    "auth_required": true,
    "session_cookies": true,
    "security_headers": true,
    "storage_rules": true
  },
  "compliance_status": "DEPLOYED|FAILED|ROLLBACK"
}
```

### 2. Security Scan Results (`security-scan-results.json`)
```json
{
  "scan_id": "unique-scan-identifier",
  "timestamp": "ISO-8601-timestamp",
  "scan_type": "SAST|DAST|DEPENDENCY|SECRETS",
  "tool": "trivy|codeql|trufflehog",
  "results": {
    "critical": 0,
    "high": 0,
    "medium": 0,
    "low": 0
  },
  "compliance_status": "PASS|FAIL|WARNING"
}
```

### 3. ADR Validation (`adr-validation.json`)
```json
{
  "validation_id": "unique-validation-id",
  "timestamp": "ISO-8601-timestamp",
  "adr_count": 0,
  "validation_results": {
    "format_compliance": "PASS|FAIL",
    "required_sections": "PASS|FAIL",
    "governance_approval": "PASS|FAIL"
  },
  "compliance_status": "VALIDATED|REJECTED"
}
```

## 🚦 Quality Gates Integration

Evidence is automatically captured by GitHub Actions workflows:

- **ci-docs.yml**: Captures build, security scan, and compliance validation evidence
- **deploy-firebase.yml**: Captures deployment and security control evidence
- **weekly-digest.yml**: Captures governance decision evidence
- **guards-*.yml**: Captures security guard and isolation evidence

## 📊 Compliance Reporting

Evidence is aggregated into compliance reports:

- **Daily**: Security scan summaries
- **Weekly**: Governance decision digests
- **Monthly**: Security posture reports
- **Quarterly**: Audit readiness summaries
- **Annual**: Full compliance review

## 🔍 Audit Trail Requirements

All evidence must include:

1. **Timestamp**: ISO-8601 formatted UTC timestamp
2. **Actor**: Who performed the action (GitHub actor, system, etc.)
3. **Action**: What was performed (deploy, scan, validate, etc.)
4. **Result**: Success/failure status with details
5. **Context**: Relevant metadata (commit hash, branch, etc.)
6. **Compliance Status**: Pass/fail against compliance requirements

## 🛡️ Data Protection

- Evidence may contain sensitive security information
- Access restricted via CODEOWNERS and branch protections
- Never expose credentials, API keys, or internal system details
- Sanitize logs and error messages before storage
- Encrypt sensitive fields using GitHub secrets

## 📋 Retention Policy

- **Evidence Files**: 7 years retention (SOC2/HIPAA requirement)
- **Deployment Evidence**: Permanent retention for audit trail
- **Security Scans**: 3 years retention
- **Quality Gates**: 1 year retention
- **Compliance Reports**: Permanent retention

Evidence older than retention period is automatically archived to cold storage.
