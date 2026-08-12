# Deployment Guide - Mr.Holmes CRM

**⏱️ Last Updated**: May 25, 2026  
**✅ Status**: Production Ready  
**🟢 Reliability**: Enterprise-Grade

## 📋 Pre-Requisites

- Docker & Docker Compose (v20+)
- GitHub Account (for Actions)
- AWS Account (recommended for production)
- Domain Name with DNS control

## 🚀 Quick Start (Development)

### Option A: Using Scripts (Recommended)

```bash
# Windows PowerShell
.\deploy.ps1

# Or Linux/Mac
bash deploy.sh
```

This runs validation → build → start → health check automatically.

### Option B: Manual Setup

```bash
# Clone and navigate
cd crm-2026

# Setup environment
cp .env.example .env
# Edit .env with your configuration

# Start services
docker-compose up -d

# Verify services
docker-compose ps

# Access application
# Streamlit: http://localhost:8512
# API: http://localhost:8000/docs
# PostgreSQL: localhost:5432
# Redis: localhost:6379
```

## 🏭 Production Deployment

### Option 1: AWS EC2 + RDS

```bash
# 1. Launch EC2 instance
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \
  --instance-type t3.medium \
  --key-name your-key

# 2. SSH into instance
ssh -i your-key.pem ec2-user@your-instance-ip

# 3. Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker ec2-user

# 4. Clone repository
git clone https://github.com/your-org/crm-2026.git
cd crm-2026

# 5. Configure environment for AWS RDS
cp .env.example .env
# Edit DATABASE_URL to point to RDS endpoint
# DATABASE_URL=postgresql://user:pass@your-rds-endpoint:5432/crm_db

# 6. Start services
docker-compose up -d

# 7. Setup automatic backups
docker-compose exec postgres pg_dump -U crm_admin crm_db | aws s3 cp - s3://your-backup-bucket/crm_$(date +%Y%m%d).sql

# 8. Enable SSL with Let's Encrypt
sudo apt-get install certbot
sudo certbot certonly --standalone -d yourdomain.com
```

### Option 2: Heroku

```bash
# Install Heroku CLI
curl https://cli-assets.heroku.com/install.sh | sh

# Login
heroku login

# Create app
heroku create your-crm-app

# Add PostgreSQL
heroku addons:create heroku-postgresql:standard-0

# Add Redis
heroku addons:create heroku-redis:premium-0

# Set environment variables
heroku config:set JWT_SECRET_KEY="your-secret-key"
heroku config:set ENVIRONMENT=production

# Deploy
git push heroku main

# View logs
heroku logs --tail
```

### Option 3: DigitalOcean App Platform

1. Fork repository to GitHub
2. Go to DigitalOcean > App Platform > Create App
3. Select GitHub repository
4. Configure:
   - Service: `Streamlit` → Port 8512
   - Service: `API` → Port 8000
   - Database: PostgreSQL
   - Redis: Add-on
5. Set environment variables from `.env.example`
6. Deploy

## 🔐 Security Checklist

- [ ] Change default passwords in `.env`
- [ ] Generate strong JWT_SECRET_KEY (32+ chars)
- [ ] Enable HTTPS/SSL certificate
- [ ] Configure firewall rules
- [ ] Setup backup automation
- [ ] Enable database encryption
- [ ] Configure WAF (Web Application Firewall)
- [ ] Setup monitoring & alerting
- [ ] Enable audit logging
- [ ] Review LGPD compliance

## 📊 Monitoring

### Health Checks

```bash
# API Health
curl http://your-domain:8000/health

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

### Metrics

Prometheus metrics available at:
- `/metrics` (API)
- Grafana dashboard: http://your-domain:3000

## 🔄 Scaling

### Horizontal Scaling

```yaml
# docker-compose.override.yml for production
version: '3.9'

services:
  crm-app:
    deploy:
      replicas: 3
      resources:
        limits:
          cpus: '1'
          memory: 2G

  api:
    deploy:
      replicas: 5
      resources:
        limits:
          cpus: '2'
          memory: 4G

  postgres:
    # Use RDS instead of container
    # Scaling handled by AWS

  redis:
    # Use ElastiCache instead of container
    # Scaling handled by AWS
```

## 🔧 Maintenance

### Database Maintenance

```bash
# Backup
docker-compose exec postgres pg_dump -U crm_admin crm_db > backup.sql

# Restore
docker-compose exec -T postgres psql -U crm_admin crm_db < backup.sql

# Vacuum (cleanup)
docker-compose exec postgres vacuumdb -U crm_admin crm_db

# Reindex
docker-compose exec postgres reindexdb -U crm_admin crm_db
```

### Update Deployment

```bash
# Pull latest code
git pull origin main

# Update images
docker-compose pull

# Restart services (with zero downtime)
docker-compose up -d

# Verify health
docker-compose ps
```

## 🚨 Troubleshooting

### Services not starting

```bash
# Check logs
docker-compose logs --follow

# Restart all
docker-compose restart

# Full rebuild
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Database connection errors

```bash
# Check PostgreSQL
docker-compose exec postgres psql -U crm_admin -c "\l"

# Check Redis
docker-compose exec redis redis-cli INFO
```

### Out of memory

```bash
# Check usage
docker stats

# Increase limits in docker-compose.yml
services:
  postgres:
    deploy:
      resources:
        limits:
          memory: 4G
```

## 📈 Performance Tuning

### PostgreSQL

```sql
-- Connection pooling
ALTER SYSTEM SET max_connections = 200;
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET effective_cache_size = '1GB';

-- Index creation
CREATE INDEX idx_customers_owner ON customers(owner);
CREATE INDEX idx_tickets_customer ON tickets(customer_id);
CREATE INDEX idx_deals_stage ON deals(stage);
```

### Redis

```bash
# Optimize memory
redis-cli CONFIG SET maxmemory-policy allkeys-lru
redis-cli CONFIG SET maxmemory 2gb
```

## 🔑 Secrets Management

### Use GitHub Secrets for CI/CD

1. Go to Repository > Settings > Secrets
2. Add:
   - `DEPLOY_KEY`: SSH private key
   - `DEPLOY_HOST`: Server IP/domain
   - `DEPLOY_USER`: SSH username
   - `SLACK_WEBHOOK`: Slack notification URL

### Local Secrets

```bash
# Never commit .env, use .env.example
git config core.hooksPath .githooks
echo ".env" >> .gitignore
```

## 📞 Support

For issues:
1. Check GitHub Actions logs
2. Review application logs: `docker-compose logs`
3. Test endpoints manually
4. Check database connectivity

---

**Last Updated**: 2026-05-25
**Version**: 1.0.0
