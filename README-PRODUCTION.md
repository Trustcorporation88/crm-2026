# 🚀 Mr.Holmes CRM - Production-Ready SaaS

**Status**: Production Infrastructure Ready ✅

---

## 📦 What's Included

✅ **Multi-tier Architecture**
- Streamlit UI (Port 8512)
- FastAPI REST API (Port 8000)
- PostgreSQL Database
- Redis Cache Layer
- Docker Containerization

✅ **Enterprise Features**
- Role-Based Access Control (RBAC)
- JWT Authentication
- Audit Logging
- API Rate Limiting
- Webhook Support (WhatsApp, Email, Forms)
- Multi-channel Integration Ready

✅ **DevOps & CI/CD**
- Docker Compose for local development
- GitHub Actions pipeline
- Automated testing & security scanning
- Zero-downtime deployment
- Automated backups

✅ **Compliance & Security**
- LGPD/GDPR ready
- Encryption at rest
- Secrets management
- Security audit trails
- Data retention policies

---

## 🎯 Quick Start

### 1. Local Development

```bash
git clone https://github.com/your-org/crm-2026.git
cd crm-2026

# Setup environment
cp .env.example .env

# Start all services
docker-compose up -d

# Verify services are running
docker-compose ps

# Access:
# - Streamlit: http://localhost:8512
# - API: http://localhost:8000/docs
# - Swagger: http://localhost:8000/docs
```

### 2. Production Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed instructions:
- AWS EC2 + RDS setup
- Heroku deployment
- DigitalOcean App Platform
- SSL/HTTPS configuration
- Monitoring & backups

### 3. Environment Configuration

```bash
# Create production environment file
cp .env.example .env.production

# Edit with production values
nano .env.production

# Required for production:
JWT_SECRET_KEY=your-strong-secret-key-here
DATABASE_URL=postgresql://user:password@rds-endpoint:5432/crm_db
REDIS_URL=redis://:password@elasticache-endpoint:6379/0
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Load Balancer (SSL)              │
│                  (CloudFront/CloudFlare)            │
└──────────────┬──────────────────────────┬───────────┘
               │                          │
        ┌──────▼──────┐          ┌────────▼────────┐
        │  Streamlit  │          │   FastAPI REST  │
        │  App (UI)   │          │   API (Backend) │
        │ :8512       │          │   :8000         │
        └──────┬──────┘          └────────┬────────┘
               │                          │
               └──────────┬───────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
   ┌────▼────┐      ┌─────▼─────┐   ┌──────▼──────┐
   │PostgreSQL│      │   Redis   │   │ Monitoring  │
   │ Database │      │  (Cache)  │   │ (Prometheus)│
   └──────────┘      └───────────┘   └─────────────┘
        │
   ┌────▼────┐
   │S3 Backups
   │  (AWS)  │
   └─────────┘

Integrations:
├── WhatsApp (Twilio)
├── Email (SendGrid)
├── Slack
├── Google Calendar
└── Zapier
```

---

## 📊 API Endpoints

### Authentication
- `POST /auth/login` - User login
- `POST /auth/refresh` - Refresh token
- `POST /auth/logout` - Logout

### Customers
- `GET /api/customers` - List customers
- `POST /api/customers` - Create customer
- `GET /api/customers/{id}` - Get customer details
- `PUT /api/customers/{id}` - Update customer
- `DELETE /api/customers/{id}` - Delete customer

### Tickets
- `GET /api/tickets` - List tickets
- `POST /api/tickets` - Create ticket
- `GET /api/tickets/{id}` - Get ticket

### Deals
- `GET /api/deals` - List deals
- `POST /api/deals` - Create deal

### Webhooks
- `POST /webhooks/whatsapp` - WhatsApp messages
- `POST /webhooks/email` - Email messages
- `POST /webhooks/form` - Form submissions

### Reports
- `GET /api/reports/dashboard` - Dashboard metrics
- `GET /api/reports/export/{type}` - Export report

Full API documentation: `http://localhost:8000/docs`

---

## 🔐 Security Features

✅ JWT-based authentication
✅ Role-Based Access Control (Admin, Sales, Support, Marketing, CS)
✅ Encrypted passwords (SHA256)
✅ Audit logging for all actions
✅ Rate limiting on sensitive endpoints
✅ CORS configuration
✅ LGPD compliance (data retention, right to be forgotten)
✅ Encryption at rest (TLS/SSL)
✅ Secrets management via environment variables
✅ Regular security scanning in CI/CD

**Default Users**:
- admin / admin123
- atendimento / atend123
- vendas / vendas123
- marketing / mkt123
- cs / cs123

---

## 📈 Scaling

### Horizontal Scaling
```bash
# Scale API workers
docker-compose up -d --scale api=5

# Behind a load balancer (Nginx/HAProxy)
# Auto-scaling groups in AWS/Kubernetes
```

### Vertical Scaling
```yaml
# docker-compose.override.yml
services:
  postgres:
    # Use RDS instead for better scaling
  redis:
    # Use ElastiCache for cluster support
  api:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
```

---

## 🔄 CI/CD Pipeline

Every push triggers:
1. ✅ Security scanning (Trivy, Bandit)
2. ✅ Code quality checks (Black, Ruff, Pylint)
3. ✅ Unit tests (pytest)
4. ✅ Docker image build & push
5. ✅ Deploy to production (main branch only)
6. ✅ Smoke tests & health checks
7. ✅ Slack notifications

**GitHub Actions Dashboard**: `.github/workflows/`

---

## 📊 Monitoring & Observability

### Health Checks
```bash
# API health
curl http://localhost:8000/health

# Database
docker-compose exec postgres pg_isready

# Redis
docker-compose exec redis redis-cli ping
```

### Logs
```bash
# Streamlit logs
docker-compose logs -f crm-app

# API logs
docker-compose logs -f api

# Database logs
docker-compose logs -f postgres
```

### Metrics (Prometheus)
```bash
# Coming soon: Grafana dashboard at http://localhost:3000
```

---

## 🔄 Database Migrations

```bash
# Create migration
alembic revision --autogenerate -m "Add new field"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

---

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=. --cov-report=html

# Specific test
pytest tests/test_api.py::TestHealth -v

# Integration tests
pytest tests/integration/ -v
```

---

## 📚 Documentation

- [DEPLOYMENT.md](DEPLOYMENT.md) - Complete deployment guide
- [API Documentation](http://localhost:8000/docs) - Interactive API docs (Swagger)
- `.github/workflows/deploy.yml` - CI/CD pipeline definition

---

## 🔧 Troubleshooting

### Services won't start
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Database connection errors
```bash
docker-compose exec postgres psql -U crm_admin -c "\l"
docker-compose logs postgres
```

### Out of memory
```bash
docker stats
# Increase in docker-compose.yml
```

### API not responding
```bash
docker-compose logs api
curl -v http://localhost:8000/health
```

---

## 🚀 Next Steps

1. **Setup Production Server** - Follow DEPLOYMENT.md
2. **Configure Integrations** - WhatsApp (Twilio), Email (SendGrid)
3. **Enable Monitoring** - Setup Grafana/DataDog alerts
4. **Setup Backup Strategy** - RDS automated backups + S3
5. **Team Onboarding** - Create user accounts, assign roles

---

## 📞 Support & Issues

- **Documentation**: See DEPLOYMENT.md
- **API Docs**: http://localhost:8000/docs
- **Logs**: `docker-compose logs`
- **GitHub Issues**: Report bugs & feature requests

---

## 📄 License

Proprietary - All rights reserved

---

**Version**: 1.0.0
**Last Updated**: 2026-05-25
**Status**: ✅ Production Ready

🎉 **Mr.Holmes CRM is ready for deployment!**
