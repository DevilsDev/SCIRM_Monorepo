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
	docker-compose -f docker-compose.dev.yml up --build

dev-backend: ## Start backend services only
	@echo "🚀 Starting backend services..."
	docker-compose -f docker-compose.dev.yml up --build coordinator planner researcher executor reviewer api-gateway

dev-frontend: ## Start frontend development server
	@echo "🚀 Starting frontend development server..."
	cd apps/frontend && npm run dev

# Testing
test: ## Run all tests
	@echo "🧪 Running all tests..."
	$(MAKE) test-backend
	$(MAKE) test-frontend
	$(MAKE) test-integration

test-backend: ## Run backend tests
	@echo "🧪 Running backend tests..."
	python -m pytest services/ libs/ -v --cov=. --cov-report=html --cov-report=term

test-frontend: ## Run frontend tests
	@echo "🧪 Running frontend tests..."
	cd apps/frontend && npm test

test-integration: ## Run integration tests
	@echo "🧪 Running integration tests..."
	python -m pytest tests/integration/ -v

test-e2e: ## Run end-to-end tests
	@echo "🧪 Running E2E tests..."
	python -m pytest tests/e2e/ -v

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
build: ## Build all services
	@echo "🏗️ Building all services..."
	docker-compose build

build-backend: ## Build backend services
	@echo "🏗️ Building backend services..."
	docker build -t scirm/coordinator:latest services/coordinator/
	docker build -t scirm/planner:latest services/planner/
	docker build -t scirm/researcher:latest services/researcher/
	docker build -t scirm/executor:latest services/executor/
	docker build -t scirm/reviewer:latest services/reviewer/
	docker build -t scirm/api-gateway:latest apps/api-gateway/

build-frontend: ## Build frontend application
	@echo "🏗️ Building frontend..."
	cd apps/frontend && npm run build
	docker build -t scirm/frontend:latest apps/frontend/

# Documentation
docs: ## Build documentation
	@echo "📚 Building documentation..."
	mkdocs build

docs-serve: ## Serve documentation locally
	@echo "📚 Serving documentation at http://localhost:8001"
	mkdocs serve --dev-addr=localhost:8001

docs-deploy: ## Deploy documentation to GitHub Pages
	@echo "📚 Deploying documentation..."
	mkdocs gh-deploy --force

# Database
db-migrate: ## Run database migrations
	@echo "🗄️ Running database migrations..."
	alembic upgrade head

db-reset: ## Reset database
	@echo "🗄️ Resetting database..."
	alembic downgrade base
	alembic upgrade head

db-seed: ## Seed database with test data
	@echo "🌱 Seeding database..."
	python scripts/seed_database.py

# Deployment
deploy-staging: ## Deploy to staging environment
	@echo "🚀 Deploying to staging..."
	kubectl apply -f infra/k8s/staging/ --recursive
	kubectl rollout status deployment/coordinator -n scirm-staging
	kubectl rollout status deployment/frontend -n scirm-staging

deploy-prod: ## Deploy to production environment
	@echo "🚀 Deploying to production..."
	kubectl apply -f infra/k8s/production/ --recursive
	kubectl rollout status deployment/coordinator -n scirm-production
	kubectl rollout status deployment/frontend -n scirm-production

# Monitoring
logs: ## View application logs
	@echo "📋 Viewing logs..."
	kubectl logs -f deployment/coordinator -n scirm-staging

logs-prod: ## View production logs
	@echo "📋 Viewing production logs..."
	kubectl logs -f deployment/coordinator -n scirm-production

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

setup-git: ## Set up git hooks and branching
	@echo "🌿 Setting up git configuration..."
	chmod +x .github/scripts/setup-repository.sh
	./.github/scripts/setup-repository.sh

setup-env: ## Set up environment files
	@echo "⚙️ Setting up environment files..."
	cp .env.example .env.local
	cp .env.example .env.staging
	cp .env.example .env.production
	@echo "✅ Environment files created. Please update with actual values."

init: ## Initialize project for development
	@echo "🎯 Initializing SCIRM project..."
	$(MAKE) install
	$(MAKE) setup-env
	$(MAKE) db-migrate
	$(MAKE) db-seed
	@echo "✅ Project initialized successfully!"

# Health checks
health: ## Check service health
	@echo "🏥 Checking service health..."
	curl -f http://localhost:8000/health || echo "❌ API Gateway unhealthy"
	curl -f http://localhost:8001/health || echo "❌ Coordinator unhealthy"
	curl -f http://localhost:8002/health || echo "❌ Planner unhealthy"
	curl -f http://localhost:8003/health || echo "❌ Researcher unhealthy"
	curl -f http://localhost:8004/health || echo "❌ Executor unhealthy"
	curl -f http://localhost:8005/health || echo "❌ Reviewer unhealthy"

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
