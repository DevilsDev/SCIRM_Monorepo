# Firebase Hosting Governance & Security

## Overview
This document outlines the governance model and security controls for SCIRM's Firebase hosting infrastructure, including both auth-gated and static hosting configurations.

## Architecture

### Auth-Gated Firebase Site
- **Purpose**: Internal documentation with Google OAuth authentication
- **Location**: `/firebase/`
- **URL**: `https://scirm-dd5c3.web.app`
- **Authentication**: Session cookies via Cloud Functions (2nd gen)
- **Storage**: Private Google Cloud Storage bucket

### Static Firebase Site  
- **Purpose**: Public documentation without authentication
- **Location**: `/firebase-static/`
- **URL**: `https://scirm-dd5c3-static.web.app`
- **Authentication**: None (public access)
- **Storage**: Firebase Hosting static files

## Security Controls

### Authentication Flow (Auth-Gated Site)
1. **Unauthenticated Request** → Redirect to `/login`
2. **Google OAuth** → ID token exchange
3. **Cloud Function** → Session cookie creation
4. **Subsequent Requests** → Session cookie validation
5. **Content Delivery** → Stream from private GCS bucket

### Security Headers
Both sites enforce strict security headers:
```http
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
Content-Security-Policy: [restrictive policy]
Referrer-Policy: strict-origin-when-cross-origin
```

### Access Controls
- **Auth-Gated**: Google OAuth with authorized domains
- **Static**: Public read-only access
- **Admin**: Service account with minimal permissions
- **Audit**: All access logged with UID, timestamp, path

## Cloud Function Security

### secureDocs Function (2nd Gen)
```javascript
// Session validation
const sessionCookie = req.cookies.__session;
const decodedClaims = await admin.auth().verifySessionCookie(sessionCookie);

// Audit logging
console.log({
  uid: decodedClaims.uid,
  email: decodedClaims.email,
  path: req.path,
  timestamp: new Date().toISOString(),
  ip: req.ip
});
```

### Permissions Model
- **Principle of Least Privilege**: Function only has GCS read access
- **Service Account**: Dedicated account with minimal IAM roles
- **Secrets**: Stored in GitHub Secrets, never committed
- **Rotation**: Service account keys rotated quarterly

## Storage Security

### Google Cloud Storage Layout
```
gs://scirm-dd5c3-docs/
├── docs/prod/           # Current production docs
├── docs/releases/       # Versioned releases
└── audit/              # Access logs
```

### Bucket Permissions
- **Public Access**: Disabled
- **Function Access**: Read-only via service account
- **Admin Access**: Limited to deployment automation
- **Lifecycle**: Automatic cleanup of old releases

## Compliance & Governance

### Google SD&D Alignment
- **Design-First**: PRD/PDD define requirements before implementation
- **Quality Gates**: Required checks for all deployments
- **Staged Rollout**: firebase-setup branch → validation → main
- **Auditability**: Complete evidence trail in `/compliance/artifacts/`

### Evidence Capture
Every deployment generates evidence JSON:
```json
{
  "deployment_id": "firebase-auth-20250822-081239",
  "timestamp": "2025-08-22T08:12:39Z",
  "commit_sha": "abc123...",
  "branch": "main",
  "workflow_url": "https://github.com/...",
  "artifacts": ["functions", "hosting", "storage"],
  "security_scan": "passed",
  "compliance_check": "passed"
}
```

### Branch Protection
- **main**: 2 approvals, required checks, signed commits
- **firebase-setup**: Deploy blocked, validation required
- **internal-dashboards**: Never deployed, restricted access

## Monitoring & Alerting

### Key Metrics
- **Authentication Success Rate**: >99.5%
- **Function Cold Start**: <2 seconds
- **Content Delivery**: <500ms p95
- **Error Rate**: <0.1%

### Alerts
- **Authentication Failures**: >5% in 5 minutes
- **Function Errors**: Any 5xx responses
- **Unauthorized Access**: Failed session validation
- **Storage Access**: Unusual access patterns

## Incident Response

### Security Incidents
1. **Detection**: Automated monitoring alerts
2. **Assessment**: Security team triage
3. **Containment**: Disable affected components
4. **Investigation**: Audit log analysis
5. **Recovery**: Restore from known good state
6. **Post-Mortem**: Document lessons learned

### Contact Information
- **Security Lead**: @SecurityLead
- **SRE On-Call**: @SRELead  
- **Compliance Officer**: @ComplianceOfficer

## Maintenance

### Regular Tasks
- **Monthly**: Review access logs and user permissions
- **Quarterly**: Rotate service account keys
- **Annually**: Security architecture review
- **As-Needed**: Update security headers and CSP

### Dependency Updates
- **Firebase SDK**: Monthly security updates
- **Cloud Functions Runtime**: Follow Google LTS schedule
- **Security Headers**: Review against OWASP recommendations
