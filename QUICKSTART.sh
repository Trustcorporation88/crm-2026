#!/bin/bash
# Quick Start - Mr.Holmes CRM v2.0

echo "🚀 Mr.Holmes CRM v2.0 - Quick Start Guide"
echo "==========================================="
echo ""

# Step 1
echo "Step 1: Install Dependencies"
echo "$ pip install -r requirements-v2.txt"
echo ""
echo "Expected: ✓ All dependencies installed"
echo ""

# Step 2
echo "Step 2: Apply Database Migrations"
echo "$ psql -U postgres -d mr_holmes < migrations/001_add_indexes.sql"
echo ""
echo "Expected: ✓ 18 indexes created"
echo ""

# Step 3
echo "Step 3: Start Docker Services"
echo "$ docker-compose up -d"
echo ""
echo "Expected: ✓ 4 services running (postgres, redis, fastapi, streamlit)"
echo ""

# Step 4
echo "Step 4: Verify Health"
echo "$ curl http://localhost:8000/health"
echo ""
echo "Expected: {'status': 'healthy', 'version': '2.0.0'}"
echo ""

# Step 5
echo "Step 5: Test Rate Limiting (Make 6 requests in 60 seconds)"
echo "$ for i in {{1..6}}; do curl http://localhost:8000/auth/login -X POST; sleep 10; done"
echo ""
echo "Expected: ✓ Request 6 returns 429 (Too Many Requests)"
echo ""

# Step 6
echo "Step 6: View API Documentation"
echo "Open browser: http://localhost:8000/docs"
echo ""
echo "Expected: ✓ Interactive Swagger documentation"
echo ""

# Step 7
echo "Step 7: Monitor Metrics"
echo "Open browser: http://localhost:9090"
echo ""
echo "Expected: ✓ Prometheus dashboard with metrics"
echo ""

# Step 8
echo "Step 8: View Dashboards"
echo "Open browser: http://localhost:3000 (admin/admin)"
echo ""
echo "Expected: ✓ Grafana with business metrics"
echo ""

echo ""
echo "==========================================="
echo "✅ If all steps pass: System is ready!"
echo "==========================================="
echo ""
echo "📚 Full documentation: INTEGRATION-V2.md"
echo "📊 Status report: IMPLEMENTATION-STATUS-V2.md"
echo ""
