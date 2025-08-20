#!/bin/bash
# setup-secrets.sh - Bulk secret configuration for SCIRM platform

set -e

echo "🔐 Setting up SCIRM repository secrets..."

# Check if GitHub CLI is installed
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI not found. Please install gh CLI first."
    echo "   Visit: https://cli.github.com/"
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
else
    echo "⚠️  staging-kubeconfig.yaml not found - create this file first"
fi

if [ -f "production-kubeconfig.yaml" ]; then
    base64 -i production-kubeconfig.yaml | tr -d '\n' | gh secret set PRODUCTION_KUBECONFIG
    echo "✅ PRODUCTION_KUBECONFIG set"
else
    echo "⚠️  production-kubeconfig.yaml not found - create this file first"
fi

# Set security keys
echo "🔒 Generating and setting security keys..."
openssl rand -base64 32 | gh secret set JWT_SECRET_KEY
openssl rand -base64 32 | gh secret set ENCRYPTION_KEY
echo "✅ Security keys generated and set"

# Prompt for manual secrets
echo ""
echo "📝 Setting up manual secrets..."

read -p "Enter Slack Webhook URL (or press Enter to skip): " SLACK_URL
if [ ! -z "$SLACK_URL" ]; then
    echo "$SLACK_URL" | gh secret set SLACK_WEBHOOK_URL
    echo "✅ SLACK_WEBHOOK_URL set"
fi

read -p "Enter Grafana API Key (or press Enter to skip): " GRAFANA_KEY
if [ ! -z "$GRAFANA_KEY" ]; then
    echo "$GRAFANA_KEY" | gh secret set GRAFANA_API_KEY
    echo "✅ GRAFANA_API_KEY set"
fi

read -p "Enter OpenAI API Key (or press Enter to skip): " OPENAI_KEY
if [ ! -z "$OPENAI_KEY" ]; then
    echo "$OPENAI_KEY" | gh secret set OPENAI_API_KEY
    echo "✅ OPENAI_API_KEY set"
fi

read -p "Enter Anthropic API Key (or press Enter to skip): " ANTHROPIC_KEY
if [ ! -z "$ANTHROPIC_KEY" ]; then
    echo "$ANTHROPIC_KEY" | gh secret set ANTHROPIC_API_KEY
    echo "✅ ANTHROPIC_API_KEY set"
fi

read -p "Enter Database URL (or press Enter to skip): " DB_URL
if [ ! -z "$DB_URL" ]; then
    echo "$DB_URL" | gh secret set DATABASE_URL
    echo "✅ DATABASE_URL set"
fi

read -p "Enter Redis URL (or press Enter to skip): " REDIS_URL
if [ ! -z "$REDIS_URL" ]; then
    echo "$REDIS_URL" | gh secret set REDIS_URL
    echo "✅ REDIS_URL set"
fi

echo ""
echo "🎉 Secret setup complete!"
echo ""
echo "📋 Summary of configured secrets:"
gh secret list
echo ""
echo "📖 For detailed configuration instructions, see:"
echo "   docs/operations/secrets-configuration.md"
