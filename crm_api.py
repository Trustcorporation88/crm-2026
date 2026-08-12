"""
Mr.Holmes CRM - FastAPI Backend v2.0
Enhanced REST API with rate limiting, caching, monitoring, and automation.
"""

import os
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Iterator, Optional, Dict, Any
from functools import lru_cache

from fastapi import FastAPI, Depends, status, Request, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
import jwt
import redis

# Import new modules
from structured_logging import get_logger, set_correlation_id, get_correlation_id
from error_handlers import (
    register_error_handlers,
    CRMException,
    AuthenticationError,
    AuthorizationError,
    InternalServerError,
    NotFoundError,
    NotImplementedEndpoint,
    ValidationError,
)
from cache_utils import clear_cache_pattern, init_redis as init_cache_redis
from prometheus_metrics import add_metrics_middleware, record_login_attempt, record_cache_hit, record_cache_miss
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

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
    # Naive local timestamps make webhook ordering unreliable across hosts.
    timestamp: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

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

# Add rate limiting (the handler is required, otherwise a throttled request
# surfaces as an unhandled 500 instead of a 429).
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ====== CORS MIDDLEWARE ======
DEFAULT_ORIGINS = ["http://localhost:3000", "http://localhost:8512"]
origins = os.getenv("CORS_ORIGINS", json.dumps(DEFAULT_ORIGINS))
try:
    origins_list = json.loads(origins)
    if not isinstance(origins_list, list):
        raise ValueError("CORS_ORIGINS must be a JSON list")
except (json.JSONDecodeError, ValueError):
    # Fall back to a comma-separated list before giving up on the value.
    origins_list = [item.strip() for item in origins.split(",") if item.strip()] or DEFAULT_ORIGINS

# Credentials cannot be combined with a wildcard origin: browsers reject the
# response and the CRM session cookie silently stops working.
allow_credentials = "*" not in origins_list
if not allow_credentials:
    logger.warning("CORS_ORIGINS contains '*'; disabling allow_credentials")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins_list,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register custom error handlers
register_error_handlers(app)

security = HTTPBearer()

# ====== AUTH FUNCTIONS ======
def _is_blacklisted(token: str) -> bool:
    """Return True when a token was explicitly revoked via /auth/logout."""
    try:
        return bool(get_redis().get(f"blacklist:{token}"))
    except redis.RedisError as exc:
        # Fail closed: if the revocation list is unreachable we cannot prove the
        # token is still valid.
        logger.error("Blacklist lookup failed", error=str(exc))
        raise AuthenticationError("Unable to validate session")


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """Verify JWT token and return user info"""
    token = credentials.credentials

    if _is_blacklisted(token):
        logger.warning("Revoked token presented")
        raise AuthenticationError("Token has been revoked")

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])

        logger.info(
            "Token verified successfully",
            user_id=payload.get("user_id"),
            username=payload.get("username")
        )

        return payload

    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        raise AuthenticationError("Token expired")

    except jwt.InvalidTokenError as e:
        logger.warning("Invalid token", error=str(e))
        raise AuthenticationError("Invalid token")

def get_db() -> Iterator[Session]:
    """Database session dependency"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_pagination(skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)) -> PaginationParams:
    """Get pagination parameters"""
    return PaginationParams(skip=skip, limit=limit)

# ====== DATA ACCESS ======
# Os endpoints consultam o crm_backend — a mesma camada que serve o app
# Streamlit, com o mesmo banco (SQLite ou Postgres). Antes, todos devolviam
# listas vazias: a API parecia existir, mas não era integrável.

def _records(df, skip: int = 0, limit: int = 50) -> tuple[list, int]:
    """Fatia um DataFrame em registros JSON-áveis + total."""
    total = int(len(df))
    page = df.iloc[skip: skip + limit].to_dict("records") if total else []
    return page, total


def _crm_data():
    import crm_backend

    crm_backend.init_database()
    return crm_backend.get_data()


# ====== ROUTES: HEALTH & METRICS ======
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    components: Dict[str, str] = {}

    # Check database. SQLAlchemy 2.0 requires an executable construct, a raw
    # string raises ObjectNotExecutableError.
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            components["database"] = "up"
        finally:
            db.close()
    except Exception as e:
        logger.error("Health check: database unreachable", error=str(e))
        components["database"] = "down"

    # Check Redis
    try:
        get_redis().ping()
        components["redis"] = "up"
    except Exception as e:
        logger.error("Health check: redis unreachable", error=str(e))
        components["redis"] = "down"

    healthy = all(state == "up" for state in components.values())

    if not healthy:
        raise CRMException(
            code="SERVICE_UNAVAILABLE",
            message="Service unavailable",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details={"components": components},
        )

    logger.info("Health check passed")
    return {
        "status": "healthy",
        "components": components,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": API_VERSION,
        "correlation_id": get_correlation_id()
    }

@app.get("/metrics")
async def get_metrics():
    """Prometheus metrics endpoint"""
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    from prometheus_metrics import REGISTRY as CUSTOM_REGISTRY

    # Must be served as text/plain in the Prometheus exposition format,
    # otherwise the scraper rejects the payload.
    return PlainTextResponse(
        content=generate_latest(CUSTOM_REGISTRY),
        media_type=CONTENT_TYPE_LATEST,
    )

# ====== ROUTES: AUTH ======
@app.post("/auth/login", response_model=LoginResponse)
@limiter.limit("5/minute")
async def login(request: Request, login_request: LoginRequest, db: Session = Depends(get_db)):
    """
    Authenticate user and return JWT token
    Rate limited to 5 attempts per minute
    """
    logger.info("Login attempt", username=login_request.username)

    # Authentication is owned by crm_backend (used by the Streamlit app and by
    # crm_whatsapp_webhook /auth/token). This endpoint is intentionally not a
    # second implementation of it.
    record_login_attempt(False)
    raise AuthenticationError("Authenticate via the CRM auth service (/auth/token)")

@app.post("/auth/refresh")
async def refresh_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Refresh JWT token"""
    token = credentials.credentials

    # A revoked token must not be exchangeable for a fresh one.
    if _is_blacklisted(token):
        logger.warning("Refresh attempted with revoked token")
        raise AuthenticationError("Token has been revoked")

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])

        # Rebuild the claims instead of copying: reusing the old payload would
        # carry over iat/jti and let a token be refreshed indefinitely.
        claims = {k: v for k, v in payload.items() if k not in {"exp", "iat"}}
        now = datetime.now(timezone.utc)
        new_token = jwt.encode(
            {**claims, "iat": now, "exp": now + timedelta(hours=24)},
            JWT_SECRET,
            algorithm=JWT_ALGORITHM
        )

        logger.info("Token refreshed", user_id=payload.get("user_id"))
        return {"access_token": new_token, "token_type": "bearer"}

    except jwt.InvalidTokenError as e:
        logger.warning("Token refresh failed", error=str(e))
        raise AuthenticationError("Invalid token")

@app.post("/auth/logout")
async def logout(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Logout user (add token to blacklist)"""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        # Already unusable; nothing to revoke.
        return {"message": "Logout successful"}
    except jwt.InvalidTokenError:
        raise AuthenticationError("Invalid token")

    # Keep the entry until the token would have expired anyway, otherwise a
    # long-lived token becomes usable again after the old hardcoded hour.
    exp = payload.get("exp")
    ttl = 3600
    if isinstance(exp, (int, float)):
        ttl = max(1, int(exp - datetime.now(timezone.utc).timestamp()))

    try:
        get_redis().setex(f"blacklist:{token}", ttl, "true")
    except redis.RedisError as exc:
        logger.error("Could not blacklist token", error=str(exc))
        raise CRMException(
            code="SERVICE_UNAVAILABLE",
            message="Logout could not be completed",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    logger.info("User logged out", user_id=payload.get("user_id"))
    return {"message": "Logout successful"}

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

        customers = _crm_data()["customers"]
        page, total = _records(customers, pagination.skip, pagination.limit)
        result = {
            "data": page,
            "pagination": {
                "skip": pagination.skip,
                "limit": pagination.limit,
                "total": total
            },
            "correlation_id": get_correlation_id()
        }
        
        # Cache result for 1 hour
        redis_client.setex(cache_key, 3600, json.dumps(result))
        
        return result
    
    except CRMException:
        # Domain errors already carry the right status code.
        raise
    except Exception as e:
        logger.error("Error listing customers", error=str(e))
        raise InternalServerError()

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

        customers = _crm_data()["customers"]
        match = customers[customers["customer_id"] == customer_id]
        if match.empty:
            raise NotFoundError("Cliente", customer_id)

        result = {**match.iloc[0].to_dict(), "correlation_id": get_correlation_id()}
        redis_client.setex(cache_key, 3600, json.dumps(result))
        return result
    
    except CRMException:
        # Domain errors already carry the right status code.
        raise
    except Exception as e:
        logger.error("Error getting customer", error=str(e))
        raise InternalServerError()

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
        import crm_backend

        # Garante o schema antes de escrever — mesmo contrato dos GETs, que
        # passam por _crm_data(). Sem isto, a primeira escrita num banco novo
        # (ou num schema de teste isolado) falha com "relation does not exist".
        crm_backend.init_database()
        created_id = crm_backend.add_customer(
            customer.model_dump(),
            actor={"username": user.get("username", "api"), "role": user.get("role", "admin")},
            source="api",
        )
        logger.info(f"New customer created by {user.get('username')}: {created_id}")

        # Invalidate cache
        clear_cache_pattern("customers:*")

        return {
            "status": "created",
            "customer_id": created_id,
            "correlation_id": get_correlation_id()
        }
    
    except CRMException:
        # Domain errors already carry the right status code.
        raise
    except Exception as e:
        logger.error("Error creating customer", error=str(e))
        raise InternalServerError()

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
        import crm_backend

        # Antes, este handler apenas invalidava o cache e devolvia
        # {"status": "updated"} com HTTP 200 — sem tocar no banco. Quem
        # integrasse com a API acreditava ter gravado, e nada era gravado.
        crm_backend.init_database()
        try:
            updated = crm_backend.update_entity(
                "customer",
                customer_id,
                customer.model_dump(exclude_unset=True),
                actor={"username": user.get("username", "api"), "role": user.get("role", "admin")},
                source="api",
            )
        except ValueError as exc:
            # update_entity sinaliza "não existe" e "payload sem campo válido"
            # pela mesma via. Traduzimos para o status correto em vez de
            # deixar virar 500 no except genérico lá embaixo.
            if "not found" in str(exc):
                raise NotFoundError("Customer", customer_id) from exc
            raise ValidationError(str(exc)) from exc

        logger.info(f"Customer {customer_id} updated by {user.get('username')}")

        # Invalidate cache
        redis_client = get_redis()
        redis_client.delete(f"customer:{customer_id}")
        clear_cache_pattern("customers:*")

        return {
            "status": "updated",
            "customer_id": customer_id,
            "customer": updated,
            "correlation_id": get_correlation_id()
        }

    except CRMException:
        # Domain errors already carry the right status code.
        raise
    except Exception as e:
        logger.error("Error updating customer", error=str(e))
        raise InternalServerError()

@app.delete("/api/customers/{customer_id}")
@limiter.limit("10/minute")
async def delete_customer(
    request: Request,
    customer_id: str,
    db: Session = Depends(get_db),
    user: Dict = Depends(verify_token)
):
    """Remove o cliente.

    Atenção: é remoção definitiva (DELETE), não soft delete. A docstring
    anterior prometia soft delete e o handler não apagava nada; agora o
    comportamento e a descrição batem. O registro completo da linha vai para
    audit_log antes da remoção, que é o que atende à exigência de rastro.
    """
    try:
        if user.get("role") != "admin":
            logger.warning(f"Unauthorized delete attempt by {user.get('username')}")
            raise AuthorizationError("Only admins can delete customers")

        import crm_backend

        # Mesmo defeito do PUT: antes devolvia {"status": "deleted"} sem
        # remover coisa alguma. delete_entity já faz a checagem de permissão
        # e grava o registro completo em audit_log.
        crm_backend.init_database()
        try:
            crm_backend.delete_entity(
                "customer",
                customer_id,
                actor={"username": user.get("username", "api"), "role": user.get("role", "admin")},
                source="api",
            )
        except ValueError as exc:
            if "not found" in str(exc):
                raise NotFoundError("Customer", customer_id) from exc
            raise ValidationError(str(exc)) from exc

        logger.info(f"Customer {customer_id} deleted by {user.get('username')}")

        # Invalidate cache
        redis_client = get_redis()
        redis_client.delete(f"customer:{customer_id}")
        clear_cache_pattern("customers:*")

        return {
            "status": "deleted",
            "customer_id": customer_id,
            "correlation_id": get_correlation_id()
        }

    except CRMException:
        # Domain errors already carry the right status code.
        raise
    except Exception as e:
        logger.error("Error deleting customer", error=str(e))
        raise InternalServerError()

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

        tickets = _crm_data()["tickets"]
        if status_filter:
            tickets = tickets[tickets["status"] == status_filter]
        page, total = _records(tickets, pagination.skip, pagination.limit)
        return {
            "data": page,
            "pagination": {
                "skip": pagination.skip,
                "limit": pagination.limit,
                "total": total
            },
            "correlation_id": get_correlation_id()
        }
    
    except CRMException:
        # Domain errors already carry the right status code.
        raise
    except Exception as e:
        logger.error("Error listing tickets", error=str(e))
        raise InternalServerError()

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

        tickets = _crm_data()["tickets"]
        match = tickets[tickets["ticket_id"] == ticket_id]
        if match.empty:
            raise NotFoundError("Chamado", ticket_id)

        return {**match.iloc[0].to_dict(), "correlation_id": get_correlation_id()}
    
    except CRMException:
        # Domain errors already carry the right status code.
        raise
    except Exception as e:
        logger.error("Error getting ticket", error=str(e))
        raise InternalServerError()

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
        import crm_backend

        # Garante o schema antes de escrever — mesmo contrato dos GETs, que
        # passam por _crm_data(). Sem isto, a primeira escrita num banco novo
        # (ou num schema de teste isolado) falha com "relation does not exist".
        crm_backend.init_database()
        created_id = crm_backend.add_ticket(
            ticket.model_dump(),
            actor={"username": user.get("username", "api"), "role": user.get("role", "admin")},
            source="api",
        )
        logger.info(f"New ticket created by {user.get('username')}: {created_id}")

        return {
            "status": "created",
            "ticket_id": created_id,
            "correlation_id": get_correlation_id()
        }
    
    except CRMException:
        # Domain errors already carry the right status code.
        raise
    except Exception as e:
        logger.error("Error creating ticket", error=str(e))
        raise InternalServerError()

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

        deals = _crm_data()["deals"]
        if stage:
            deals = deals[deals["stage"] == stage]
        page, total = _records(deals, pagination.skip, pagination.limit)
        return {
            "data": page,
            "pagination": {
                "skip": pagination.skip,
                "limit": pagination.limit,
                "total": total
            },
            "correlation_id": get_correlation_id()
        }
    
    except CRMException:
        # Domain errors already carry the right status code.
        raise
    except Exception as e:
        logger.error("Error listing deals", error=str(e))
        raise InternalServerError()

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

        deals = _crm_data()["deals"]
        match = deals[deals["deal_id"] == deal_id]
        if match.empty:
            raise NotFoundError("Negociação", deal_id)

        return {**match.iloc[0].to_dict(), "correlation_id": get_correlation_id()}
    
    except CRMException:
        # Domain errors already carry the right status code.
        raise
    except Exception as e:
        logger.error("Error getting deal", error=str(e))
        raise InternalServerError()

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
        import crm_backend

        # Garante o schema antes de escrever — mesmo contrato dos GETs, que
        # passam por _crm_data(). Sem isto, a primeira escrita num banco novo
        # (ou num schema de teste isolado) falha com "relation does not exist".
        crm_backend.init_database()
        created_id = crm_backend.add_deal(
            deal.model_dump(),
            actor={"username": user.get("username", "api"), "role": user.get("role", "admin")},
            source="api",
        )
        logger.info(f"New deal created by {user.get('username')}: {created_id}")

        return {
            "status": "created",
            "deal_id": created_id,
            "correlation_id": get_correlation_id()
        }
    
    except CRMException:
        # Domain errors already carry the right status code.
        raise
    except Exception as e:
        logger.error("Error creating deal", error=str(e))
        raise InternalServerError()

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
        redis_client.setex(webhook_key, 86400, payload.model_dump_json())
        
        return {
            "status": "received",
            "event_type": payload.event_type,
            "correlation_id": get_correlation_id()
        }
    
    except CRMException:
        # Domain errors already carry the right status code.
        raise
    except Exception as e:
        logger.error("Error processing WhatsApp webhook", error=str(e))
        raise InternalServerError()

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
    
    except CRMException:
        # Domain errors already carry the right status code.
        raise
    except Exception as e:
        logger.error("Error processing email webhook", error=str(e))
        raise InternalServerError()

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
    
    except CRMException:
        # Domain errors already carry the right status code.
        raise
    except Exception as e:
        logger.error("Error processing form webhook", error=str(e))
        raise InternalServerError()

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
    
    except CRMException:
        # Domain errors already carry the right status code.
        raise
    except Exception as e:
        logger.error("Error listing integrations", error=str(e))
        raise InternalServerError()

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

        # Este handler nunca conectou nada: recebia as credenciais e devolvia
        # {"status": "connected"}. Responder 501 é mais honesto do que
        # confirmar uma integração inexistente — e evita que alguém envie
        # credencial real para um endpoint que só a descarta.
        raise NotImplementedEndpoint("connect_integration")
    
    except CRMException:
        # Domain errors already carry the right status code.
        raise
    except Exception as e:
        logger.error("Error connecting integration", error=str(e))
        raise InternalServerError()

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

        data = _crm_data()
        customers, tickets, deals = data["customers"], data["tickets"], data["deals"]
        open_tickets = tickets[tickets["status"] != "Resolvido"] if not tickets.empty else tickets
        open_deals = deals[deals["stage"] != "Fechado ganho"] if not deals.empty else deals

        return {
            "customers_total": int(len(customers)),
            "tickets_open": int(len(open_tickets)),
            "pipeline_value": float(open_deals["value"].sum()) if not open_deals.empty else 0.0,
            "health_score": int(customers["health_score"].mean()) if not customers.empty else 0,
            "correlation_id": get_correlation_id()
        }
    
    except CRMException:
        # Domain errors already carry the right status code.
        raise
    except Exception as e:
        logger.error("Error generating dashboard report", error=str(e))
        raise InternalServerError()

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

        # Nunca gerou arquivo algum; devolvia "generating" e encerrava.
        raise NotImplementedEndpoint("export_report")
    
    except CRMException:
        # Domain errors already carry the right status code.
        raise
    except Exception as e:
        logger.error("Error exporting report", error=str(e))
        raise InternalServerError()

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
            raise AuthorizationError("Admin access required")
        
        logger.info("Users list requested by admin")

        users = _crm_data()["users"]
        # get_data() já projeta apenas username/full_name/role/is_active —
        # nunca o hash de senha.
        return {
            "users": users.to_dict("records"),
            "correlation_id": get_correlation_id()
        }
    
    except CRMException:
        raise
    except Exception as e:
        logger.error("Error listing users", error=str(e))
        raise InternalServerError()

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
            raise AuthorizationError("Admin access required")
        
        logger.info(f"Backup triggered by {user.get('username')}")

        # Não existe rotina de backup no projeto: o handler apenas respondia
        # "backup_started". Um backup que o operador acredita ter feito e que
        # nunca aconteceu é pior do que não ter o botão.
        raise NotImplementedEndpoint("trigger_backup")
    
    except CRMException:
        raise
    except Exception as e:
        logger.error("Error triggering backup", error=str(e))
        raise InternalServerError()

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
            raise AuthorizationError("Admin access required")
        
        logger.info("Audit logs requested by admin")

        # Antes devolvia {"logs": [], "total": 0} fixo, ignorando o parâmetro
        # limit — o que fazia a tela de auditoria parecer vazia mesmo com o
        # banco cheio. A tabela audit_log já é populada por log_audit_event.
        audit = _crm_data().get("audit_log")
        if audit is None or audit.empty:
            return {"logs": [], "total": 0, "correlation_id": get_correlation_id()}

        total = int(len(audit))
        page = audit.head(limit).to_dict(orient="records")
        return {
            "logs": page,
            "total": total,
            "returned": len(page),
            "correlation_id": get_correlation_id()
        }

    except CRMException:
        raise
    except Exception as e:
        logger.error("Error retrieving logs", error=str(e))
        raise InternalServerError()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

