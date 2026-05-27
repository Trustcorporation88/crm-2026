#!/bin/bash
# setup-v2.0.sh - Mr.Holmes CRM v2.0 Setup Script

set -e

echo "🚀 Mr.Holmes CRM v2.0 Setup"
echo "================================"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 1. Install Python dependencies
echo -e "${YELLOW}[1/6] Installing Python dependencies...${NC}"
pip install -r requirements.txt
pip install -r requirements-v2.txt

echo -e "${GREEN}✓ Dependencies installed${NC}"

# 2. Verify PostgreSQL connection
echo -e "${YELLOW}[2/6] Verifying PostgreSQL connection...${NC}"
if ! psql -U postgres -d mr_holmes -c "SELECT 1" > /dev/null 2>&1; then
    echo -e "${RED}✗ PostgreSQL connection failed${NC}"
    echo "Make sure PostgreSQL is running and credentials are correct"
    exit 1
fi
echo -e "${GREEN}✓ PostgreSQL connected${NC}"

# 3. Apply database migrations
echo -e "${YELLOW}[3/6] Applying database migrations...${NC}"
if [ -f "migrations/001_add_indexes.sql" ]; then
    psql -U postgres -d mr_holmes < migrations/001_add_indexes.sql
    echo -e "${GREEN}✓ Database indexes created${NC}"
else
    echo -e "${RED}✗ Migration file not found${NC}"
    exit 1
fi

# 4. Create necessary directories
echo -e "${YELLOW}[4/6] Creating directories...${NC}"
mkdir -p logs
mkdir -p templates
mkdir -p migrations
mkdir -p grafana/dashboards
mkdir -p grafana/provisioning/datasources
mkdir -p grafana/provisioning/dashboards
echo -e "${GREEN}✓ Directories created${NC}"

# 5. Verify Redis connection
echo -e "${YELLOW}[5/6] Verifying Redis connection...${NC}"
if ! redis-cli ping > /dev/null 2>&1; then
    echo -e "${RED}✗ Redis connection failed${NC}"
    echo "Make sure Redis is running"
    exit 1
fi
echo -e "${GREEN}✓ Redis connected${NC}"

# 6. Validate Python environment
echo -e "${YELLOW}[6/6] Validating Python environment...${NC}"
python validate.py
echo -e "${GREEN}✓ Environment validated${NC}"

echo ""
echo -e "${GREEN}======================================"
echo -e "✓ Setup completed successfully!"
echo -e "=====================================${NC}"
echo ""
echo "Next steps:"
echo "1. Update .env with your configuration"
echo "2. Start Docker: docker-compose up -d"
echo "3. Run health checks: curl http://localhost:8000/health"
echo "4. Access API docs: http://localhost:8000/docs"
echo "5. Monitor metrics: http://localhost:9090"
echo "6. View Grafana: http://localhost:3000 (admin/admin)"
