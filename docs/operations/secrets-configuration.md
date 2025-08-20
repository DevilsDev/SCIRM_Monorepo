# Repository Secrets Configuration

This document outlines the required GitHub repository secrets for the SCIRM platform CI/CD pipeline and deployment automation.

## Required Secrets

### Deployment Secrets

#### `STAGING_KUBECONFIG`
**Description**: Kubernetes configuration for staging environment access  
**Format**: Base64 encoded kubeconfig file  
**Usage**: Used by deployment workflows to access staging Kubernetes cluster  
**Setup**:
```bash
# Generate kubeconfig for staging
kubectl config view --raw --minify > staging-kubeconfig.yaml
# Base64 encode the file
base64 -i staging-kubeconfig.yaml | tr -d '\n'
# Add the output to GitHub secrets
```

#### `PRODUCTION_KUBECONFIG`
**Description**: Kubernetes configuration for production environment access  
**Format**: Base64 encoded kubeconfig file  
**Usage**: Used by deployment workflows to access production Kubernetes cluster  
**Setup**:
```bash
# Generate kubeconfig for production
kubectl config view --raw --minify > production-kubeconfig.yaml
# Base64 encode the file
base64 -i production-kubeconfig.yaml | tr -d '\n'
# Add the output to GitHub secrets
```

### Monitoring & Alerting Secrets

#### `SLACK_WEBHOOK_URL`
**Description**: Slack webhook URL for deployment and alert notifications  
**Format**: `https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX`  
**Usage**: Sends notifications about deployment status, CI/CD results, and system alerts  
**Setup**:
1. Go to your Slack workspace
2. Create a new Slack app or use existing one
3. Enable Incoming Webhooks
4. Create a webhook for your desired channel
5. Copy the webhook URL to GitHub secrets

#### `GRAFANA_API_KEY`
**Description**: Grafana API key for dashboard management  
**Format**: `eyJrIjoiXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX`  
**Usage**: Updates monitoring dashboards during deployments  
**Setup**:
1. Log into Grafana instance
2. Go to Configuration → API Keys
3. Create new API key with Editor role
4. Copy the key to GitHub secrets

### External Service API Keys

#### `OPENAI_API_KEY`
**Description**: OpenAI API key for GPT-4 integration  
**Format**: `sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`  
**Usage**: Used by AI agents for natural language processing  
**Setup**: Obtain from OpenAI platform and add to secrets

#### `ANTHROPIC_API_KEY`
**Description**: Anthropic API key for Claude integration  
**Format**: `sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`  
**Usage**: Alternative AI model for agent processing  
**Setup**: Obtain from Anthropic console and add to secrets

#### `WEAVIATE_API_KEY`
**Description**: Weaviate vector database API key  
**Format**: `WVF5YThaHlkYwhGUSmCRgsX3tD5ngdN8pkih`  
**Usage**: Vector database operations for RAG functionality  
**Setup**: Obtain from Weaviate Cloud Services and add to secrets

#### `PINECONE_API_KEY`
**Description**: Pinecone vector database API key  
**Format**: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`  
**Usage**: Alternative vector database for embeddings  
**Setup**: Obtain from Pinecone console and add to secrets

### Database Secrets

#### `DATABASE_URL`
**Description**: PostgreSQL database connection string  
**Format**: `postgresql://username:password@host:port/database`  
**Usage**: Main application database connection  
**Setup**: Configure with your PostgreSQL instance credentials

#### `REDIS_URL`
**Description**: Redis cache connection string  
**Format**: `redis://username:password@host:port`  
**Usage**: Caching and session storage  
**Setup**: Configure with your Redis instance credentials

### Security & Compliance Secrets

#### `JWT_SECRET_KEY`
**Description**: Secret key for JWT token signing  
**Format**: 256-bit random string (base64 encoded)  
**Usage**: Authentication token generation and validation  
**Setup**:
```bash
# Generate secure random key
openssl rand -base64 32
```

#### `ENCRYPTION_KEY`
**Description**: AES encryption key for sensitive data  
**Format**: 256-bit random string (base64 encoded)  
**Usage**: Encrypt sensitive data at rest  
**Setup**:
```bash
# Generate encryption key
openssl rand -base64 32
```

## Setting Up Secrets

### Via GitHub Web Interface

1. Navigate to your repository on GitHub
2. Go to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Enter the secret name and value
5. Click **Add secret**

### Via GitHub CLI

```bash
# Set individual secrets
gh secret set STAGING_KUBECONFIG < staging-kubeconfig-base64.txt
gh secret set PRODUCTION_KUBECONFIG < production-kubeconfig-base64.txt
gh secret set SLACK_WEBHOOK_URL --body "https://hooks.slack.com/services/..."
gh secret set GRAFANA_API_KEY --body "eyJrIjoiXXXXXXXXXX..."

# Set API keys
gh secret set OPENAI_API_KEY --body "sk-xxxxxxxxxxxxxxxx..."
gh secret set ANTHROPIC_API_KEY --body "sk-ant-xxxxxxxxxxxxxxxx..."
gh secret set WEAVIATE_API_KEY --body "WVF5YThaHlkYwhGUSmCRgsX3tD5ngdN8pkih"
gh secret set PINECONE_API_KEY --body "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

# Set database URLs
gh secret set DATABASE_URL --body "postgresql://user:pass@host:5432/scirm"
gh secret set REDIS_URL --body "redis://user:pass@host:6379"

# Set security keys
gh secret set JWT_SECRET_KEY --body "$(openssl rand -base64 32)"
gh secret set ENCRYPTION_KEY --body "$(openssl rand -base64 32)"
```

### Bulk Setup Script

```bash
#!/bin/bash
# setup-secrets.sh - Bulk secret configuration

set -e

echo "🔐 Setting up SCIRM repository secrets..."

# Check if GitHub CLI is installed
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI not found. Please install gh CLI first."
    exit 1
fi

# Verify authentication
if ! gh auth status &> /dev/null; then
    echo "❌ Not authenticated with GitHub CLI. Run 'gh auth login' first."
    exit 1
fi

# Set deployment secrets
echo "📦 Setting deployment secrets..."
if [ -f "staging-kubeconfig.yaml" ]; then
    base64 -i staging-kubeconfig.yaml | tr -d '\n' | gh secret set STAGING_KUBECONFIG
    echo "✅ STAGING_KUBECONFIG set"
fi

if [ -f "production-kubeconfig.yaml" ]; then
    base64 -i production-kubeconfig.yaml | tr -d '\n' | gh secret set PRODUCTION_KUBECONFIG
    echo "✅ PRODUCTION_KUBECONFIG set"
fi

# Set security keys
echo "🔒 Generating and setting security keys..."
openssl rand -base64 32 | gh secret set JWT_SECRET_KEY
openssl rand -base64 32 | gh secret set ENCRYPTION_KEY
echo "✅ Security keys generated and set"

echo ""
echo "⚠️  Manual setup required for:"
echo "   - SLACK_WEBHOOK_URL (obtain from Slack)"
echo "   - GRAFANA_API_KEY (obtain from Grafana)"
echo "   - OPENAI_API_KEY (obtain from OpenAI)"
echo "   - ANTHROPIC_API_KEY (obtain from Anthropic)"
echo "   - WEAVIATE_API_KEY (obtain from Weaviate)"
echo "   - PINECONE_API_KEY (obtain from Pinecone)"
echo "   - DATABASE_URL (configure with your database)"
echo "   - REDIS_URL (configure with your Redis instance)"
echo ""
echo "📖 See docs/operations/secrets-configuration.md for detailed setup instructions"
```

## Environment-Specific Secrets

### Staging Environment
- Use development/staging API keys with limited quotas
- Point to staging databases and services
- Use test Slack channels for notifications

### Production Environment
- Use production API keys with full quotas
- Point to production databases with backups
- Use production Slack channels for alerts
- Enable additional monitoring and logging

## Security Best Practices

### Secret Rotation
- Rotate API keys every 90 days
- Update database credentials quarterly
- Regenerate JWT secrets after security incidents

### Access Control
- Limit repository access to authorized team members
- Use environment-specific secrets for different deployment stages
- Audit secret access regularly

### Monitoring
- Monitor API key usage and quotas
- Set up alerts for failed authentication attempts
- Log secret access for compliance auditing

## Troubleshooting

### Common Issues

#### Secret Not Found
```
Error: Secret STAGING_KUBECONFIG not found
```
**Solution**: Verify the secret name matches exactly (case-sensitive)

#### Invalid Kubeconfig
```
Error: Unable to connect to the server
```
**Solution**: Ensure kubeconfig is properly base64 encoded and has correct cluster access

#### API Key Quota Exceeded
```
Error: Rate limit exceeded for API key
```
**Solution**: Check API key quotas and upgrade plan if necessary

### Validation Script

```bash
#!/bin/bash
# validate-secrets.sh - Validate required secrets are configured

REQUIRED_SECRETS=(
    "STAGING_KUBECONFIG"
    "PRODUCTION_KUBECONFIG"
    "SLACK_WEBHOOK_URL"
    "GRAFANA_API_KEY"
    "OPENAI_API_KEY"
    "JWT_SECRET_KEY"
    "ENCRYPTION_KEY"
)

echo "🔍 Validating repository secrets..."

for secret in "${REQUIRED_SECRETS[@]}"; do
    if gh secret list | grep -q "$secret"; then
        echo "✅ $secret"
    else
        echo "❌ $secret (missing)"
    fi
done
```

## Next Steps

1. **Set up required secrets** using the methods above
2. **Test deployment pipeline** with staging environment
3. **Validate monitoring** and alerting integrations
4. **Document any custom secrets** specific to your environment
5. **Set up secret rotation** schedule and procedures
