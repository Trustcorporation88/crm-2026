# prometheus_metrics.py - Prometheus metrics for monitoring
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry
from fastapi import FastAPI, Request
from fastapi.responses import Response
import time
from structured_logging import get_logger

logger = get_logger("prometheus_metrics")

# Create registry
REGISTRY = CollectorRegistry()

# HTTP Metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
    registry=REGISTRY
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration",
    ["method", "endpoint"],
    registry=REGISTRY
)

http_request_size_bytes = Histogram(
    "http_request_size_bytes",
    "HTTP request size",
    ["method", "endpoint"],
    registry=REGISTRY
)

http_response_size_bytes = Histogram(
    "http_response_size_bytes",
    "HTTP response size",
    ["method", "endpoint"],
    registry=REGISTRY
)

# Application Metrics
active_connections = Gauge(
    "active_connections",
    "Active database connections",
    registry=REGISTRY
)

database_query_duration_seconds = Histogram(
    "database_query_duration_seconds",
    "Database query duration",
    ["operation", "table"],
    registry=REGISTRY
)

# Business Metrics
customers_total = Gauge(
    "customers_total",
    "Total customers",
    registry=REGISTRY
)

tickets_open = Gauge(
    "tickets_open",
    "Open tickets",
    registry=REGISTRY
)

deals_pipeline_value = Gauge(
    "deals_pipeline_value",
    "Total deal pipeline value",
    ["stage"],
    registry=REGISTRY
)

# Authentication Metrics
login_attempts_total = Counter(
    "login_attempts_total",
    "Total login attempts",
    ["result"],  # success, failed
    registry=REGISTRY
)

# Cache Metrics
cache_hits_total = Counter(
    "cache_hits_total",
    "Total cache hits",
    ["cache_type"],
    registry=REGISTRY
)

cache_misses_total = Counter(
    "cache_misses_total",
    "Total cache misses",
    ["cache_type"],
    registry=REGISTRY
)

# Webhook Metrics
webhook_deliveries_total = Counter(
    "webhook_deliveries_total",
    "Total webhook deliveries",
    ["event_type", "status"],
    registry=REGISTRY
)

def add_metrics_middleware(app: FastAPI):
    """Add Prometheus metrics middleware to FastAPI app"""
    
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        start_time = time.time()
        
        # Extract endpoint
        endpoint = request.url.path
        method = request.method
        
        try:
            # Get request size
            if request.method in ["POST", "PUT", "PATCH"]:
                body = await request.body()
                http_request_size_bytes.labels(
                    method=method,
                    endpoint=endpoint
                ).observe(len(body))
                
                # Re-create receive for body consumption
                async def receive():
                    return {"type": "http.disconnect"}
                
                request._receive = receive
        except Exception:
            pass
        
        response = await call_next(request)
        
        # Record metrics
        duration = time.time() - start_time
        
        http_request_duration_seconds.labels(
            method=method,
            endpoint=endpoint
        ).observe(duration)
        
        http_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status=response.status_code
        ).inc()
        
        try:
            http_response_size_bytes.labels(
                method=method,
                endpoint=endpoint
            ).observe(response.headers.get("content-length", 0))
        except Exception:
            pass
        
        logger.debug(
            "HTTP request processed",
            method=method,
            endpoint=endpoint,
            status=response.status_code,
            duration_ms=duration * 1000
        )
        
        return response

def record_login_attempt(success: bool):
    """Record login attempt"""
    result = "success" if success else "failed"
    login_attempts_total.labels(result=result).inc()

def record_cache_hit(cache_type: str):
    """Record cache hit"""
    cache_hits_total.labels(cache_type=cache_type).inc()

def record_cache_miss(cache_type: str):
    """Record cache miss"""
    cache_misses_total.labels(cache_type=cache_type).inc()

def record_webhook_delivery(event_type: str, success: bool):
    """Record webhook delivery"""
    status = "success" if success else "failed"
    webhook_deliveries_total.labels(event_type=event_type, status=status).inc()

def record_database_query(operation: str, table: str, duration_ms: float):
    """Record database query"""
    database_query_duration_seconds.labels(
        operation=operation,
        table=table
    ).observe(duration_ms / 1000)

def update_business_metrics(
    total_customers: int = None,
    open_tickets: int = None,
    pipeline_by_stage: dict = None
):
    """Update business metrics"""
    if total_customers is not None:
        customers_total.set(total_customers)
    
    if open_tickets is not None:
        tickets_open.set(open_tickets)
    
    if pipeline_by_stage:
        for stage, value in pipeline_by_stage.items():
            deals_pipeline_value.labels(stage=stage).set(value)
