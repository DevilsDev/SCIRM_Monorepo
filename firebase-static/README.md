# Firebase Static Site Configuration

## Overview
This directory contains configuration for the **public static Firebase hosting** site that serves documentation without authentication. This is separate from the auth-gated Firebase site in `/firebase/`.

## Purpose
- **Public documentation sharing** without authentication barriers
- **Simple static hosting** for open documentation
- **Parallel deployment** alongside auth-gated site

## Configuration

### Firebase Project Setup
```bash
# Initialize static site (separate from auth-gated site)
firebase init hosting

# Select different hosting site ID from main Firebase project
# Example: scirm-dd5c3-static
```

### Deployment
```bash
# Deploy static site only
firebase deploy --only hosting

# Deploy from CI/CD
# Uses FIREBASE_SERVICE_ACCOUNT_KEY secret
```

## When to Use

### Use Static Site When:
- ✅ Public documentation sharing
- ✅ No authentication required
- ✅ Simple content delivery
- ✅ SEO-friendly public docs

### Use Auth-Gated Site When:
- 🔐 Internal documentation
- 🔐 Governance dashboards
- 🔐 Compliance materials
- 🔐 Sensitive technical details

## Security Considerations
- **No sensitive content** should be deployed to static site
- **Guard workflows** prevent internal dashboards from being included
- **Public by default** - assume all content is publicly accessible

## File Structure
```
firebase-static/
├── firebase.json          # Static hosting configuration
├── .firebaserc           # Project aliases
├── public/               # Static files (built from /site)
└── README.md            # This file
```

## Setup Checklist
- [ ] Firebase project configured with static hosting
- [ ] GitHub secrets configured (FIREBASE_SERVICE_ACCOUNT_KEY)
- [ ] Guard workflows prevent internal content inclusion
- [ ] CI/CD pipeline deploys from main branch only
