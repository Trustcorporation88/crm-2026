# Mr.Holmes CRM - Makefile
# Comandos rápidos para desenvolvimento e deployment

.PHONY: help validate build up down logs clean restart health test deploy

DOCKER_COMPOSE := docker-compose
PYTHON := python3
PYTEST := pytest

help:
	@echo ""
	@echo "🚀 Mr.Holmes CRM - Development & Deployment Commands"
	@echo ""
	@echo "Setup & Validation:"
	@echo "  make validate     - Validate environment, Docker, dependencies"
	@echo "  make health       - Check health of all services"
	@echo ""
	@echo "Development:"
	@echo "  make build        - Build Docker images"
	@echo "  make up           - Start all services (docker-compose up -d)"
	@echo "  make down         - Stop all services (docker-compose down)"
	@echo "  make restart      - Restart all services"
	@echo "  make logs         - Show logs from all services"
	@echo "  make logs-crm     - Show Streamlit CRM logs"
	@echo "  make logs-api     - Show FastAPI logs"
	@echo ""
	@echo "Testing & Quality:"
	@echo "  make test         - Run pytest test suite"
	@echo "  make lint         - Run code linting (ruff)"
	@echo "  make format       - Format code (black)"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean        - Clean up containers, images, volumes"
	@echo "  make reset        - Full reset (containers + data + volumes)"
	@echo "  make backup       - Backup database"
	@echo ""
	@echo "Deployment:"
	@echo "  make deploy       - Deploy to production"
	@echo ""

# Setup & Validation
validate:
	@echo "🔍 Validating environment..."
	@$(PYTHON) validate.py

health:
	@echo "💓 Checking service health..."
	@$(PYTHON) healthcheck.py

health-monitor:
	@echo "📊 Monitoring services (continuous)..."
	@$(PYTHON) healthcheck.py --monitor --interval 5 --duration 600

# Development
build:
	@echo "🐳 Building Docker images..."
	@$(DOCKER_COMPOSE) build

up:
	@echo "▶️  Starting services..."
	@$(DOCKER_COMPOSE) up -d
	@echo ""
	@echo "✅ Services started!"
	@echo "  Streamlit: http://localhost:8512"
	@echo "  API:       http://localhost:8000/docs"
	@echo "  Adminer:   http://localhost:8080"
	@echo ""

down:
	@echo "⏹️  Stopping services..."
	@$(DOCKER_COMPOSE) down

restart: down up

logs:
	@$(DOCKER_COMPOSE) logs -f

logs-crm:
	@$(DOCKER_COMPOSE) logs -f crm-app

logs-api:
	@$(DOCKER_COMPOSE) logs -f api

logs-db:
	@$(DOCKER_COMPOSE) logs -f postgres

# Testing & Quality
test:
	@echo "🧪 Running tests..."
	@$(PYTEST) tests/ -v --cov=. --cov-report=html
	@echo ""
	@echo "✅ Test coverage report: htmlcov/index.html"

lint:
	@echo "🔎 Linting code..."
	@$(PYTHON) -m ruff check .

format:
	@echo "✨ Formatting code..."
	@$(PYTHON) -m black .

# Maintenance
clean:
	@echo "🧹 Cleaning up..."
	@$(DOCKER_COMPOSE) down
	@docker system prune -f
	@echo "✅ Cleanup complete"

reset:
	@echo "⚠️  FULL RESET - This will delete all data!"
	@read -p "Type 'yes' to confirm: " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		echo "🔄 Resetting..."; \
		$(DOCKER_COMPOSE) down -v; \
		docker system prune -af; \
		echo "✅ Reset complete"; \
	else \
		echo "Reset cancelled"; \
	fi

backup:
	@echo "💾 Backing up database..."
	@mkdir -p backups
	@$(DOCKER_COMPOSE) exec -T postgres pg_dump -U crm crm > backups/backup_$(shell date +%Y%m%d_%H%M%S).sql
	@echo "✅ Backup saved to backups/"

# Deployment
deploy:
	@echo "🚀 Deploying to production..."
	@echo ""
	@echo "1. Validating environment..."
	@$(PYTHON) validate.py || exit 1
	@echo ""
	@echo "2. Building images..."
	@$(DOCKER_COMPOSE) build || exit 1
	@echo ""
	@echo "3. Starting services..."
	@$(DOCKER_COMPOSE) up -d || exit 1
	@echo ""
	@echo "4. Checking health..."
	@sleep 5
	@$(PYTHON) healthcheck.py || exit 1
	@echo ""
	@echo "✅ Deployment complete!"

# Database management
db-shell:
	@echo "🗄️  Connecting to PostgreSQL..."
	@$(DOCKER_COMPOSE) exec postgres psql -U crm -d crm

db-migrate:
	@echo "🔄 Running database migrations..."
	@$(DOCKER_COMPOSE) exec api alembic upgrade head

redis-cli:
	@echo "📍 Connecting to Redis..."
	@$(DOCKER_COMPOSE) exec redis redis-cli

# Development shortcuts
run-streamlit:
	@echo "📊 Starting Streamlit (development)..."
	@streamlit run crm_app.py --server.port=8512

run-api:
	@echo "🔌 Starting FastAPI (development)..."
	@uvicorn crm_api:app --host 0.0.0.0 --port 8000 --reload

install-deps:
	@echo "📦 Installing dependencies..."
	@pip install -r requirements.txt
	@pip install -r web_requirements.txt
	@pip install -r requirements-prod.txt

# Info commands
info:
	@echo "ℹ️  System Information:"
	@echo ""
	@echo "Docker:"
	@docker --version
	@docker-compose --version
	@echo ""
	@echo "Python:"
	@$(PYTHON) --version
	@echo ""
	@echo "Services:"
	@$(DOCKER_COMPOSE) ps
	@echo ""

ps:
	@$(DOCKER_COMPOSE) ps

status: health

# Default target
.DEFAULT_GOAL := help
