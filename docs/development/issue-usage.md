# GitHub Issue Templates Usage Guide

This guide explains when and how to use each GitHub issue template in the SCIRM project, along with required CI checks and best practices.

## Issue Templates Overview

### 🎯 Epic Template
**Use for**: Large cross-cutting initiatives that span multiple services or components
- **Examples**: Core OLTP API, RAG Ingestion & Search, Agent Swarm Orchestration, CAG Guardrails, Observability & Dashboards
- **Default Labels**: `type: epic`, `prio: p1`
- **Key Sections**: Context, Goals & Non-Goals, Scope (In/Out), Deliverables, Acceptance Criteria, Definition of Done, Dependencies, Risks & Mitigations, Task Checklist

### 🔧 Task/Feature Template
**Use for**: Shippable units beneath epics (service endpoints, pipelines, dashboards)
- **Examples**: User authentication endpoint, database migration, monitoring dashboard, API documentation
- **Default Labels**: `type: task`, `prio: p1`
- **Key Sections**: Summary, Background, Implementation Plan, Testing Plan, Documentation Updates, Acceptance Criteria, Implementation Checklist

### 🐛 Bug Report Template
**Use for**: Reporting bugs or defects in the SCIRM system
- **Examples**: Build failures, API errors, UI issues, performance problems
- **Default Labels**: `type: bug`, `prio: p1`
- **Key Sections**: Environment, Steps to Reproduce, Expected vs Actual Behavior, Logs/Artifacts, Impact Assessment, Workaround, Root Cause, Fix Plan, Verification Steps

### 📚 Debugging Playbook Template
**Use for**: Creating reusable debugging runbooks and troubleshooting guides
- **Examples**: MkDocs Strict Build Fails, Firebase Hosting Deploy Fails, Database Migrations & RLS, RAG Ingestion/Search Breaks
- **Default Labels**: `type: task`, `prio: p1`
- **Key Sections**: Symptoms, Probable Causes, Step-by-Step Fix, Verification, Prevention, Copy-Paste Checklist, Post-Mortem Template

## Label System

### Type Labels
- `type: epic` - Large cross-cutting initiatives
- `type: feature` - New features or enhancements
- `type: task` - Tasks or maintenance work
- `type: bug` - Bugs or defects
- `type: doc` - Documentation updates

### Area Labels
- `area: api` - API Gateway and endpoints
- `area: database` - Database and migrations
- `area: rag` - RAG ingestion and search
- `area: agents` - Agent swarm orchestration
- `area: cag` - Context-aware guardrails
- `area: observability` - Monitoring and metrics
- `area: ci-cd` - CI/CD pipelines
- `area: deploy` - Deployment and hosting
- `area: docs` - Documentation system

### Priority Labels
- `prio: p0` - Critical priority (system down, security issues)
- `prio: p1` - High priority (major features, important bugs)
- `prio: p2` - Medium priority (enhancements, minor issues)

### Risk Labels
- `risk: security` - Security-related risks
- `risk: compliance` - Compliance-related risks
- `risk: data` - Data-related risks

### Status Labels
- `blocked` - Blocked by dependency
- `needs: design` - Needs design review
- `needs: decision` - Needs architectural or business decision
- `good first issue` - Good for newcomers

## Branch Strategy & CI Requirements

### Branch Strategy
- **Work branches**: `feat/*` for features, `fix/*` for bugs, `docs/*` for documentation
- **Target branch**: All PRs merge into `main`
- **Docs deployment**: Only from `firebase-hosting` branch

### Required CI Checks
All PRs must pass the following checks:
1. **Build** - Code compiles successfully
2. **Lint** - Code style and formatting checks
3. **Tests** - Unit, integration, and contract tests
4. **Security scans** - SAST, dependency vulnerability checks
5. **MkDocs strict build** - Documentation builds without warnings
6. **Content sanitizer** - No internal links in public docs

### Documentation Updates
When creating issues that require documentation updates, specify which files need changes:
- `docs/product/prd.md` - Product Requirements Document
- `docs/product/pdd.md` - Product Design Document
- `docs/architecture/database.md` - Database architecture
- `docs/roadmap/roadmap.md` - Project roadmap
- `docs/architecture/adr/` - Architecture Decision Records

## Best Practices

### Epic Issues
- Break down into smaller, manageable tasks
- Include clear acceptance criteria and definition of done
- Link to relevant documentation paths (no external repo links)
- Add ADR reminder for architectural changes
- Specify dependencies clearly

### Task/Feature Issues
- Include implementation and testing plans
- Specify documentation update requirements
- Provide detailed acceptance criteria with checkboxes
- Consider risks and mitigation strategies

### Bug Reports
- Provide detailed reproduction steps
- Include environment information and logs
- Assess impact and priority accurately
- Suggest workarounds when possible
- Plan verification steps for fixes

### Debugging Playbooks
- Focus on reusable, step-by-step solutions
- Include copy-paste command checklists
- Provide prevention strategies
- Use consistent post-mortem format

## Seeding Canonical Issues

Use the "Seed Issues" workflow to create standard Epic and Playbook issues:

1. Go to **Actions** → **Seed GitHub Issues**
2. Click **Run workflow**
3. Optionally enable **dry run** to preview changes
4. Review created issues and customize as needed

The workflow creates:
- **5 Epic Issues**: Core OLTP API, RAG Ingestion & Search, Agent Swarm Orchestration, CAG Guardrails, Observability & Dashboards
- **8 Debugging Playbooks**: Common troubleshooting scenarios

## Quality Gates

### Before Creating Issues
- Choose the appropriate template
- Apply correct labels
- Fill all required fields
- Reference internal documentation paths only

### Before Closing Issues
- Verify acceptance criteria met
- Ensure CI checks pass
- Update related documentation
- Add post-mortem for bugs (if applicable)

## Support & Resources

- **Documentation**: Check `docs/` directory for comprehensive guides
- **Security Issues**: Use GitHub Security Advisories for vulnerabilities
- **Architecture Decisions**: Document in `docs/architecture/adr/`
- **CI/CD Issues**: Check workflow files in `.github/workflows/`

---

**Remember**: All work follows Google SD&D principles with design-first approach, quality gates, and comprehensive testing requirements.
