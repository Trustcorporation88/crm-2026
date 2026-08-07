#!/usr/bin/env python3
"""Migra os dados do SQLite para o PostgreSQL (Supabase).

Uso típico:

    # 1. Ensaio: mostra o que seria copiado, sem escrever nada
    python migrate_to_postgres.py --sqlite Data/crm.sqlite3 \\
        --postgres "postgresql://...:5432/postgres" --dry-run

    # 2. Execução
    python migrate_to_postgres.py --sqlite Data/crm.sqlite3 \\
        --postgres "postgresql://...:5432/postgres"

    # 3. Só verificar uma migração já feita
    python migrate_to_postgres.py --sqlite Data/crm.sqlite3 \\
        --postgres "postgresql://..." --verify-only

Princípios:

* **Não destrutivo.** O SQLite é aberto somente para leitura. O script nunca
  apaga a origem; o rollback é simplesmente voltar a apontar a aplicação para
  o arquivo.
* **Ordem de dependência.** As tabelas são copiadas respeitando as chaves
  estrangeiras.
* **Verificação obrigatória.** Ao final compara contagem por tabela e um
  checksum do conteúdo. Migração "concluída" sem conferência é migração não
  verificada.
* **Repetível.** Linhas já presentes são ignoradas por conflito de chave, então
  reexecutar não duplica dados.

Use a **conexão direta** da Supabase (porta 5432) para rodar isto — o pooler em
modo transação não é adequado para carga em lote.
"""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
import sys
from typing import Any, Iterable

# Ordem que respeita as chaves estrangeiras: pais antes dos filhos.
# `cadences` precisa vir antes de `cadence_steps` — a ordem alfabética
# inverteria os dois.
TABLE_ORDER = [
    "users",
    "customers",
    "tickets",
    "deals",
    "campaigns",
    "tasks",
    "interactions",
    "role_permissions",
    "audit_log",
    "webhook_events",
    "refresh_tokens",
    "auth_throttle",
    "user_preferences",
    "aci_connections",
    "aci_tool_calls",
    "aci_policies",
    "cadences",
    "cadence_steps",
    "cadence_enrollments",
    "cadence_actions",
    "lead_scoring_rules",
    "lead_scores",
    "message_templates",
    "health_snapshots",
]

# Chave usada para ignorar duplicados em reexecução.
CONFLICT_KEYS = {
    "users": "username",
    "customers": "customer_id",
    "tickets": "ticket_id",
    "deals": "deal_id",
    "campaigns": "campaign",
    "tasks": "task",
    "role_permissions": "role, action",
    "user_preferences": "username, pref_key",
    "aci_tool_calls": "call_id",
}

BATCH_SIZE = 500


class MigrationError(RuntimeError):
    pass


def log(message: str) -> None:
    print(message, flush=True)


# ---------------------------------------------------------------------------
# Leitura da origem
# ---------------------------------------------------------------------------

def open_sqlite(path: str) -> sqlite3.Connection:
    """Abre o SQLite em modo somente leitura."""
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def sqlite_tables(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return sorted(row["name"] for row in rows)


def table_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return [row["name"] for row in rows]


def read_rows(connection: sqlite3.Connection, table: str, columns: list[str]) -> list[tuple]:
    column_list = ", ".join(f'"{c}"' for c in columns)
    cursor = connection.execute(f"SELECT {column_list} FROM {table}")
    return [tuple(row) for row in cursor.fetchall()]


# ---------------------------------------------------------------------------
# Checksum de conteúdo
# ---------------------------------------------------------------------------

# Marcador para NULL. Representar NULL como string vazia faria uma migração
# que trocasse um pelo outro passar na verificação — justamente o tipo de
# corrupção silenciosa que este checksum existe para pegar.
_NULL_SENTINEL = "\x00NULL\x00"


def checksum(rows: Iterable[tuple]) -> str:
    """Impressão digital do conteúdo, independente da ordem das linhas.

    Contagem igual não prova conteúdo igual — este checksum prova.
    """
    digests = sorted(
        hashlib.sha256(
            "\x1f".join(_NULL_SENTINEL if v is None else str(v) for v in row).encode("utf-8")
        ).hexdigest()
        for row in rows
    )
    return hashlib.sha256("".join(digests).encode("ascii")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Escrita no destino
# ---------------------------------------------------------------------------

def ensure_schema(postgres_url: str) -> None:
    """Cria o schema no destino usando o próprio backend da aplicação."""
    import os

    os.environ["DATABASE_URL"] = postgres_url
    # Import tardio: o backend lê DATABASE_URL na conexão.
    import crm_backend

    crm_backend.init_database()


def copy_table(pg_conn: Any, table: str, columns: list[str], rows: list[tuple]) -> int:
    if not rows:
        return 0

    from psycopg2.extras import execute_values

    column_list = ", ".join(f'"{c}"' for c in columns)
    conflict = CONFLICT_KEYS.get(table)
    suffix = f" ON CONFLICT ({conflict}) DO NOTHING" if conflict else ""

    inserted = 0
    with pg_conn.cursor() as cursor:
        for start in range(0, len(rows), BATCH_SIZE):
            batch = rows[start:start + BATCH_SIZE]
            execute_values(
                cursor,
                f'INSERT INTO "{table}" ({column_list}) VALUES %s{suffix}',
                batch,
            )
            inserted += len(batch)
    return inserted


def existing_tables(pg_conn: Any) -> set[str]:
    with pg_conn.cursor() as cursor:
        cursor.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = current_schema()"
        )
        return {row[0] for row in cursor.fetchall()}


def destination_row_count(pg_conn: Any, tables: Iterable[str]) -> int:
    present = existing_tables(pg_conn)
    total = 0
    with pg_conn.cursor() as cursor:
        for table in tables:
            if table not in present:
                continue
            cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
            total += int(cursor.fetchone()[0])
    return total


def truncate_all(pg_conn: Any, tables: Iterable[str]) -> None:
    """Esvazia o destino antes de copiar.

    A criação do schema semeia dados de exemplo (usuários e clientes padrão).
    Se sobrevivessem, ficariam misturados aos dados reais e ainda colidiriam
    com os ids da origem.
    """
    present = existing_tables(pg_conn)
    targets = [f'"{t}"' for t in tables if t in present]
    if not targets:
        return
    with pg_conn.cursor() as cursor:
        cursor.execute(f"TRUNCATE {', '.join(targets)} RESTART IDENTITY CASCADE")
    pg_conn.commit()


def resync_sequences(pg_conn: Any, tables: Iterable[str]) -> list[str]:
    """Realinha as sequências das colunas SERIAL após a cópia.

    Copiar ids explícitos não move a sequência: sem este passo o primeiro
    cadastro novo tentaria reutilizar o id 1 e falharia por chave duplicada.
    """
    resynced: list[str] = []
    present = existing_tables(pg_conn)
    with pg_conn.cursor() as cursor:
        for table in tables:
            if table not in present:
                continue
            cursor.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = current_schema() AND table_name = %s
                  AND column_default LIKE 'nextval%%'
                """,
                (table,),
            )
            for (column,) in cursor.fetchall():
                cursor.execute(
                    f"""
                    SELECT setval(
                        pg_get_serial_sequence('"{table}"', '{column}'),
                        COALESCE((SELECT MAX("{column}") FROM "{table}"), 0) + 1,
                        false
                    )
                    """
                )
                resynced.append(f"{table}.{column}")
    pg_conn.commit()
    return resynced


def count_postgres(pg_conn: Any, table: str) -> int:
    with pg_conn.cursor() as cursor:
        cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
        return int(cursor.fetchone()[0])


def read_postgres_rows(pg_conn: Any, table: str, columns: list[str]) -> list[tuple]:
    column_list = ", ".join(f'"{c}"' for c in columns)
    with pg_conn.cursor() as cursor:
        cursor.execute(f'SELECT {column_list} FROM "{table}"')
        return [tuple(row) for row in cursor.fetchall()]


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------

def migrate(
    sqlite_path: str,
    postgres_url: str,
    dry_run: bool = False,
    verify_only: bool = False,
    replace: bool = False,
) -> int:
    import psycopg2

    source = open_sqlite(sqlite_path)
    available = set(sqlite_tables(source))
    ordered = [t for t in TABLE_ORDER if t in available]
    extra = sorted(available - set(TABLE_ORDER))

    if extra:
        log(f"⚠️  Tabelas fora da ordem conhecida (serão copiadas por último): {', '.join(extra)}")
        ordered.extend(extra)

    log(f"Origem : {sqlite_path}  ({len(ordered)} tabelas)")
    log(f"Destino: {postgres_url.split('@')[-1]}")
    log("")

    plan: dict[str, tuple[list[str], list[tuple]]] = {}
    for table in ordered:
        columns = table_columns(source, table)
        rows = read_rows(source, table, columns)
        plan[table] = (columns, rows)
        log(f"  {table:<20} {len(rows):>6} linhas  checksum={checksum(rows)}")

    total = sum(len(rows) for _, rows in plan.values())
    log(f"\nTotal na origem: {total} linhas")

    if dry_run:
        log("\n[ensaio] Nada foi escrito. Remova --dry-run para executar.")
        return 0

    if not verify_only:
        # Antes de qualquer escrita: o destino já tem dados reais?
        guard = psycopg2.connect(postgres_url)
        try:
            preexisting = destination_row_count(guard, ordered)
        finally:
            guard.close()

        if preexisting and not replace:
            log(
                f"\n❌ O destino já contém {preexisting} linhas.\n"
                "   Rodar a migração agora sobrescreveria esses dados.\n"
                "   Se for mesmo isso que você quer, repita com --replace."
            )
            return 1

        log("\nCriando schema no destino…")
        ensure_schema(postgres_url)

    pg_conn = psycopg2.connect(postgres_url)
    try:
        if not verify_only:
            # A criação do schema semeia dados de exemplo; eles não podem
            # sobreviver a uma migração de dados reais.
            log("Limpando dados de exemplo do destino…")
            truncate_all(pg_conn, ordered)

            log("Copiando dados…")
            for table in ordered:
                columns, rows = plan[table]
                copied = copy_table(pg_conn, table, columns, rows)
                log(f"  {table:<20} {copied:>6} linhas enviadas")
            pg_conn.commit()

            resynced = resync_sequences(pg_conn, ordered)
            if resynced:
                log(f"Sequências realinhadas: {', '.join(resynced)}")

        # -------------------------------------------------------------
        # Verificação: contagem e checksum por tabela.
        # -------------------------------------------------------------
        log("\nVerificando…")
        problems: list[str] = []
        for table in ordered:
            columns, rows = plan[table]
            origem = len(rows)
            destino = count_postgres(pg_conn, table)

            if origem != destino:
                problems.append(f"{table}: origem {origem} linhas, destino {destino}")
                log(f"  ✗ {table:<20} {origem} → {destino}")
                continue

            origem_hash = checksum(rows)
            destino_hash = checksum(read_postgres_rows(pg_conn, table, columns))
            if origem_hash != destino_hash:
                problems.append(
                    f"{table}: checksum diferente ({origem_hash} ≠ {destino_hash})"
                )
                log(f"  ✗ {table:<20} conteúdo divergente")
                continue

            log(f"  ✓ {table:<20} {origem} linhas · checksum {origem_hash}")

        if problems:
            log("\n❌ VERIFICAÇÃO FALHOU:")
            for problem in problems:
                log(f"   - {problem}")
            log("\nNão aponte a aplicação para o Postgres enquanto isto não fechar.")
            return 1

        log(f"\n✅ Migração verificada: {total} linhas conferem em contagem e conteúdo.")
        log("   O SQLite de origem não foi alterado — o rollback é voltar a apontar para ele.")
        return 0
    finally:
        pg_conn.close()
        source.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Migra o CRM de SQLite para PostgreSQL.")
    parser.add_argument("--sqlite", required=True, help="Caminho do arquivo .sqlite3 de origem")
    parser.add_argument("--postgres", required=True, help="URL de conexão do Postgres de destino")
    parser.add_argument("--dry-run", action="store_true", help="Só mostra o plano, não escreve")
    parser.add_argument("--verify-only", action="store_true", help="Só confere uma migração já feita")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Autoriza sobrescrever um destino que já contém dados",
    )
    args = parser.parse_args()

    try:
        return migrate(args.sqlite, args.postgres, args.dry_run, args.verify_only, args.replace)
    except MigrationError as exc:
        log(f"❌ {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
