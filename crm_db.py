"""Camada de banco: mesma interface para SQLite e PostgreSQL.

O CRM nasceu em SQLite num volume único — arranjo em que um incidente de disco
é perda de base. Este módulo permite mover a persistência para Postgres
gerenciado (Supabase) sem reescrever as 38 chamadas do backend: elas continuam
falando `with connect() as conn: conn.execute(sql, params)`.

O que o módulo resolve:

* **Placeholders.** SQLite usa ``?`` e ``:nome``; Postgres usa ``%s`` e
  ``%(nome)s``. A tradução respeita literais de string — ``'%H:%M'`` não pode
  virar placeholder.
* **Acesso por nome de coluna.** ``row["coluna"]`` funciona nos dois.
* **Dialeto de DDL.** ``AUTOINCREMENT``, ``INSERT OR IGNORE``,
  ``INSERT OR REPLACE`` e ``PRAGMA table_info`` ganham equivalente Postgres.
* **Ciclo de vida.** Em SQLite o ``with`` não fecha a conexão, o que é barato;
  contra um Postgres remoto vazaria conexão a cada requisição. Aqui o ``with``
  confirma em sucesso, desfaz em erro e **sempre fecha**.

Seleção do backend: se ``DATABASE_URL`` apontar para ``postgres://`` ou
``postgresql://``, usa Postgres; caso contrário, SQLite.
"""

from __future__ import annotations

import os
import re
import sqlite3
from typing import Any, Iterable, Sequence


# ---------------------------------------------------------------------------
# Seleção de backend
# ---------------------------------------------------------------------------

POSTGRES_SCHEMES = ("postgres://", "postgresql://", "postgresql+psycopg2://")


def database_url() -> str:
    """Valor efetivo de DATABASE_URL, tolerante aos erros clássicos de colagem.

    Em painéis de variável (Railway etc.) é comum o valor chegar com aspas,
    espaços, ou com o próprio prefixo "DATABASE_URL=" colado junto — quando a
    pessoa copia a linha inteira de um exemplo. Sem esta normalização, o app
    ignora a variável em silêncio e continua no SQLite, sem dar nenhuma pista.
    """
    value = os.getenv("DATABASE_URL", "").strip().strip('"').strip("'").strip()
    if value.upper().startswith("DATABASE_URL="):
        value = value.split("=", 1)[1].strip().strip('"').strip("'").strip()
    return value


def is_postgres() -> bool:
    """True quando a persistência configurada é Postgres."""
    return database_url().startswith(POSTGRES_SCHEMES)


def backend_name() -> str:
    return "postgres" if is_postgres() else "sqlite"


# ---------------------------------------------------------------------------
# Tradução de SQL
# ---------------------------------------------------------------------------

def _split_sql_literals(sql: str) -> list[tuple[str, bool]]:
    """Divide o SQL em trechos (texto, é_literal).

    Traduzir placeholders com regex simples corrompe literais: a máscara
    ``'%Y-%m-%d %H:%M'`` contém ``:`` e viraria parâmetro nomeado. Aqui os
    literais entre aspas são isolados e nunca tocados.
    """
    parts: list[tuple[str, bool]] = []
    buffer: list[str] = []
    index = 0
    length = len(sql)

    while index < length:
        char = sql[index]
        if char in ("'", '"'):
            if buffer:
                parts.append(("".join(buffer), False))
                buffer = []
            quote = char
            literal = [char]
            index += 1
            while index < length:
                literal.append(sql[index])
                # Aspas duplicadas ('' ou "") escapam a si mesmas.
                if sql[index] == quote:
                    if index + 1 < length and sql[index + 1] == quote:
                        literal.append(sql[index + 1])
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            parts.append(("".join(literal), True))
            continue
        buffer.append(char)
        index += 1

    if buffer:
        parts.append(("".join(buffer), False))
    return parts


_NAMED_PARAM = re.compile(r"(?<![:\w]):([a-zA-Z_]\w*)")


def translate_placeholders(sql: str) -> str:
    """Converte placeholders do estilo SQLite para o do psycopg2."""
    out: list[str] = []
    for chunk, is_literal in _split_sql_literals(sql):
        if is_literal:
            out.append(chunk)
            continue
        chunk = chunk.replace("?", "%s")
        chunk = _NAMED_PARAM.sub(r"%(\1)s", chunk)
        out.append(chunk)
    return "".join(out)


def translate_ddl(sql: str) -> str:
    """Traduz DDL e comandos específicos do SQLite para Postgres."""
    out: list[str] = []
    for chunk, is_literal in _split_sql_literals(sql):
        if is_literal:
            out.append(chunk)
            continue

        # Chave primária autoincremento.
        chunk = re.sub(
            r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b",
            "SERIAL PRIMARY KEY",
            chunk,
            flags=re.IGNORECASE,
        )
        # SQLite aceita REAL; o equivalente com precisão no Postgres é outro.
        chunk = re.sub(r"\bREAL\b", "DOUBLE PRECISION", chunk, flags=re.IGNORECASE)
        # SQLite não tem tipo booleano; INTEGER continua servindo, então fica.
        out.append(chunk)
    return "".join(out)


_INSERT_OR_IGNORE = re.compile(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", re.IGNORECASE)
_INSERT_OR_REPLACE = re.compile(r"\bINSERT\s+OR\s+REPLACE\s+INTO\b", re.IGNORECASE)
_PRAGMA_TABLE_INFO = re.compile(r"\bPRAGMA\s+table_info\s*\(\s*(\w+)\s*\)", re.IGNORECASE)


def translate_statement(sql: str, conflict_targets: dict[str, str] | None = None) -> str:
    """Traduz um comando completo para o dialeto Postgres.

    ``conflict_targets`` informa a coluna de conflito por tabela, necessária
    para converter ``INSERT OR REPLACE`` num ``ON CONFLICT ... DO UPDATE``.
    """
    conflict_targets = conflict_targets or CONFLICT_TARGETS

    # PRAGMA table_info -> catálogo padrão.
    pragma = _PRAGMA_TABLE_INFO.search(sql)
    if pragma:
        table = pragma.group(1)
        return (
            "SELECT column_name AS name FROM information_schema.columns "
            f"WHERE table_schema = current_schema() AND table_name = '{table}'"
        )

    if _INSERT_OR_IGNORE.search(sql):
        sql = _INSERT_OR_IGNORE.sub("INSERT INTO", sql)
        sql = _append_conflict_clause(sql, "DO NOTHING", conflict_targets)
    elif _INSERT_OR_REPLACE.search(sql):
        sql = _INSERT_OR_REPLACE.sub("INSERT INTO", sql)
        sql = _append_conflict_clause(sql, "DO UPDATE", conflict_targets)

    return translate_placeholders(translate_ddl(sql))


# Coluna de conflito por tabela, para converter os upserts do SQLite.
CONFLICT_TARGETS: dict[str, str] = {
    "campaigns": "campaign",
    "role_permissions": "role, action",
    "user_preferences": "username, pref_key",
    "customers": "customer_id",
    "tickets": "ticket_id",
    "deals": "deal_id",
    "tasks": "task",
    "users": "username",
    "meta_state": "key",
}


def _table_and_columns(sql: str) -> tuple[str, list[str]]:
    match = re.search(r"INSERT\s+INTO\s+(\w+)\s*\(([^)]*)\)", sql, re.IGNORECASE | re.DOTALL)
    if not match:
        return "", []
    table = match.group(1)
    columns = [c.strip() for c in match.group(2).split(",") if c.strip()]
    return table, columns


def _append_conflict_clause(sql: str, action: str, conflict_targets: dict[str, str]) -> str:
    table, columns = _table_and_columns(sql)
    target = conflict_targets.get(table)
    if not target:
        # Sem chave declarada não dá para inferir o conflito com segurança.
        raise ValueError(
            f"Tabela «{table}» não tem coluna de conflito registrada em CONFLICT_TARGETS."
        )

    if action == "DO NOTHING":
        return f"{sql.rstrip().rstrip(';')} ON CONFLICT ({target}) DO NOTHING"

    key_columns = {c.strip() for c in target.split(",")}
    updates = ", ".join(
        f"{col} = EXCLUDED.{col}" for col in columns if col not in key_columns
    )
    if not updates:
        return f"{sql.rstrip().rstrip(';')} ON CONFLICT ({target}) DO NOTHING"
    return f"{sql.rstrip().rstrip(';')} ON CONFLICT ({target}) DO UPDATE SET {updates}"


def split_script(script: str) -> list[str]:
    """Divide um script DDL em comandos, ignorando ';' dentro de literais."""
    statements: list[str] = []
    current: list[str] = []
    for chunk, is_literal in _split_sql_literals(script):
        if is_literal:
            current.append(chunk)
            continue
        start = 0
        for index, char in enumerate(chunk):
            if char == ";":
                current.append(chunk[start:index])
                statement = "".join(current).strip()
                if statement:
                    statements.append(statement)
                current = []
                start = index + 1
        current.append(chunk[start:])
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


# ---------------------------------------------------------------------------
# Conexão unificada
# ---------------------------------------------------------------------------

class _Result:
    """Resultado de execute() com a mesma superfície nos dois backends."""

    def __init__(self, cursor: Any, owns_cursor: bool = False) -> None:
        self._cursor = cursor
        self._owns_cursor = owns_cursor

    def fetchone(self) -> Any:
        return self._cursor.fetchone()

    def fetchall(self) -> list[Any]:
        return self._cursor.fetchall()

    @property
    def rowcount(self) -> int:
        return int(self._cursor.rowcount or 0)

    def __iter__(self):
        return iter(self._cursor)


class Connection:
    """Conexão que aceita a mesma chamada nos dois bancos.

    Mantém o contrato que o backend já usa: ``execute`` direto na conexão,
    linhas acessíveis por nome e ``with`` que confirma a transação.
    """

    def __init__(self, raw: Any, postgres: bool) -> None:
        self._raw = raw
        self._postgres = postgres

    # -- API usada pelo backend -------------------------------------------
    def execute(self, sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> _Result:
        if not self._postgres:
            return _Result(self._raw.execute(sql, params))
        cursor = self._raw.cursor()
        cursor.execute(translate_statement(sql), params or None)
        return _Result(cursor, owns_cursor=True)

    def executemany(self, sql: str, seq: Iterable[Any]) -> _Result:
        if not self._postgres:
            return _Result(self._raw.executemany(sql, seq))
        cursor = self._raw.cursor()
        cursor.executemany(translate_statement(sql), list(seq))
        return _Result(cursor, owns_cursor=True)

    def executescript(self, script: str) -> None:
        """Executa um script DDL inteiro."""
        if not self._postgres:
            self._raw.executescript(script)
            return
        cursor = self._raw.cursor()
        for statement in split_script(script):
            cursor.execute(translate_statement(statement))
        self._raw.commit()

    def cursor(self) -> Any:
        """Cursor cru — o pandas usa isto em ``read_sql_query``."""
        return self._raw.cursor()

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        self._raw.close()

    @property
    def raw(self) -> Any:
        return self._raw

    # -- Ciclo de vida -----------------------------------------------------
    def __enter__(self) -> "Connection":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            if exc_type is None:
                self._raw.commit()
            else:
                self._raw.rollback()
        finally:
            # Contra um Postgres remoto, não fechar aqui vaza conexão a cada
            # requisição — o SQLite perdoava isso, o Postgres não.
            self._raw.close()
        return False


def _connect_sqlite(path: str) -> Connection:
    raw = sqlite3.connect(path)
    raw.row_factory = sqlite3.Row
    return Connection(raw, postgres=False)


def pg_schema() -> str:
    """Schema Postgres a usar. Vazio significa o padrão (``public``).

    Serve para isolar ambientes dentro do mesmo banco — é como os testes
    ganham uma base limpa por caso, e é a base para separar organizações.
    """
    return os.getenv("CRM_PG_SCHEMA", "").strip()


def _connect_postgres(url: str) -> Connection:
    import psycopg2
    from psycopg2.extras import DictCursor

    # psycopg2 não entende o sufixo de driver do SQLAlchemy.
    clean = url.replace("postgresql+psycopg2://", "postgresql://")
    raw = psycopg2.connect(clean, cursor_factory=DictCursor)

    schema = pg_schema()
    if schema:
        if not schema.isidentifier():
            raise ValueError(f"Nome de schema inválido: {schema!r}")
        with raw.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            cursor.execute(f'SET search_path TO "{schema}"')
        raw.commit()

    return Connection(raw, postgres=True)


def connect(sqlite_path: str | None = None) -> Connection:
    """Abre conexão com o banco configurado."""
    if is_postgres():
        return _connect_postgres(database_url())
    if not sqlite_path:
        raise ValueError("Caminho do SQLite não informado e DATABASE_URL não é Postgres.")
    return _connect_sqlite(sqlite_path)
