# 📋 SCIRM Documentation Site Verification Checklist

**Site URL:** https://scirm-dd5c3.web.app  
**Purpose:** Manual QA checklist for Firebase Hosting deployments  
**Branch:** firebase-hosting only  
**Last Updated:** 2025-08-22

---

## 🖥️ UI Verification

- [ ] **Homepage loads** without broken styles/scripts
- [ ] **No repository links** visible anywhere on site
- [ ] **Sidebar shows** all public docs; pages render latest markdown
- [ ] **Mobile & desktop** responsive behavior verified
- [ ] **Footer shows** "Last Updated" timestamp & short commit SHA

## 🔒 Security Headers (via browser devtools or curl)

- [ ] **Strict-Transport-Security** present
- [ ] **X-Frame-Options:** DENY
- [ ] **X-Content-Type-Options:** nosniff
- [ ] **Content-Security-Policy** present, no inline script violations

## 📄 Content Policy

- [ ] **No /docs/dashboards/** or /compliance/dashboards/** content in site
- [ ] **No external links** other than allow-list (scirm-dd5c3.web.app, optional company domain)

## 🔄 One-Way Flow Process

This verification system enforces a strict one-way deployment flow:

1. **main** → Source of truth for documentation (NO DEPLOYMENTS)
2. **docs-sync workflow** → Syncs changes to firebase-hosting (dashboards excluded)
3. **firebase-hosting** → Exclusive deployment branch (ONLY branch that deploys)
4. **Firebase Hosting** → Live site at https://scirm-dd5c3.web.app

**Security Policy**: 
- ✅ Only firebase-hosting deploys
- 🚫 Main branch blocked from deployment  
- 🚫 Internal dashboards never sync to firebase-hosting
- 🔒 Content sanitizer blocks repository links and internal content

## 🌿 Branch Policy

- [ ] **Deployed commit** belongs to firebase-hosting
- [ ] **main or other branches** did not trigger a deploy

## 📊 Compliance Evidence

- [ ] **Deployment evidence JSON** exists for this release
- [ ] **Verification evidence JSON + Markdown** summary exist
- [ ] **Timestamps, commit SHA, workflow run URL** recorded

---

## ✅ Sign-Off

**Verifier:** ____________________  
**Date/Time:** ____________________  
**Deployment SHA:** ____________________  
**Overall Status:** ✅ PASS / ❌ FAIL  

**Notes:**  
_________________________________________________
