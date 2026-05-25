"""SQLite backend for the Mr.Holmes CRM app."""

from __future__ import annotations

import hmac
import hashlib
import json
import os
import secrets
import sqlite3
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import pandas as pd


BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.getenv("CRM_DATA_DIR", os.path.join(BASE_DIR, "Data"))
DB_PATH = os.getenv("CRM_DB_PATH", os.path.join(DATA_DIR, "crm.sqlite3"))

ACTIONS = [
    "customer.create",
    "customer.update",
    "customer.delete",
    "ticket.create",
    "ticket.update",
    "ticket.delete",
    "deal.create",
    "deal.update",
    "deal.delete",
    "campaign.create",
    "campaign.update",
    "campaign.delete",
    "channel.intake",
    "admin.view",
    "audit.view",
    "webhook.ingest",
    "rbac.manage",
    "aci.connect",
    "aci.tools.read",
    "aci.tools.execute",
    "aci.calls.read",
    "aci.policies.manage",
]

DEFAULT_ROLE_PERMISSIONS = {
    "admin": ACTIONS,
    "atendimento": [
        "customer.create",
        "customer.update",
        "ticket.create",
        "ticket.update",
        "channel.intake",
        "aci.tools.read",
        "aci.tools.execute",
    ],
    "vendas": ["customer.create", "customer.update", "deal.create", "deal.update", "aci.tools.read", "aci.tools.execute"],
    "marketing": ["campaign.create", "campaign.update", "aci.tools.read", "aci.tools.execute"],
}

ACI_TOOL_CATALOG: dict[str, dict[str, list[str]]] = {
    "google": {
        "google_calendar": ["create_event", "list_events"],
        "google_sheets": ["append_row", "read_sheet"],
    },
    "notion": {
        "notion_pages": ["create_page", "query_database"],
    },
    "slack": {
        "slack_messages": ["post_message", "list_channels"],
    },
}

ENTITY_CONFIG = {
    "customer": {"table": "customers", "pk": "customer_id"},
    "ticket": {"table": "tickets", "pk": "ticket_id"},
    "deal": {"table": "deals", "pk": "deal_id"},
    "campaign": {"table": "campaigns", "pk": "campaign"},
}


DEFAULT_USERS = [
    {
        "username": "admin",
        "full_name": "Helena Duarte",
        "role": "admin",
        "password_hash": "",
        "is_active": 1,
    },
    {
        "username": "atendimento",
        "full_name": "Amanda Souza",
        "role": "atendimento",
        "password_hash": "",
        "is_active": 1,
    },
    {
        "username": "vendas",
        "full_name": "Rafael Nogueira",
        "role": "vendas",
        "password_hash": "",
        "is_active": 1,
    },
    {
        "username": "marketing",
        "full_name": "Bianca Torres",
        "role": "marketing",
        "password_hash": "",
        "is_active": 1,
    },
    {
        "username": "cs",
        "full_name": "Camila Costa",
        "role": "atendimento",
        "password_hash": "",
        "is_active": 1,
    },
]


DEFAULT_CUSTOMERS = [
    {
        "customer_id": "C001",
        "name": "Grupo Aurora",
        "segment": "Varejo",
        "city": "Sao Paulo",
        "country": "Brasil",
        "owner": "Camila Costa",
        "status": "Ativo",
        "health_score": 89,
        "lifetime_value": 420000,
        "last_purchase": "2026-05-15",
        "channel": "WhatsApp",
        "next_action": "Renovar contrato premium em 7 dias",
        "source": "Customer Success",
    },
    {
        "customer_id": "C002",
        "name": "Northwind Labs",
        "segment": "SaaS",
        "city": "Austin",
        "country": "Estados Unidos",
        "owner": "Daniel Freitas",
        "status": "Expansao",
        "health_score": 76,
        "lifetime_value": 285000,
        "last_purchase": "2026-05-08",
        "channel": "Email",
        "next_action": "Apresentar add-on de automacao",
        "source": "Upsell",
    },
    {
        "customer_id": "C003",
        "name": "Clina Prime",
        "segment": "Saude",
        "city": "Rio de Janeiro",
        "country": "Brasil",
        "owner": "Bruna Melo",
        "status": "Risco",
        "health_score": 58,
        "lifetime_value": 167000,
        "last_purchase": "2026-04-22",
        "channel": "Telefone",
        "next_action": "Escalonar onboarding e revisar SLA",
        "source": "Onboarding",
    },
    {
        "customer_id": "C004",
        "name": "Pacific Trail Foods",
        "segment": "Food Service",
        "city": "Chicago",
        "country": "Estados Unidos",
        "owner": "Camila Costa",
        "status": "Ativo",
        "health_score": 92,
        "lifetime_value": 510000,
        "last_purchase": "2026-05-20",
        "channel": "Portal",
        "next_action": "Ofertar programa de fidelizacao B2B",
        "source": "Renovacao",
    },
    {
        "customer_id": "C005",
        "name": "Ecoplus Engenharia",
        "segment": "Industria",
        "city": "Curitiba",
        "country": "Brasil",
        "owner": "Rafael Nogueira",
        "status": "Novo",
        "health_score": 71,
        "lifetime_value": 94000,
        "last_purchase": "2026-05-12",
        "channel": "Campanha",
        "next_action": "Enviar proposta de implantacao",
        "source": "Inbound",
    },
]


DEFAULT_TICKETS = [
    {
        "ticket_id": "T-401",
        "customer_id": "C001",
        "subject": "Integracao de pedidos travando no fechamento",
        "channel": "WhatsApp",
        "status": "Em progresso",
        "priority": "Alta",
        "owner": "Amanda Souza",
        "sla_hours": 4,
        "age_hours": 2,
        "csat": 4.8,
        "category": "Integracao",
        "opened_at": "2026-05-25 08:30",
    },
    {
        "ticket_id": "T-402",
        "customer_id": "C003",
        "subject": "Treinamento do time de recepcao",
        "channel": "Email",
        "status": "Aguardando cliente",
        "priority": "Media",
        "owner": "Igor Lima",
        "sla_hours": 12,
        "age_hours": 10,
        "csat": 4.3,
        "category": "Onboarding",
        "opened_at": "2026-05-24 14:10",
    },
    {
        "ticket_id": "T-403",
        "customer_id": "C005",
        "subject": "Primeira configuracao do portal do cliente",
        "channel": "Telefone",
        "status": "Novo",
        "priority": "Alta",
        "owner": "Amanda Souza",
        "sla_hours": 8,
        "age_hours": 7,
        "csat": 0.0,
        "category": "Implantacao",
        "opened_at": "2026-05-25 09:50",
    },
    {
        "ticket_id": "T-404",
        "customer_id": "C002",
        "subject": "Solicitacao de dashboard compartilhado",
        "channel": "Portal",
        "status": "Resolvido",
        "priority": "Baixa",
        "owner": "Leandro Martins",
        "sla_hours": 24,
        "age_hours": 6,
        "csat": 4.9,
        "category": "Produto",
        "opened_at": "2026-05-23 11:40",
    },
    {
        "ticket_id": "T-405",
        "customer_id": "C004",
        "subject": "Ajuste em regras de roteamento",
        "channel": "Chat",
        "status": "Em progresso",
        "priority": "Critica",
        "owner": "Leandro Martins",
        "sla_hours": 2,
        "age_hours": 3,
        "csat": 4.1,
        "category": "Operacao",
        "opened_at": "2026-05-25 10:15",
    },
]


DEFAULT_DEALS = [
    {
        "deal_id": "D-201",
        "customer_id": "C005",
        "name": "Plano Growth + onboarding",
        "stage": "Proposta",
        "value": 68000,
        "probability": 65,
        "owner": "Rafael Nogueira",
        "close_date": "2026-05-31",
        "source": "Inbound",
    },
    {
        "deal_id": "D-202",
        "customer_id": "C003",
        "name": "Expansao de 20 licencas",
        "stage": "Negociacao",
        "value": 104000,
        "probability": 55,
        "owner": "Camila Costa",
        "close_date": "2026-06-04",
        "source": "Customer Success",
    },
    {
        "deal_id": "D-203",
        "customer_id": "C002",
        "name": "Modulo de marketing regional",
        "stage": "Descoberta",
        "value": 72000,
        "probability": 30,
        "owner": "Daniel Freitas",
        "close_date": "2026-06-12",
        "source": "Upsell",
    },
    {
        "deal_id": "D-204",
        "customer_id": "C004",
        "name": "Renovacao enterprise multi-site",
        "stage": "Fechado ganho",
        "value": 190000,
        "probability": 100,
        "owner": "Camila Costa",
        "close_date": "2026-05-19",
        "source": "Renovacao",
    },
]


DEFAULT_CAMPAIGNS = [
    {
        "campaign": "Reativacao carteira 60 dias",
        "channel": "Email",
        "leads": 48,
        "qualified": 19,
        "conversion_rate": 39.6,
        "revenue": 87000,
    },
    {
        "campaign": "WhatsApp pos-venda premium",
        "channel": "WhatsApp",
        "leads": 32,
        "qualified": 17,
        "conversion_rate": 53.1,
        "revenue": 123000,
    },
    {
        "campaign": "Webinar CX Brasil-US",
        "channel": "Eventos",
        "leads": 110,
        "qualified": 26,
        "conversion_rate": 23.6,
        "revenue": 54000,
    },
]


DEFAULT_TASKS = [
    {
        "task": "Revisar ticket T-405 com engenharia",
        "owner": "Leandro Martins",
        "due_date": "2026-05-25",
        "priority": "Critica",
        "entity": "T-405",
    },
    {
        "task": "Enviar proposta final para Ecoplus Engenharia",
        "owner": "Rafael Nogueira",
        "due_date": "2026-05-26",
        "priority": "Alta",
        "entity": "D-201",
    },
    {
        "task": "Agendar QBR com Grupo Aurora",
        "owner": "Camila Costa",
        "due_date": "2026-05-27",
        "priority": "Media",
        "entity": "C001",
    },
    {
        "task": "Publicar playbook de onboarding clinicas",
        "owner": "Bruna Melo",
        "due_date": "2026-05-29",
        "priority": "Media",
        "entity": "C003",
    },
]


DEFAULT_INTERACTIONS = [
    {
        "customer_id": "C001",
        "event_at": "2026-05-25 08:30",
        "event_type": "ticket",
        "title": "Ticket aberto",
        "body": "Cliente sinalizou falha no fechamento de pedidos via WhatsApp.",
        "channel": "WhatsApp",
        "owner": "Amanda Souza",
        "related_id": "T-401",
    },
    {
        "customer_id": "C001",
        "event_at": "2026-05-21 15:20",
        "event_type": "meeting",
        "title": "Reuniao executiva",
        "body": "Time aprovou expansao de mais 12 usuarios para operacao de atendimento.",
        "channel": "Meeting",
        "owner": "Camila Costa",
        "related_id": "",
    },
    {
        "customer_id": "C001",
        "event_at": "2026-05-15 10:00",
        "event_type": "purchase",
        "title": "Compra registrada",
        "body": "Renovacao anual do modulo service ops.",
        "channel": "CS",
        "owner": "Camila Costa",
        "related_id": "",
    },
    {
        "customer_id": "C002",
        "event_at": "2026-05-23 17:10",
        "event_type": "ticket",
        "title": "Ticket resolvido",
        "body": "Dashboard compartilhado liberado com permissao por equipe.",
        "channel": "Portal",
        "owner": "Leandro Martins",
        "related_id": "T-404",
    },
    {
        "customer_id": "C002",
        "event_at": "2026-05-12 09:00",
        "event_type": "campaign",
        "title": "Campanha",
        "body": "Cliente entrou na segmentacao de upsell do modulo de marketing.",
        "channel": "Email",
        "owner": "Bianca Torres",
        "related_id": "",
    },
    {
        "customer_id": "C003",
        "event_at": "2026-05-24 14:10",
        "event_type": "ticket",
        "title": "Ticket aguardando cliente",
        "body": "Time solicitou lista de usuarios para treinamento assistido.",
        "channel": "Email",
        "owner": "Igor Lima",
        "related_id": "T-402",
    },
    {
        "customer_id": "C003",
        "event_at": "2026-05-18 11:45",
        "event_type": "risk",
        "title": "Risco identificado",
        "body": "Queda de uso em 3 unidades e aumento do tempo de resposta.",
        "channel": "CS",
        "owner": "Bruna Melo",
        "related_id": "",
    },
    {
        "customer_id": "C004",
        "event_at": "2026-05-25 10:15",
        "event_type": "incident",
        "title": "Incidente critico",
        "body": "Regra de roteamento impactando fila premium.",
        "channel": "Chat",
        "owner": "Leandro Martins",
        "related_id": "T-405",
    },
    {
        "customer_id": "C004",
        "event_at": "2026-05-19 16:00",
        "event_type": "deal",
        "title": "Negocio ganho",
        "body": "Renovacao enterprise multi-site assinada.",
        "channel": "Sales",
        "owner": "Camila Costa",
        "related_id": "D-204",
    },
    {
        "customer_id": "C005",
        "event_at": "2026-05-25 09:50",
        "event_type": "ticket",
        "title": "Primeiro atendimento",
        "body": "Cliente iniciou onboarding do portal e solicitou apoio guiado.",
        "channel": "Telefone",
        "owner": "Amanda Souza",
        "related_id": "T-403",
    },
    {
        "customer_id": "C005",
        "event_at": "2026-05-12 13:30",
        "event_type": "lead",
        "title": "Lead convertido",
        "body": "Origem via campanha de performance industrial.",
        "channel": "Inbound",
        "owner": "Rafael Nogueira",
        "related_id": "D-201",
    },
]


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _seed_passwords() -> None:
    passwords = {
        "admin": "admin123",
        "atendimento": "atend123",
        "vendas": "vendas123",
        "marketing": "mkt123",
        "cs": "cs123",
    }
    for user in DEFAULT_USERS:
        user["password_hash"] = hash_password(passwords[user["username"]])


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS customers (
            customer_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            segment TEXT NOT NULL,
            city TEXT NOT NULL,
            country TEXT NOT NULL,
            owner TEXT NOT NULL,
            status TEXT NOT NULL,
            health_score INTEGER NOT NULL,
            lifetime_value REAL NOT NULL,
            last_purchase TEXT NOT NULL,
            channel TEXT NOT NULL,
            next_action TEXT NOT NULL,
            source TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tickets (
            ticket_id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            subject TEXT NOT NULL,
            channel TEXT NOT NULL,
            status TEXT NOT NULL,
            priority TEXT NOT NULL,
            owner TEXT NOT NULL,
            sla_hours INTEGER NOT NULL,
            age_hours INTEGER NOT NULL,
            csat REAL NOT NULL,
            category TEXT NOT NULL,
            opened_at TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        );

        CREATE TABLE IF NOT EXISTS deals (
            deal_id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            name TEXT NOT NULL,
            stage TEXT NOT NULL,
            value REAL NOT NULL,
            probability INTEGER NOT NULL,
            owner TEXT NOT NULL,
            close_date TEXT NOT NULL,
            source TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        );

        CREATE TABLE IF NOT EXISTS campaigns (
            campaign TEXT PRIMARY KEY,
            channel TEXT NOT NULL,
            leads INTEGER NOT NULL,
            qualified INTEGER NOT NULL,
            conversion_rate REAL NOT NULL,
            revenue REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tasks (
            task TEXT PRIMARY KEY,
            owner TEXT NOT NULL,
            due_date TEXT NOT NULL,
            priority TEXT NOT NULL,
            entity TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id TEXT NOT NULL,
            event_at TEXT NOT NULL,
            event_type TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            channel TEXT NOT NULL,
            owner TEXT NOT NULL,
            related_id TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        );

        CREATE TABLE IF NOT EXISTS role_permissions (
            role TEXT NOT NULL,
            action TEXT NOT NULL,
            PRIMARY KEY (role, action)
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_at TEXT NOT NULL,
            actor_username TEXT NOT NULL,
            actor_role TEXT NOT NULL,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            source TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS webhook_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            received_at TEXT NOT NULL,
            channel TEXT NOT NULL,
            event_type TEXT NOT NULL,
            status TEXT NOT NULL,
            source_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            note TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS refresh_tokens (
            token_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            client_fingerprint_hash TEXT,
            issued_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            revoked_at TEXT,
            replaced_by TEXT,
            FOREIGN KEY (username) REFERENCES users(username)
        );

        CREATE TABLE IF NOT EXISTS auth_throttle (
            subject TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            window_started_at TEXT NOT NULL,
            request_count INTEGER NOT NULL,
            fail_count INTEGER NOT NULL,
            locked_until TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (subject, endpoint)
        );

        CREATE TABLE IF NOT EXISTS aci_connections (
            connection_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            external_account_id TEXT,
            status TEXT NOT NULL,
            scopes_json TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(username)
        );

        CREATE TABLE IF NOT EXISTS aci_tool_calls (
            call_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            actor_username TEXT NOT NULL,
            provider TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            action_name TEXT NOT NULL,
            request_json TEXT NOT NULL,
            response_json TEXT NOT NULL,
            status TEXT NOT NULL,
            latency_ms INTEGER NOT NULL,
            error_code TEXT,
            error_message TEXT,
            correlation_id TEXT NOT NULL,
            idempotency_key TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(username)
        );
        """
    )
    connection.commit()


def _table_has_rows(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(f"SELECT COUNT(*) AS total FROM {table_name}").fetchone()
    return bool(row["total"])


def _seed_defaults(connection: sqlite3.Connection) -> None:
    if not _table_has_rows(connection, "users"):
        connection.executemany(
            """
            INSERT INTO users (username, full_name, role, password_hash, is_active)
            VALUES (:username, :full_name, :role, :password_hash, :is_active)
            """,
            DEFAULT_USERS,
        )

    if not _table_has_rows(connection, "customers"):
        connection.executemany(
            """
            INSERT INTO customers (
                customer_id, name, segment, city, country, owner, status,
                health_score, lifetime_value, last_purchase, channel, next_action, source
            ) VALUES (
                :customer_id, :name, :segment, :city, :country, :owner, :status,
                :health_score, :lifetime_value, :last_purchase, :channel, :next_action, :source
            )
            """,
            DEFAULT_CUSTOMERS,
        )

    if not _table_has_rows(connection, "tickets"):
        connection.executemany(
            """
            INSERT INTO tickets (
                ticket_id, customer_id, subject, channel, status, priority, owner,
                sla_hours, age_hours, csat, category, opened_at
            ) VALUES (
                :ticket_id, :customer_id, :subject, :channel, :status, :priority, :owner,
                :sla_hours, :age_hours, :csat, :category, :opened_at
            )
            """,
            DEFAULT_TICKETS,
        )

    if not _table_has_rows(connection, "deals"):
        connection.executemany(
            """
            INSERT INTO deals (
                deal_id, customer_id, name, stage, value, probability, owner, close_date, source
            ) VALUES (
                :deal_id, :customer_id, :name, :stage, :value, :probability, :owner, :close_date, :source
            )
            """,
            DEFAULT_DEALS,
        )

    if not _table_has_rows(connection, "campaigns"):
        connection.executemany(
            """
            INSERT INTO campaigns (campaign, channel, leads, qualified, conversion_rate, revenue)
            VALUES (:campaign, :channel, :leads, :qualified, :conversion_rate, :revenue)
            """,
            DEFAULT_CAMPAIGNS,
        )

    if not _table_has_rows(connection, "tasks"):
        connection.executemany(
            """
            INSERT INTO tasks (task, owner, due_date, priority, entity)
            VALUES (:task, :owner, :due_date, :priority, :entity)
            """,
            DEFAULT_TASKS,
        )

    if not _table_has_rows(connection, "interactions"):
        connection.executemany(
            """
            INSERT INTO interactions (
                customer_id, event_at, event_type, title, body, channel, owner, related_id
            ) VALUES (
                :customer_id, :event_at, :event_type, :title, :body, :channel, :owner, :related_id
            )
            """,
            DEFAULT_INTERACTIONS,
        )

    if not _table_has_rows(connection, "role_permissions"):
        role_rows: list[dict[str, str]] = []
        for role, actions in DEFAULT_ROLE_PERMISSIONS.items():
            for action in actions:
                role_rows.append({"role": role, "action": action})
        connection.executemany(
            """
            INSERT INTO role_permissions (role, action)
            VALUES (:role, :action)
            """,
            role_rows,
        )

    connection.commit()


def _migrate_role_permissions(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        "SELECT role, action FROM role_permissions"
    ).fetchall()
    current: dict[str, set[str]] = {}
    for row in rows:
        role = row["role"]
        action = row["action"]
        current.setdefault(role, set()).add(action)

    inserts: list[tuple[str, str]] = []

    admin_current = current.get("admin", set())
    for action in ACTIONS:
        if action not in admin_current:
            inserts.append(("admin", action))

    for role, defaults in DEFAULT_ROLE_PERMISSIONS.items():
        role_current = current.get(role, set())
        if not role_current:
            for action in defaults:
                inserts.append((role, action))

    if inserts:
        connection.executemany(
            "INSERT OR IGNORE INTO role_permissions (role, action) VALUES (?, ?)",
            inserts,
        )
        connection.commit()


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def _migrate_refresh_tokens_schema(connection: sqlite3.Connection) -> None:
    columns = _table_columns(connection, "refresh_tokens")
    if "client_fingerprint_hash" not in columns:
        connection.execute(
            "ALTER TABLE refresh_tokens ADD COLUMN client_fingerprint_hash TEXT"
        )
        connection.commit()


def _migrate_auth_throttle_schema(connection: sqlite3.Connection) -> None:
    columns = _table_columns(connection, "auth_throttle")
    if not columns:
        return
    if "fail_count" not in columns:
        connection.execute(
            "ALTER TABLE auth_throttle ADD COLUMN fail_count INTEGER NOT NULL DEFAULT 0"
        )
        connection.commit()
    if "locked_until" not in columns:
        connection.execute(
            "ALTER TABLE auth_throttle ADD COLUMN locked_until TEXT"
        )
        connection.commit()


def init_database() -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    _seed_passwords()
    with _connect() as connection:
        _create_schema(connection)
        _seed_defaults(connection)
        _migrate_role_permissions(connection)
        _migrate_refresh_tokens_schema(connection)
        _migrate_auth_throttle_schema(connection)
    return DB_PATH


def _next_code(connection: sqlite3.Connection, table_name: str, column_name: str, prefix: str) -> str:
    row = connection.execute(
        f"SELECT {column_name} AS code FROM {table_name} WHERE {column_name} LIKE ? ORDER BY {column_name} DESC LIMIT 1",
        (f"{prefix}%",),
    ).fetchone()
    if row is None or row["code"] is None:
        number = 1
    else:
        digits = "".join(char for char in row["code"] if char.isdigit())
        number = int(digits or "0") + 1
    return f"{prefix}{number:03d}"


def get_data() -> dict[str, Any]:
    with _connect() as connection:
        data = {
            "users": pd.read_sql_query(
                "SELECT username, full_name, role, is_active FROM users ORDER BY full_name",
                connection,
            ),
            "customers": pd.read_sql_query(
                "SELECT * FROM customers ORDER BY name",
                connection,
            ),
            "tickets": pd.read_sql_query(
                "SELECT * FROM tickets ORDER BY opened_at DESC",
                connection,
            ),
            "deals": pd.read_sql_query(
                "SELECT * FROM deals ORDER BY close_date ASC",
                connection,
            ),
            "campaigns": pd.read_sql_query(
                "SELECT * FROM campaigns ORDER BY revenue DESC",
                connection,
            ),
            "tasks": pd.read_sql_query(
                "SELECT * FROM tasks ORDER BY due_date ASC",
                connection,
            ),
            "interactions": pd.read_sql_query(
                "SELECT * FROM interactions ORDER BY event_at DESC, id DESC",
                connection,
            ),
            "audit_log": pd.read_sql_query(
                "SELECT * FROM audit_log ORDER BY event_at DESC, id DESC",
                connection,
            ),
            "role_permissions": pd.read_sql_query(
                "SELECT * FROM role_permissions ORDER BY role, action",
                connection,
            ),
            "webhook_events": pd.read_sql_query(
                "SELECT * FROM webhook_events ORDER BY received_at DESC, id DESC",
                connection,
            ),
        }
    return data


def get_user_by_username(username: str) -> dict[str, str] | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT username, full_name, role, is_active FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if row is None or not row["is_active"]:
        return None
    return {
        "username": row["username"],
        "full_name": row["full_name"],
        "role": row["role"],
    }


def get_permissions(role: str) -> set[str]:
    with _connect() as connection:
        rows = connection.execute(
            "SELECT action FROM role_permissions WHERE role = ?",
            (role,),
        ).fetchall()
    return {row["action"] for row in rows}


def has_permission(role: str, action: str) -> bool:
    return action in get_permissions(role)


def get_roles() -> list[str]:
    with _connect() as connection:
        rows = connection.execute("SELECT DISTINCT role FROM users ORDER BY role").fetchall()
    return [row["role"] for row in rows]


def get_actions() -> list[str]:
    return sorted(ACTIONS)


def get_rbac_matrix() -> dict[str, list[str]]:
    with _connect() as connection:
        rows = connection.execute(
            "SELECT role, action FROM role_permissions ORDER BY role, action"
        ).fetchall()
    matrix: dict[str, list[str]] = {}
    for row in rows:
        matrix.setdefault(row["role"], []).append(row["action"])
    return matrix


def get_api_jwt_secret() -> str:
    secret = os.getenv("CRM_API_JWT_SECRET", "")
    if secret:
        return secret
    secret_file = os.path.join(DATA_DIR, ".api_jwt_secret")
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(secret_file):
        with open(secret_file, "r", encoding="utf-8") as file:
            content = file.read().strip()
            if content:
                return content
    generated = secrets.token_urlsafe(48)
    with open(secret_file, "w", encoding="utf-8") as file:
        file.write(generated)
    return generated


def get_access_token_ttl_minutes() -> int:
    raw = os.getenv("CRM_ACCESS_TOKEN_TTL_MINUTES", "60").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 60
    return max(1, value)


def get_access_token_leeway_seconds() -> int:
    raw = os.getenv("CRM_ACCESS_TOKEN_LEEWAY_SECONDS", "30").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 30
    return max(0, value)


def get_auth_rate_limit_window_seconds() -> int:
    raw = os.getenv("CRM_AUTH_RATE_LIMIT_WINDOW_SECONDS", "60").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 60
    return max(1, value)


def get_auth_rate_limit_max_attempts() -> int:
    raw = os.getenv("CRM_AUTH_RATE_LIMIT_MAX_ATTEMPTS", "10").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 10
    return max(1, value)


def get_auth_lock_threshold() -> int:
    raw = os.getenv("CRM_AUTH_LOCK_THRESHOLD", "5").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 5
    return max(1, value)


def get_auth_lock_seconds() -> int:
    raw = os.getenv("CRM_AUTH_LOCK_SECONDS", "300").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 300
    return max(1, value)


def _hash_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_fingerprint(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _get_or_create_auth_throttle(connection: sqlite3.Connection, subject: str, endpoint: str) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT subject, endpoint, window_started_at, request_count, fail_count, locked_until, updated_at
        FROM auth_throttle
        WHERE subject = ? AND endpoint = ?
        """,
        (subject, endpoint),
    ).fetchone()
    if row is not None:
        return row
    now = _utcnow().isoformat()
    connection.execute(
        """
        INSERT INTO auth_throttle (subject, endpoint, window_started_at, request_count, fail_count, locked_until, updated_at)
        VALUES (?, ?, ?, 0, 0, NULL, ?)
        """,
        (subject, endpoint, now, now),
    )
    connection.commit()
    return connection.execute(
        """
        SELECT subject, endpoint, window_started_at, request_count, fail_count, locked_until, updated_at
        FROM auth_throttle
        WHERE subject = ? AND endpoint = ?
        """,
        (subject, endpoint),
    ).fetchone()


def consume_auth_attempt(subject: str, endpoint: str) -> None:
    now = _utcnow()
    window_seconds = get_auth_rate_limit_window_seconds()
    max_attempts = get_auth_rate_limit_max_attempts()
    with _connect() as connection:
        row = _get_or_create_auth_throttle(connection, subject, endpoint)
        window_started_at = _parse_iso_datetime(row["window_started_at"]) or now
        locked_until = _parse_iso_datetime(row["locked_until"])
        request_count = int(row["request_count"])
        fail_count = int(row["fail_count"])

        if locked_until and now < locked_until:
            raise ValueError("Authentication temporarily locked. Try again later.")

        if (now - window_started_at).total_seconds() >= window_seconds:
            window_started_at = now
            request_count = 0
            fail_count = 0
            locked_until = None

        request_count += 1
        connection.execute(
            """
            UPDATE auth_throttle
            SET window_started_at = ?, request_count = ?, fail_count = ?, locked_until = ?, updated_at = ?
            WHERE subject = ? AND endpoint = ?
            """,
            (
                window_started_at.isoformat(),
                request_count,
                fail_count,
                locked_until.isoformat() if locked_until else None,
                now.isoformat(),
                subject,
                endpoint,
            ),
        )
        connection.commit()

    if request_count > max_attempts:
        raise ValueError("Rate limit exceeded for authentication endpoint")


def register_auth_failure(subject: str, endpoint: str) -> None:
    now = _utcnow()
    lock_threshold = get_auth_lock_threshold()
    lock_seconds = get_auth_lock_seconds()
    with _connect() as connection:
        row = _get_or_create_auth_throttle(connection, subject, endpoint)
        fail_count = int(row["fail_count"]) + 1
        locked_until = _parse_iso_datetime(row["locked_until"])
        if fail_count >= lock_threshold:
            locked_until = now + timedelta(seconds=lock_seconds)
        connection.execute(
            """
            UPDATE auth_throttle
            SET fail_count = ?, locked_until = ?, updated_at = ?
            WHERE subject = ? AND endpoint = ?
            """,
            (
                fail_count,
                locked_until.isoformat() if locked_until else None,
                now.isoformat(),
                subject,
                endpoint,
            ),
        )
        connection.commit()


def register_auth_success(subject: str, endpoint: str) -> None:
    now = _utcnow().isoformat()
    with _connect() as connection:
        connection.execute(
            """
            UPDATE auth_throttle
            SET fail_count = 0, locked_until = NULL, updated_at = ?
            WHERE subject = ? AND endpoint = ?
            """,
            (now, subject, endpoint),
        )
        connection.commit()


def get_auth_throttle_snapshot(limit: int = 200) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 1000))
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT subject, endpoint, window_started_at, request_count, fail_count, locked_until, updated_at
            FROM auth_throttle
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_auth_throttle_page(
    limit: int = 200,
    cursor_updated_at: str | None = None,
    cursor_subject: str | None = None,
    cursor_endpoint: str | None = None,
    subject_prefix: str | None = None,
    endpoint_filter: str | None = None,
    sort_by: str = "updated_at",
    sort_order: str = "desc",
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 1000))
    subject_prefix_value = (subject_prefix or "").strip()
    endpoint_filter_value = (endpoint_filter or "").strip()

    where_parts: list[str] = []
    params: list[Any] = []

    if subject_prefix_value:
        where_parts.append("subject LIKE ?")
        params.append(f"{subject_prefix_value}%")
    if endpoint_filter_value:
        where_parts.append("endpoint = ?")
        params.append(endpoint_filter_value)

    safe_sort_by = sort_by if sort_by in {"updated_at", "fail_count", "request_count"} else "updated_at"
    safe_sort_order = "ASC" if str(sort_order).lower() == "asc" else "DESC"

    if safe_sort_by == "updated_at":
        order_clause = f"updated_at {safe_sort_order}, subject ASC, endpoint ASC"
    elif safe_sort_by == "fail_count":
        order_clause = f"fail_count {safe_sort_order}, request_count DESC, updated_at DESC, subject ASC, endpoint ASC"
    else:
        order_clause = f"request_count {safe_sort_order}, fail_count DESC, updated_at DESC, subject ASC, endpoint ASC"

    if (
        safe_sort_by == "updated_at"
        and safe_sort_order == "DESC"
        and cursor_updated_at
        and cursor_subject is not None
        and cursor_endpoint is not None
    ):
        where_parts.append(
            """
            (
                (updated_at < ?)
                OR (
                    updated_at = ?
                    AND (
                        subject > ?
                        OR (subject = ? AND endpoint > ?)
                    )
                )
            )
            """
        )
        params.extend(
            [
                cursor_updated_at,
                cursor_updated_at,
                cursor_subject,
                cursor_subject,
                cursor_endpoint,
            ]
        )

    where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    query = f"""
        SELECT subject, endpoint, window_started_at, request_count, fail_count, locked_until, updated_at
        FROM auth_throttle
        {where_clause}
        ORDER BY {order_clause}
        LIMIT ?
    """
    params.append(safe_limit)

    with _connect() as connection:
        rows = connection.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def clear_auth_throttle(subject: str | None = None, endpoint: str | None = None) -> int:
    subject_value = (subject or "").strip()
    endpoint_value = (endpoint or "").strip()
    with _connect() as connection:
        if subject_value and endpoint_value:
            result = connection.execute(
                "DELETE FROM auth_throttle WHERE subject = ? AND endpoint = ?",
                (subject_value, endpoint_value),
            )
        elif subject_value:
            result = connection.execute(
                "DELETE FROM auth_throttle WHERE subject = ?",
                (subject_value,),
            )
        elif endpoint_value:
            result = connection.execute(
                "DELETE FROM auth_throttle WHERE endpoint = ?",
                (endpoint_value,),
            )
        else:
            result = connection.execute("DELETE FROM auth_throttle")
        connection.commit()
    return int(result.rowcount or 0)


def unlock_auth_throttle(subject_prefix: str, endpoint: str | None = None) -> int:
    prefix = (subject_prefix or "").strip()
    endpoint_value = (endpoint or "").strip()
    if not prefix:
        return 0
    now = _utcnow().isoformat()
    with _connect() as connection:
        if endpoint_value:
            result = connection.execute(
                """
                UPDATE auth_throttle
                SET fail_count = 0, locked_until = NULL, updated_at = ?
                WHERE subject LIKE ? AND endpoint = ?
                """,
                (now, f"{prefix}%", endpoint_value),
            )
        else:
            result = connection.execute(
                """
                UPDATE auth_throttle
                SET fail_count = 0, locked_until = NULL, updated_at = ?
                WHERE subject LIKE ?
                """,
                (now, f"{prefix}%"),
            )
        connection.commit()
    return int(result.rowcount or 0)


def get_auth_throttle_metrics(
    subject_prefix: str | None = None,
    endpoint_filter: str | None = None,
) -> dict[str, Any]:
    now = _utcnow()
    subject_prefix_value = (subject_prefix or "").strip()
    endpoint_filter_value = (endpoint_filter or "").strip()

    where_parts: list[str] = []
    params: list[Any] = []
    if subject_prefix_value:
        where_parts.append("subject LIKE ?")
        params.append(f"{subject_prefix_value}%")
    if endpoint_filter_value:
        where_parts.append("endpoint = ?")
        params.append(endpoint_filter_value)
    where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

    with _connect() as connection:
        total_row = connection.execute(
            f"SELECT COUNT(*) AS total FROM auth_throttle {where_clause}",
            params,
        ).fetchone()
        rows = connection.execute(
            f"""
            SELECT subject, endpoint, fail_count, locked_until, request_count, updated_at
            FROM auth_throttle
            {where_clause}
            ORDER BY fail_count DESC, request_count DESC, updated_at DESC
            LIMIT 10
            """,
            params,
        ).fetchall()

    active_locks = 0
    top_subjects: list[dict[str, Any]] = []
    for row in rows:
        locked_until = _parse_iso_datetime(row["locked_until"])
        if locked_until and locked_until > now:
            active_locks += 1
        top_subjects.append(
            {
                "subject": row["subject"],
                "endpoint": row["endpoint"],
                "fail_count": int(row["fail_count"]),
                "request_count": int(row["request_count"]),
                "locked_until": row["locked_until"],
                "updated_at": row["updated_at"],
            }
        )

    return {
        "total_rows": int(total_row["total"] if total_row else 0),
        "active_locks_in_top10": active_locks,
        "top_subjects": top_subjects,
    }


def _issue_refresh_token_record(
    username: str,
    client_fingerprint: str | None,
    expires_days: int = 14,
) -> tuple[str, str]:
    refresh_token = secrets.token_urlsafe(48)
    token_hash = _hash_token(refresh_token)
    client_fingerprint_hash = _hash_fingerprint(client_fingerprint)
    issued_at = _utcnow()
    expires_at = issued_at + timedelta(days=max(1, expires_days))
    token_id = f"rt_{secrets.token_hex(12)}"
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO refresh_tokens (
                token_id, username, token_hash, client_fingerprint_hash,
                issued_at, expires_at, revoked_at, replaced_by
            )
            VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)
            """,
            (
                token_id,
                username,
                token_hash,
                client_fingerprint_hash,
                issued_at.isoformat(),
                expires_at.isoformat(),
            ),
        )
        connection.commit()
    return token_id, refresh_token


def create_refresh_token(
    actor: dict[str, str],
    client_fingerprint: str | None,
    expires_days: int = 14,
) -> str:
    token_id, refresh_token = _issue_refresh_token_record(
        actor["username"],
        client_fingerprint=client_fingerprint,
        expires_days=expires_days,
    )
    log_audit_event(
        actor,
        "auth.token.issue",
        "refresh_token",
        token_id,
        {
            "username": actor["username"],
            "expires_days": max(1, expires_days),
            "has_client_fingerprint": bool(client_fingerprint),
        },
        "api-auth",
    )
    return refresh_token


def create_access_token(actor: dict[str, str], expires_minutes: int | None = None) -> str:
    now = datetime.now(timezone.utc)
    ttl_minutes = expires_minutes if expires_minutes is not None else get_access_token_ttl_minutes()
    scopes = sorted(get_permissions(actor["role"]))
    payload = {
        "sub": actor["username"],
        "role": actor["role"],
        "full_name": actor.get("full_name", ""),
        "scopes": scopes,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=max(1, ttl_minutes))).timestamp()),
    }
    token = jwt.encode(payload, get_api_jwt_secret(), algorithm="HS256")
    return str(token)


def verify_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            get_api_jwt_secret(),
            algorithms=["HS256"],
            leeway=get_access_token_leeway_seconds(),
        )
    except jwt.InvalidTokenError as exc:
        raise ValueError("Invalid or expired token") from exc
    required_fields = ["sub", "role", "exp", "scopes"]
    for field in required_fields:
        if field not in payload:
            raise ValueError("Token missing required claims")
    if not isinstance(payload.get("scopes"), list):
        raise ValueError("Token scopes must be a list")
    return payload


def rotate_refresh_token(
    refresh_token: str,
    expected_username: str | None = None,
    client_fingerprint: str | None = None,
    expires_days: int = 14,
) -> dict[str, Any]:
    token_hash = _hash_token(refresh_token)
    client_fingerprint_hash = _hash_fingerprint(client_fingerprint)
    now = _utcnow()
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT token_id, username, issued_at, expires_at, revoked_at, replaced_by, client_fingerprint_hash
            FROM refresh_tokens
            WHERE token_hash = ?
            """,
            (token_hash,),
        ).fetchone()
        if row is None:
            raise ValueError("Invalid refresh token")
        if row["revoked_at"]:
            raise ValueError("Refresh token already revoked")
        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at <= now:
            raise ValueError("Refresh token expired")
        if expected_username and row["username"] != expected_username:
            raise ValueError("Refresh token does not belong to actor")
        if row["client_fingerprint_hash"]:
            if not client_fingerprint_hash:
                raise ValueError("Client fingerprint is required for this refresh token")
            if row["client_fingerprint_hash"] != client_fingerprint_hash:
                raise ValueError("Refresh token fingerprint mismatch")
        actor = get_user_by_username(row["username"])
        if actor is None:
            raise ValueError("Refresh token user is inactive or missing")

        new_token_id, new_refresh_token = _issue_refresh_token_record(
            actor["username"],
            client_fingerprint=client_fingerprint,
            expires_days=expires_days,
        )
        connection.execute(
            """
            UPDATE refresh_tokens
            SET revoked_at = ?, replaced_by = ?
            WHERE token_id = ?
            """,
            (now.isoformat(), new_token_id, row["token_id"]),
        )
        connection.commit()

    log_audit_event(
        actor,
        "auth.token.refresh",
        "refresh_token",
        str(row["token_id"]),
        {
            "replaced_by": new_token_id,
            "username": actor["username"],
            "fingerprint_bound": bool(client_fingerprint),
        },
        "api-auth",
    )
    return {
        "actor": actor,
        "refresh_token": new_refresh_token,
        "token_id": new_token_id,
    }


def revoke_refresh_token(
    refresh_token: str,
    actor: dict[str, str] | None = None,
    client_fingerprint: str | None = None,
) -> bool:
    token_hash = _hash_token(refresh_token)
    client_fingerprint_hash = _hash_fingerprint(client_fingerprint)
    now = _utcnow()
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT token_id, username, revoked_at, client_fingerprint_hash
            FROM refresh_tokens
            WHERE token_hash = ?
            """,
            (token_hash,),
        ).fetchone()
        if row is None:
            return False
        if row["client_fingerprint_hash"]:
            if not client_fingerprint_hash:
                return False
            if row["client_fingerprint_hash"] != client_fingerprint_hash:
                return False
        if row["revoked_at"]:
            return True
        connection.execute(
            "UPDATE refresh_tokens SET revoked_at = ? WHERE token_id = ?",
            (now.isoformat(), row["token_id"]),
        )
        connection.commit()

    effective_actor = actor or get_user_by_username(row["username"])
    log_audit_event(
        effective_actor,
        "auth.token.revoke",
        "refresh_token",
        str(row["token_id"]),
        {"username": row["username"]},
        "api-auth",
    )
    return True


def revoke_all_refresh_tokens_for_user(username: str, actor: dict[str, str] | None = None) -> int:
    now = _utcnow().isoformat()
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT token_id
            FROM refresh_tokens
            WHERE username = ? AND revoked_at IS NULL
            """,
            (username,),
        ).fetchall()
        token_ids = [row["token_id"] for row in rows]
        if token_ids:
            connection.execute(
                """
                UPDATE refresh_tokens
                SET revoked_at = ?
                WHERE username = ? AND revoked_at IS NULL
                """,
                (now, username),
            )
            connection.commit()

    if token_ids:
        log_audit_event(
            actor,
            "auth.token.revoke_all",
            "refresh_token",
            username,
            {
                "username": username,
                "revoked_count": len(token_ids),
                "token_ids": token_ids,
            },
            "api-auth",
        )
    return len(token_ids)


def _resolve_actor(actor: dict[str, str] | None) -> dict[str, str]:
    default_actor = {
        "username": "system",
        "full_name": "System",
        "role": "admin",
    }
    if actor is None:
        return default_actor
    resolved = {
        "username": actor.get("username", "system"),
        "full_name": actor.get("full_name", "System"),
        "role": actor.get("role", "admin"),
    }
    return resolved


def _ensure_permission(actor: dict[str, str] | None, action: str) -> dict[str, str]:
    resolved_actor = _resolve_actor(actor)
    if resolved_actor["username"] == "system":
        return resolved_actor
    if not has_permission(resolved_actor["role"], action):
        raise PermissionError(f"Usuario sem permissao para acao: {action}")
    return resolved_actor


def _safe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    safe = dict(payload)
    for key in ["password", "password_hash", "token", "signature", "secret"]:
        if key in safe:
            safe[key] = "***"
    return safe


def log_audit_event(
    actor: dict[str, str] | None,
    action: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any],
    source: str,
) -> None:
    resolved_actor = _resolve_actor(actor)
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO audit_log (
                event_at, actor_username, actor_role, action,
                entity_type, entity_id, source, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                resolved_actor["username"],
                resolved_actor["role"],
                action,
                entity_type,
                entity_id,
                source,
                json.dumps(_safe_payload(payload), ensure_ascii=True),
            ),
        )
        connection.commit()


def log_webhook_event(
    channel: str,
    event_type: str,
    status: str,
    source_id: str,
    payload: dict[str, Any],
    note: str,
) -> None:
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO webhook_events (
                received_at, channel, event_type, status, source_id, payload_json, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                channel,
                event_type,
                status,
                source_id,
                json.dumps(payload, ensure_ascii=True),
                note,
            ),
        )
        connection.commit()


def get_timeline(interactions_df: pd.DataFrame) -> dict[str, list[tuple[str, str, str]]]:
    grouped: dict[str, list[tuple[str, str, str]]] = {}
    if interactions_df.empty:
        return grouped
    for customer_id, group in interactions_df.groupby("customer_id"):
        grouped[customer_id] = [
            (row["event_at"], row["title"], row["body"])
            for _, row in group.sort_values("event_at", ascending=False).iterrows()
        ]
    return grouped


def verify_login(username: str, password: str) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT username, full_name, role, is_active, password_hash FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if row is None or not row["is_active"]:
        return None
    if row["password_hash"] != hash_password(password):
        return None
    return {
        "username": row["username"],
        "full_name": row["full_name"],
        "role": row["role"],
    }


def get_role_sections(role: str) -> list[str]:
    mapping = {
        "admin": [
            "Visao Executiva",
            "Atendimento",
            "Canais",
            "Clientes 360",
            "Pipeline",
            "Marketing",
            "Benchmark",
            "Admin",
        ],
        "atendimento": ["Visao Executiva", "Atendimento", "Canais", "Clientes 360", "Benchmark"],
        "vendas": ["Visao Executiva", "Clientes 360", "Pipeline", "Benchmark"],
        "marketing": ["Visao Executiva", "Clientes 360", "Marketing", "Benchmark"],
    }
    return mapping.get(role, ["Visao Executiva"])


def add_interaction(
    customer_id: str,
    title: str,
    body: str,
    channel: str,
    owner: str,
    related_id: str = "",
    event_type: str = "note",
) -> None:
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO interactions (customer_id, event_at, event_type, title, body, channel, owner, related_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                customer_id,
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                event_type,
                title,
                body,
                channel,
                owner,
                related_id,
            ),
        )
        connection.commit()


def _get_entity_row(connection: sqlite3.Connection, entity_type: str, entity_id: str) -> dict[str, Any] | None:
    config = ENTITY_CONFIG.get(entity_type)
    if not config:
        raise ValueError(f"Unsupported entity type: {entity_type}")
    table_name = config["table"]
    pk = config["pk"]
    row = connection.execute(
        f"SELECT * FROM {table_name} WHERE {pk} = ?",
        (entity_id,),
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def update_entity(
    entity_type: str,
    entity_id: str,
    updates: dict[str, Any],
    actor: dict[str, str] | None,
    source: str = "api",
) -> dict[str, Any]:
    action = f"{entity_type}.update"
    resolved_actor = _ensure_permission(actor, action)
    config = ENTITY_CONFIG.get(entity_type)
    if config is None:
        raise ValueError(f"Unsupported entity type: {entity_type}")
    table_name = config["table"]
    pk = config["pk"]

    disallowed = {pk}
    normalized = {key: value for key, value in updates.items() if key not in disallowed}
    if not normalized:
        raise ValueError("No valid fields to update")

    with _connect() as connection:
        before = _get_entity_row(connection, entity_type, entity_id)
        if before is None:
            raise ValueError(f"{entity_type} {entity_id} not found")
        valid_columns = set(before.keys()) - {pk}
        filtered_updates = {key: value for key, value in normalized.items() if key in valid_columns}
        if not filtered_updates:
            raise ValueError("No valid columns in update payload")
        set_clause = ", ".join([f"{key} = ?" for key in filtered_updates.keys()])
        values = list(filtered_updates.values()) + [entity_id]
        connection.execute(
            f"UPDATE {table_name} SET {set_clause} WHERE {pk} = ?",
            values,
        )
        connection.commit()
        after = _get_entity_row(connection, entity_type, entity_id)

    log_audit_event(
        resolved_actor,
        action,
        entity_type,
        entity_id,
        {
            "before": before,
            "after": after,
            "changed_fields": list(filtered_updates.keys()),
        },
        source,
    )
    return after or {}


def delete_entity(
    entity_type: str,
    entity_id: str,
    actor: dict[str, str] | None,
    source: str = "api",
) -> dict[str, Any]:
    action = f"{entity_type}.delete"
    resolved_actor = _ensure_permission(actor, action)
    config = ENTITY_CONFIG.get(entity_type)
    if config is None:
        raise ValueError(f"Unsupported entity type: {entity_type}")
    table_name = config["table"]
    pk = config["pk"]

    with _connect() as connection:
        before = _get_entity_row(connection, entity_type, entity_id)
        if before is None:
            raise ValueError(f"{entity_type} {entity_id} not found")
        connection.execute(
            f"DELETE FROM {table_name} WHERE {pk} = ?",
            (entity_id,),
        )
        connection.commit()

    log_audit_event(
        resolved_actor,
        action,
        entity_type,
        entity_id,
        {
            "before": before,
            "after": None,
            "changed_fields": list(before.keys()),
        },
        source,
    )
    return before


def update_role_permissions(role: str, actions: list[str], actor: dict[str, str] | None, source: str = "admin-ui") -> None:
    resolved_actor = _ensure_permission(actor, "rbac.manage")
    wanted = sorted({action for action in actions if action in ACTIONS})
    with _connect() as connection:
        current_rows = connection.execute(
            "SELECT action FROM role_permissions WHERE role = ?",
            (role,),
        ).fetchall()
        before = sorted([row["action"] for row in current_rows])
        connection.execute("DELETE FROM role_permissions WHERE role = ?", (role,))
        connection.executemany(
            "INSERT INTO role_permissions (role, action) VALUES (?, ?)",
            [(role, action) for action in wanted],
        )
        connection.commit()

    log_audit_event(
        resolved_actor,
        "rbac.manage",
        "role",
        role,
        {
            "before": before,
            "after": wanted,
            "changed_fields": ["role_permissions"],
        },
        source,
    )


def add_customer(payload: dict[str, Any], actor: dict[str, str] | None = None, source: str = "ui") -> str:
    resolved_actor = _ensure_permission(actor, "customer.create")
    with _connect() as connection:
        customer_id = _next_code(connection, "customers", "customer_id", "C")
        connection.execute(
            """
            INSERT INTO customers (
                customer_id, name, segment, city, country, owner, status,
                health_score, lifetime_value, last_purchase, channel, next_action, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                customer_id,
                payload["name"],
                payload["segment"],
                payload["city"],
                payload["country"],
                payload["owner"],
                payload.get("status", "Novo"),
                int(payload.get("health_score", 70)),
                float(payload.get("lifetime_value", 0)),
                payload.get("last_purchase", datetime.now().strftime("%Y-%m-%d")),
                payload.get("channel", "Formulario"),
                payload.get("next_action", "Qualificar e registrar a proxima acao"),
                payload.get("source", "Manual"),
            ),
        )
        connection.commit()
    add_interaction(
        customer_id,
        "Conta criada",
        f"Conta criada via {payload.get('source', 'Manual')}.",
        payload.get("channel", "Formulario"),
        resolved_actor["full_name"],
        related_id=customer_id,
        event_type="account",
    )
    log_audit_event(
        resolved_actor,
        "customer.create",
        "customer",
        customer_id,
        {
            "name": payload["name"],
            "segment": payload["segment"],
            "country": payload["country"],
            "owner": payload["owner"],
        },
        source,
    )
    return customer_id


def add_ticket(payload: dict[str, Any], actor: dict[str, str] | None = None, source: str = "ui") -> str:
    resolved_actor = _ensure_permission(actor, "ticket.create")
    with _connect() as connection:
        ticket_id = _next_code(connection, "tickets", "ticket_id", "T-")
        connection.execute(
            """
            INSERT INTO tickets (
                ticket_id, customer_id, subject, channel, status, priority, owner,
                sla_hours, age_hours, csat, category, opened_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticket_id,
                payload["customer_id"],
                payload["subject"],
                payload["channel"],
                payload.get("status", "Novo"),
                payload["priority"],
                payload["owner"],
                int(payload.get("sla_hours", 8)),
                int(payload.get("age_hours", 0)),
                float(payload.get("csat", 0.0)),
                payload.get("category", "Geral"),
                payload.get("opened_at", datetime.now().strftime("%Y-%m-%d %H:%M")),
            ),
        )
        connection.commit()
    add_interaction(
        payload["customer_id"],
        "Ticket criado",
        payload.get("message", payload["subject"]),
        payload["channel"],
        resolved_actor["full_name"],
        related_id=ticket_id,
        event_type="ticket",
    )
    log_audit_event(
        resolved_actor,
        "ticket.create",
        "ticket",
        ticket_id,
        {
            "customer_id": payload["customer_id"],
            "subject": payload["subject"],
            "priority": payload["priority"],
            "channel": payload["channel"],
        },
        source,
    )
    return ticket_id


def add_deal(payload: dict[str, Any], actor: dict[str, str] | None = None, source: str = "ui") -> str:
    resolved_actor = _ensure_permission(actor, "deal.create")
    with _connect() as connection:
        deal_id = _next_code(connection, "deals", "deal_id", "D-")
        connection.execute(
            """
            INSERT INTO deals (
                deal_id, customer_id, name, stage, value, probability, owner, close_date, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                deal_id,
                payload["customer_id"],
                payload["name"],
                payload["stage"],
                float(payload["value"]),
                int(payload["probability"]),
                payload["owner"],
                payload["close_date"],
                payload["source"],
            ),
        )
        connection.commit()
    add_interaction(
        payload["customer_id"],
        "Oportunidade criada",
        f"Nova oportunidade em {payload['stage']} no valor de R$ {float(payload['value']):,.0f}.",
        "Sales",
        resolved_actor["full_name"],
        related_id=deal_id,
        event_type="deal",
    )
    log_audit_event(
        resolved_actor,
        "deal.create",
        "deal",
        deal_id,
        {
            "customer_id": payload["customer_id"],
            "name": payload["name"],
            "stage": payload["stage"],
            "value": float(payload["value"]),
        },
        source,
    )
    return deal_id


def add_campaign(payload: dict[str, Any], actor: dict[str, str] | None = None, source: str = "ui") -> str:
    resolved_actor = _ensure_permission(actor, "campaign.create")
    campaign_name = payload["campaign"].strip()
    with _connect() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO campaigns (campaign, channel, leads, qualified, conversion_rate, revenue)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                campaign_name,
                payload["channel"],
                int(payload["leads"]),
                int(payload["qualified"]),
                float(payload["conversion_rate"]),
                float(payload["revenue"]),
            ),
        )
        connection.commit()
    log_audit_event(
        resolved_actor,
        "campaign.create",
        "campaign",
        campaign_name,
        {
            "channel": payload["channel"],
            "leads": int(payload["leads"]),
            "qualified": int(payload["qualified"]),
            "conversion_rate": float(payload["conversion_rate"]),
            "revenue": float(payload["revenue"]),
        },
        source,
    )
    return campaign_name


def create_channel_ticket(
    payload: dict[str, Any],
    actor: dict[str, str] | None = None,
    source: str = "channel-intake",
) -> tuple[str, str]:
    resolved_actor = _ensure_permission(actor, "channel.intake")
    customer_id = payload.get("customer_id", "")
    if not customer_id:
        customer_id = add_customer(
            {
                "name": payload["customer_name"],
                "segment": payload.get("segment", "Novo lead"),
                "city": payload.get("city", "Nao informado"),
                "country": payload.get("country", "Brasil"),
                "owner": payload["owner"],
                "status": "Novo",
                "health_score": 70,
                "lifetime_value": 0,
                "last_purchase": datetime.now().strftime("%Y-%m-%d"),
                "channel": payload["channel"],
                "next_action": payload.get("next_action", "Responder entrada de canal e qualificar conta"),
                "source": payload["channel"],
            },
            actor=resolved_actor,
            source=source,
        )
    ticket_id = add_ticket(
        {
            "customer_id": customer_id,
            "subject": payload["subject"],
            "channel": payload["channel"],
            "priority": payload["priority"],
            "owner": payload["owner"],
            "sla_hours": payload["sla_hours"],
            "category": payload["category"],
            "message": payload["message"],
        },
        actor=resolved_actor,
        source=source,
    )
    return customer_id, ticket_id


def get_webhook_verify_token() -> str:
    token = os.getenv("CRM_WHATSAPP_VERIFY_TOKEN", "")
    if token:
        return token
    secret_file = os.path.join(DATA_DIR, ".webhook_token")
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(secret_file):
        with open(secret_file, "r", encoding="utf-8") as file:
            content = file.read().strip()
            if content:
                return content
    generated = secrets.token_urlsafe(24)
    with open(secret_file, "w", encoding="utf-8") as file:
        file.write(generated)
    return generated


def get_webhook_hmac_secret() -> str:
    secret = os.getenv("CRM_WHATSAPP_HMAC_SECRET", "")
    if secret:
        return secret
    secret_file = os.path.join(DATA_DIR, ".webhook_hmac_secret")
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(secret_file):
        with open(secret_file, "r", encoding="utf-8") as file:
            content = file.read().strip()
            if content:
                return content
    generated = secrets.token_urlsafe(48)
    with open(secret_file, "w", encoding="utf-8") as file:
        file.write(generated)
    return generated


def verify_webhook_hmac(raw_body: bytes, signature_header: str | None) -> bool:
    if not signature_header:
        return False
    value = signature_header.strip()
    if value.startswith("sha256="):
        value = value.split("=", 1)[1]
    expected = hmac.new(
        key=get_webhook_hmac_secret().encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, value)


def process_whatsapp_webhook(payload: dict[str, Any], source: str = "whatsapp-webhook") -> dict[str, str]:
    actor = {"username": "system", "full_name": "Webhook Bot", "role": "admin"}
    message_obj = payload.get("message", {})
    source_id = str(message_obj.get("id", "")) or str(payload.get("id", "unknown"))
    customer_name = str(message_obj.get("customer_name", "")).strip() or str(message_obj.get("from", "Lead WhatsApp")).strip()
    subject = str(message_obj.get("subject", "Atendimento WhatsApp"))
    body = str(message_obj.get("text", "")).strip() or str(payload)
    owner = str(message_obj.get("owner", "Amanda Souza"))
    priority = str(message_obj.get("priority", "Media"))
    country = str(message_obj.get("country", "Brasil"))
    city = str(message_obj.get("city", "Nao informado"))

    try:
        customer_id, ticket_id = create_channel_ticket(
            {
                "customer_name": customer_name,
                "subject": subject,
                "channel": "WhatsApp",
                "priority": priority,
                "owner": owner,
                "sla_hours": 4,
                "category": "Relacionamento",
                "message": body,
                "city": city,
                "country": country,
                "segment": "Lead inbound",
                "customer_id": str(message_obj.get("customer_id", "")),
            },
            actor=actor,
            source=source,
        )
        log_webhook_event(
            "WhatsApp",
            "message",
            "processed",
            source_id,
            payload,
            f"ticket={ticket_id}; customer={customer_id}",
        )
        return {
            "status": "processed",
            "customer_id": customer_id,
            "ticket_id": ticket_id,
        }
    except Exception as exc:
        log_webhook_event(
            "WhatsApp",
            "message",
            "error",
            source_id,
            payload,
            str(exc),
        )
        raise


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def start_aci_connection(
    provider: str,
    tenant_id: str,
    redirect_uri: str,
    actor: dict[str, str] | None,
    source: str = "api-aci-connect-start",
) -> dict[str, Any]:
    resolved_actor = _ensure_permission(actor, "aci.connect")
    provider_key = provider.strip().lower()
    if provider_key not in ACI_TOOL_CATALOG:
        raise ValueError("Unsupported provider")
    connection_id = f"conn_{uuid.uuid4().hex[:16]}"
    now = _now_iso()
    state = secrets.token_urlsafe(24)
    scopes = ["tools.read", "tools.execute"]
    auth_base = os.getenv("CRM_ACI_AUTH_BASE_URL", "https://aci.dev/oauth/authorize")
    authorization_url = (
        f"{auth_base}?provider={provider_key}&state={state}&connection_id={connection_id}"
        f"&redirect_uri={redirect_uri}"
    )

    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO aci_connections (
                connection_id, tenant_id, user_id, provider, external_account_id, status,
                scopes_json, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                connection_id,
                tenant_id,
                resolved_actor["username"],
                provider_key,
                "",
                "pending",
                json.dumps(scopes, ensure_ascii=True),
                json.dumps({"redirect_uri": redirect_uri, "state": state}, ensure_ascii=True),
                now,
                now,
            ),
        )
        connection.commit()

    log_audit_event(
        resolved_actor,
        "aci.connect",
        "aci_connection",
        connection_id,
        {
            "provider": provider_key,
            "tenant_id": tenant_id,
            "status": "pending",
        },
        source,
    )
    return {
        "connection_id": connection_id,
        "authorization_url": authorization_url,
        "status": "pending",
    }


def complete_aci_connection(
    connection_id: str,
    code: str,
    state: str,
    actor: dict[str, str] | None,
    source: str = "api-aci-connect-callback",
) -> dict[str, Any]:
    resolved_actor = _ensure_permission(actor, "aci.connect")
    if not code.strip() or not state.strip():
        raise ValueError("code and state are required")

    now = _now_iso()
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM aci_connections WHERE connection_id = ?",
            (connection_id,),
        ).fetchone()
        if row is None:
            raise ValueError("connection not found")
        if row["user_id"] != resolved_actor["username"] and resolved_actor["role"] != "admin":
            raise PermissionError("connection does not belong to actor")

        metadata = json.loads(row["metadata_json"] or "{}")
        expected_state = str(metadata.get("state", ""))
        if expected_state and expected_state != state:
            raise ValueError("state mismatch")

        external_account_id = f"{row['provider']}_{resolved_actor['username']}"
        updated_metadata = dict(metadata)
        updated_metadata["oauth_code_preview"] = code[:6] + "..."
        updated_metadata["verified_at"] = now

        connection.execute(
            """
            UPDATE aci_connections
            SET status = ?, external_account_id = ?, metadata_json = ?, updated_at = ?
            WHERE connection_id = ?
            """,
            (
                "active",
                external_account_id,
                json.dumps(updated_metadata, ensure_ascii=True),
                now,
                connection_id,
            ),
        )
        connection.commit()

    log_audit_event(
        resolved_actor,
        "aci.connect",
        "aci_connection",
        connection_id,
        {
            "status": "active",
            "external_account_id": external_account_id,
        },
        source,
    )
    return {
        "connection_id": connection_id,
        "status": "active",
        "external_account_id": external_account_id,
    }


def list_aci_tools(provider: str | None, actor: dict[str, str] | None) -> list[dict[str, Any]]:
    _ensure_permission(actor, "aci.tools.read")
    providers = [provider.strip().lower()] if provider else sorted(ACI_TOOL_CATALOG.keys())
    rows: list[dict[str, Any]] = []
    for provider_key in providers:
        tools = ACI_TOOL_CATALOG.get(provider_key)
        if not tools:
            continue
        for tool_name, actions in tools.items():
            rows.append(
                {
                    "provider": provider_key,
                    "tool_name": tool_name,
                    "actions": actions,
                    "requires_approval": False,
                }
            )
    return rows


def _find_active_connection(connection: sqlite3.Connection, tenant_id: str, user_id: str, provider: str) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT *
        FROM aci_connections
        WHERE tenant_id = ? AND user_id = ? AND provider = ? AND status = 'active'
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (tenant_id, user_id, provider),
    ).fetchone()


def execute_aci_tool_call(
    tenant_id: str,
    provider: str,
    tool_name: str,
    action_name: str,
    input_payload: dict[str, Any],
    actor: dict[str, str] | None,
    idempotency_key: str | None = None,
    source: str = "api-aci-tool-call",
) -> dict[str, Any]:
    resolved_actor = _ensure_permission(actor, "aci.tools.execute")
    provider_key = provider.strip().lower()
    correlation_id = f"corr_{uuid.uuid4().hex[:16]}"
    request_payload = {
        "tenant_id": tenant_id,
        "provider": provider_key,
        "tool_name": tool_name,
        "action_name": action_name,
        "input": input_payload,
    }

    started = time.perf_counter()
    now = _now_iso()
    with _connect() as connection:
        if idempotency_key:
            previous = connection.execute(
                """
                SELECT * FROM aci_tool_calls
                WHERE user_id = ? AND idempotency_key = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (resolved_actor["username"], idempotency_key),
            ).fetchone()
            if previous:
                return {
                    "call_id": previous["call_id"],
                    "status": previous["status"],
                    "output": json.loads(previous["response_json"] or "{}"),
                    "latency_ms": int(previous["latency_ms"]),
                    "correlation_id": previous["correlation_id"],
                    "idempotent_replay": True,
                }

        active_connection = _find_active_connection(connection, tenant_id, resolved_actor["username"], provider_key)
        status = "success"
        error_code = ""
        error_message = ""
        response_payload: dict[str, Any]

        provider_tools = ACI_TOOL_CATALOG.get(provider_key, {})
        allowed_actions = provider_tools.get(tool_name, [])
        if active_connection is None:
            status = "failed"
            error_code = "connection_not_active"
            error_message = "No active connection for provider"
            response_payload = {}
        elif action_name not in allowed_actions:
            status = "failed"
            error_code = "unsupported_action"
            error_message = "Tool action is not available for provider"
            response_payload = {}
        else:
            response_payload = {
                "provider": provider_key,
                "tool_name": tool_name,
                "action_name": action_name,
                "executed": True,
                "result": "ok",
                "echo": input_payload,
            }

        latency_ms = int((time.perf_counter() - started) * 1000)
        call_id = f"call_{uuid.uuid4().hex[:16]}"
        connection.execute(
            """
            INSERT INTO aci_tool_calls (
                call_id, tenant_id, user_id, actor_username, provider, tool_name, action_name,
                request_json, response_json, status, latency_ms, error_code, error_message,
                correlation_id, idempotency_key, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                call_id,
                tenant_id,
                resolved_actor["username"],
                resolved_actor["username"],
                provider_key,
                tool_name,
                action_name,
                json.dumps(request_payload, ensure_ascii=True),
                json.dumps(response_payload, ensure_ascii=True),
                status,
                latency_ms,
                error_code or None,
                error_message or None,
                correlation_id,
                idempotency_key,
                now,
            ),
        )
        connection.commit()

    log_audit_event(
        resolved_actor,
        "aci.tools.execute",
        "aci_tool_call",
        call_id,
        {
            "provider": provider_key,
            "tool_name": tool_name,
            "action_name": action_name,
            "status": status,
            "error_code": error_code,
            "correlation_id": correlation_id,
        },
        source,
    )
    return {
        "call_id": call_id,
        "status": status,
        "output": response_payload,
        "latency_ms": latency_ms,
        "error_code": error_code or None,
        "error_message": error_message or None,
        "correlation_id": correlation_id,
        "idempotent_replay": False,
    }


def get_aci_tool_calls(
    actor: dict[str, str] | None,
    limit: int = 50,
    cursor: str | None = None,
    status_filter: str | None = None,
    tool_name: str | None = None,
) -> dict[str, Any]:
    _ensure_permission(actor, "aci.calls.read")
    resolved_limit = max(1, min(limit, 200))
    last_id = int(cursor) if cursor and cursor.isdigit() else None
    where = []
    params: list[Any] = []

    if last_id is not None:
        where.append("rowid < ?")
        params.append(last_id)
    if status_filter:
        where.append("status = ?")
        params.append(status_filter.strip().lower())
    if tool_name:
        where.append("tool_name = ?")
        params.append(tool_name.strip())

    where_clause = f"WHERE {' AND '.join(where)}" if where else ""
    query = f"""
        SELECT rowid AS _rowid, call_id, tenant_id, user_id, provider, tool_name, action_name,
               status, latency_ms, error_code, error_message, correlation_id, created_at
        FROM aci_tool_calls
        {where_clause}
        ORDER BY rowid DESC
        LIMIT ?
    """
    params.append(resolved_limit)

    with _connect() as connection:
        rows = connection.execute(query, tuple(params)).fetchall()

    items = [dict(row) for row in rows]
    next_cursor = str(items[-1]["_rowid"]) if items else None
    for item in items:
        item.pop("_rowid", None)
    return {
        "rows": items,
        "next_cursor": next_cursor,
    }
