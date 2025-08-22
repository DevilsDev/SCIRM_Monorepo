# SCIRM Documentation

This directory contains the complete documentation for the SCIRM (Supply Chain Intelligence & Risk Management) platform.

## 📖 Documentation Site

The documentation is published as a static website using MkDocs Material:
- **Public URL**: https://scirm-dd5c3.web.app
- **Build System**: MkDocs with Material theme
- **Deployment**: Automated via GitHub Actions from `main` branch

## 📁 Structure

```
docs/
├── intro/              # Platform overview and getting started
│   ├── overview.md     # What is SCIRM
│   └── getting-started.md
├── product/            # Product documentation
│   ├── prd.md         # Product Requirements Document
│   ├── pdd.md         # Product Design Document
│   └── anti-patterns.md
├── architecture/       # Technical architecture
│   ├── system-overview.md
│   ├── agents.md      # Multi-agent architecture
│   └── adr/           # Architecture Decision Records
├── security/           # Security and compliance
├── roadmap/            # Development roadmap
├── changelog/          # Release notes and history
├── support/            # FAQ and troubleshooting
└── assets/             # Images, diagrams, and media
```

## ✍️ Content Guidelines

### Writing Standards
- **Markdown Format**: Use standard Markdown with front matter
- **Relative Links**: All links must be relative to the docs directory
- **Local Assets**: Store all images in `/docs/assets/`
- **No Repository Links**: Avoid links to GitHub or external code repositories

### Link Examples
```markdown
✅ Good: [Architecture Overview](architecture/system-overview.md)
✅ Good: ![Diagram](assets/architecture-diagram.png)
❌ Avoid: [External Code Links](https://external-repo.com/code/)
❌ Avoid: Edit this page links
```

### Page Structure
Each documentation page should follow this structure:

```markdown
# Page Title

Brief introduction explaining the purpose and scope.

## Main Sections

Content organized with clear headings and subheadings.

### Subsections

Detailed information with examples and code blocks where appropriate.

## Related Pages

- [Related Topic 1](../other-section/topic.md)
- [Related Topic 2](./another-topic.md)
```

## 🔧 Local Development

### Prerequisites
```bash
pip install mkdocs-material mkdocs-mermaid2-plugin
```

### Commands
```bash
# Serve locally with hot reload
mkdocs serve

# Build static site
mkdocs build

# Build with strict mode (fails on warnings)
mkdocs build --strict
```

### Testing
```bash
# Validate all links work
mkdocs build --strict

# Check for repository links (should return no results)
grep -r "repository-links" docs/

# Verify no internal dashboard content
find docs/ -path "*/dashboards/*" -name "*.md"
```

## 🚀 Publishing

### Automatic Deployment
Documentation automatically deploys when changes are pushed to `main`:

1. Make changes to files in `/docs/`
2. Commit and push to `main` branch
3. GitHub Actions builds and deploys to Firebase Hosting
4. Site updates at https://scirm-dd5c3.web.app

### Manual Deployment
For immediate deployment:

```bash
# Build documentation
mkdocs build

# Deploy to Firebase (requires Firebase CLI)
cd firebase-static
firebase deploy --only hosting
```

## 🛡️ Content Security

### Branch Isolation
- **main**: Public documentation only
- **internal-dashboards**: Internal content (never deployed publicly)
- Automated guards prevent internal content from being deployed publicly

### Compliance
- All deployments generate audit evidence
- Evidence stored in `/compliance/artifacts/deployment-logs/`
- Includes timestamps, commit SHAs, and security scan results

## 📝 Contributing

### Adding New Content
1. Create new `.md` files in appropriate directories
2. Update `mkdocs.yml` navigation if needed
3. Use relative links and local assets only
4. Test locally with `mkdocs serve`
5. Submit pull request to `main` branch

### Updating Existing Content
1. Edit existing `.md` files
2. Maintain existing link structure
3. Update related pages if necessary
4. Test build with `mkdocs build --strict`

### Content Review
All documentation changes require:
- Technical accuracy review
- Link validation
- Compliance with style guidelines
- No repository references

## 🎯 Content Strategy

### Target Audiences
- **Executives**: High-level overview and business value
- **Technical Teams**: Architecture and implementation details
- **End Users**: Getting started and user guides
- **Compliance**: Security and governance documentation

### Content Types
- **Conceptual**: What is SCIRM and why use it
- **Procedural**: How to use features and capabilities
- **Reference**: Technical specifications and APIs
- **Troubleshooting**: Common issues and solutions

This documentation system provides comprehensive, secure, and maintainable documentation for the SCIRM platform while ensuring content isolation and compliance requirements.
