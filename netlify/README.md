# Netlify Static Site Configuration

## Overview
Configuration for **public static Netlify deployment** that serves documentation without authentication. This provides an alternative hosting option alongside Firebase static hosting.

## Purpose
- **Free tier hosting** for public documentation
- **CDN distribution** with global edge locations
- **Simple deployment** from GitHub integration
- **Backup hosting** option for Firebase static site

## Configuration

### Environment Variables
Required GitHub secrets for deployment:
```bash
NETLIFY_AUTH_TOKEN    # Personal access token from Netlify dashboard
NETLIFY_SITE_ID       # Site ID from Netlify site settings
```

### Setup Steps
1. **Create Netlify account** (free tier)
2. **Generate personal access token**:
   - Go to Netlify → User settings → Applications
   - Create new personal access token
   - Add to GitHub secrets as `NETLIFY_AUTH_TOKEN`
3. **Create new site**:
   - Note the Site ID from site settings
   - Add to GitHub secrets as `NETLIFY_SITE_ID`

## Free Tier Limits
- **100 GB bandwidth** per month
- **300 build minutes** per month
- **1000 form submissions** per month
- **Custom domains** supported
- **HTTPS** included

## Deployment
Automated via GitHub Actions:
```yaml
# .github/workflows/deploy-netlify.yml
- uses: netlify/actions/cli@master
  with:
    args: deploy --prod --dir=site
  env:
    NETLIFY_AUTH_TOKEN: ${{ secrets.NETLIFY_AUTH_TOKEN }}
    NETLIFY_SITE_ID: ${{ secrets.NETLIFY_SITE_ID }}
```

## Security Headers
Configured in `netlify.toml`:
- **HSTS** for HTTPS enforcement
- **Content Security Policy** for XSS protection
- **X-Content-Type-Options** to prevent MIME sniffing
- **Referrer Policy** for privacy

## Guard Protections
- **Branch restrictions**: Only deploys from `main`
- **Content filtering**: Prevents internal dashboards inclusion
- **Evidence capture**: All deployments logged to `/compliance/artifacts/`

## File Structure
```
netlify/
├── netlify.toml         # Netlify configuration
├── README.md           # This file
└── _headers            # Additional headers (optional)
```

## Troubleshooting

### Common Issues
- **Build failures**: Check MkDocs configuration
- **Missing secrets**: Verify GitHub secrets are set
- **Deploy limits**: Monitor free tier usage
- **Content blocked**: Check guard workflow logs

### Support
- [Netlify Documentation](https://docs.netlify.com/)
- [Netlify Community](https://community.netlify.com/)
- [GitHub Actions Integration](https://github.com/netlify/actions)
