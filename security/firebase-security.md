# Firebase Security Configuration

## 🔒 Authentication & Authorization

### Google OAuth Integration
- **Provider**: Google OAuth 2.0
- **Scope**: Email and profile access only
- **Session Management**: HTTP-only cookies with 5-day expiry
- **Token Validation**: Firebase Admin SDK server-side validation

### Access Control
```typescript
// Session cookie validation in secureDocs function
const sessionCookie = req.cookies?.__session;
const decodedClaims = await admin.auth().verifySessionCookie(sessionCookie, true);
```

## 🛡️ Security Headers

### Mandatory Headers (firebase.json)
```json
{
  "headers": [
    {
      "key": "Strict-Transport-Security",
      "value": "max-age=31536000; includeSubDomains; preload"
    },
    {
      "key": "X-Frame-Options", 
      "value": "DENY"
    },
    {
      "key": "X-Content-Type-Options",
      "value": "nosniff"
    },
    {
      "key": "Content-Security-Policy",
      "value": "default-src 'self'; script-src 'self' 'unsafe-inline' https://www.gstatic.com https://apis.google.com"
    }
  ]
}
```

## ☁️ Cloud Storage Security

### Storage Rules (storage.rules)
```javascript
rules_version = '2';
service firebase.storage {
  match /b/{bucket}/o {
    match /docs/{allPaths=**} {
      allow read: if request.auth != null;  // Authenticated users only
      allow write: if false;                // CI/CD service account only
    }
    match /{allPaths=**} {
      allow read, write: if false;          // Block all other access
    }
  }
}
```

## 🔑 Secrets Management

### Required GitHub Secrets
- `FIREBASE_SERVICE_ACCOUNT_KEY`: Service account JSON for deployment
- `FIREBASE_PROJECT_ID`: Firebase project identifier (can use vars instead)

### Environment Variables
```bash
# Production deployment
FIREBASE_PROJECT_ID=scirm-docs-prod
GCLOUD_PROJECT=scirm-docs-prod
```

## 🚨 Security Monitoring

### Audit Logging
- All requests logged with IP, user agent, timestamp
- Authentication failures tracked
- File access patterns monitored
- Deployment activities recorded

### Security Alerts
- Failed authentication attempts > 5/minute
- Unusual access patterns
- Storage rule violations
- Function execution errors

## 🔒 Network Security

### HTTPS Enforcement
- All traffic forced to HTTPS
- HSTS headers with 1-year max-age
- Preload directive enabled

### CORS Policy
- Restricted to Firebase domains only
- No wildcard origins allowed
- Credentials required for all requests

## 🛡️ Function Security

### Runtime Security
- Node.js 20 LTS (latest security patches)
- Memory limit: 512MB (prevent DoS)
- Timeout: 30 seconds (prevent hanging)
- No shell access or file system writes

### Input Validation
- All user inputs sanitized
- Path traversal prevention
- File type validation
- Size limits enforced

## 📋 Compliance Controls

### SOC2 Type II
- ✅ Access controls implemented
- ✅ Audit logging enabled
- ✅ Data encryption at rest/transit
- ✅ Change management process

### GDPR
- ✅ User consent for authentication
- ✅ Data minimization (email/profile only)
- ✅ Right to deletion (account removal)
- ✅ Data portability (export capability)

### HIPAA (if applicable)
- ✅ Administrative safeguards
- ✅ Physical safeguards (Google Cloud)
- ✅ Technical safeguards
- ✅ Audit controls

## 🚦 Security Testing

### Automated Security Scans
- Dependency vulnerability scanning (Trivy)
- Secret detection (TruffleHog)
- Static code analysis (CodeQL)
- Container image scanning

### Manual Security Reviews
- Quarterly penetration testing
- Annual security architecture review
- Code review for all security changes
- Incident response testing

## 🔧 Security Hardening

### Function Hardening
- Minimal dependencies
- Regular security updates
- Error handling without information disclosure
- Rate limiting on authentication endpoints

### Infrastructure Hardening
- Service account with minimal permissions
- VPC firewall rules (if applicable)
- Resource quotas and limits
- Monitoring and alerting

## 📞 Incident Response

### Security Incident Process
1. **Detection**: Automated alerts or manual discovery
2. **Assessment**: Severity and impact evaluation
3. **Containment**: Immediate threat mitigation
4. **Investigation**: Root cause analysis
5. **Recovery**: Service restoration
6. **Lessons Learned**: Process improvement

### Contact Information
- **Security Team**: security@scirm.ai
- **On-Call**: +1-XXX-XXX-XXXX
- **Escalation**: CTO, CISO

## 🔄 Security Updates

### Patch Management
- Critical patches: 24 hours
- High severity: 7 days
- Medium/Low: 30 days
- Dependency updates: Monthly

### Security Review Schedule
- Code changes: Every PR
- Configuration changes: Every deployment
- Architecture changes: Quarterly
- Full security audit: Annually
