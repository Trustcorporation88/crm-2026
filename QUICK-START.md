# 🚀 Mr.Holmes CRM - Quick Reference Card

**Seu guia rápido para deployment production em minutos**

---

## ⚡ SETUP EM 5 MINUTOS

### 1️⃣ Validar Ambiente
```bash
python validate.py
```
✅ Se tudo passa, vai para próximo passo

### 2️⃣ Copiar Configuração
```bash
cp .env.example .env
nano .env  # Edit com seus valores
```

### 3️⃣ Build & Deploy
```bash
make build
make up
```

### 4️⃣ Verificar Saúde
```bash
python healthcheck.py
```

### 5️⃣ Acessar
- **Streamlit**: http://localhost:8512
- **API Docs**: http://localhost:8000/docs
- **Admin DB**: http://localhost:8080

✅ **PRONTO PARA USAR!**

---

## 📋 COMANDOS MAIS USADOS

| Comando | O quê faz |
|---------|-----------|
| `make help` | Lista todos os comandos |
| `make up` | Inicia todos os serviços |
| `make down` | Para todos os serviços |
| `make logs` | Ver logs de todos os serviços |
| `make logs-crm` | Ver logs Streamlit |
| `make logs-api` | Ver logs API |
| `make test` | Rodar testes |
| `make restart` | Reiniciar tudo |
| `make health` | Health check dos serviços |
| `make clean` | Limpar containers/images |

---

## 🐳 DOCKER ESSENTIALS

```bash
# Ver status
docker-compose ps

# Ver espaço usado
docker system df

# Limpar tudo
docker system prune -a

# Ver logs
docker-compose logs -f crm-app  # Streamlit
docker-compose logs -f api      # FastAPI
docker-compose logs -f postgres # BD
docker-compose logs -f redis    # Cache
```

---

## 🗄️ BANCO DE DADOS

```bash
# Conectar ao Postgres
docker-compose exec postgres psql -U crm -d crm

# Backup
docker-compose exec -T postgres pg_dump -U crm crm > backup.sql

# Restore
cat backup.sql | docker-compose exec -T postgres psql -U crm crm

# Clear all data
docker-compose exec postgres psql -U crm -d crm -c "TRUNCATE TABLE users RESTART IDENTITY CASCADE;"
```

---

## 🔴 PROBLEMAS COMUNS

### ❌ Port already in use
```bash
# Windows
netstat -ano | findstr :8512
taskkill /PID <PID> /F

# Mac/Linux
lsof -ti:8512 | xargs kill -9
```

### ❌ Docker daemon not running
```bash
# Windows/Mac: Abrir Docker Desktop

# Linux
sudo systemctl start docker
```

### ❌ PostgreSQL não conecta
```bash
# Verificar se está rodando
docker-compose logs postgres

# Reiniciar
docker-compose restart postgres

# Aguardar pronto (30s)
docker-compose logs postgres | grep "ready to accept"
```

### ❌ API diz "connection refused"
```bash
# Ver erros
docker-compose logs api

# Checar se PostgreSQL está up
docker-compose logs postgres | grep "ready"

# Reiniciar tudo
docker-compose restart
```

### ❌ Falta espaço em disco
```bash
docker system prune -a  # Remove tudo não usado
df -h                    # Verificar espaço
```

---

## 🚀 DEPLOY EM PRODUÇÃO

### AWS EC2
```bash
# SSH na instância
ssh -i key.pem ec2-user@your-ip

# Instalar Docker
curl -fsSL https://get.docker.com | sudo sh

# Clone repo
git clone https://github.com/your-repo/crm-2026.git
cd crm-2026

# Configure .env com RDS
nano .env

# Deploy
docker-compose up -d

# Check health
curl http://localhost:8000/health
```

### Heroku
```bash
heroku create your-app
heroku addons:create heroku-postgresql:standard-0
heroku addons:create heroku-redis:premium-0
heroku config:set JWT_SECRET_KEY="your-secret"
git push heroku main
heroku logs --tail
```

---

## 📊 MONITORAMENTO

```bash
# Health check real-time
python healthcheck.py --monitor --interval 5

# Ver métricos Docker
docker stats

# Ver logs todos serviços
docker-compose logs --tail 50 -f
```

---

## 🔧 TROUBLESHOOTING AUTOMÁTICO

```bash
# Diagnóstico completo
python troubleshoot.py

# Info do sistema
python troubleshoot.py --info

# Quick fix automático
python troubleshoot.py --fix
```

---

## 🔑 CREDENCIAIS DEFAULT

| Campo | Valor |
|-------|-------|
| **Login** | admin |
| **Senha** | admin123 |
| **DB User** | crm |
| **DB Pass** | crm123 |
| **Redis** | Sem senha |

⚠️ **Mudar em produção!**

---

## 📁 ESTRUTURA IMPORTANTE

```
crm-2026/
├── docker-compose.yml        → Configuração produção
├── docker-compose.override.yml → Dev com hot-reload
├── .env                       → Variáveis (GITIGNORE!)
├── .env.example              → Template
├── crm_app.py               → Streamlit UI
├── crm_api.py               → FastAPI REST
├── validate.py              → Validar setup
├── healthcheck.py           → Check saúde
├── troubleshoot.py          → Debug automático
├── Makefile                 → Comandos rápidos
└── requirements-prod.txt    → Dependencies

```

---

## 🔒 SEGURANÇA BÁSICA

```bash
# 1. Mudar JWT secret
openssl rand -hex 32  # Gera novo

# 2. Mudar senhas default
# Editar crm_backend.py DEFAULT_USERS

# 3. Habilitar HTTPS
# certbot certonly --standalone -d seu-dominio.com

# 4. Backup automático
# docker-compose exec postgres pg_dump ... > backup.sql

# 5. Monitorar logs
# docker-compose logs -f | grep ERROR
```

---

## 🎯 CHECKLIST PRE-DEPLOY

- [ ] `python validate.py` ✅ passa
- [ ] `.env` configurado com valores reais
- [ ] Portas 8512, 8000, 5432, 6379 disponíveis
- [ ] Disco tem >10GB espaço
- [ ] Docker daemon rodando
- [ ] `make up` sucesso
- [ ] `python healthcheck.py` tudo verde
- [ ] Login funciona (admin/admin123)
- [ ] API responde: `curl http://localhost:8000/health`

---

## 📱 URLS IMPORTANTES

| URL | Descrição |
|-----|-----------|
| http://localhost:8512 | CRM Streamlit |
| http://localhost:8000 | API Root |
| http://localhost:8000/docs | API Swagger |
| http://localhost:8000/redoc | API ReDoc |
| http://localhost:8080 | Adminer (DB admin) |
| http://localhost:8081 | Redis Commander |
| http://localhost:1025 | Mailhog (emails) |

---

## 🆘 PRECISA DE AJUDA?

1. **Logs**: `make logs` ou `docker-compose logs -f`
2. **Diagnóstico**: `python troubleshoot.py`
3. **Validação**: `python validate.py`
4. **Health**: `python healthcheck.py`
5. **Documentação**: Ver [DEPLOYMENT.md](DEPLOYMENT.md)

---

## 📞 COMANDO MÁGICO (Resolve 90% dos problemas)

```bash
docker-compose down && docker system prune -a && docker-compose up -d
```

⚠️ **Aviso**: Isso deleta tudo não usado. Backup primeiro!

---

**Versão**: 1.0.0  
**Data**: 2026-05-25  
**Status**: 🟢 Production Ready
