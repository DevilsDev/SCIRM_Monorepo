# Pull Request - SCIRM Security & Quality Checklist

## 📋 PR Information
- **Type**: [ ] Feature [ ] Bug Fix [ ] Documentation [ ] Refactor [ ] Security [ ] Infrastructure
- **Scope**: [ ] Frontend [ ] Backend [ ] Agent Services [ ] Infrastructure [ ] Documentation
- **Breaking Change**: [ ] Yes [ ] No

## 📝 Description
Brief description of the changes and their impact.

## 🔗 Related Issues
Closes #(issue number)

## 🛡️ Security & Compliance Checklist

### ✅ Required Status Checks
- [ ] `docs-build` - Documentation builds successfully
- [ ] `lint` - Code style and formatting passes
- [ ] `tests` - All unit and integration tests pass
- [ ] `security-scans` - No high/critical vulnerabilities
- [ ] `codeql-analysis` - Static code analysis passes
- [ ] `no-internal-dashboards-to-main` - No internal content in public deployment

### 🔐 Commit Security
- [ ] **All commits are signed** (Verified badge visible on GitHub)
- [ ] Commit messages follow conventional commit format
- [ ] No sensitive data (passwords, keys, tokens) in commits
- [ ] No hardcoded secrets or API keys

### 🚫 Branch Protection Compliance
- [ ] **NOT merging from `internal-dashboards` to `main`**
- [ ] Branch is up to date with main
- [ ] Linear history maintained (no merge commits)
- [ ] PR has required approvals (2 for main branch)

### 📋 Code Quality
- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Complex logic is documented
- [ ] Error handling implemented
- [ ] Performance impact considered

### 🧪 Testing Requirements
- [ ] Unit tests added/updated for new functionality
- [ ] Integration tests cover critical paths
- [ ] Manual testing completed
- [ ] All tests pass locally
- [ ] Test coverage maintained or improved

### 📚 Documentation
- [ ] Documentation updated for new features
- [ ] API changes documented
- [ ] ADR created for architectural decisions
- [ ] README updated if needed

### 🔒 Security Review
- [ ] No SQL injection vulnerabilities
- [ ] Input validation implemented
- [ ] Authentication/authorization checked
- [ ] Data encryption considered
- [ ] OWASP Top 10 compliance verified

### 📊 Compliance & Governance
- [ ] SOC2 controls maintained
- [ ] GDPR data handling compliant
- [ ] HIPAA requirements met (if applicable)
- [ ] Audit trail preserved
- [ ] No internal dashboards in public docs

## 🎯 Testing Strategy
Describe how this change was tested:
- [ ] Unit tests
- [ ] Integration tests  
- [ ] Manual testing
- [ ] Security testing
- [ ] Performance testing

## 🚨 Risk Assessment
- **Risk Level**: [ ] Low [ ] Medium [ ] High
- **Rollback Plan**: Describe rollback strategy if needed
- **Dependencies**: List any external dependencies

## 📸 Screenshots/Evidence
Add screenshots, logs, or other evidence of testing.

## 👥 Reviewer Guidelines
**For Code Owners:**
- [ ] Security implications reviewed
- [ ] Architecture alignment verified
- [ ] Compliance requirements met
- [ ] Performance impact acceptable

**For Security Team:**
- [ ] No security vulnerabilities introduced
- [ ] Authentication/authorization correct
- [ ] Data handling compliant
- [ ] Secrets management proper

## 🚀 Deployment Notes
- [ ] Database migrations needed
- [ ] Configuration changes required
- [ ] Infrastructure updates needed
- [ ] Monitoring/alerting updated

## ⚠️ Breaking Changes
If this introduces breaking changes, describe:
- What breaks
- Migration path
- Backward compatibility plan

## 📝 Additional Notes
Any additional context for reviewers.

---

**🛡️ Security Reminder**: This PR will be automatically blocked if:
- Commits are not signed
- Internal dashboard content is included
- Required status checks fail
- Code owner approval is missing
