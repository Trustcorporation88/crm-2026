@echo off
REM setup-v2.0.cmd - Mr.Holmes CRM v2.0 Setup Script for Windows

setlocal enabledelayedexpansion

echo.
echo 🚀 Mr.Holmes CRM v2.0 Setup
echo ================================
echo.

REM 1. Install Python dependencies
echo [1/6] Installing Python dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo Error installing requirements.txt
    exit /b 1
)
pip install -r requirements-v2.txt
if errorlevel 1 (
    echo Error installing requirements-v2.txt
    exit /b 1
)
echo ✓ Dependencies installed
echo.

REM 2. Verify PostgreSQL connection
echo [2/6] Verifying PostgreSQL connection...
psql -U postgres -d mr_holmes -c "SELECT 1" > nul 2>&1
if errorlevel 1 (
    echo ✗ PostgreSQL connection failed
    echo Make sure PostgreSQL is running and credentials are correct
    exit /b 1
)
echo ✓ PostgreSQL connected
echo.

REM 3. Apply database migrations
echo [3/6] Applying database migrations...
if exist "migrations\001_add_indexes.sql" (
    psql -U postgres -d mr_holmes < migrations\001_add_indexes.sql
    if errorlevel 1 (
        echo Error applying migrations
        exit /b 1
    )
    echo ✓ Database indexes created
) else (
    echo ✗ Migration file not found
    exit /b 1
)
echo.

REM 4. Create necessary directories
echo [4/6] Creating directories...
if not exist "logs" mkdir logs
if not exist "templates" mkdir templates
if not exist "migrations" mkdir migrations
if not exist "grafana\dashboards" mkdir grafana\dashboards
if not exist "grafana\provisioning\datasources" mkdir grafana\provisioning\datasources
if not exist "grafana\provisioning\dashboards" mkdir grafana\provisioning\dashboards
echo ✓ Directories created
echo.

REM 5. Verify Redis connection
echo [5/6] Verifying Redis connection...
redis-cli ping > nul 2>&1
if errorlevel 1 (
    echo ✗ Redis connection failed
    echo Make sure Redis is running
    exit /b 1
)
echo ✓ Redis connected
echo.

REM 6. Validate Python environment
echo [6/6] Validating Python environment...
python validate.py
if errorlevel 1 (
    echo Error validating environment
    exit /b 1
)
echo ✓ Environment validated
echo.

echo ======================================
echo ✓ Setup completed successfully!
echo ======================================
echo.
echo Next steps:
echo 1. Update .env with your configuration
echo 2. Start Docker: docker-compose up -d
echo 3. Run health checks: curl http://localhost:8000/health
echo 4. Access API docs: http://localhost:8000/docs
echo 5. Monitor metrics: http://localhost:9090
echo 6. View Grafana: http://localhost:3000 (admin/admin)
echo.

pause
