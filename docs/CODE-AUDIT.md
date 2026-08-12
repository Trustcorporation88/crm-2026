# Auditoria de código — camada API v2.0

Auditoria de verificação e correção do repositório, com foco em executabilidade,
segurança, correção lógica e higiene de código.

**Baseline:** 25 testes passando, `tests/test_api.py` impossível de coletar.
**Depois:** 46 testes passando, incluindo 10 novos testes de regressão.

## Resumo

O núcleo do CRM (`crm_backend.py`, `crm_whatsapp_webhook.py`) está sólido: JWT
verificado com assinatura, HMAC comparado com `compare_digest`, rotação e
revogação de refresh token, throttle progressivo de autenticação, nenhum segredo
versionado. Esses 25 testes já passavam e continuam passando.

Os defeitos estavam concentrados na camada "v2.0" (`crm_api.py` e módulos de
apoio). Essa camada **nunca executou**: tinha dois erros de import que impediam
o módulo de carregar. Todo o código abaixo desses imports nunca rodou, o que
explica a densidade de bugs encontrados.

## Severidade alta

| # | Arquivo | Problema | Correção |
|---|---------|----------|----------|
| 1 | `crm_api.py` | `from fastapi.security import HTTPAuthCredentials` — nome inexistente. O módulo não carregava. | `HTTPAuthorizationCredentials` |
| 2 | `crm_api.py` | `from structured_logging import ... init_redis` — função inexistente. Segundo erro de import. | Import removido |
| 3 | `prometheus_metrics.py` | O middleware lia o corpo da requisição e substituía `receive` por um `http.disconnect`, deixando o endpoint sem payload. **Quebrava todo POST/PUT/PATCH.** | Mede via `Content-Length`, sem tocar no stream |
| 4 | `error_handlers.py` | Logava com `message=...`, que colide com o parâmetro do próprio método e com atributo reservado do `LogRecord` → `TypeError` dentro do handler de erro. **Toda exceção de domínio quebrava o handler.** | Renomeado para `error_message` + guarda geral no logger |
| 5 | `crm_api.py` | `/auth/logout` gravava o token numa blacklist que **nada lia**. O logout não invalidava nada. | `verify_token` e `/auth/refresh` consultam a blacklist; TTL passa a acompanhar o `exp` do token |
| 6 | `crm_api.py` | Checagens de papel usavam `ValidationError(status_code=...)`, argumento que a classe não aceita → `TypeError`, capturado pelo `except Exception` e reembalado. **Negação de permissão virava 500.** | `AuthorizationError` → 403 correto |
| 7 | `requirements-prod.txt` | `slowapi` ausente, embora `crm_api.py` o importe. O CI e o deploy instalam esse arquivo → a API não subiria. | Dependência adicionada |

## Severidade média

| # | Arquivo | Problema | Correção |
|---|---------|----------|----------|
| 8 | `crm_api.py` | `db.execute("SELECT 1")` — SQLAlchemy 2.0 exige construto executável. O health check falhava sempre. | `text("SELECT 1")` + status por componente |
| 9 | `crm_api.py` | `RateLimitExceeded` sem handler registrado: estouro de limite virava 500 em vez de 429. | Handler do slowapi registrado |
| 10 | `crm_api.py` | `/metrics` devolvia bytes via encoder JSON; o Prometheus não conseguia coletar. | `PlainTextResponse` com `CONTENT_TYPE_LATEST` |
| 11 | `crm_api.py` | `redis.delete("customers:*")` — o DEL do Redis não expande glob. O cache de listagem nunca era invalidado. | `clear_cache_pattern()` |
| 12 | `structured_logging.py` | `correlation_id` guardado no objeto do logger: sob concorrência, o ID de uma requisição vazava para outra. | `ContextVar`, isolado por requisição |
| 13 | `structured_logging.py` | `get_logger()` anexava um handler novo a cada chamada, duplicando cada linha de log. | Handler idempotente |
| 14 | `crm_api.py` | 18 blocos `except Exception` engoliam `CRMException` e devolviam `str(e)` ao cliente, vazando detalhe interno. | Re-lança erro de domínio; genérico vira `InternalServerError` |
| 15 | `crm_api.py` | `/auth/refresh` copiava o payload inteiro, carregando `iat` antigo e permitindo renovação indefinida. | Claims reconstruídas |
| 16 | `crm_api.py` | CORS com `allow_credentials=True` junto de origem `*` — combinação rejeitada pelo navegador. | Desabilita credenciais quando há wildcard |

## Severidade baixa

- `crm_api.py`: `payload.dict()` (removido no Pydantic v2) → `model_dump_json()`.
- `crm_api.py`: `WebhookPayload.timestamp` usava hora local ingênua → UTC com timezone.
- `crm_api.py`: `except:` nu na leitura de `CORS_ORIGINS` → exceções específicas com fallback.
- `error_handlers.py`: `datetime.utcnow()` (deprecado) → `datetime.now(timezone.utc)`.
- 43 imports mortos e f-strings sem placeholder removidos em 18 arquivos.
- `crm_backend.py`: nomes de tabela interpolados por f-string agora passam por
  `_safe_identifier()`. Não havia injeção — todos os chamadores usam literais
  internos — mas o ponto de interpolação fica protegido contra uso futuro.

## Testes

`tests/conftest.py` exigia um Postgres e um Redis reais, e chegava a executar
`DROP DATABASE`. Passou a usar SQLite temporário e `fakeredis` com servidor
compartilhado, sem dependência de serviço externo.

`tests/test_api.py` esperava 403 para requisições sem credencial. O correto é
401 (403 é para autenticado-porém-proibido); as expectativas foram ajustadas.

`tests/test_api_regressions.py` (novo) cobre os defeitos acima. **9 dos 10
testes falham no código original e passam no corrigido** — verificado numa
árvore de trabalho separada.

## Pendências recomendadas (fora do escopo desta correção)

1. **Sobreposição arquitetural.** `crm_api.py` e `crm_whatsapp_webhook.py`
   implementam dois conjuntos paralelos de auth e webhooks. O segundo é o que
   está em uso e testado; o primeiro é majoritariamente placeholder que devolve
   listas vazias. Decidir qual é o serviço oficial e remover o outro.
2. **Endpoints placeholder.** Os handlers de customers/tickets/deals em
   `crm_api.py` não consultam banco: retornam `{"data": []}`. Estão prontos para
   uso indevido caso alguém os considere funcionais.
3. **Webhooks sem autenticação.** As rotas `/webhooks/*` de `crm_api.py` não
   validam HMAC, ao contrário das de `crm_whatsapp_webhook.py`. Se forem
   expostas, aceitam POST de qualquer origem.
4. **Cinco arquivos de requirements** com versões divergentes
   (`requirements.txt`, `-prod`, `-v2`, `-docker`, `web_requirements.txt`).
   Consolidar para evitar novas lacunas como a do `slowapi`.
