# Mr.Holmes CRM v2.0 - Integration Guide

## 📋 Overview

This guide explains how to integrate all v2.0 infrastructure files into your existing CRM setup.

## 🔧 Installation Steps

### 1. Install New Dependencies

```bash
# Install v2.0 dependencies
pip install -r requirements-v2.txt

# Or install individually
pip install slowapi prometheus-client python-json-logger aiohttp python-dotenv
```

### 2. Database Migrations

```bash
# Apply database indexes for performance
psql -U postgres -d mr_holmes < migrations/001_add_indexes.sql

# Verify indexes were created
psql -U postgres -d mr_holmes -c "SELECT indexname FROM pg_indexes WHERE tablename LIKE '%';"
```

### 3. Environment Configuration

Add to your `.env` file:

```env
# Rate limiting (optional, defaults to 5/minute for login)
RATE_LIMIT_LOGIN=5/minute
RATE_LIMIT_API=30/minute
RATE_LIMIT_WEBHOOKS=100/minute

# SSO Configuration (optional)
AZURE_AD_CLIENT_ID=your_client_id
AZURE_AD_CLIENT_SECRET=your_secret
AZURE_AD_TENANT_ID=your_tenant_id
AZURE_AD_REDIRECT_URI=http://localhost:8000/auth/callback/azure_ad

GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback/google

OKTA_CLIENT_ID=your_client_id
OKTA_CLIENT_SECRET=your_secret
OKTA_ORG_URL=https://yourorg.okta.com
OKTA_REDIRECT_URI=http://localhost:8000/auth/callback/okta

# Monitoring
PROMETHEUS_SCRAPE_INTERVAL=15s
GRAFANA_ADMIN_PASSWORD=admin
```

### 4. Docker Compose Updates

Add to your `docker-compose.yml`:

```yaml
# Add these services for monitoring
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    networks:
      - crm-network

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin
    volumes:
      - grafana_data:/var/lib/grafana
    networks:
      - crm-network

volumes:
  prometheus_data:
  grafana_data:
```

Then start with:
```bash
docker-compose up -d
```

### 5. Email Templates Setup

If using SendGrid:

```bash
pip install sendgrid

# Set environment variable
export SENDGRID_API_KEY=your_api_key
```

Create `email_service.py`:
```python
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import jinja2

def render_template(template_name: str, context: dict) -> str:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader('templates'))
    template = env.get_template(f"email_{template_name}.html")
    return template.render(**context)

def send_email(to: str, template_name: str, context: dict) -> bool:
    try:
        sg = SendGridAPIClient(os.getenv('SENDGRID_API_KEY'))
        html_content = render_template(template_name, context)
        
        message = Mail(
            from_email='noreply@mrholmes.com',
            to_emails=to,
            subject=context.get('subject', f'Message from Mr.Holmes'),
            html_content=html_content
        )
        
        response = sg.send(message)
        return response.status_code == 202
    
    except Exception as e:
        logger.error(f"Error sending email: {e}")
        return False
```

## 📊 Monitoring Setup

### 1. Access Prometheus

Navigate to: `http://localhost:9090`

Useful queries:
```promql
# Request rate
rate(http_requests_total[5m])

# Error rate
rate(http_requests_total{status=~"5.."}[5m])

# Response time (95th percentile)
histogram_quantile(0.95, http_request_duration_seconds)

# Cache hit rate
rate(cache_hits_total[5m]) / (rate(cache_hits_total[5m]) + rate(cache_misses_total[5m]))
```

### 2. Access Grafana

Navigate to: `http://localhost:3000`

Default credentials: `admin` / `admin`

Import dashboard JSON from `grafana/dashboards/` directory.

### 3. Configure Alerts

Edit `alert_rules.yml` to customize alert thresholds:

```yaml
- alert: HighErrorRate
  expr: (rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m])) > 0.05
  for: 5m
```

## 🔐 Security Features

### 1. Rate Limiting

Automatic rate limiting on all endpoints:
- Login: 5/minute
- API calls: 30/minute
- Webhooks: 100/minute

Customize in endpoint decorators:
```python
@app.post("/api/customers")
@limiter.limit("10/minute")
async def create_customer(...):
    ...
```

### 2. Structured Logging

All logs include correlation IDs for tracing:

```python
from structured_logging import get_logger, get_correlation_id

logger = get_logger("my_module")
logger.info("Action performed", user_id=123, correlation_id=get_correlation_id())
```

Logs output as JSON to `logs/crm_api.log`

### 3. Error Handling

Custom exceptions with specific HTTP status codes:

```python
from error_handlers import ValidationError, AuthenticationError, NotFoundError

# Usage
if not is_valid:
    raise ValidationError("Invalid input", status_code=422)
```

## 🚀 Testing

Run integration tests:

```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=crm_api --cov-report=html
```

### Test Example

```python
import pytest
from httpx import AsyncClient
from crm_api import app

@pytest.mark.asyncio
async def test_list_customers():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/customers?skip=0&limit=50")
        assert response.status_code == 200
        assert "pagination" in response.json()
```

## 📈 Performance Tuning

### 1. Cache Configuration

Adjust TTLs in `cache_utils.py`:

```python
class CacheStrategy:
    CUSTOMER_TTL = 3600      # 1 hour
    TICKET_TTL = 600        # 10 minutes
    DEAL_TTL = 1800         # 30 minutes
    CONFIG_TTL = 86400      # 1 day
```

### 2. Database Indexes

Check index performance:

```sql
-- View all indexes
SELECT indexname, tablename FROM pg_indexes WHERE schemaname = 'public';

-- Analyze query performance
EXPLAIN ANALYZE SELECT * FROM customers WHERE city = 'São Paulo';

-- Rebuild indexes if needed
REINDEX INDEX customers_city_idx;
```

### 3. Connection Pooling

Adjust in `crm_api.py`:

```python
engine = create_engine(
    DATABASE_URL,
    pool_size=20,      # Number of connections to maintain
    max_overflow=40,   # Max connections over pool_size
    pool_recycle=3600  # Recycle connections every hour
)
```

## 🔄 Workflow Automation

Initialize workflows in your startup:

```python
from workflow_engine import init_workflows, get_workflow_engine

# On app startup
@app.on_event("startup")
async def startup():
    init_workflows()
```

Trigger workflows:

```python
engine = get_workflow_engine()
results = await engine.execute(
    WorkflowTrigger.CUSTOMER_CREATED,
    {"customer_id": 123, "email": "user@example.com"}
)
```

## 🌍 Multi-Language Support

Initialize i18n on app startup:

```python
from i18n import init_i18n, t, set_language

@app.on_event("startup")
async def startup():
    init_i18n("translations")

# Use in endpoints
@app.get("/api/customers")
async def list_customers():
    return {"message": t("no_data")}  # Returns translated message
```

Set language per-request:

```python
@app.get("/api/customers")
async def list_customers(lang: str = "en"):
    set_language(lang)
    return {"message": t("customers")}
```

## 🆘 Troubleshooting

### Issue: Rate limit errors on health checks

**Solution**: Exclude health checks from rate limiting:

```python
app = FastAPI()
app.state.limiter = limiter
app.state.limiter_exempt_paths = ["/health", "/metrics"]
```

### Issue: Cache not working

**Solution**: Verify Redis connection:

```bash
redis-cli ping
# Should return: PONG
```

### Issue: Metrics endpoint returns 404

**Solution**: Ensure metrics endpoint is added:

```python
@app.get("/metrics")
async def get_metrics():
    from prometheus_client import generate_latest
    from prometheus_metrics import REGISTRY
    return generate_latest(REGISTRY)
```

### Issue: SSO authentication fails

**Solution**: Verify environment variables and callback URLs match your provider's configuration.

## 📚 Additional Resources

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [FastAPI Best Practices](https://fastapi.tiangolo.com/)
- [SQLAlchemy Performance](https://docs.sqlalchemy.org/en/20/faq/performance.html)

## 🤝 Support

For issues or questions:
1. Check the logs: `tail -f logs/crm_api.log`
2. Run health checks: `curl http://localhost:8000/health`
3. Review Prometheus metrics: `http://localhost:9090`
4. Check Grafana dashboards: `http://localhost:3000`
