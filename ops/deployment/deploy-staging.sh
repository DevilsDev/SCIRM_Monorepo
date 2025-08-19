#!/bin/bash

# SCIRM Platform Staging Deployment Script
# Deploys complete SCIRM platform to Kubernetes staging environment

set -e

echo "🚀 Starting SCIRM Platform Staging Deployment..."

# Configuration
NAMESPACE="scirm-staging"
DOCKER_REGISTRY="scirm"
VERSION=${1:-"latest"}

# Check prerequisites
echo "🔍 Checking prerequisites..."

# Check kubectl
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl not found. Please install kubectl."
    exit 1
fi

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found. Please install Docker."
    exit 1
fi

# Check cluster connection
if ! kubectl cluster-info &> /dev/null; then
    echo "❌ Cannot connect to Kubernetes cluster. Please check your kubeconfig."
    exit 1
fi

echo "✅ Prerequisites check passed"

# Build and push Docker images
echo "🏗️ Building and pushing Docker images..."

services=("coordinator" "planner" "researcher" "executor" "reviewer" "api-gateway")

for service in "${services[@]}"; do
    echo "Building $service..."
    if [ -d "services/$service" ]; then
        docker build -t $DOCKER_REGISTRY/$service:$VERSION services/$service/
    elif [ -d "apps/$service" ]; then
        docker build -t $DOCKER_REGISTRY/$service:$VERSION apps/$service/
    else
        echo "⚠️ Directory not found for $service, skipping..."
        continue
    fi
    
    # Push to registry (uncomment when registry is configured)
    # docker push $DOCKER_REGISTRY/$service:$VERSION
    echo "✅ Built $service:$VERSION"
done

# Build frontend
echo "Building frontend..."
docker build -t $DOCKER_REGISTRY/frontend:$VERSION apps/frontend/
# docker push $DOCKER_REGISTRY/frontend:$VERSION
echo "✅ Built frontend:$VERSION"

# Create namespace if it doesn't exist
echo "📁 Creating namespace..."
kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

# Apply RBAC configurations
echo "🔐 Applying RBAC configurations..."
kubectl apply -f security/rbac.yml

# Apply compliance configurations
echo "📋 Applying compliance configurations..."
kubectl apply -f compliance/

# Apply secrets and configmaps
echo "🔑 Applying secrets and configurations..."
kubectl apply -f infra/k8s/staging/secrets.yml

# Apply network policies
echo "🌐 Applying network policies..."
kubectl apply -f security/security-policy.yml

# Deploy infrastructure services first
echo "🗄️ Deploying infrastructure services..."

# PostgreSQL
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  namespace: $NAMESPACE
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:15
        env:
        - name: POSTGRES_DB
          value: scirm_staging
        - name: POSTGRES_USER
          value: scirm
        - name: POSTGRES_PASSWORD
          value: staging_password
        ports:
        - containerPort: 5432
        volumeMounts:
        - name: postgres-storage
          mountPath: /var/lib/postgresql/data
      volumes:
      - name: postgres-storage
        emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: $NAMESPACE
spec:
  selector:
    app: postgres
  ports:
  - port: 5432
    targetPort: 5432
EOF

# Redis
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
  namespace: $NAMESPACE
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        ports:
        - containerPort: 6379
---
apiVersion: v1
kind: Service
metadata:
  name: redis
  namespace: $NAMESPACE
spec:
  selector:
    app: redis
  ports:
  - port: 6379
    targetPort: 6379
EOF

# Weaviate
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: weaviate
  namespace: $NAMESPACE
spec:
  replicas: 1
  selector:
    matchLabels:
      app: weaviate
  template:
    metadata:
      labels:
        app: weaviate
    spec:
      containers:
      - name: weaviate
        image: semitechnologies/weaviate:1.21.2
        env:
        - name: QUERY_DEFAULTS_LIMIT
          value: "25"
        - name: AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED
          value: "true"
        - name: PERSISTENCE_DATA_PATH
          value: "/var/lib/weaviate"
        - name: DEFAULT_VECTORIZER_MODULE
          value: "none"
        - name: ENABLE_MODULES
          value: "text2vec-openai,generative-openai"
        ports:
        - containerPort: 8080
---
apiVersion: v1
kind: Service
metadata:
  name: weaviate
  namespace: $NAMESPACE
spec:
  selector:
    app: weaviate
  ports:
  - port: 8080
    targetPort: 8080
EOF

echo "⏳ Waiting for infrastructure services to be ready..."
kubectl wait --for=condition=available --timeout=300s deployment/postgres -n $NAMESPACE
kubectl wait --for=condition=available --timeout=300s deployment/redis -n $NAMESPACE
kubectl wait --for=condition=available --timeout=300s deployment/weaviate -n $NAMESPACE

# Deploy SCIRM services
echo "🤖 Deploying SCIRM agent services..."
kubectl apply -f infra/k8s/staging/coordinator-deployment.yml
kubectl apply -f infra/k8s/staging/all-services.yml

# Wait for deployments to be ready
echo "⏳ Waiting for SCIRM services to be ready..."
kubectl wait --for=condition=available --timeout=600s deployment/coordinator -n $NAMESPACE
kubectl wait --for=condition=available --timeout=600s deployment/planner -n $NAMESPACE
kubectl wait --for=condition=available --timeout=600s deployment/researcher -n $NAMESPACE
kubectl wait --for=condition=available --timeout=600s deployment/executor -n $NAMESPACE
kubectl wait --for=condition=available --timeout=600s deployment/reviewer -n $NAMESPACE
kubectl wait --for=condition=available --timeout=600s deployment/api-gateway -n $NAMESPACE
kubectl wait --for=condition=available --timeout=600s deployment/frontend -n $NAMESPACE

# Deploy monitoring stack
echo "📊 Deploying monitoring stack..."
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -

# Prometheus
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: prometheus
  namespace: monitoring
spec:
  replicas: 1
  selector:
    matchLabels:
      app: prometheus
  template:
    metadata:
      labels:
        app: prometheus
    spec:
      containers:
      - name: prometheus
        image: prom/prometheus:latest
        ports:
        - containerPort: 9090
        volumeMounts:
        - name: prometheus-config
          mountPath: /etc/prometheus/prometheus.yml
          subPath: prometheus.yml
      volumes:
      - name: prometheus-config
        configMap:
          name: prometheus-config
---
apiVersion: v1
kind: Service
metadata:
  name: prometheus
  namespace: monitoring
spec:
  selector:
    app: prometheus
  ports:
  - port: 9090
    targetPort: 9090
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: prometheus-config
  namespace: monitoring
data:
  prometheus.yml: |
    global:
      scrape_interval: 15s
    scrape_configs:
    - job_name: 'scirm-services'
      kubernetes_sd_configs:
      - role: pod
        namespaces:
          names:
          - scirm-staging
      relabel_configs:
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
        action: keep
        regex: true
EOF

# Grafana
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: grafana
  namespace: monitoring
spec:
  replicas: 1
  selector:
    matchLabels:
      app: grafana
  template:
    metadata:
      labels:
        app: grafana
    spec:
      containers:
      - name: grafana
        image: grafana/grafana:latest
        env:
        - name: GF_SECURITY_ADMIN_PASSWORD
          value: admin
        ports:
        - containerPort: 3000
---
apiVersion: v1
kind: Service
metadata:
  name: grafana
  namespace: monitoring
spec:
  selector:
    app: grafana
  ports:
  - port: 3000
    targetPort: 3000
  type: LoadBalancer
EOF

# Run database migrations
echo "🗄️ Running database migrations..."
kubectl exec -n $NAMESPACE deployment/coordinator -- python -c "
import asyncio
import asyncpg
import os

async def run_migrations():
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    
    # Read and execute init script
    with open('/app/scripts/init-db.sql', 'r') as f:
        sql = f.read()
    
    await conn.execute(sql)
    await conn.close()
    print('Database migrations completed')

asyncio.run(run_migrations())
" || echo "⚠️ Database migration failed, continuing..."

# Health checks
echo "🏥 Performing health checks..."
sleep 30

# Check service health
services_to_check=("coordinator" "planner" "researcher" "executor" "reviewer" "api-gateway")
for service in "${services_to_check[@]}"; do
    echo "Checking $service health..."
    kubectl exec -n $NAMESPACE deployment/$service -- curl -f http://localhost:8000/health || echo "⚠️ $service health check failed"
done

# Get service endpoints
echo "🌐 Service endpoints:"
kubectl get services -n $NAMESPACE
kubectl get services -n monitoring

# Get pod status
echo "📋 Pod status:"
kubectl get pods -n $NAMESPACE
kubectl get pods -n monitoring

echo ""
echo "🎉 SCIRM Platform staging deployment completed!"
echo ""
echo "📋 Access Information:"
echo "- API Gateway: $(kubectl get service api-gateway -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo 'Pending LoadBalancer IP')"
echo "- Frontend: $(kubectl get service frontend -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo 'Pending LoadBalancer IP')"
echo "- Grafana: $(kubectl get service grafana -n monitoring -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo 'Pending LoadBalancer IP'):3000"
echo "- Prometheus: kubectl port-forward -n monitoring svc/prometheus 9090:9090"
echo ""
echo "📖 Next steps:"
echo "1. Configure DNS records for LoadBalancer IPs"
echo "2. Set up SSL certificates"
echo "3. Configure external API keys in secrets"
echo "4. Run integration tests: make test-integration"
echo "5. Monitor system health in Grafana dashboard"
