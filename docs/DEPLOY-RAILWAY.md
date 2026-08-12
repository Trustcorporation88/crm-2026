# Deploy no Railway com banco no Supabase

Arranjo em uso: a aplicação Streamlit roda no **Railway**, e o banco é um
Postgres gerenciado no **Supabase**.

Este documento substitui o antigo guia da Render, que deixou de ser usada.

---

## Como o Railway monta a aplicação

O `railway.toml` manda usar o `Dockerfile` do repositório. Não há passo de
build manual: cada push na `main` dispara um novo deploy.

O contêiner sobe o Streamlit na porta que o Railway injeta em `PORT`. O
`docker-entrypoint.sh` traduz essa variável para `STREAMLIT_SERVER_PORT`,
porque o comando usa forma exec e não expande variável de shell.

Verificação de saúde: `/_stcore/health`, endpoint interno do Streamlit. Ele
confirma que o processo web responde — **não** que o banco está acessível.
Uma instância sem banco passa na verificação e falha na primeira tela.

## Ligar o Supabase

No Supabase: **Project Settings → Database → Connection string → URI**.

Use o **pooler em modo sessão**, no host `aws-<região>.pooler.supabase.com`,
**porta 5432**. Não use a conexão direta (`db.<ref>.supabase.co`): ela é IPv6
nos planos sem o add-on de IPv4, e o Railway sai por IPv4 — a conexão
simplesmente não se estabelece.

Cuidado para não confundir as portas do pooler, que é fácil:

| Porta | Modo | Para quê |
|---|---|---|
| **5432** | sessão | **este caso** — back-end persistente em rede IPv4 |
| 6543 | transação | funções serverless e edge |

O modo transação não mantém estado de sessão entre comandos, o que quebra
recursos que o driver usa por padrão. Para esta aplicação, sessão na 5432.

Copie a URI para `DATABASE_URL` nas variáveis do Railway. É a presença dessa
variável que faz o app usar Postgres — sem ela, ele silenciosamente cai no
SQLite local, que some a cada deploy.

O schema é criado sozinho no primeiro arranque, e atualizado nos seguintes:
`init_database()` roda `CREATE TABLE IF NOT EXISTS` e as migrações de coluna
a cada inicialização. Não há passo de migração separado.

As demais variáveis estão em [`RAILWAY-ENV.example`](../RAILWAY-ENV.example).

## Primeiro acesso

No primeiro arranque de um banco vazio, cinco contas são criadas. A senha de
cada uma vem de `CRM_SEED_PASSWORD_<LOGIN>` ou, na ausência dela, é sorteada e
**registrada uma única vez no log de inicialização**.

Com Postgres, isso acontece **uma vez só na vida do banco**. Definir a variável
depois não muda a senha de quem já existe — o seed só roda com a tabela vazia.

Se ninguém souber a senha do `admin`, o caminho é redefinir direto no banco.
No Supabase → **SQL Editor**:

```sql
UPDATE users
SET password_hash = crypt('SUA-SENHA-AQUI', gen_salt('bf', 12))
WHERE username = 'admin';
```

Isso funciona porque o `pgcrypto` (já instalado no Supabase) gera hash bcrypt
no formato `$2a$`, que é aceito pela verificação de senha da aplicação.

Feito o acesso, use **Administração → «Contas de acesso»** para criar as
demais contas e redefinir senhas pela interface. Não é preciso repetir SQL.

## O que verificar depois de um deploy

Consultas de diagnóstico para rodar no SQL Editor do Supabase:

```sql
-- Os índices foram criados? Esperado: 20.
SELECT COUNT(*) FROM pg_indexes
WHERE schemaname = 'public' AND indexname LIKE 'idx_%';

-- A tabela de versão dos dados existe? Ela é usada pelo cache da interface.
SELECT COUNT(*) FROM information_schema.tables
WHERE table_schema = 'public' AND table_name = 'meta_state';

-- Há atividade registrada?
SELECT COUNT(*) AS eventos, MAX(event_at) AS ultimo FROM audit_log;
```

Índices em zero ou `meta_state` ausente significam que o contêiner está
rodando uma versão anterior do código — o schema se atualiza no arranque, então
basta um redeploy.

## Limites conhecidos deste arranjo

**A suíte de testes roda em SQLite.** O caminho Postgres é exercitado em
produção, mas não pelos testes: são backends diferentes, e a tradução entre os
dialetos vive em `crm_db.py`. Divergência de comportamento aparece em produção
antes de aparecer no CI.

**Nenhuma métrica é exportada.** A instrumentação Prometheus vivia no
`crm_api.py`, que foi aposentado. Os arquivos `prometheus.yml`, `alert_rules.yml`
e `grafana/` seguem no repositório como infraestrutura pronta, sem nada de
aplicação para coletar.

**Não há backup automático.** O Supabase faz backup no nível do projeto,
conforme o plano contratado. O repositório não tem rotina própria, apesar de
`.env.example` documentar variáveis `BACKUP_*` que nenhum código lê.

**Não há mais keep-alive.** Existia um workflow que pingava
`crm.trustcorp.com.br` a cada 10 minutos para impedir a hibernação do plano
free da Render — cerca de 140 execuções por dia. Com a saída da Render ele
perdeu a função e foi removido.

Se o plano do Railway em uso hibernar por inatividade, o caminho correto é o
recurso de *always-on* da própria plataforma, não um agendador externo batendo
na porta a cada dez minutos.

## Docker local

O `docker-compose.yml` continua servindo para desenvolvimento: sobe Postgres
local, a aplicação e o serviço de webhook. Não é o que roda no Railway, que
usa apenas o `Dockerfile`.
