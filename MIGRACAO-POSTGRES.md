# Migração para PostgreSQL — Supabase + Railway

Roteiro para tirar o CRM do SQLite num volume único e colocá-lo num Postgres
gerenciado, sem perder dados e com rollback em um passo.

---

## Por que

Hoje a base inteira vive num arquivo SQLite dentro de um volume do Railway.
Não há réplica nem backup testado: um incidente de disco é perda de dados. É a
pendência estrutural nº 1 do projeto — pesa mais do que qualquer funcionalidade.

## A arquitetura proposta

| Camada | Onde | Por quê |
|---|---|---|
| Aplicação (Streamlit + API) | **Railway** | Já roda bem lá; nada muda |
| Banco de dados | **Supabase** | Postgres gerenciado, backup diário e restauração a ponto no tempo |

Manter o compute no Railway e mover só o dado é o menor movimento que resolve o
maior risco. Não recomendo Postgres no Railway: o backup gerenciado e o PITR da
Supabase são exatamente o que falta hoje, e você já paga por eles no plano Pro.

---

## Qual string de conexão usar

A Supabase oferece três endpoints, e escolher errado é a causa mais comum de
falha nesta integração. Segundo a
[documentação oficial](https://supabase.com/docs/guides/database/connecting-to-postgres):

| Uso | Endpoint | Observação |
|---|---|---|
| **Migração dos dados** (o script abaixo) | Conexão direta, porta **5432** | IPv6, ou IPv4 com o add-on. É o indicado para carga em lote e `pg_dump` |
| **Aplicação no Railway** | Pooler em **session mode** | Cliente persistente em rede IPv4 — o caso do Streamlit |
| Não usar aqui | Pooler em transaction mode (6543) | Feito para serverless/edge, não para processo longo |

Se a conexão direta não abrir a partir da sua máquina, é IPv6: rode a migração
de um ambiente com IPv6 ou contrate o add-on de IPv4.

---

## Execução

### 1. Faça a cópia de segurança do arquivo atual

No Railway, baixe `crm.sqlite3` do volume. **Não pule este passo** — é o seu
rollback.

### 2. Ensaie sem escrever nada

```bash
python migrate_to_postgres.py \
  --sqlite crm.sqlite3 \
  --postgres "postgresql://postgres:SENHA@db.SEU-PROJETO.supabase.co:5432/postgres" \
  --dry-run
```

Mostra tabela por tabela quantas linhas seriam copiadas e o checksum de cada
uma. Nada é escrito.

### 3. Execute

Remova `--dry-run`. O script cria o schema, limpa os dados de exemplo, copia na
ordem das chaves estrangeiras, realinha as sequências e **verifica**: compara
contagem e checksum de conteúdo entre origem e destino, tabela por tabela.

Só considere concluído se a saída terminar em `✅ Migração verificada`.

Se o destino já tiver dados, o script para e exige `--replace`. É proposital:
sobrescrever base com dado real precisa ser uma decisão explícita.

### 4. Aponte a aplicação

No Railway, defina:

```
DATABASE_URL=postgresql://postgres.SEU-PROJETO:SENHA@REGIAO.pooler.supabase.com:5432/postgres
```

A aplicação detecta o esquema `postgresql://` e passa a usar Postgres. Sem essa
variável, continua no SQLite — é assim que o rollback funciona.

### 5. Confira no ar

Entre no sistema, abra Clientes 360, registre uma interação e confirme que ela
aparece na linha do tempo. Escrever é o que prova que a migração funcionou;
leitura sozinha não prova.

### Rollback

Remova a variável `DATABASE_URL` no Railway e reinicie. A aplicação volta ao
arquivo SQLite, que o script **nunca alterou** — ele abre a origem em modo
somente leitura.

---

## O que foi feito no código

**`crm_db.py` — camada de compatibilidade.** O backend continua escrevendo
`with _connect() as conn: conn.execute(sql, params)`. A camada traduz:

- placeholders `?` e `:nome` para o formato do psycopg2, **sem tocar em
  literais** (a máscara `'%H:%M:%S'` não pode virar parâmetro);
- `INSERT OR IGNORE` e `INSERT OR REPLACE` para `ON CONFLICT`;
- `AUTOINCREMENT` para `SERIAL`, `REAL` para `DOUBLE PRECISION`;
- `PRAGMA table_info` para consulta ao catálogo padrão.

Também corrige um vazamento que o SQLite perdoava: agora o `with` **fecha** a
conexão. Contra um Postgres remoto, não fechar consumiria o limite de conexões
do projeto.

**Um bug real de portabilidade foi encontrado e corrigido.** A listagem de
chamadas ACI paginava pelo `rowid`, coluna implícita que só existe no SQLite —
no Postgres a consulta falha. Passou a usar chave composta `(created_at,
call_id)`, portável e determinística. Esse defeito só apareceu porque a suíte
foi executada contra um Postgres de verdade.

---

## Como isto foi verificado

- **258 testes passam nos dois bancos.** A suíte inteira roda contra SQLite e
  contra PostgreSQL 15 com o mesmo resultado — é a prova de paridade.
- **Migração testada ponta a ponta**: SQLite populado (com acentos, aspas e
  ponto-e-vírgula dentro de texto) para Postgres limpo, conferida por checksum.
- **Escrita pós-migração testada**: cliente novo criado e interação gravada sem
  colisão de sequência — a falha clássica de quem copia ids sem realinhar o
  `nextval`.
- **Login testado após a migração**: os hashes de senha sobrevivem.
- O verificador distingue `NULL` de string vazia. Sem isso, uma migração que
  trocasse um pelo outro passaria despercebida.

### Limite desta verificação

Tudo acima foi validado contra um **PostgreSQL 15 local**. Não foi possível
testar contra a sua instância Supabase a partir deste ambiente — a saída de rede
aqui bloqueia protocolo de banco. As diferenças esperadas são de conectividade
(TLS, pooler, IPv6), não de dialeto SQL. Faça o passo 2 (ensaio) antes do 3.

---

## Depois da migração

Duas coisas passam a ser possíveis e valem a pena:

1. **Backup com restauração a ponto no tempo** — já incluso no plano Pro, mas
   confirme que está ativo no painel da Supabase.
2. **Isolamento por organização** — a camada já suporta schema separado via
   `CRM_PG_SCHEMA`, que é a base para multi-tenant (pendência estrutural nº 3).
   Hoje isso é usado para isolar cada teste da suíte.
