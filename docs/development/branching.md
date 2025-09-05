# GitHub Branching Strategy

This document outlines the branching strategy and workflow for the SCIRM platform development.

## Branch Types

### Main Branches

#### `main`
- **Purpose**: Production-ready code
- **Protection**: Requires 2 approvals, CI passing, signed commits
- **Deployment**: Automatically deploys to production on merge
- **Merge Sources**: `release/*` and `hotfix/*` branches only

#### `develop`
- **Purpose**: Integration branch for next release
- **Protection**: Requires CI passing, PR merges only
- **Deployment**: Automatically deploys to staging environment
- **Merge Sources**: `feature/*` and `bugfix/*` branches

### Supporting Branches

#### `feature/*`
- **Purpose**: New feature development
- **Naming**: `feature/<short-descriptive-name>`
- **Base**: Created from `develop`
- **Merge Target**: `develop`
- **Lifecycle**: Deleted after merge

Examples:
```
feature/risk-dashboard
feature/cag-engine
feature/user-authentication
```

#### `bugfix/*`
- **Purpose**: Non-critical bug fixes
- **Naming**: `bugfix/<short-descriptive-name>`
- **Base**: Created from `develop`
- **Merge Target**: `develop`
- **Lifecycle**: Deleted after merge

Examples:
```
bugfix/dashboard-loading
bugfix/api-timeout
bugfix/chart-rendering
```

#### `release/*`
- **Purpose**: Prepare production release
- **Naming**: `release/vX.Y.Z`
- **Base**: Created from `develop`
- **Merge Target**: Both `main` and `develop`
- **Lifecycle**: Deleted after merge

Examples:
```
release/v1.0.0
release/v1.2.1
release/v2.0.0-beta.1
```

#### `hotfix/*`
- **Purpose**: Critical production fixes
- **Naming**: `hotfix/<short-descriptive-name>`
- **Base**: Created from `main`
- **Merge Target**: Both `main` and `develop`
- **Lifecycle**: Deleted after merge

Examples:
```
hotfix/security-patch
hotfix/critical-api-fix
hotfix/data-corruption
```

#### `docs/*`
- **Purpose**: Documentation-only updates
- **Naming**: `docs/<topic>`
- **Base**: Created from `develop` or `main`
- **Merge Target**: Source branch
- **Lifecycle**: Deleted after merge

Examples:
```
docs/api-reference
docs/deployment-guide
docs/architecture-update
```

## Workflow Diagrams

### Feature Development Flow


> **TODO**: This diagram requires manual conversion from Mermaid to PlantUML.
> See the PlantUML documentation for proper syntax.

```plantuml
@startuml
!theme plain
title Unknown Diagram Type (Conversion Required)

> **NOTE**: Unknown Mermaid diagram type.
> Manual conversion to PlantUML required.

rectangle "TODO: Convert to PlantUML" as TODO
@enduml
```

### Release Flow


> **TODO**: This diagram requires manual conversion from Mermaid to PlantUML.
> See the PlantUML documentation for proper syntax.

```plantuml
@startuml
!theme plain
title Unknown Diagram Type (Conversion Required)

> **NOTE**: Unknown Mermaid diagram type.
> Manual conversion to PlantUML required.

rectangle "TODO: Convert to PlantUML" as TODO
@enduml
```

### Hotfix Flow


> **TODO**: This diagram requires manual conversion from Mermaid to PlantUML.
> See the PlantUML documentation for proper syntax.

```plantuml
@startuml
!theme plain
title Unknown Diagram Type (Conversion Required)

> **NOTE**: Unknown Mermaid diagram type.
> Manual conversion to PlantUML required.

rectangle "TODO: Convert to PlantUML" as TODO
@enduml
```

## Branch Protection Rules

### `main` Branch
```yaml
protection_rules:
  required_status_checks:
    strict: true
    contexts:
      - "CI / test-backend"
      - "CI / test-frontend"
      - "CI / integration-tests"
      - "CI / security-scan"
  enforce_admins: true
  required_pull_request_reviews:
    required_approving_review_count: 2
    dismiss_stale_reviews: true
    require_code_owner_reviews: true
  restrictions:
    users: []
    teams: ["core-team"]
  required_signatures: true
```

### `develop` Branch
```yaml
protection_rules:
  required_status_checks:
    strict: true
    contexts:
      - "CI / test-backend"
      - "CI / test-frontend"
  enforce_admins: false
  required_pull_request_reviews:
    required_approving_review_count: 1
    dismiss_stale_reviews: true
  restrictions: null
```

## Commit Message Convention

We follow [Conventional Commits](https://www.conventionalcommits.org/) specification:

### Format
```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

### Types
- **feat**: New feature
- **fix**: Bug fix
- **docs**: Documentation changes
- **style**: Code style changes (formatting, etc.)
- **refactor**: Code refactoring
- **test**: Adding or updating tests
- **chore**: Maintenance tasks
- **ci**: CI/CD changes
- **perf**: Performance improvements
- **security**: Security improvements

### Examples
```
feat(coordinator): add task retry mechanism

Implements exponential backoff for failed agent tasks
with configurable max retries and timeout settings.

Closes #123
```

```
fix(api): resolve authentication token expiry

- Update JWT expiration handling
- Add token refresh endpoint
- Improve error messages

Fixes #456
```

```
docs(architecture): update agent interaction diagrams

Add sequence diagrams for new CAG/RAG integration
patterns and update API documentation.
```

## Pull Request Templates

### Feature PR Template
```markdown
## Description
Brief description of the changes

## Type of Change
- [ ] New feature
- [ ] Bug fix
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing completed

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] No breaking changes (or documented)
```

### Release PR Template
```markdown
## Release: v{version}

### Changes
- List of features
- List of bug fixes
- List of breaking changes

### Testing
- [ ] All tests passing
- [ ] Staging deployment successful
- [ ] Performance testing completed

### Documentation
- [ ] CHANGELOG.md updated
- [ ] API documentation updated
- [ ] Release notes prepared
```

## Workflow Integration

### CI/CD Triggers

#### Feature Branches
- **On Push**: Run unit tests, linting, type checking
- **On PR**: Full CI suite including integration tests
- **On Merge**: Deploy to feature environment (optional)

#### `develop` Branch
- **On Push**: Full CI suite
- **On Success**: Deploy to staging environment
- **On Failure**: Notify team via Slack

#### `release/*` Branches
- **On Creation**: Version validation, changelog check
- **On Push**: Full CI suite + security scans
- **On PR to main**: Production readiness checks

#### `main` Branch
- **On Merge**: Production deployment
- **On Tag**: Create GitHub release, publish documentation

### Automated Actions

#### Branch Cleanup
```yaml
# .github/workflows/cleanup.yml
name: Cleanup
on:
  pull_request:
    types: [closed]

jobs:
  cleanup:
    if: github.event.pull_request.merged == true
    runs-on: ubuntu-latest
    steps:
      - name: Delete merged branch
        run: |
          git push origin --delete ${{ github.head_ref }}
```

#### Release Automation
```yaml
# .github/workflows/release.yml
name: Release
on:
  push:
    branches: [main]
    tags: ['v*']

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - name: Create Release
        uses: softprops/action-gh-release@v1
        if: startsWith(github.ref, 'refs/tags/')
```

## Best Practices

### Branch Naming
- Use lowercase with hyphens
- Be descriptive but concise
- Include ticket/issue number when applicable

```bash
# Good
feature/user-authentication
bugfix/dashboard-loading-issue-123
hotfix/security-vulnerability-cve-2024-001

# Bad
feature/stuff
fix/bug
my-branch
```

### Commit Practices
- Make atomic commits (one logical change per commit)
- Write clear, descriptive commit messages
- Reference issues/tickets in commit messages
- Sign commits for security

### Pull Request Guidelines
- Keep PRs focused and reasonably sized
- Provide clear description and context
- Include testing instructions
- Request appropriate reviewers
- Respond to feedback promptly

### Code Review Standards
- Review for functionality, security, and maintainability
- Check test coverage and quality
- Verify documentation updates
- Ensure coding standards compliance
- Test locally when possible

## Emergency Procedures

### Critical Production Issue
1. Create `hotfix/*` branch from `main`
2. Implement minimal fix
3. Test thoroughly in staging
4. Create PR to `main` with emergency label
5. Get expedited review (1 approval minimum)
6. Deploy immediately after merge
7. Backport to `develop` branch

### Rollback Procedure
1. Identify last known good commit on `main`
2. Create `hotfix/rollback-to-{commit}`
3. Revert problematic changes
4. Follow standard hotfix process
5. Investigate and plan proper fix

## Tools and Automation

### Git Hooks
```bash
# pre-commit hook
#!/bin/sh
npm run lint
npm run type-check
python -m pytest tests/unit/
```

### Branch Management Scripts
```bash
# scripts/new-feature.sh
#!/bin/bash
git checkout develop
git pull origin develop
git checkout -b feature/$1
git push -u origin feature/$1
```

### Release Scripts
```bash
# scripts/prepare-release.sh
#!/bin/bash
VERSION=$1
git checkout develop
git pull origin develop
git checkout -b release/v$VERSION
npm version $VERSION
git add package*.json
git commit -m "chore: bump version to v$VERSION"
git push -u origin release/v$VERSION
```

---

**Next**: See [Contributing Guide](contributing.md) for detailed development workflow and [Release Process](releases.md) for deployment procedures.
