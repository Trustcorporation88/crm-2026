# MR TRUST CRM

Sistema de gestão de relacionamento com clientes da Trust Corporation. Vendas,
atendimento e marketing num só lugar: funil com previsão ponderada, visão 360
do cliente e execução guiada do dia.

## Começando

Requer **Python 3.11 ou superior**.

```bash
pip install -r requirements.txt
streamlit run crm_app.py
```

Na primeira execução o banco é criado e as contas iniciais recebem **senhas
aleatórias, exibidas uma única vez no log de inicialização**. Anote-as, ou
defina-as antes de subir:

```bash
export CRM_SEED_PASSWORD_ADMIN='escolha-uma-senha-forte'
```

Copie `.env.example` para `.env` e ajuste o que for necessário.

## Testes

```bash
python -m pytest
```

## Documentação

| Documento | Para quê |
|---|---|
| **[docs/ESTADO-ATUAL.md](docs/ESTADO-ATUAL.md)** | **O que o sistema faz hoje — comece por aqui** |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Deploy com Docker |
| [docs/DEPLOY-RENDER.md](docs/DEPLOY-RENDER.md) | Deploy na Render |
| [docs/MIGRACAO-POSTGRES.md](docs/MIGRACAO-POSTGRES.md) | Migrar de SQLite para Postgres |
| [docs/CODE-AUDIT.md](docs/CODE-AUDIT.md) | Auditoria da camada de API |
| [docs/historico/](docs/historico/) | Documentos antigos, preservados como registro |

Os documentos em `docs/historico/` descrevem funcionalidades que nunca foram
integradas ao produto. Estão guardados pelo valor de registro, não como
descrição do sistema — cada um traz um aviso no topo.

## Estrutura

```
crm_app.py               interface Streamlit (aplicação principal)
crm_backend.py           lógica de domínio, autenticação, RBAC, auditoria
crm_db.py                camada SQLite/Postgres
crm_whatsapp_webhook.py  serviço oficial (webhook + API de entidades)
tests/                   suíte de testes
docs/                    documentação
nao_integrado/           código escrito mas nunca ligado ao produto
```

## Segurança

Se encontrar uma vulnerabilidade, não abra issue pública — fale diretamente com
os responsáveis pelo repositório.

Antes de expor uma instância publicamente, confira a seção de configuração em
[docs/ESTADO-ATUAL.md](docs/ESTADO-ATUAL.md): há variáveis cuja ausência tem
efeito relevante, e `CRM_DEMO_LOGIN` ligado permite que qualquer visitante
entre sem senha.
