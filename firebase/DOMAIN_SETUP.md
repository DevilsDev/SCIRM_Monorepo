# Firebase Domain Configuration Fix

## Issue
Firebase Authentication is failing because the Netlify domain is not authorized.

## Required Steps

### 1. Add Authorized Domain in Firebase Console
1. Go to [Firebase Console](https://console.firebase.google.com/project/scirm-dd5c3/authentication/settings)
2. Navigate to Authentication → Settings → Authorized domains
3. Click "Add domain"
4. Add: `scirm-platform.windsurf.build`
5. Save changes

### 2. Update Firebase Hosting Configuration
The current setup serves from `scirm-dd5c3.firebaseapp.com` but users access via Netlify.

### 3. Alternative: Use Firebase Hosting Directly
Consider using Firebase hosting directly instead of Netlify:
- Domain: `https://scirm-dd5c3.web.app`
- No domain authorization issues
- Integrated with Cloud Functions

## Current Errors Fixed
- ✅ CSP frame-src policy updated
- ✅ Firebase config formatting corrected
- ⚠️ Domain authorization still needed

## Test After Domain Addition
1. Visit: `https://scirm-platform.windsurf.build/login.html`
2. Click "Sign in with Google"
3. Should work without configuration errors
