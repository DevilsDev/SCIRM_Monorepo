# Secrets Management & Service Account Security

## Overview
This document defines the secrets management strategy for SCIRM's secure documentation platform, including service account creation, least-privilege access, and rotation procedures.

## Required Secrets

### GitHub Repository Secrets
```bash
# Firebase Authentication & Deployment
FIREBASE_SERVICE_ACCOUNT_KEY    # JSON service account key
FIREBASE_PROJECT_ID            # Firebase project ID (scirm-dd5c3)

# Netlify Static Deployment  
NETLIFY_AUTH_TOKEN            # Personal access token
NETLIFY_SITE_ID              # Site identifier
```

## Service Account Setup

### Firebase Service Account Creation
1. **Navigate to IAM & Admin** in Google Cloud Console
2. **Create Service Account**:
   ```bash
   Name: scirm-docs-deploy
   Description: SCIRM documentation deployment automation
   ```
3. **Assign Minimal Roles**:
   - `Firebase Admin SDK Administrator Service Agent`
   - `Cloud Functions Developer`
   - `Storage Object Admin` (for docs bucket only)
   - `Firebase Hosting Admin`

### Key Generation & Storage
```bash
# Generate JSON key
gcloud iam service-accounts keys create scirm-docs-key.json \
  --iam-account=scirm-docs-deploy@scirm-dd5c3.iam.gserviceaccount.com

# Add to GitHub Secrets (base64 encoded)
cat scirm-docs-key.json | base64 | pbcopy
```

⚠️ **CRITICAL**: Never commit service account keys to version control

## Least Privilege Access

### Service Account Permissions
```json
{
  "bindings": [
    {
      "role": "roles/firebase.admin",
      "members": ["serviceAccount:scirm-docs-deploy@scirm-dd5c3.iam.gserviceaccount.com"],
      "condition": {
        "title": "Deploy Only",
        "description": "Restrict to deployment operations",
        "expression": "request.time.getHours() >= 0 && request.time.getHours() <= 23"
      }
    }
  ]
}
```

### Bucket-Specific Access
```bash
# Grant read/write only to docs bucket
gsutil iam ch serviceAccount:scirm-docs-deploy@scirm-dd5c3.iam.gserviceaccount.com:objectAdmin gs://scirm-dd5c3-docs

# Deny access to other buckets
gsutil iam ch -d serviceAccount:scirm-docs-deploy@scirm-dd5c3.iam.gserviceaccount.com gs://scirm-dd5c3-other
```

## Netlify Token Management

### Personal Access Token Creation
1. **Login to Netlify** → User Settings → Applications
2. **Generate New Token**:
   ```
   Name: SCIRM Docs Deploy
   Scopes: sites:write, deploys:write
   Expiration: 90 days
   ```
3. **Store in GitHub Secrets** as `NETLIFY_AUTH_TOKEN`

### Site ID Retrieval
```bash
# Get site ID from Netlify CLI
netlify sites:list

# Or from site settings URL
# https://app.netlify.com/sites/[SITE_ID]/settings
```

## Rotation Procedures

### Quarterly Service Account Rotation
```bash
#!/bin/bash
# rotate-firebase-key.sh

# 1. Generate new key
gcloud iam service-accounts keys create new-key.json \
  --iam-account=scirm-docs-deploy@scirm-dd5c3.iam.gserviceaccount.com

# 2. Update GitHub secret
gh secret set FIREBASE_SERVICE_ACCOUNT_KEY < new-key.json

# 3. Test deployment
gh workflow run deploy-firebase-auth.yml

# 4. Delete old key after successful test
gcloud iam service-accounts keys delete OLD_KEY_ID \
  --iam-account=scirm-docs-deploy@scirm-dd5c3.iam.gserviceaccount.com

# 5. Cleanup
rm new-key.json
```

### Netlify Token Rotation (90 days)
1. **Generate new token** in Netlify dashboard
2. **Update GitHub secret**: `NETLIFY_AUTH_TOKEN`
3. **Test deployment** via GitHub Actions
4. **Revoke old token** in Netlify dashboard

## Security Best Practices

### Secret Hygiene
- ✅ **Use GitHub Secrets** for all sensitive values
- ✅ **Rotate regularly** (quarterly for service accounts)
- ✅ **Audit access** monthly via Cloud Console
- ✅ **Monitor usage** with Cloud Logging
- ❌ **Never commit** secrets to version control
- ❌ **Never log** secret values in CI/CD
- ❌ **Never share** secrets via chat/email

### Access Monitoring
```bash
# Monitor service account usage
gcloud logging read "protoPayload.authenticationInfo.principalEmail=scirm-docs-deploy@scirm-dd5c3.iam.gserviceaccount.com" \
  --limit=50 --format="table(timestamp,protoPayload.methodName,protoPayload.resourceName)"
```

### Emergency Procedures
If secrets are compromised:
1. **Immediately revoke** all affected keys/tokens
2. **Generate new credentials** with different names
3. **Update GitHub secrets** with new values
4. **Force redeploy** all affected services
5. **Audit logs** for unauthorized access
6. **Document incident** in `/compliance/artifacts/`

## Compliance Requirements

### Audit Trail
All secret operations must be logged:
```json
{
  "timestamp": "2025-08-22T08:12:39Z",
  "operation": "key_rotation",
  "service_account": "scirm-docs-deploy@scirm-dd5c3.iam.gserviceaccount.com",
  "old_key_id": "abc123...",
  "new_key_id": "def456...",
  "operator": "security-team@scirm.com",
  "approval": "JIRA-SEC-2025-001"
}
```

### SOC2 Compliance
- **Access Reviews**: Quarterly service account permission audits
- **Key Rotation**: Documented rotation procedures and evidence
- **Monitoring**: Automated alerts for unusual access patterns
- **Documentation**: This document and related procedures

## Troubleshooting

### Common Issues
- **Authentication failures**: Check key expiration and permissions
- **Deployment failures**: Verify service account has required roles
- **Access denied**: Review IAM bindings and conditions
- **Token expired**: Rotate Netlify token (90-day expiry)

### Support Contacts
- **Security Team**: @SecurityLead
- **DevOps Team**: @SRELead
- **Compliance**: @ComplianceOfficer

## References
- [Google Cloud IAM Best Practices](https://cloud.google.com/iam/docs/using-iam-securely)
- [GitHub Secrets Documentation](https://docs.github.com/en/actions/security-guides/encrypted-secrets)
- [Netlify API Authentication](https://docs.netlify.com/api/get-started/#authentication)
