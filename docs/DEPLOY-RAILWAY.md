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

Use o **Session pooler** (porta 6543), não a conexão direta. O app abre e
fecha uma conexão por operação; sem o pooler, o limite de conexões do Postgres
se esgota rápido.

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

## A vitrine pública: democrm.trustcorp.com.br

Um **segundo serviço no Railway**, do mesmo repositório, servindo uma operação
fictícia da MEiSHOP. Serve para mandar o link a uma franqueadora ou a uma
construtora sem que ela veja um único cliente real.

### Por que um serviço separado, e não uma seção dentro do CRM

Porque o isolamento tem de ser de infraestrutura, não de código. Um "modo
demonstração" dentro da instância de produção significaria dado fictício e dado
real no mesmo banco, separados apenas por um `if` — e um `if` errado é um
incidente. Serviços separados não têm como se misturar.

### Como o banco funciona (e por que não tem banco)

A vitrine roda **sem `DATABASE_URL`**, o que a faz cair no SQLite dentro do
contêiner. Em produção isso seria um defeito grave; aqui é o recurso: o banco é
efêmero, morre a cada deploy, e a carga acontece de novo na primeira visita.

**A vitrine se restaura sozinha.** Um visitante pode editar, apagar e
desarrumar o que quiser durante a apresentação; o próximo deploy devolve tudo.
Nenhum banco a mais para pagar, nenhum volume a configurar.

### Criar o serviço

No projeto do Railway: **New → GitHub Repo → o mesmo `crm-2026`**. Ele lê o
`railway.toml` e usa o mesmo `Dockerfile`. Depois, em **Variables**:

| Variável | Valor | Por quê |
|---|---|---|
| `CRM_DEMO_DATASET` | `meishop` | liga a carga da vitrine |
| `CRM_SEED_PASSWORD_ADMIN` | senha só desta vitrine | não repetir a de produção |
| `DATABASE_URL` | **não definir** | é o que mantém o SQLite efêmero |

⚠️ **`DATABASE_URL` não pode existir neste serviço.** Se existir, o app grava no
Postgres apontado por ela. A carga tem trava e se recusa a rodar nesse caso —
mas a trava é a segunda linha de defesa, não a primeira.

Confirme também que o serviço de produção **não** tem `CRM_DEMO_DATASET`. É a
mesma proteção pelo outro lado.

### Apontar o domínio

No serviço da vitrine: **Settings → Networking → Custom Domain** →
`democrm.trustcorp.com.br`. O Railway devolve **dois** registros.

O DNS do `trustcorp.com.br` é gerenciado na **Cloudflare** — o
`crm.trustcorp.com.br` responde hoje em IPs dela (`104.21.x`, `172.67.x`), o
que significa que passa pelo proxy. É lá que os registros entram:

| Tipo | Nome | Valor | Proxy |
|---|---|---|---|
| CNAME | `democrm` | o destino que o Railway mostrar | **desligado** (nuvem cinza) |
| TXT | o que o Railway mostrar | o que o Railway mostrar | — |

**Os dois são obrigatórios.** Este documento dizia que bastava o CNAME, e
estava errado. O TXT é como o Railway confirma que o domínio é seu antes de
rotear tráfego, e a falta dele tem um sintoma que engana:

> Sem o registro TXT, o endereço responde **404** mesmo com o CNAME
> resolvendo corretamente.

Quem não sabe disso vai procurar o defeito na aplicação, que está sã, enquanto
o problema está no DNS.

Sobre o proxy da Cloudflare: comece com a **nuvem cinza** (DNS only), porque
com o proxy no meio o Railway pode não conseguir emitir o certificado. Se
depois quiser ligar o proxy, o modo SSL/TLS da Cloudflare precisa ser **Full**
— em *Full (Strict)* a resposta é `ERR_TOO_MANY_REDIRECTS`.

O certificado é emitido automaticamente depois que o DNS propaga; o Railway
tenta por até 72 horas antes de desistir. Enquanto não propagar, o endereço
`*.up.railway.app` do próprio serviço já funciona — e serve perfeitamente para
mandar a um cliente, porque o domínio bonito é acabamento, não requisito.

### Limite de domínios por plano

Vale saber antes de planejar endereços, porque a mensagem do Railway não
explica o motivo:

| Plano | Domínios próprios |
|---|---|
| Trial | 1 no total |
| **Hobby** | **2 por serviço** |
| Pro | 20 por serviço |

No Trial, `exemplo.com` e `www.exemplo.com` já contam como dois — o limite é
por domínio distinto, não por site.

### O que o visitante vê

Uma faixa em toda tela, na entrada e depois de entrar:

> 🎭 **Ambiente de demonstração.** Clientes, contratos e chamados desta tela são
> fictícios, criados para apresentar o sistema.

Sem isso a vitrine é indistinguível do CRM real: mesma marca, mesmas telas,
endereço parecido. Os dois estragos que o aviso evita são alguém da equipe
trabalhar horas dentro da demonstração, e um cliente em prospecção achar que
está vendo a carteira real da Trust.

### Acesso

Login `admin` com a senha de `CRM_SEED_PASSWORD_ADMIN`. Mande link e senha na
mesma mensagem para o cliente.

Existe a alternativa de `CRM_DEMO_LOGIN=true`, que troca a senha por botões de
"entrar com um clique". É legítimo aqui — é para isso que a variável existe.
Mas note que `democrm.trustcorp.com.br` é um endereço público sob a marca da
Trust: com o acesso livre ligado, qualquer pessoa que encontre o endereço entra,
e buscadores encontram. Com senha, você controla quem entra e revoga trocando a
variável. **Nunca ligue `CRM_DEMO_LOGIN` no serviço de produção.**

### Trocar os dados da vitrine

A operação fictícia vive em [`demo_meishop.py`](../demo_meishop.py), em listas
Python legíveis (`CONTAS`, `NEGOCIOS`, `CHAMADOS`, `TAREFAS`, `CAMPANHAS`).
Editar e dar push republica a vitrine com os dados novos.

Para conferir localmente antes de publicar:

```bash
env -u DATABASE_URL python demo_meishop.py
CRM_DB_PATH=Data/demo_meishop.sqlite3 streamlit run crm_app.py
```

### O custo

Um contêiner a mais, cobrado por RAM e CPU como o primeiro. Vale ligar o
**Serverless** neste serviço (`Settings → Deploy → Serverless`): uma vitrine
fica ociosa quase todo o tempo, e o preço do sono é a primeira tela demorar
alguns segundos — o que numa demonstração agendada não incomoda.

## Docker local

O `docker-compose.yml` continua servindo para desenvolvimento: sobe Postgres
local, a aplicação e o serviço de webhook. Não é o que roda no Railway, que
usa apenas o `Dockerfile`.
