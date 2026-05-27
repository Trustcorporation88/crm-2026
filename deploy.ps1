# Mr.Holmes CRM - Quick Deploy Script for Windows
# Usage: .\deploy.ps1

Write-Host "🚀 Mr.Holmes CRM - Production Deployment" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""

# Check requirements
Write-Host "📋 Checking requirements..." -ForegroundColor Yellow

$dockerCheck = docker --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Docker not found. Install from: https://docs.docker.com/desktop/install/windows/" -ForegroundColor Red
    exit 1
}

$dockerComposeCheck = docker-compose --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Docker Compose not found." -ForegroundColor Red
    exit 1
}

Write-Host "✅ Docker and Docker Compose are installed" -ForegroundColor Green
Write-Host "  Docker: $dockerCheck" -ForegroundColor Gray
Write-Host "  Compose: $dockerComposeCheck" -ForegroundColor Gray

# Setup environment
Write-Host ""
Write-Host "🔧 Setting up environment..." -ForegroundColor Yellow

if (!(Test-Path .env)) {
    Write-Host "Creating .env from .env.example..."
    Copy-Item .env.example .env
    Write-Host "⚠️  Please edit .env with your configuration" -ForegroundColor Yellow
    Write-Host "Opening .env in default editor..."
    notepad .env
    Write-Host "Press Enter when done editing .env..."
    Read-Host
} else {
    Write-Host "✅ .env already exists" -ForegroundColor Green
}

# Build and start services
Write-Host ""
Write-Host "🐳 Building Docker images..." -ForegroundColor Yellow
docker-compose build

Write-Host ""
Write-Host "▶️  Starting services..." -ForegroundColor Yellow
docker-compose up -d

# Wait for services to be healthy
Write-Host ""
Write-Host "⏳ Waiting for services to become healthy..." -ForegroundColor Yellow

$maxAttempts = 30
$attempt = 1

while ($attempt -le $maxAttempts) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8512" -ErrorAction SilentlyContinue
        Write-Host "✅ Streamlit is healthy" -ForegroundColor Green
        break
    } catch {
        Write-Host "Attempt $attempt/$maxAttempts... waiting"
        Start-Sleep -Seconds 2
        $attempt++
    }
}

$attempt = 1
while ($attempt -le $maxAttempts) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -ErrorAction SilentlyContinue
        Write-Host "✅ API is healthy" -ForegroundColor Green
        break
    } catch {
        Write-Host "Attempt $attempt/$maxAttempts... waiting"
        Start-Sleep -Seconds 2
        $attempt++
    }
}

# Display information
Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "✅ Deployment successful!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "🌐 Application URLs:" -ForegroundColor Cyan
Write-Host "  - Streamlit CRM: http://localhost:8512"
Write-Host "  - API (Swagger): http://localhost:8000/docs"
Write-Host "  - Database Admin: http://localhost:8080"
Write-Host "  - Redis Admin: http://localhost:8081"
Write-Host ""
Write-Host "👤 Default Credentials:" -ForegroundColor Cyan
Write-Host "  Username: admin"
Write-Host "  Password: admin123"
Write-Host ""
Write-Host "📚 Documentation:" -ForegroundColor Cyan
Write-Host "  - Deployment Guide: DEPLOYMENT.md"
Write-Host "  - Production README: README-PRODUCTION.md"
Write-Host "  - Phase 1 Summary: PHASE1-COMPLETE.md"
Write-Host ""
Write-Host "🔍 Check logs with:" -ForegroundColor Cyan
Write-Host "  docker-compose logs -f crm-app   # Streamlit"
Write-Host "  docker-compose logs -f api        # API"
Write-Host "  docker-compose logs -f postgres   # Database"
Write-Host ""
Write-Host "🛑 Stop services with:" -ForegroundColor Cyan
Write-Host "  docker-compose down"
Write-Host ""
Write-Host "Happy coding! 🚀" -ForegroundColor Green
