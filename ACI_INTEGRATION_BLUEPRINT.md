# Blueprint Tecnico: Integracao CRM + ACI

## 1) Objetivo

Definir um plano executavel para integrar o CRM atual com ACI como camada de tool-calling externo, preservando:

- seguranca (JWT, RBAC, throttle, auditoria)
- separacao por tenant/usuario
- rastreabilidade completa de cada chamada externa
- fallback seguro em falhas de integracao

Este blueprint foi desenhado para o estado atual do CRM e para adocao incremental em producao.

## 2) Estado Atual (base existente)

API ja disponivel no CRM:

- health e webhook WhatsApp
- auth JWT + refresh + logout
- update/delete auditados
- admin RBAC
- admin auth-throttle

Arquivos-chave existentes:

- crm_whatsapp_webhook.py
- crm_backend.py
- crm_app.py

## 3) Escopo da Integracao ACI

### 3.1 O que entra na Fase 1

- conexao de contas externas por usuario/tenant
- descoberta de tools disponiveis via ACI
- execucao de tool-call com auditoria completa
- historico e consulta operacional de chamadas

### 3.2 O que fica fora da Fase 1

- automacoes multi-etapas com scheduler
- politicas adaptativas por risco em tempo real
- reconciliacao assincrona de alto volume

## 4) Arquitetura Alvo

Fluxo logico:

1. Frontend CRM solicita acao externa
2. Backend CRM valida JWT, role e permissao de acao
3. Backend CRM chama ACI Gateway interno
4. ACI Gateway chama API/SDK do ACI
5. Resultado retorna ao CRM
6. CRM grava auditoria before/after + telemetria da chamada

Componentes novos propostos:

- aci_gateway.py: cliente unico para ACI (auth, discovery, call)
- aci_service.py: regras de negocio e validacao de permissoes
- tabelas de persistencia para conexoes e tool-calls

## 5) Contratos de Dados (modelo minimo)

### 5.1 Tabela aci_connections

Campos sugeridos:

- connection_id (pk)
- tenant_id
- user_id
- provider
- external_account_id
- status (active, revoked, error)
- scopes_json
- metadata_json
- created_at
- updated_at

### 5.2 Tabela aci_tool_calls

Campos sugeridos:

- call_id (pk)
- tenant_id
- user_id
- actor_username
- tool_name
- action_name
- request_json
- response_json
- status (success, failed, timeout, denied)
- latency_ms
- error_code
- error_message
- correlation_id
- created_at

### 5.3 Tabela aci_tool_policies

Campos sugeridos:

- policy_id (pk)
- role
- tool_name
- action_name
- allowed (0,1)
- max_calls_per_hour
- requires_approval (0,1)
- created_at
- updated_at

## 6) Endpoints Novos Propostos

Todos os endpoints abaixo usam auth JWT + validacao RBAC por acao.

### 6.1 Iniciar conexao externa

POST /api/aci/connect/start

Request:

{
  "provider": "google",
  "tenant_id": "default",
  "redirect_uri": "https://crm.exemplo.com/aci/callback"
}

Response:

{
  "connection_id": "conn_123",
  "authorization_url": "https://..."
}

Permissao sugerida: aci.connect

### 6.2 Callback de conexao

POST /api/aci/connect/callback

Request:

{
  "connection_id": "conn_123",
  "code": "oauth_code",
  "state": "state_token"
}

Response:

{
  "ok": true,
  "status": "active"
}

Permissao sugerida: aci.connect

### 6.3 Listar tools disponiveis

GET /api/aci/tools?provider=google

Response:

{
  "tools": [
    {
      "tool_name": "google_calendar",
      "actions": ["create_event", "list_events"],
      "requires_approval": false
    }
  ]
}

Permissao sugerida: aci.tools.read

### 6.4 Executar tool-call

POST /api/aci/tool-call

Request:

{
  "tenant_id": "default",
  "provider": "google",
  "tool_name": "google_calendar",
  "action_name": "create_event",
  "input": {
    "title": "Reuniao de onboarding",
    "start": "2026-05-28T14:00:00Z",
    "end": "2026-05-28T14:30:00Z"
  },
  "idempotency_key": "crm-ticket-123-create-event"
}

Response (sucesso):

{
  "call_id": "call_987",
  "status": "success",
  "output": {
    "event_id": "evt_abc",
    "link": "https://calendar.google.com/..."
  },
  "latency_ms": 420,
  "correlation_id": "corr_123"
}

Response (erro):

{
  "call_id": "call_987",
  "status": "failed",
  "error_code": "provider_rate_limited",
  "error_message": "Too many requests",
  "latency_ms": 310,
  "correlation_id": "corr_123"
}

Permissao sugerida: aci.tools.execute

### 6.5 Listar historico de tool-calls

GET /api/aci/tool-calls?status=failed&limit=50&cursor=...

Response:

{
  "rows": [
    {
      "call_id": "call_987",
      "tool_name": "google_calendar",
      "action_name": "create_event",
      "status": "failed",
      "latency_ms": 310,
      "created_at": "2026-05-25T17:22:00Z"
    }
  ],
  "next_cursor": "..."
}

Permissao sugerida: aci.calls.read

## 7) Regras de Seguranca (obrigatorio)

1. Nenhum secret/token de provider no frontend.
2. Token de acesso externo armazenado apenas server-side, criptografado em repouso.
3. Aplicar principio de menor privilegio por role + tool + acao.
4. Idempotency key obrigatoria para acoes mutaveis.
5. Timeout e retry com backoff para chamadas externas.
6. Registrar correlation_id em todos os logs.
7. Sanitizar payloads para evitar vazar PII sensivel nos logs.
8. Nao permitir execucao de tool fora da matriz de politica.
9. Bloqueio por throttle em falhas repetidas por usuario/tenant.
10. Trilha de auditoria before/after para comandos mutaveis.

## 8) Mapeamento RBAC sugerido

Acoes novas:

- aci.connect
- aci.tools.read
- aci.tools.execute
- aci.calls.read
- aci.policies.manage

Sugestao inicial por role:

- admin: todas
- atendimento: aci.tools.read, aci.tools.execute (tools permitidas)
- vendas: aci.tools.read, aci.tools.execute (tools comerciais)
- marketing: aci.tools.read, aci.tools.execute (tools de campanha)
- cs: aci.tools.read, aci.tools.execute (tools de suporte)

## 9) Implementacao em 3 Fases

### Fase 1 (MVP operacional)

- criar gateway ACI
- criar endpoints connect/start, tools, tool-call
- persistir historico de chamadas
- integrar 2 tools de alto impacto

Criticos de aceite:

- sucesso de chamadas > 95% no ambiente de teste
- logs completos com correlation_id
- sem secret exposto no frontend

### Fase 2 (governanca e escala)

- matriz de politica role-tool-action editavel
- endpoint de listagem paginada por filtros
- dashboard admin de falhas e latencia

Criticos de aceite:

- bloqueio efetivo de chamadas nao autorizadas
- observabilidade por tenant e por role

### Fase 3 (producao endurecida)

- fallback por provider indisponivel
- dead-letter para falhas recorrentes
- playbooks de incidentes e rotacao de credenciais

Criticos de aceite:

- RTO e RPO definidos para indisponibilidade externa
- testes de caos para timeout/rate-limit

## 10) Checklist de Producao

- variaveis de ambiente separadas por ambiente
- segredo ACI armazenado em cofre seguro
- criptografia de tokens em repouso
- alarme para taxa de erro > limite
- alarme para latencia p95 > limite
- auditoria habilitada para todas as acoes mutaveis
- testes automatizados de auth, RBAC, idempotencia e timeout
- procedimento de revogacao de conexao externa por usuario

## 11) Plano de Testes (minimo)

- auth negada sem token e com token invalido
- role sem permissao nao executa tool
- idempotency impede duplicacao de acao mutavel
- falha do provider gera status failed e log consistente
- listagem paginada retorna cursor corretamente
- policy update impacta autorizacao imediatamente

## 12) Entregaveis Tecnicos sugeridos

- modulo CRM/aci_gateway.py
- modulo CRM/aci_service.py
- migracoes de schema para aci_connections e aci_tool_calls
- endpoints /api/aci/* no crm_whatsapp_webhook.py
- testes em CRM/tests/test_crm_aci_integration.py
- painel admin no crm_app.py para conexoes e historico

---

Se quiser, o proximo passo e transformar este blueprint em implementacao Fase 1 com patch direto no codigo e testes automatizados.
