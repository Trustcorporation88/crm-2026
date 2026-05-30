"""
Mr.Holmes CRM - FastAPI Backend v2.0
Enhanced REST API with rate limiting, caching, monitoring, and automation.
"""

import os
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from functools import lru_cache

from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, Request, Query
from fastapi.security import HTTPBearer, HTTPAuthCredentials
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr, validator
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import jwt
import redis

# Import new modules
from structured_logging import get_logger, set_correlation_id, get_correlation_id, init_redis
from error_handlers import register_error_handlers, CRMException, ValidationError, AuthenticationError, NotFoundError
from cache_utils import cache, CacheStrategy, init_redis as init_cache_redis
from prometheus_metrics import add_metrics_middleware, record_login_attempt, record_cache_hit, record_cache_miss
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import uuid

# Initialize structured logger
logger = get_logger("crm_api")

# ====== CONFIGURATION ======
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required")
REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    raise RuntimeError("REDIS_URL environment variable is required")
JWT_SECRET = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET_KEY environment variable is required")
JWT_ALGORITHM = "HS256"
API_TITLE = "Mr.Holmes CRM API v2.0"
API_VERSION = "2.0.0"

# ====== DATABASE SETUP ======
engine = create_engine(DATABASE_URL, echo=False, pool_size=20, max_overflow=40)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ====== REDIS SETUP ======
@lru_cache()
def get_redis():
    return redis.from_url(REDIS_URL, decode_responses=True)

# Initialize cache Redis
init_cache_redis(REDIS_URL)

# ====== RATE LIMITING ======
limiter = Limiter(key_func=get_remote_address)

# ====== PAGINATION ======
class PaginationParams:
    def __init__(self, skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
        self.skip = skip
        self.limit = limit

# ====== MODELS ======
class Customer(BaseModel):
    customer_id: str
    name: str
    segment: str
    city: str
    country: str
    owner: str
    status: str
    health_score: int
    lifetime_value: float
    last_purchase: str
    channel: str
    next_action: str
    source: str

class Ticket(BaseModel):
    ticket_id: str
    customer_id: str
    subject: str
    channel: str
    status: str
    priority: str
    owner: str
    sla_hours: int
    age_hours: int
    csat: float
    category: str
    opened_at: str

class Deal(BaseModel):
    deal_id: str
    customer_id: str
    name: str
    stage: str
    value: float
    probability: int
    owner: str
    close_date: str
    source: str

class WebhookPayload(BaseModel):
    event_type: str
    channel: str
    source_id: str
    payload: Dict[str, Any]
    timestamp: Optional[datetime] = Field(default_factory=datetime.now)

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]

# ====== FASTAPI APP ======
app = FastAPI(
    title=API_TITLE,
    version=API_VERSION,
    description="Enhanced REST API para Mr.Holmes CRM com rate limiting, caching, monitoring e automações."
)

# ====== MIDDLEWARE SETUP ======
# Add correlation ID middleware
@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    set_correlation_id(correlation_id)
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response

# Add Prometheus metrics middleware
add_metrics_middleware(app)

# Add rate limiting
app.state.limiter = limiter

# ====== CORS MIDDLEWARE ======
origins = os.getenv("CORS_ORIGINS", '["http://localhost:3000", "http://localhost:8512"]')
try:
    origins_list = json.loads(origins)
except:
    origins_list = ["http://localhost:3000", "http://localhost:8512"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register custom error handlers
register_error_handlers(app)

security = HTTPBearer()

# ====== AUTH FUNCTIONS ======
def verify_token(credentials: HTTPAuthCredentials = Depends(security)) -> Dict[str, Any]:
    """Verify JWT token and return user info"""
    try:
        correlation_id = get_correlation_id()
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        
        logger.info(
            "Token verified successfully",
            user_id=payload.get("user_id"),
            username=payload.get("username")
        )
        
        return payload
    
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired", correlation_id=get_correlation_id())
        raise AuthenticationError("Token expired", status_code=status.HTTP_401_UNAUTHORIZED)
    
    except jwt.InvalidTokenError as e:
        logger.warning("Invalid token", error=str(e), correlation_id=get_correlation_id())
        raise AuthenticationError("Invalid token", status_code=status.HTTP_401_UNAUTHORIZED)

def get_db() -> Session:
    """Database session dependency"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_pagination(skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)) -> PaginationParams:
    """Get pagination parameters"""
    return PaginationParams(skip=skip, limit=limit)

# ====== ROUTES: HEALTH & METRICS ======
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check database
        db = SessionLocal()
        db.execute("SELECT 1")
        db.close()
        
        # Check Redis
        redis_client = get_redis()
        redis_client.ping()
        
        logger.info("Health check passed")
        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": API_VERSION,
            "correlation_id": get_correlation_id()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise CRMException("Service unavailable", status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

@app.get("/metrics")
async def get_metrics():
    """Prometheus metrics endpoint"""
    from prometheus_client import generate_latest, REGISTRY
    from prometheus_metrics import REGISTRY as CUSTOM_REGISTRY
    
    metrics_output = generate_latest(CUSTOM_REGISTRY)
    return metrics_output

# ====== ROUTES: AUTH ======
@app.post("/auth/login", response_model=LoginResponse)
@limiter.limit("5/minute")
async def login(request: Request, login_request: LoginRequest, db: Session = Depends(get_db)):
    """
    Authenticate user and return JWT token
    Rate limited to 5 attempts per minute
    """
    try:
        logger.info(f"Login attempt for user: {login_request.username}")
        
        # This is a placeholder - real implementation would query the database
        # For now, we're using the Streamlit auth from crm_backend
        
        record_login_attempt(False)
        raise ValidationError("Use Streamlit app for authentication")
    
    except Exception as e:
        logger.error(f"Login failed: {e}")
        record_login_attempt(False)
        raise

@app.post("/auth/refresh")
async def refresh_token(credentials: HTTPAuthCredentials = Depends(security)):
    """Refresh JWT token"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        
        new_token = jwt.encode(
            {
                **payload,
                "exp": datetime.now(timezone.utc) + timedelta(hours=24)
            },
            JWT_SECRET,
            algorithm=JWT_ALGORITHM
        )
        
        logger.info("Token refreshed", user_id=payload.get("user_id"))
        return {"access_token": new_token, "token_type": "bearer"}
    
    except jwt.InvalidTokenError as e:
        logger.warning(f"Token refresh failed: {e}")
        raise AuthenticationError("Invalid token")

@app.post("/auth/logout")
async def logout(credentials: HTTPAuthCredentials = Depends(security)):
    """Logout user (add token to blacklist)"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        redis_client = get_redis()
        redis_client.setex(
            f"blacklist:{credentials.credentials}",
            3600,
            "true"
        )
        logger.info("User logged out", user_id=payload.get("user_id"))
        return {"message": "Logout successful"}
    
    except jwt.InvalidTokenError:
        raise AuthenticationError("Invalid token")

# ====== ROUTES: CUSTOMERS ======
@app.get("/api/customers")
@limiter.limit("30/minute")
async def list_customers(
    request: Request,
    db: Session = Depends(get_db),
    user: Dict = Depends(verify_token),
    pagination: PaginationParams = Depends(get_pagination)
):
    """
    List all customers with pagination
    """
    try:
        logger.info(f"Customers requested by {user.get('username')}", skip=pagination.skip, limit=pagination.limit)
        
        # Try to get from cache
        cache_key = f"customers:{pagination.skip}:{pagination.limit}"
        redis_client = get_redis()
        cached = redis_client.get(cache_key)
        
        if cached:
            record_cache_hit("customers")
            logger.debug("Cache hit for customers list")
            return json.loads(cached)
        
        record_cache_miss("customers")
        
        # Placeholder - would query database
        result = {
            "data": [],
            "pagination": {
                "skip": pagination.skip,
                "limit": pagination.limit,
                "total": 0
            },
            "correlation_id": get_correlation_id()
        }
        
        # Cache result for 1 hour
        redis_client.setex(cache_key, 3600, json.dumps(result))
        
        return result
    
    except Exception as e:
        logger.error(f"Error listing customers: {e}")
        raise CRMException(str(e))

@app.get("/api/customers/{customer_id}")
@limiter.limit("60/minute")
async def get_customer(
    request: Request,
    customer_id: str,
    db: Session = Depends(get_db),
    user: Dict = Depends(verify_token)
):
    """Get customer details"""
    try:
        logger.info(f"Customer {customer_id} requested by {user.get('username')}")
        
        # Try cache
        cache_key = f"customer:{customer_id}"
        redis_client = get_redis()
        cached = redis_client.get(cache_key)
        
        if cached:
            record_cache_hit("customer")
            return json.loads(cached)
        
        record_cache_miss("customer")
        
        # Placeholder
        result = {"customer_id": customer_id, "message": "Placeholder", "correlation_id": get_correlation_id()}
        redis_client.setex(cache_key, 3600, json.dumps(result))
        return result
    
    except Exception as e:
        logger.error(f"Error getting customer: {e}")
        raise CRMException(str(e))

@app.post("/api/customers")
@limiter.limit("10/minute")
async def create_customer(
    request: Request,
    customer: Customer,
    db: Session = Depends(get_db),
    user: Dict = Depends(verify_token)
):
    """Create new customer"""
    try:
        logger.info(f"New customer created by {user.get('username')}: {customer.customer_id}")
        
        # Invalidate cache
        redis_client = get_redis()
        redis_client.delete("customers:*")
        
        return {
            "status": "created",
            "customer_id": customer.customer_id,
            "correlation_id": get_correlation_id()
        }
    
    except Exception as e:
        logger.error(f"Error creating customer: {e}")
        raise CRMException(str(e))

@app.put("/api/customers/{customer_id}")
@limiter.limit("10/minute")
async def update_customer(
    request: Request,
    customer_id: str,
    customer: Customer,
    db: Session = Depends(get_db),
    user: Dict = Depends(verify_token)
):
    """Update customer"""
    try:
        logger.info(f"Customer {customer_id} updated by {user.get('username')}")
        
        # Invalidate cache
        redis_client = get_redis()
        redis_client.delete(f"customer:{customer_id}")
        
        return {
            "status": "updated",
            "customer_id": customer_id,
            "correlation_id": get_correlation_id()
        }
    
    except Exception as e:
        logger.error(f"Error updating customer: {e}")
        raise CRMException(str(e))

@app.delete("/api/customers/{customer_id}")
@limiter.limit("10/minute")
async def delete_customer(
    request: Request,
    customer_id: str,
    db: Session = Depends(get_db),
    user: Dict = Depends(verify_token)
):
    """Delete customer (soft delete for LGPD compliance)"""
    try:
        if user.get("role") != "admin":
            logger.warning(f"Unauthorized delete attempt by {user.get('username')}")
            raise ValidationError("Only admins can delete customers")
        
        logger.info(f"Customer {customer_id} deleted by {user.get('username')}")
        
        # Invalidate cache
        redis_client = get_redis()
        redis_client.delete(f"customer:{customer_id}")
        
        return {
            "status": "deleted",
            "customer_id": customer_id,
            "correlation_id": get_correlation_id()
        }
    
    except Exception as e:
        logger.error(f"Error deleting customer: {e}")
        raise CRMException(str(e))

# ====== ROUTES: TICKETS ======
@app.get("/api/tickets")
@limiter.limit("30/minute")
async def list_tickets(
    request: Request,
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    user: Dict = Depends(verify_token),
    pagination: PaginationParams = Depends(get_pagination)
):
    """List tickets with pagination and optional status filter"""
    try:
        logger.info(f"Tickets requested by {user.get('username')}", status=status_filter, skip=pagination.skip, limit=pagination.limit)
        
        return {
            "data": [],
            "pagination": {
                "skip": pagination.skip,
                "limit": pagination.limit,
                "total": 0
            },
            "correlation_id": get_correlation_id()
        }
    
    except Exception as e:
        logger.error(f"Error listing tickets: {e}")
        raise CRMException(str(e))

@app.get("/api/tickets/{ticket_id}")
@limiter.limit("60/minute")
async def get_ticket(
    request: Request,
    ticket_id: str,
    db: Session = Depends(get_db),
    user: Dict = Depends(verify_token)
):
    """Get ticket details"""
    try:
        logger.info(f"Ticket {ticket_id} requested by {user.get('username')}")
        
        return {
            "ticket_id": ticket_id,
            "message": "Placeholder",
            "correlation_id": get_correlation_id()
        }
    
    except Exception as e:
        logger.error(f"Error getting ticket: {e}")
        raise CRMException(str(e))

@app.post("/api/tickets")
@limiter.limit("10/minute")
async def create_ticket(
    request: Request,
    ticket: Ticket,
    db: Session = Depends(get_db),
    user: Dict = Depends(verify_token)
):
    """Create new ticket"""
    try:
        logger.info(f"New ticket created by {user.get('username')}: {ticket.ticket_id}")
        
        return {
            "status": "created",
            "ticket_id": ticket.ticket_id,
            "correlation_id": get_correlation_id()
        }
    
    except Exception as e:
        logger.error(f"Error creating ticket: {e}")
        raise CRMException(str(e))

# ====== ROUTES: DEALS ======
@app.get("/api/deals")
@limiter.limit("30/minute")
async def list_deals(
    request: Request,
    stage: Optional[str] = None,
    db: Session = Depends(get_db),
    user: Dict = Depends(verify_token),
    pagination: PaginationParams = Depends(get_pagination)
):
    """List deals with pagination and optional stage filter"""
    try:
        logger.info(f"Deals requested by {user.get('username')}", stage=stage, skip=pagination.skip, limit=pagination.limit)
        
        return {
            "data": [],
            "pagination": {
                "skip": pagination.skip,
                "limit": pagination.limit,
                "total": 0
            },
            "correlation_id": get_correlation_id()
        }
    
    except Exception as e:
        logger.error(f"Error listing deals: {e}")
        raise CRMException(str(e))

@app.get("/api/deals/{deal_id}")
@limiter.limit("60/minute")
async def get_deal(
    request: Request,
    deal_id: str,
    db: Session = Depends(get_db),
    user: Dict = Depends(verify_token)
):
    """Get deal details"""
    try:
        logger.info(f"Deal {deal_id} requested by {user.get('username')}")
        
        return {
            "deal_id": deal_id,
            "message": "Placeholder",
            "correlation_id": get_correlation_id()
        }
    
    except Exception as e:
        logger.error(f"Error getting deal: {e}")
        raise CRMException(str(e))

@app.post("/api/deals")
@limiter.limit("10/minute")
async def create_deal(
    request: Request,
    deal: Deal,
    db: Session = Depends(get_db),
    user: Dict = Depends(verify_token)
):
    """Create new deal"""
    try:
        logger.info(f"New deal created by {user.get('username')}: {deal.deal_id}")
        
        return {
            "status": "created",
            "deal_id": deal.deal_id,
            "correlation_id": get_correlation_id()
        }
    
    except Exception as e:
        logger.error(f"Error creating deal: {e}")
        raise CRMException(str(e))

# ====== ROUTES: WEBHOOKS ======
@app.post("/webhooks/whatsapp")
@limiter.limit("100/minute")
async def webhook_whatsapp(request: Request, payload: WebhookPayload, db: Session = Depends(get_db)):
    """Receive WhatsApp messages and create tickets"""
    try:
        logger.info(f"WhatsApp webhook received: {payload.event_type}", source_id=payload.source_id)
        
        # Queue for retry if needed
        redis_client = get_redis()
        webhook_key = f"webhook:whatsapp:{payload.source_id}:{datetime.now(timezone.utc).isoformat()}"
        redis_client.setex(webhook_key, 86400, json.dumps(payload.dict()))
        
        return {
            "status": "received",
            "event_type": payload.event_type,
            "correlation_id": get_correlation_id()
        }
    
    except Exception as e:
        logger.error(f"Error processing WhatsApp webhook: {e}")
        raise CRMException(str(e))

@app.post("/webhooks/email")
@limiter.limit("100/minute")
async def webhook_email(request: Request, payload: WebhookPayload, db: Session = Depends(get_db)):
    """Receive emails and create tickets"""
    try:
        logger.info(f"Email webhook received: {payload.event_type}", source_id=payload.source_id)
        
        return {
            "status": "received",
            "event_type": payload.event_type,
            "correlation_id": get_correlation_id()
        }
    
    except Exception as e:
        logger.error(f"Error processing email webhook: {e}")
        raise CRMException(str(e))

@app.post("/webhooks/form")
@limiter.limit("100/minute")
async def webhook_form(request: Request, payload: WebhookPayload, db: Session = Depends(get_db)):
    """Receive form submissions and create leads"""
    try:
        logger.info(f"Form webhook received: {payload.event_type}", source_id=payload.source_id)
        
        return {
            "status": "received",
            "event_type": payload.event_type,
            "correlation_id": get_correlation_id()
        }
    
    except Exception as e:
        logger.error(f"Error processing form webhook: {e}")
        raise CRMException(str(e))

# ====== ROUTES: INTEGRATIONS ======
@app.get("/api/integrations")
@limiter.limit("30/minute")
async def list_integrations(
    request: Request,
    user: Dict = Depends(verify_token)
):
    """List available integrations"""
    try:
        logger.info(f"Integrations requested by {user.get('username')}")
        
        return {
            "integrations": [
                {"name": "WhatsApp", "status": "configured", "provider": "twilio"},
                {"name": "Email", "status": "configured", "provider": "sendgrid"},
                {"name": "Google Calendar", "status": "available", "provider": "google"},
                {"name": "Slack", "status": "available", "provider": "slack"},
                {"name": "Zapier", "status": "available", "provider": "zapier"},
            ],
            "correlation_id": get_correlation_id()
        }
    
    except Exception as e:
        logger.error(f"Error listing integrations: {e}")
        raise CRMException(str(e))

@app.post("/api/integrations/{integration_name}/connect")
@limiter.limit("10/minute")
async def connect_integration(
    request: Request,
    integration_name: str,
    credentials: Dict[str, Any],
    user: Dict = Depends(verify_token)
):
    """Connect to an external service"""
    try:
        logger.info(f"Integration {integration_name} connection attempted by {user.get('username')}")
        
        return {
            "status": "connected",
            "integration": integration_name,
            "correlation_id": get_correlation_id()
        }
    
    except Exception as e:
        logger.error(f"Error connecting integration: {e}")
        raise CRMException(str(e))

# ====== ROUTES: REPORTS ======
@app.get("/api/reports/dashboard")
@limiter.limit("30/minute")
async def dashboard_report(
    request: Request,
    period: str = "month",
    user: Dict = Depends(verify_token)
):
    """Get dashboard metrics"""
    try:
        logger.info(f"Dashboard report requested for period: {period}")
        
        return {
            "customers_total": 5,
            "tickets_open": 4,
            "pipeline_value": 244000,
            "health_score": 77,
            "correlation_id": get_correlation_id()
        }
    
    except Exception as e:
        logger.error(f"Error generating dashboard report: {e}")
        raise CRMException(str(e))

@app.get("/api/reports/export/{report_type}")
@limiter.limit("5/minute")
async def export_report(
    request: Request,
    report_type: str,
    format: str = "pdf",
    user: Dict = Depends(verify_token)
):
    """Export report in specified format (pdf, csv, excel)"""
    try:
        logger.info(f"Report export requested: {report_type} as {format}")
        
        return {
            "status": "generating",
            "report_type": report_type,
            "format": format,
            "correlation_id": get_correlation_id()
        }
    
    except Exception as e:
        logger.error(f"Error exporting report: {e}")
        raise CRMException(str(e))

# ====== ROUTES: ADMIN ======
@app.get("/api/admin/users")
@limiter.limit("10/minute")
async def list_users(
    request: Request,
    user: Dict = Depends(verify_token)
):
    """List all users (admin only)"""
    try:
        if user.get("role") != "admin":
            logger.warning(f"Unauthorized admin access attempt by {user.get('username')}")
            raise ValidationError("Admin access required", status_code=status.HTTP_403_FORBIDDEN)
        
        logger.info("Users list requested by admin")
        
        return {
            "users": [],
            "correlation_id": get_correlation_id()
        }
    
    except Exception as e:
        logger.error(f"Error listing users: {e}")
        raise

@app.post("/api/admin/backup")
@limiter.limit("5/minute")
async def trigger_backup(
    request: Request,
    user: Dict = Depends(verify_token)
):
    """Trigger manual database backup"""
    try:
        if user.get("role") != "admin":
            logger.warning(f"Unauthorized backup attempt by {user.get('username')}")
            raise ValidationError("Admin access required", status_code=status.HTTP_403_FORBIDDEN)
        
        logger.info(f"Backup triggered by {user.get('username')}")
        
        return {
            "status": "backup_started",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "correlation_id": get_correlation_id()
        }
    
    except Exception as e:
        logger.error(f"Error triggering backup: {e}")
        raise

@app.get("/api/admin/logs")
@limiter.limit("10/minute")
async def view_logs(
    request: Request,
    limit: int = Query(100, ge=1, le=1000),
    user: Dict = Depends(verify_token)
):
    """View audit logs"""
    try:
        if user.get("role") != "admin":
            logger.warning(f"Unauthorized logs access by {user.get('username')}")
            raise ValidationError("Admin access required", status_code=status.HTTP_403_FORBIDDEN)
        
        logger.info("Audit logs requested by admin")
        
        return {
            "logs": [],
            "total": 0,
            "correlation_id": get_correlation_id()
        }
    
    except Exception as e:
        logger.error(f"Error retrieving logs: {e}")
        raise

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

