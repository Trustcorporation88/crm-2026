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
| Serviço oficial | `crm_whatsapp_webhook.py` | FastAPI; recebe o webhook do WhatsApp e expõe CRUD de entidades com RBAC |

A lógica de domínio vive em `crm_backend.py`, compartilhada pelos dois.

### Decisão registrada: existia uma segunda API, e ela foi aposentada

Havia dois serviços FastAPI com **pilhas de autenticação incompatíveis** — um
token emitido por um não valia no outro. O `crm_api.py` foi removido, por três
razões verificadas antes da decisão:

1. **Não tinha consumidor.** A interface Streamlit chama `crm_backend`
   diretamente, e nenhum sistema externo apontava para ele.
2. **Não subia em lugar nenhum.** Render e Railway executam apenas o Streamlit.
3. **Seis dos seus 26 endpoints não tinham implementação** e respondiam 501.

O serviço que ficou é o que tem amarras externas reais: o provedor de WhatsApp
posta em `/webhook/whatsapp`, e o callback OAuth do ACI aponta para ele. São
URLs configuradas fora do repositório, e trocá-las exigiria janela de
indisponibilidade nas integrações.

**O que se perdeu junto:** endpoints REST de leitura e criação de clientes,
tickets e negócios (`GET`/`POST /api/customers` e similares), além do
`/metrics` do Prometheus e do log estruturado. Nada disso estava em uso. Se um
aplicativo ou parceiro precisar de API REST no futuro, o lugar é o serviço
oficial — e o histórico do git tem a implementação anterior como referência.

Saíram também os quatro módulos que existiam só para servir ao `crm_api.py`:
`error_handlers.py`, `prometheus_metrics.py`, `structured_logging.py` e
`cache_utils.py`. Com o último, o sistema deixou de depender de Redis.

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
- Gestão de contas de acesso: criar, editar papel, ativar/desativar e
  redefinir senha, em Administração → «Contas de acesso»
- Visibilidade por login: administrador vê a base inteira, os demais papéis
  veem apenas os registros sob sua responsabilidade
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
| Métricas em produção | **Nada** é exportado. A instrumentação vivia no `crm_api.py`, que foi aposentado. O `prometheus.yml`, o `alert_rules.yml` e o `grafana/` continuam no repositório como infraestrutura pronta, sem nada de aplicação para coletar |

### Decisão registrada: quem enxerga o quê

Até esta versão, qualquer pessoa autenticada lia qualquer cliente, ticket ou
negócio. A regra passou a ser:

| Papel | Enxerga |
|---|---|
| `admin` | A base inteira |
| Demais papéis | Apenas os registros onde é o responsável |
| Chamada interna (automação, webhook, migração) | A base inteira — não tem dono |

#### Como a posse é ligada

A coluna `owner` guarda o **nome exibido**; a coluna `owner_username` guarda o
**login**, e é ela que o controle de acesso usa. Renomear uma pessoa troca o
rótulo em todos os registros e não toca na chave — a pessoa continua enxergando
o que é dela.

A separação existe porque `owner` aparece direto em cerca de dez telas e num
editor de tabela do Streamlit que não aceita função de formatação: guardar o
login ali faria a interface mostrar "vendas" onde se lê "Rafael Nogueira".

O preço é o risco de as duas colunas divergirem. Ele é contido por haver um
único ponto de escrita (`_definir_responsavel`) e por um teste que varre o banco
exigindo que nenhuma linha discorde.

Um responsável que não corresponda a nenhuma conta é **recusado na escrita**.
Parece rígido, mas é o que impede o problema anterior: registro sem dono
identificável fica invisível para todo mundo.

A restrição vale para **leitura e escrita**. Alterar ou apagar registro de
outra pessoa devolve `PermissionError`, que a API traduz em HTTP 403. Esconder
na tela e liberar na API seria controle de fachada: a permissão do RBAC diz que
o papel pode editar aquele *tipo* de registro, não aquele registro específico.

Duas coisas precisaram ser arrumadas antes de ligar a regra:

1. **44% dos registros pertenciam a nomes sem conta** — "Leandro Martins",
   "Bruna Melo", "Daniel Freitas", "Igor Lima". Com a restrição ativa, eles
   ficariam invisíveis para todos. As quatro pessoas viraram contas de verdade.
2. **A lista de responsáveis da interface se alimentava dos donos já
   gravados**, então um nome sem conta virava opção selecionável e novos
   registros nasciam órfãos. Agora ela sai apenas de contas existentes.

A interface avisa, com uma legenda no topo, quando está mostrando um recorte —
filtro silencioso é indistinguível de perda de dados para quem usa.

Não há noção de território ou equipe no schema, então não existe nível
intermediário entre "vê tudo" e "vê o próprio". Se um gerente precisar ver a
carteira do time, isso vira um papel novo e uma regra nova.

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
- A posse mantém duas colunas (`owner` para exibir, `owner_username` para
  controlar acesso). Funciona e é testado, mas é denormalização: o ideal seria
  uma coluna só, com o nome resolvido na exibição
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
