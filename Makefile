# SCIRM Platform Makefile
# AI-Powered Supply Chain Risk Management Platform

.PHONY: help install dev test lint format build deploy clean docs

# Default target
help: ## Show this help message
	@echo "SCIRM Platform - Available Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Environment setup
install: ## Install all dependencies
	@echo "🔧 Installing dependencies..."
	pip install -r requirements.txt
	pip install -r requirements-dev.txt
	cd apps/frontend && npm install
	@echo "✅ Dependencies installed"

install-dev: ## Install development dependencies only
	@echo "🔧 Installing development dependencies..."
	pip install -r requirements-dev.txt
	cd apps/frontend && npm install --only=dev
	@echo "✅ Development dependencies installed"

# Development
dev: ## Start development environment
	@echo "🚀 Starting SCIRM development environment..."
	docker compose -f docker-compose.dev.yml up --build

dev-backend: ## Start backend services only
	@echo "🚀 Starting backend services..."
	docker compose -f docker-compose.dev.yml up --build postgres migrate coordinator planner researcher executor reviewer ingestion api-gateway

dev-frontend: ## Start frontend development server
	@echo "🚀 Starting frontend development server..."
	cd apps/frontend && npm run dev

# Testing
test: ## Run backend and frontend tests (as CI does)
	@echo "🧪 Running all tests..."
	$(MAKE) test-backend
	$(MAKE) test-frontend

test-backend: ## Run backend tests (in-memory store; set STORE_BACKEND=postgres and TEST_POSTGRES_URL for PostgreSQL)
	@echo "🧪 Running backend tests..."
	python -m pytest tests/security tests/ai_trust tests/intel tests/evidence tests/erp tests/db -q

test-frontend: ## Run frontend tests
	@echo "🧪 Running frontend tests..."
	cd apps/frontend && npm test

test-integration: ## Run integration tests against a running stack (make dev)
	@echo "🧪 Running integration tests..."
	python -m pytest tests/integration/ -v

test-load: ## Run load tests
	@echo "🧪 Running load tests..."
	locust -f tests/load/locustfile.py --headless -u 100 -r 10 -t 60s --host=http://localhost:8000

# Code quality
lint: ## Run linting on all code
	@echo "🔍 Running linters..."
	black --check .
	isort --check-only .
	flake8 .
	mypy services/ libs/
	cd apps/frontend && npm run lint

format: ## Format all code
	@echo "✨ Formatting code..."
	black .
	isort .
	cd apps/frontend && npm run format

type-check: ## Run type checking
	@echo "🔍 Running type checks..."
	mypy services/ libs/

security-scan: ## Run security scans
	@echo "🔒 Running security scans..."
	bandit -r services/ libs/
	safety check
	cd apps/frontend && npm audit

# Build
SERVICES := coordinator planner researcher executor reviewer risk-scorer discovery ingestion chat simulator procurement component-tracker

build: ## Build all services
	@echo "🏗️ Building all services..."
	docker compose -f docker-compose.dev.yml build

build-backend: ## Build backend service images (shared Dockerfile, repo-root context)
	@echo "🏗️ Building backend services..."
	@for svc in $(SERVICES); do \
		extra=""; \
		if [ "$$svc" = "researcher" ]; then extra="--build-arg EXTRA_PIP=weaviate-client==3.26.7"; fi; \
		docker build -f docker/service.Dockerfile --build-arg SERVICE_PATH=services/$$svc $$extra -t scirm/$$svc:latest . || exit 1; \
	done
	docker build -f docker/service.Dockerfile --build-arg SERVICE_PATH=apps/api-gateway -t scirm/api-gateway:latest .

build-frontend: ## Build frontend application
	@echo "🏗️ Building frontend..."
	docker build -t scirm/frontend:latest apps/frontend/

# Documentation
docs: ## Build documentation (strict, as CI does)
	@echo "📚 Building documentation..."
	mkdocs build --strict

docs-serve: ## Serve documentation locally
	@echo "📚 Serving documentation at http://localhost:8001"
	mkdocs serve --dev-addr=localhost:8001

# Database
db-migrate: ## Run migrations, configure the scirm_app role and seed demo tenants (Compose)
	@echo "🗄️ Running database migrations..."
	docker compose -f docker-compose.dev.yml run --rm migrate

db-reset: ## Reset database
	@echo "🗄️ Resetting database..."
	alembic downgrade base
	alembic upgrade head

# Deployment
deploy-staging: ## Deploy to staging environment
	@echo "🚀 Deploying to staging..."
	kubectl apply -f infra/k8s/staging/ --recursive
	kubectl rollout status deployment/coordinator -n scirm-staging
	kubectl rollout status deployment/frontend -n scirm-staging

# Monitoring
logs: ## View application logs
	@echo "📋 Viewing logs..."
	kubectl logs -f deployment/coordinator -n scirm-staging

metrics: ## Open Grafana dashboard
	@echo "📊 Opening Grafana dashboard..."
	kubectl port-forward svc/grafana 3000:3000 -n monitoring

# Utilities
clean: ## Clean up build artifacts
	@echo "🧹 Cleaning up..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf .coverage htmlcov/
	cd apps/frontend && rm -rf node_modules/ dist/ build/

setup-env: ## Create .env from .env.example (never overwrites an existing .env)
	@echo "⚙️ Setting up .env..."
	@test -f .env && echo ".env already exists; left unchanged" || (cp .env.example .env && echo "✅ .env created. Fill in values; never commit it.")

init: ## Initialize project for development
	@echo "🎯 Initializing SCIRM project..."
	$(MAKE) install
	$(MAKE) setup-env
	$(MAKE) db-migrate
	@echo "✅ Project initialized successfully!"

# Health checks
health: ## Check service health
	@echo "🏥 Checking service health..."
	curl -f http://localhost:8000/health || echo "API Gateway unhealthy"
	# Agent services are not published on the host; Docker reports their /ready health checks.
	docker compose -f docker-compose.dev.yml ps --format "table {{.Service}}	{{.Status}}"

# Version management
version: ## Show current version
	@echo "SCIRM Platform v$(shell cat VERSION)"

bump-version: ## Bump version (usage: make bump-version VERSION=1.2.0)
	@echo "📈 Bumping version to $(VERSION)..."
	echo "$(VERSION)" > VERSION
	git add VERSION
	git commit -m "chore: bump version to $(VERSION)"
	git tag -a "v$(VERSION)" -m "Release v$(VERSION)"
	@echo "✅ Version bumped to $(VERSION)"
