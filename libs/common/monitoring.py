"""
SCIRM Monitoring and Observability Utilities
Prometheus metrics, structured logging, and health checks.
"""

import time
from typing import Dict, Any
from functools import wraps

from fastapi import FastAPI, Request, Response
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
import structlog

# Prometheus metrics
REQUEST_COUNT = Counter(
    'scirm_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code', 'service']
)

REQUEST_DURATION = Histogram(
    'scirm_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint', 'service']
)

ACTIVE_CONNECTIONS = Gauge(
    'scirm_active_connections',
    'Number of active connections',
    ['service']
)

AGENT_TASKS = Counter(
    'scirm_agent_tasks_total',
    'Total agent tasks processed',
    ['agent', 'task_type', 'status']
)

AGENT_PROCESSING_TIME = Histogram(
    'scirm_agent_processing_seconds',
    'Agent task processing time in seconds',
    ['agent', 'task_type']
)

def setup_monitoring(app: FastAPI, service_name: str = "unknown"):
    """Setup monitoring for a FastAPI application."""
    
    # Configure structured logging
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    @app.middleware("http")
    async def monitoring_middleware(request: Request, call_next):
        """Middleware to collect metrics and logs."""
        start_time = time.time()
        
        # Extract endpoint for metrics
        endpoint = request.url.path
        method = request.method
        
        logger = structlog.get_logger()
        logger.info(
            "Request started",
            method=method,
            endpoint=endpoint,
            client_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent")
        )
        
        try:
            response = await call_next(request)
            
            # Record metrics
            duration = time.time() - start_time
            REQUEST_COUNT.labels(
                method=method,
                endpoint=endpoint,
                status_code=response.status_code,
                service=service_name
            ).inc()
            
            REQUEST_DURATION.labels(
                method=method,
                endpoint=endpoint,
                service=service_name
            ).observe(duration)
            
            logger.info(
                "Request completed",
                method=method,
                endpoint=endpoint,
                status_code=response.status_code,
                duration_ms=duration * 1000
            )
            
            return response
            
        except Exception as e:
            duration = time.time() - start_time
            REQUEST_COUNT.labels(
                method=method,
                endpoint=endpoint,
                status_code=500,
                service=service_name
            ).inc()
            
            logger.error(
                "Request failed",
                method=method,
                endpoint=endpoint,
                error=str(e),
                duration_ms=duration * 1000
            )
            raise
    
    @app.get("/metrics")
    async def get_metrics():
        """Prometheus metrics endpoint."""
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

def track_agent_task(agent_name: str, task_type: str):
    """Decorator to track agent task metrics."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            logger = structlog.get_logger()
            
            try:
                logger.info(
                    "Agent task started",
                    agent=agent_name,
                    task_type=task_type
                )
                
                result = await func(*args, **kwargs)
                
                duration = time.time() - start_time
                AGENT_TASKS.labels(
                    agent=agent_name,
                    task_type=task_type,
                    status="success"
                ).inc()
                
                AGENT_PROCESSING_TIME.labels(
                    agent=agent_name,
                    task_type=task_type
                ).observe(duration)
                
                logger.info(
                    "Agent task completed",
                    agent=agent_name,
                    task_type=task_type,
                    duration_ms=duration * 1000
                )
                
                return result
                
            except Exception as e:
                duration = time.time() - start_time
                AGENT_TASKS.labels(
                    agent=agent_name,
                    task_type=task_type,
                    status="error"
                ).inc()
                
                logger.error(
                    "Agent task failed",
                    agent=agent_name,
                    task_type=task_type,
                    error=str(e),
                    duration_ms=duration * 1000
                )
                raise
        
        return wrapper
    return decorator

class HealthChecker:
    """Health check utilities."""
    
    def __init__(self):
        self.checks: Dict[str, callable] = {}
    
    def add_check(self, name: str, check_func: callable):
        """Add a health check."""
        self.checks[name] = check_func
    
    async def run_checks(self) -> Dict[str, Any]:
        """Run all health checks."""
        results = {}
        overall_healthy = True
        
        for name, check_func in self.checks.items():
            try:
                result = await check_func() if callable(check_func) else check_func()
                results[name] = {
                    "status": "healthy" if result else "unhealthy",
                    "details": result if isinstance(result, dict) else {}
                }
                if not result:
                    overall_healthy = False
            except Exception as e:
                results[name] = {
                    "status": "error",
                    "error": str(e)
                }
                overall_healthy = False
        
        return {
            "status": "healthy" if overall_healthy else "unhealthy",
            "checks": results
        }

# Global health checker instance
health_checker = HealthChecker()
