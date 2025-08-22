# Firebase Deploy Branch Governance

**Document Version:** v1.0.0  
**Last Updated:** 2025-01-27  
**Owner:** DevOps & Security Team  
**Status:** Active  

## Overview

This document establishes the governance framework for Firebase Hosting deployments in the SCIRM repository, implementing a dedicated `firebase-hosting` branch strategy to ensure secure, auditable, and controlled deployments.

## Branch Strategy

### Branch Roles

| Branch | Purpose | Deployment | Direct Push |
|--------|---------|------------|-------------|
| `main` | Source of truth, authoring, reviews, CI checks | ❌ None | ❌ Blocked |
| `firebase-hosting` | **Exclusive Firebase Hosting deployments** | ✅ Firebase only | ⚠️ Discouraged |
| `internal-dashboards` | Internal content, governance dashboards | ❌ None | ❌ Blocked |
| `firebase-setup` | Infrastructure scaffolding | ❌ None | ❌ Blocked |
| `netlify-setup` | Netlify configuration | ❌ None | ❌ Blocked |

### Deployment Rules

1. **Firebase Hosting deployments ONLY occur from `firebase-hosting` branch**
2. **All other branches are deployment-blocked by guard workflows**
3. **Content flows:** `main` → PR → `firebase-hosting` → Deploy
4. **Emergency deployments:** Direct push to `firebase-hosting` with immediate PR for audit

## Workflow Architecture

### Deploy Workflow: `deploy-firebase-from-fh.yml`

**Triggers:**
- Push to `firebase-hosting` branch
- Manual workflow dispatch on `firebase-hosting`

**Security Validations:**
- Branch validation (must be `firebase-hosting`)
- Internal content guard (blocks internal dashboards)
- Security scanning (Bandit, Safety, Semgrep)
- Signed commit verification

**Deployment Process:**
1. MkDocs site build with public-safe navigation
2. Firebase CLI deployment to `scirm-dd5c3.web.app`
3. Deployment evidence JSON generation
4. Evidence commit back to `firebase-hosting`

### Guard Workflows

#### `guard-no-deploy-non-fh.yml`
- **Purpose:** Block deploy attempts from any branch except `firebase-hosting`
- **Status Check:** `guard-non-firebase-hosting-deploy`
- **Action:** Fails immediately with clear error message

#### `block-main-deploy.yml`
- **Purpose:** Prevent any deployment jobs on `main` branch
- **Status Check:** `no-deploy-from-main`
- **Action:** Blocks deploy workflows, allows CI/CD checks

## Branch Protection Rules

### Firebase Hosting Branch (`firebase-hosting`)

**Ruleset:** `firebase-hosting-protection.json`

- ✅ **Pull Request Required:** 1 approval minimum
- ✅ **Code Owner Review:** Required for critical changes
- ✅ **Signed Commits:** Mandatory
- ✅ **Linear History:** No merge commits
- ✅ **Creation/Deletion Protection:** Branch cannot be deleted
- ✅ **Force Push Protection:** Blocked

### Main Branch (`main`)

**Additional Protections:**
- ✅ **Required Status Checks:** `no-deploy-from-main`
- ✅ **2 Approvals Required**
- ✅ **All CI checks must pass**

## Content Flow Process

### Standard Content Updates

1. **Author** creates feature branch from `main`
2. **Author** opens PR to `main` with all required checks
3. **Reviewers** approve PR (2 approvals + code owners)
4. **Merge** to `main` (squash merge preferred)
5. **Deploy Manager** creates PR from `main` to `firebase-hosting`
6. **Deploy Manager** merges to `firebase-hosting`
7. **Automatic** Firebase deployment triggers
8. **Evidence** JSON committed to `/compliance/artifacts/deployment-logs/`

### Emergency Deployments

1. **Authorized Personnel** push directly to `firebase-hosting`
2. **Immediate** PR creation from `firebase-hosting` to `main` for audit
3. **Post-incident** review and documentation

## Security Controls

### Secrets Management

**Required GitHub Secrets:**
- `FIREBASE_SERVICE_ACCOUNT_KEY`: Firebase service account JSON
- `FIREBASE_PROJECT_ID`: Firebase project identifier (`scirm-dd5c3`)

**Access Control:**
- Secrets accessible only to `firebase-hosting` deploy workflow
- Service account follows principle of least privilege
- Regular secret rotation (quarterly)

### Content Isolation

**Internal Content Guard:**
```bash
# Blocks deployment if internal dashboard content detected
find site/ -name "*.html" -exec grep -l "internal-dashboard\|compliance-cockpit\|sensitive-data" {} \;
```

**Public Safety Checks:**
- No repository links in deployed content
- No internal URLs or sensitive endpoints
- No development secrets or API keys

### Audit Trail

**Deployment Evidence:** `/compliance/artifacts/deployment-logs/`
```json
{
  "deployment_id": "uuid",
  "timestamp": "2025-01-27T10:30:00Z",
  "branch": "firebase-hosting",
  "commit_sha": "abc123",
  "deployer": "github-actions",
  "target": "https://scirm-dd5c3.web.app",
  "workflow_run": "https://github.com/repo/actions/runs/123",
  "security_scans": {
    "bandit": "passed",
    "safety": "passed", 
    "semgrep": "passed"
  }
}
```

## Compliance Framework

### SOC 2 Type II Controls

- **CC6.1:** Logical access controls restrict unauthorized deployment
- **CC6.2:** System boundaries enforced through branch isolation
- **CC6.3:** Access rights reviewed through PR approval process
- **CC7.1:** System monitoring through deployment evidence capture

### Change Management

- **CM-3:** Configuration change control through PR workflow
- **CM-5:** Access restrictions for configuration changes
- **CM-6:** Configuration settings documented and enforced
- **CM-8:** Information system component inventory maintained

## Roles and Responsibilities

### Deploy Manager
- **Permissions:** Push to `firebase-hosting`, merge PRs
- **Responsibilities:** Content promotion, deployment oversight
- **Requirements:** Security training, signed commits

### Content Authors
- **Permissions:** Create PRs to `main`
- **Responsibilities:** Content creation, testing, documentation
- **Requirements:** Signed commits, security awareness

### Security Team
- **Permissions:** Emergency access, audit review
- **Responsibilities:** Policy enforcement, incident response
- **Requirements:** Security clearance, audit training

## Monitoring and Alerting

### Deployment Monitoring

**Success Metrics:**
- Deployment success rate: >99%
- Time to deploy: <10 minutes
- Security scan pass rate: 100%

**Alert Conditions:**
- Failed deployment to `firebase-hosting`
- Security scan failures
- Unauthorized deployment attempts
- Missing deployment evidence

### Compliance Monitoring

**Evidence Collection:**
- All deployments logged with full metadata
- Security scan results archived
- Access logs maintained for 7 years
- Audit trail immutable and timestamped

## Incident Response

### Unauthorized Deployment Attempt

1. **Immediate:** Guard workflow blocks deployment
2. **Alert:** Security team notified via Slack/email
3. **Investigation:** Review logs and determine cause
4. **Remediation:** Address root cause, update controls
5. **Documentation:** Incident report and lessons learned

### Failed Security Scan

1. **Block:** Deployment automatically blocked
2. **Notification:** Development team alerted
3. **Analysis:** Security team reviews findings
4. **Resolution:** Fix vulnerabilities before retry
5. **Verification:** Re-run scans and validate fixes

### Emergency Access

1. **Authorization:** Security team approval required
2. **Access:** Temporary elevated permissions granted
3. **Monitoring:** All actions logged and monitored
4. **Cleanup:** Permissions revoked after incident
5. **Review:** Post-incident analysis and documentation

## Rollback Procedures

### Standard Rollback

1. **Identify** last known good commit on `firebase-hosting`
2. **Create** rollback PR to `firebase-hosting`
3. **Merge** rollback PR (expedited approval)
4. **Deploy** automatically triggers
5. **Verify** rollback success and functionality

### Emergency Rollback

1. **Direct push** previous good commit to `firebase-hosting`
2. **Immediate** deployment triggers
3. **Create** audit PR for rollback action
4. **Document** incident and rollback reason
5. **Schedule** proper fix and forward deployment

## Maintenance and Updates

### Quarterly Reviews

- **Policy Review:** Update governance based on lessons learned
- **Access Review:** Validate user permissions and roles
- **Secret Rotation:** Update Firebase service account keys
- **Audit:** Review compliance evidence and gaps

### Annual Assessments

- **Security Assessment:** Penetration testing and vulnerability review
- **Compliance Audit:** SOC 2 and regulatory compliance verification
- **Process Improvement:** Workflow optimization and automation
- **Training Update:** Security awareness and procedure training

## Appendix

### Quick Reference Commands

```bash
# Create deployment PR
git checkout main
git pull origin main
git checkout firebase-hosting
git pull origin firebase-hosting
git merge main
git push origin firebase-hosting

# Emergency rollback
git checkout firebase-hosting
git reset --hard <last-good-commit>
git push --force-with-lease origin firebase-hosting

# Check deployment status
gh run list --branch firebase-hosting --workflow deploy-firebase-from-fh.yml
```

### Contact Information

- **Security Team:** security@scirm.dev
- **DevOps Team:** devops@scirm.dev
- **Emergency Hotline:** +1-555-SCIRM-911
- **Compliance Officer:** compliance@scirm.dev

---

**Document Control:**
- **Classification:** Internal Use
- **Retention:** 7 years
- **Review Cycle:** Quarterly
- **Approval:** Security Officer, DevOps Lead, Compliance Officer
