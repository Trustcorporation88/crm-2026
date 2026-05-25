#!/bin/bash

# Script de Deploy para MR TRUST CRM

# Verificar e instalar dependências do sistema
echo "Verificando dependências do sistema..."
if ! command -v python3 &> /dev/null; then
    echo "Python 3 não encontrado. Instalando..."
    sudo apt-get update
    sudo apt-get install -y python3 python3-pip
fi

# Criar e ativar ambiente virtual
echo "Preparando ambiente virtual..."
python3 -m venv .venv
source .venv/bin/activate

# Atualizar pip e instalar dependências
pip install --upgrade pip
pip install -r requirements.txt

# Configurações de ambiente
export CRM_APP_ENV="production"
export CRM_LOG_LEVEL="WARNING"
export PYTHONWARNINGS="ignore"

# Configurações de rede e segurança
export WEBHOOK_HOST="0.0.0.0"
export WEBHOOK_PORT=8512
export CRM_STREAMLIT_PORT=8513
export CRM_STREAMLIT_HOST="0.0.0.0"

# Iniciar serviço de webhook em background
echo "Iniciando webhook..."
uvicorn crm_whatsapp_webhook:app \
    --host $WEBHOOK_HOST \
    --port $WEBHOOK_PORT \
    --log-level warning &

# Iniciar aplicação Streamlit
echo "Iniciando aplicação CRM..."
streamlit run crm_app.py \
    --server.port $CRM_STREAMLIT_PORT \
    --server.address $CRM_STREAMLIT_HOST \
    --server.baseUrlPath "/crm" \
    --server.enableCORS false \
    --server.enableXsrfProtection true