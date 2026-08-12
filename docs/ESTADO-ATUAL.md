# Estado atual do sistema

Este documento descreve o que o CRM **faz hoje**, verificado contra o código.
Quando algo existe pela metade, está escrito que existe pela metade.

Ele nasceu de uma auditoria que encontrou o oposto disso: cerca de vinte
documentos na raiz do repositório descrevendo funcionalidades como concluídas
que nunca foram ligadas ao produto. Esses documentos foram preservados em
[`historico/`](historico/), com um aviso no topo de cada um.

---

## O que é

CRM em Python para operação comercial e de atendimento, em português. Duas
peças executáveis:

| Componente | Arquivo | O que é |
|---|---|---|
| Aplicação | `crm_app.py` | Interface Streamlit — é o que os usuários acessam |
| Serviço de webhook e API de entidades | `crm_whatsapp_webhook.py` | FastAPI; recebe WhatsApp e expõe CRUD com RBAC |
| API REST "v2.0" | `crm_api.py` | FastAPI; **ver a ressalva abaixo** |

A lógica de domínio vive em `crm_backend.py`, compartilhada pelos três.

### Ressalva importante: existem duas APIs

`crm_api.py` e `crm_whatsapp_webhook.py` mantêm **pilhas de autenticação
incompatíveis** — um token emitido por uma não vale na outra, e não há sessão
compartilhada. Nenhum dos dois deploys em nuvem (Render, Railway) sobe
`crm_api.py`; ambos rodam apenas o Streamlit.

Depois da correção dos endpoints que respondiam sucesso sem gravar, **6 dos 26
endpoints de `crm_api.py` respondem 501** por não terem implementação:
`/auth/login`, `/api/admin/backup`, `/api/reports/export/{tipo}`,
`/api/integrations/{nome}/connect` e os webhooks de e-mail e formulário.

Decidir qual serviço é o oficial é uma pendência aberta.

## Persistência

SQLite por padrão; Postgres quando `DATABASE_URL` está definida. A tradução
entre os dialetos fica em `crm_db.py`.

**Atenção ao ambiente:** no plano free da Render não há disco persistente, e o
SQLite vive no sistema de arquivos efêmero do contêiner — todo restart apaga a
base. Use `DATABASE_URL` apontando para um Postgres gerenciado, ou um disco
persistente no plano pago. O `render.yaml` documenta as duas opções.

### Formatos de data convivendo

As colunas de timestamp são `TEXT` e contêm **dois formatos**: linhas antigas
em `2026-05-25 08:30` e linhas novas em ISO UTC. Escritas novas são sempre ISO;
consultas com janela de tempo usam limiares **somente com a data**, único
formato que se comporta corretamente nos dois casos (ver `scoring_datas.py`).

Os dados existentes não foram convertidos. `crm_backend.normalize_timestamp()`
é a peça para isso, quando houver um PR de migração com dry-run e backup.

## O que existe e funciona

- Cadastro e gestão de clientes, tickets, negócios, campanhas e tarefas
- Funil comercial com kanban e previsão ponderada
- Linha do tempo por cliente e registro de auditoria de toda escrita
- Papéis e permissões (RBAC), com bloqueio progressivo de tentativas de login
- Recebimento de webhook do WhatsApp com validação HMAC
- Lead score, health score, previsão de receita, produtividade e cadências
- Catálogo de serviços e comparativo de mercado
- Integração ACI, com fluxo OAuth que valida `state` corretamente

## O que não existe, apesar de a documentação antiga afirmar que sim

| Descrito como pronto | Realidade |
|---|---|
| SSO (Azure AD, Google, Okta) | Código em `nao_integrado/`, nunca importado. **Tem falhas de segurança** — leia o README de lá antes de ligar |
| Tradução para quatro idiomas | Código em `nao_integrado/`, nunca importado. A interface é só em português |
| Reenvio de webhook com backoff | Código em `nao_integrado/`, nunca importado. Não há reenvio |
| Backup automático | Não existe rotina. As variáveis `BACKUP_*` do `.env.example` não são lidas por nada |
| Sentry, Datadog, envio para S3 | Documentados no `.env.example`, sem nenhuma linha de código correspondente |
| Métricas em produção | Só `crm_api.py` instrumenta métricas, e ele não sobe em Render nem Railway. Nesses ambientes **nada** é exportado |

## Configuração

Variáveis em `.env.example`. As que realmente importam:

| Variável | Efeito de não definir |
|---|---|
| `CRM_SEED_PASSWORD_<USUARIO>` | Senha inicial aleatória, registrada uma vez no log de inicialização |
| `CRM_API_JWT_SECRET` | Segredo gerado e gravado em arquivo no diretório de dados |
| `CRM_WHATSAPP_HMAC_SECRET` | Segredo gerado; emissores externos precisam do mesmo valor |
| `DATABASE_URL` | Usa SQLite local — efêmero em contêiner sem volume |
| `CRM_DEMO_LOGIN` | Desligado. Ligado, **qualquer visitante entra sem senha** |

Nenhuma conta nasce mais com senha pública. Instalações antigas que ainda
tenham `admin/admin123` são sinalizadas na interface.

## Testes

```bash
python -m pytest        # requer Python 3.11+
```

Cerca de 500 testes. Cobrem bem o backend, a segurança de autenticação, a API
e os módulos analíticos. A cobertura mais fina é a de `crm_app.py`, onde existe
apenas um smoke test de renderização — a maior parte das telas é script corrido
no nível do módulo, e não código encapsulado em funções que se possa exercitar.

## Dívida conhecida

Registrada aqui para não virar surpresa:

- `crm_app.py` tem 3.458 linhas com 31 funções e 65 instruções no nível do
  módulo, além de 545 linhas de CSS embutido e 120 acessos diretos a
  `st.session_state`
- `crm_backend.py` tem 101 funções num arquivo só, ainda que com fronteiras
  semânticas razoavelmente limpas
- Leituras da API não verificam posse: qualquer usuário autenticado lê
  qualquer registro por ID
- Valores monetários são `REAL` (ponto flutuante), não decimal
- `brand_assets.py` guarda 171 KB de PNG em base64, contornando o `COPY *.py`
  do Dockerfile
- `cadences.py` ainda grava timestamps em hora local ingênua, deliberadamente:
  migrar só a escrita quebraria a consulta de pendências

## Documentos vizinhos

- [`DEPLOYMENT.md`](DEPLOYMENT.md) — deploy com Docker
- [`DEPLOY-RENDER.md`](DEPLOY-RENDER.md) — deploy na Render
- [`MIGRACAO-POSTGRES.md`](MIGRACAO-POSTGRES.md) — migração de SQLite para Postgres
- [`CODE-AUDIT.md`](CODE-AUDIT.md) — auditoria anterior da camada de API
- [`historico/`](historico/) — documentos preservados, não confiáveis como descrição do presente
