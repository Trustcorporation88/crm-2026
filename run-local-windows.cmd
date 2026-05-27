@echo off
setlocal

cd /d "%~dp0"

set "CRM_LOCAL_MODE=1"
set "PYTHONIOENCODING=utf-8"
set "DATABASE_URL=sqlite:///crm-local.db"
set "REDIS_URL=redis://localhost:6379/0"
set "JWT_SECRET_KEY=local-dev-secret-key-with-32-plus-chars"
set "JWT_ALGORITHM=HS256"
set "API_PORT=8000"
set "API_HOST=127.0.0.1"

echo.
echo ======================================
echo Mr.Holmes CRM - Local Windows Launcher
echo ======================================
echo.
echo 1. Validando ambiente local...
python validate.py
if errorlevel 1 (
    echo.
    echo Falha na validacao. Corrija os itens acima antes de continuar.
    exit /b 1
)

echo.
echo 2. Iniciando Streamlit local...
echo URL: http://localhost:8512
python -m streamlit run crm_app.py --server.port 8512 --server.address 127.0.0.1
