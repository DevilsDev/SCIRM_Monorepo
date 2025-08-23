# 🔑 Firebase Service Account Key Rotation Runbook

**Purpose:** Secure key rotation procedure for SCIRM Firebase Hosting CI/CD  
**Frequency:** Quarterly or after security incidents  
**Prerequisites:** Google Cloud SDK (`gcloud`) installed and authenticated  
**Target Project:** `scirm-dd5c3`

---

## 🚀 Quick Rotation Steps

### 1. Create Dedicated Deployer Service Account (One-time Setup)

```bash
# Create service account for CI/CD deployments
gcloud iam service-accounts create scirm-ci-deployer \
  --display-name="SCIRM Firebase Hosting CI/CD Deployer" \
  --project=scirm-dd5c3
```

### 2. Grant Minimal Required Roles

```bash
# Grant Firebase Hosting admin role (minimum required)
gcloud projects add-iam-policy-binding scirm-dd5c3 \
  --member="serviceAccount:scirm-ci-deployer@scirm-dd5c3.iam.gserviceaccount.com" \
  --role="roles/firebasehosting.admin"

# Optional: Add viewer role if deployment verification needs it
# gcloud projects add-iam-policy-binding scirm-dd5c3 \
#   --member="serviceAccount:scirm-ci-deployer@scirm-dd5c3.iam.gserviceaccount.com" \
#   --role="roles/viewer"
```

### 3. Generate Fresh JSON Key

```bash
# Generate new service account key
gcloud iam service-accounts keys create scirm-ci-key.json \
  --iam-account=scirm-ci-deployer@scirm-dd5c3.iam.gserviceaccount.com \
  --project=scirm-dd5c3

# Verify key was created
ls -la scirm-ci-key.json
```

### 4. Update GitHub Secrets (Manual)

Navigate to GitHub repository settings → Secrets and variables → Actions:

1. **FIREBASE_SERVICE_ACCOUNT_KEY**
   - Delete old secret
   - Create new secret with contents of `scirm-ci-key.json`
   - Copy entire JSON content (including braces)

2. **FIREBASE_PROJECT_ID** 
   - Verify value is exactly: `scirm-dd5c3`

### 5. Test Locally (Optional)

```bash
# Test authentication locally
export GOOGLE_APPLICATION_CREDENTIALS=./scirm-ci-key.json
firebase use scirm-dd5c3
firebase deploy --only hosting --project scirm-dd5c3 --dry-run

# Clean up test file
unset GOOGLE_APPLICATION_CREDENTIALS
```

### 6. Rotate/Clean Old Keys

```bash
# List all keys for the service account
gcloud iam service-accounts keys list \
  --iam-account=scirm-ci-deployer@scirm-dd5c3.iam.gserviceaccount.com \
  --project=scirm-dd5c3

# Delete old key by KEY_ID (after confirming new key works)
gcloud iam service-accounts keys delete KEY_ID \
  --iam-account=scirm-ci-deployer@scirm-dd5c3.iam.gserviceaccount.com \
  --project=scirm-dd5c3 \
  --quiet
```

---

## ⚠️ Security Cautions

### 🚫 **NEVER** commit the JSON key to the repository
- Always store keys in GitHub Secrets
- Delete local key files after upload: `rm scirm-ci-key.json`
- Use `.gitignore` to prevent accidental commits

### 🔄 **ALWAYS** update GitHub Secrets immediately
- Update secrets before deleting old keys
- Test deployment pipeline with new key
- Only remove old keys after successful deployment

### 🧹 **ALWAYS** remove old keys after rotation
- List keys regularly to audit active credentials
- Remove unused keys to minimize attack surface
- Document key rotation dates for compliance

---

## 🔍 Verification Steps

### Test New Key in CI/CD

1. **Trigger deployment** by pushing to `firebase-hosting` branch:
   ```bash
   # Create trivial change to trigger deploy
   echo "$(date)" > docs/.deploy-stamp
   git add docs/.deploy-stamp
   git commit -m "test: trigger deployment with new service account key"
   git push origin firebase-hosting
   ```

2. **Monitor workflow** in GitHub Actions tab

3. **Verify deployment** at: https://scirm-dd5c3.web.app

### Check Secrets Validation

The deploy workflow includes robust secrets checking:
- ✅ `Check Required Secrets` step validates presence
- ✅ `Debug Secrets Presence` shows PRESENT/MISSING status
- ✅ `Prepare Service Account File` validates JSON syntax

---

## 📋 Rotation Checklist

- [ ] Service account `scirm-ci-deployer` exists with correct roles
- [ ] New JSON key generated and downloaded
- [ ] GitHub Secrets updated with new key content
- [ ] Local test deployment successful (optional)
- [ ] CI/CD pipeline test deployment successful
- [ ] Old keys identified and documented
- [ ] Old keys deleted after successful verification
- [ ] Local key files securely deleted
- [ ] Rotation date documented for next cycle

---

## 🆘 Troubleshooting

### "Invalid service account key" error
- Verify JSON is complete and valid
- Check for extra whitespace or truncation
- Ensure key is for correct service account

### "Permission denied" error
- Verify service account has `roles/firebasehosting.admin`
- Check project ID matches `scirm-dd5c3`
- Confirm key is active (not deleted)

### "Project not found" error
- Verify `FIREBASE_PROJECT_ID` secret is `scirm-dd5c3`
- Check service account project binding

---

## 📅 Rotation Schedule

| **Frequency** | **Trigger** | **Owner** |
|---------------|-------------|-----------|
| Quarterly | Scheduled maintenance | DevOps Team |
| Immediate | Security incident | Security Team |
| Immediate | Key compromise | Incident Response |
| Annual | Compliance audit | Compliance Team |

**Next Rotation Due:** _[Update after each rotation]_

---

## 🔗 Related Documentation

- Firebase Key Rotation Helper Workflow: `.github/workflows/firebase-key-rotation-helper.yml`
- Deploy Workflow: `.github/workflows/deploy-firebase-from-fh.yml`
- [Security Documentation](../security/README.md)
- Compliance Artifacts: `compliance/artifacts/`
