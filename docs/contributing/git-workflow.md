# Git Workflow - SCIRM Development

## Branch Strategy

### Protected Branches

- **`main`**: Production branch - **NEVER push directly**
  - Requires PR with 2 approvals
  - All status checks must pass
  - Signed commits required
  - Linear history enforced

- **`internal-dashboards`**: Internal operational data - **NEVER merge to main**
  - Contains sensitive metrics and dashboards
  - Isolated from public deployments
  - Requires PR for changes within branch

- **`firebase-setup`**, **`netlify-setup`**: Infrastructure branches
  - Setup and configuration only
  - Require PR to merge to main
  - No direct deployments

### Feature Development

1. **Create feature branch from main**:
   ```bash
   git checkout main
   git pull origin main
   git checkout -b feat/your-feature-name
   ```

2. **Branch naming conventions**:
   - `feat/feature-name` - New features
   - `fix/bug-description` - Bug fixes  
   - `docs/documentation-update` - Documentation changes
   - `refactor/component-name` - Code refactoring
   - `test/test-description` - Test additions

3. **Make changes with signed commits**:
   ```bash
   git add .
   git commit -S -m "feat: add new risk assessment algorithm"
   ```

4. **Push and create PR**:
   ```bash
   git push origin feat/your-feature-name
   # Create PR via GitHub UI
   ```

## Pull Request Process

### Requirements
- ✅ **2 approvals** from code owners
- ✅ **All status checks pass**:
  - `docs-build` - Documentation builds successfully
  - `lint` - Code style and formatting
  - `tests` - Unit and integration tests
  - `security-scans` - Security vulnerability scans
  - `codeql-analysis` - Static code analysis
  - `no-internal-dashboards-to-main` - Branch isolation check
- ✅ **Signed commits** - All commits must be cryptographically signed
- ✅ **Code owner review** - Required for protected paths

### PR Checklist
- [ ] Branch is up to date with main
- [ ] All commits are signed (verified badge on GitHub)
- [ ] Tests added/updated for new functionality
- [ ] Documentation updated if needed
- [ ] No sensitive data or secrets in code
- [ ] Security implications considered
- [ ] Breaking changes documented

## Commit Guidelines

### Conventional Commits
Use conventional commit format:
```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

**Examples**:
```bash
git commit -S -m "feat(auth): add OAuth2 integration for Firebase"
git commit -S -m "fix(dashboard): resolve memory leak in risk visualization"
git commit -S -m "docs: update API documentation for v2.0"
```

### Commit Signing
All commits **MUST** be signed. See [commit-signing.md](./commit-signing.md) for setup instructions.

## Prohibited Actions

### ❌ Direct Push to Main
```bash
# THIS IS BLOCKED
git push origin main
```

### ❌ Merging internal-dashboards to main
```bash
# THIS WILL FAIL CI
git checkout main
git merge internal-dashboards
```

### ❌ Unsigned Commits
```bash
# Missing -S flag - will fail PR checks
git commit -m "unsigned commit"
```

## Emergency Procedures

### Hotfix Process
1. Create hotfix branch from main:
   ```bash
   git checkout main
   git checkout -b hotfix/critical-security-fix
   ```

2. Make minimal fix with signed commit
3. Create PR with "HOTFIX" label
4. Request expedited review from security team
5. Merge after required approvals

### Rollback Process
1. Identify problematic commit
2. Create revert PR:
   ```bash
   git checkout main
   git checkout -b fix/revert-problematic-change
   git revert <commit-hash>
   git commit -S -m "fix: revert problematic change"
   ```

## Status Check Details

### Required Checks
- **docs-build**: MkDocs documentation builds without errors
- **lint**: Code passes style and formatting checks
- **tests**: All unit and integration tests pass
- **security-scans**: No high/critical vulnerabilities found
- **codeql-analysis**: Static analysis passes
- **no-internal-dashboards-to-main**: Prevents dashboard content leaks

### Troubleshooting Failed Checks
- **Build failures**: Check MkDocs configuration and markdown syntax
- **Lint failures**: Run `markdownlint docs/` locally
- **Test failures**: Run `pytest tests/` locally  
- **Security issues**: Review Trivy scan results in Actions
- **Unsigned commits**: See commit signing setup guide

## Best Practices

### Before Creating PR
1. Rebase on latest main:
   ```bash
   git checkout main
   git pull origin main
   git checkout your-branch
   git rebase main
   ```

2. Squash related commits if needed:
   ```bash
   git rebase -i HEAD~3  # Interactive rebase last 3 commits
   ```

3. Verify all commits are signed:
   ```bash
   git log --show-signature -5
   ```

### Code Review Guidelines
- Review for security implications
- Verify test coverage for new features
- Check documentation updates
- Ensure no sensitive data exposure
- Validate architectural decisions

## Repository Structure

```
SCIRM_Monorepo/
├── .github/
│   ├── workflows/          # CI/CD pipelines
│   ├── rulesets/          # Branch protection rules
│   └── CODEOWNERS         # Code ownership
├── docs/                  # Public documentation
├── apps/                  # Frontend applications
├── services/              # Agent microservices
├── libs/                  # Shared libraries
├── infra/                 # Infrastructure as code
└── tests/                 # Test suites
```

## Support

For questions about the git workflow:
- Check existing ADRs in `docs/architecture/adr/`
- Review failed status checks in GitHub Actions
- Contact code owners for protected paths
- Escalate security concerns to @SecurityLead

---

**Remember**: This workflow enforces security, quality, and compliance. Every step is designed to protect production and maintain audit trails.
