# SCIRM - Supply Chain Intelligence & Risk Management

AI-powered platform for predictive supply chain risk management with multi-agent architecture and real-time analytics.

## 📚 Documentation

The SCIRM documentation is published as a static website with two deployment options:

### Public Static Documentation
- **URL**: https://scirm-dd5c3.web.app
- **Content**: Public-facing documentation, architecture, and user guides
- **Deployment**: Automated from `main` branch via GitHub Actions
- **Build**: MkDocs Material theme with search and navigation

### Auth-Gated Internal Documentation
- **URL**: https://scirm-dd5c3.firebaseapp.com
- **Content**: Internal dashboards, compliance cockpit, and governance materials
- **Authentication**: Google OAuth with session cookies
- **Access**: Restricted to authorized team members only

## 🚀 Publishing Documentation

### Firebase Hosting Deployment Process
Documentation deploys **ONLY** from the `firebase-hosting` branch to ensure security and proper review:

```bash
# 1. Make documentation changes on main
git checkout main
git add docs/
git commit -S -m "docs: update documentation"
git push origin main

# 2. Create deployment PR from main to firebase-hosting
git checkout firebase-hosting
git pull origin firebase-hosting
git checkout -b deploy/update-docs-$(date +%Y%m%d)
git merge main
git push origin deploy/update-docs-$(date +%Y%m%d)

# 3. Open PR: deploy/update-docs-YYYYMMDD → firebase-hosting
# 4. After PR approval and merge → automatic deployment triggers
```

### Emergency Deployment
For urgent fixes (authorized personnel only):

```bash
# Direct push to firebase-hosting (creates audit trail)
git checkout firebase-hosting
git merge main
git push origin firebase-hosting
# Immediately create audit PR: firebase-hosting → main
```

## 📁 Documentation Structure

```
docs/
├── intro/              # Overview and getting started
├── product/            # PRD, PDD, and anti-patterns
├── architecture/       # System design and ADRs
├── security/           # Security overview and compliance
├── roadmap/            # Development roadmap
├── changelog/          # Release notes and history
├── support/            # FAQ and troubleshooting
└── assets/             # Images and diagrams
```

## ✍️ Authoring Guidelines

### Content Standards
- Use **Markdown** format with front matter
- Include **relative links** only (no repository links)
- Store **images** in `/docs/assets/` directory
- Follow **MkDocs Material** formatting conventions

### Link Hygiene
❌ **Avoid**: Links to repository or external code
❌ **Avoid**: Edit buttons or "View Source" links
✅ **Use**: Relative links within documentation site
✅ **Use**: Local asset references

### Example Page Structure
```markdown
# Page Title

Brief introduction paragraph.

## Section Header

Content with [relative links](../other-page.md) and local images:

![Diagram](../assets/diagram.png)
```

## 🛡️ Branch Strategy & Guards

### Branch Protection
- **main**: Production documentation, requires 2 approvals
- **internal-dashboards**: Internal content only, never deployed publicly
- **firebase-setup**: Infrastructure scaffolding
- **netlify-setup**: Netlify configuration

### Deployment Guards
- ✅ Only `firebase-hosting` branch can deploy public documentation
- ✅ `main` branch blocked from deployments (source of truth only)
- ✅ Internal dashboards blocked from public deployment
- ✅ Content isolation enforced via CI/CD
- ✅ Repository links automatically detected and blocked
- ✅ Guard workflows prevent unauthorized deployment attempts

## 🔧 Local Development

### Setup
```bash
# Install MkDocs
pip install mkdocs-material mkdocs-mermaid2-plugin

# Serve locally
mkdocs serve

# Build for production
mkdocs build --strict
```

### Testing
```bash
# Validate configuration
mkdocs build --strict

# Check for repository links
grep -r "github.com" docs/

# Validate internal content isolation
find docs/ -path "*/dashboards/*" -name "*.md"
```

## 📋 Compliance & Evidence

All deployments generate compliance evidence automatically:
- **Location**: `/compliance/artifacts/deployment-logs/`
- **Format**: JSON with deployment metadata
- **Retention**: Permanent audit trail
- **Contents**: Timestamps, commit SHAs, security scans, compliance checks

## 🏗️ Platform Architecture

SCIRM implements a multi-agent AI architecture with:
- **5 Specialized Agents**: Coordinator, Planner, Researcher, Executor, Reviewer
- **Sub-500ms Response**: Real-time risk assessment
- **Enterprise Security**: SOC2, GDPR, HIPAA compliance
- **Kubernetes Deployment**: Cloud-native scalability

For detailed technical information, visit the [documentation site](https://scirm-dd5c3.web.app).

## 📞 Support

- **Documentation Issues**: Create repository issue
- **Access Requests**: Contact system administrators
- **Technical Support**: See documentation support section