# Deploy Mr.Holmes CRM no Render

**URL de produção:** https://crm-2026.onrender.com

## Status atual (plano Free)

| Item | Situação |
|------|----------|
| App Streamlit | ✅ Live |
| Banco | SQLite em disco efêmero (dados podem resetar em redeploy) |
| Cold start | ~30–60 s após inatividade |
| Módulos v2 | Cadências, Health Score, Templates, Forecast, etc. |

Modelo completo: `RENDER-ENV.example`

## Variáveis de ambiente (Render → Environment)

| Variável | Valor recomendado |
|----------|-------------------|
| `CRM_LOCAL_MODE` | `1` |
| `JWT_SECRET_KEY` | string aleatória com 32+ caracteres |
| `JWT_ALGORITHM` | `HS256` |
| `CRM_PUBLIC_URL` | `https://crm-2026.onrender.com` |
| `DEEPSEEK_API_KEY` | Chave da API DeepSeek (chat nos guias ℹ️) |
| `DEEPSEEK_MODEL` | `deepseek-chat` (opcional) |

Opcional (persistência ao migrar para plano pago):

| Variável | Valor |
|----------|--------|
| `CRM_DATA_DIR` | `/data` (com disco persistente montado) |

## Login padrão

- **Usuário:** `admin`
- **Senha:** `admin123`

Altere após o primeiro acesso em produção.

## Próximo nível (quando precisar)

1. **Starter Web Service** (~US$ 7/mês) — sem hibernação, mais estável.
2. **Disco persistente** (1 GB) — `CRM_DATA_DIR=/data` para SQLite não sumir.
3. **PostgreSQL no Render** — para API (`crm_api.py`); o app Streamlit ainda usa SQLite até migração futura.
4. **Domínio customizado** — Settings → Custom Domains → `crm.seudominio.com.br`.

## Redeploy

Push na branch `main` dispara deploy automático, ou: **Manual Deploy** → latest commit.

## Build local (testar Docker)

```bash
docker build -t crm-2026 .
docker run -p 8512:8512 -e CRM_LOCAL_MODE=1 -e JWT_SECRET_KEY=local-dev-secret-key-with-32-plus-chars crm-2026
```

Abra http://localhost:8512
