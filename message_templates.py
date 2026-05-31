"""Message templates with variable substitution."""
from __future__ import annotations
from datetime import datetime
from typing import Any
from crm_backend import _connect, log_audit_event

DEFAULTS = [
    ("welcome_whatsapp","WhatsApp","Onboarding","Boas-vindas WhatsApp",
     "Ola {{customer_name}}, aqui e {{owner}}. Bem-vindo a bordo."),
    ("welcome_email","Email","Onboarding","Boas-vindas por Email",
     "Ola {{customer_name}},\n\nE um prazer ter voce com a gente.\n\n{{owner}}"),
    ("follow_up_d1","WhatsApp","Follow-up","Follow-up D+1",
     "Oi {{customer_name}}, tudo bem? Posso esclarecer algum ponto?"),
    ("follow_up_d3","Email","Follow-up","Follow-up D+3",
     "Ola {{customer_name}}, queria entender se a proposta faz sentido.\n\n{{owner}}"),
    ("follow_up_d7","Email","Follow-up","Follow-up D+7",
     "Oi {{customer_name}}, vou parar por aqui. Se mudar algo, e so chamar.\n\n{{owner}}"),
    ("ticket_received","WhatsApp","Atendimento","Ticket recebido",
     "Oi {{customer_name}}, recebemos #{{ticket_id}}. {{owner}} ja esta cuidando."),
    ("ticket_resolved","WhatsApp","Atendimento","Ticket resolvido",
     "Oi {{customer_name}}, #{{ticket_id}} foi resolvido. Da uma olhada."),
    ("renewal_reminder","Email","Retencao","Lembrete de renovacao",
     "Ola {{customer_name}}, contrato vence em breve. Vamos marcar 15min?\n\n{{owner}}"),
    ("csat_request","WhatsApp","Pesquisa","Pedido CSAT",
     "Oi {{customer_name}}, como foi #{{ticket_id}}? De 1 a 5?"),
    ("abandoned_cart","Email","Reativacao","Reativacao",
     "Ola {{customer_name}}, faz tempo. Tenho novidades. 10min?\n\n{{owner}}"),
]

def init_templates_schema() -> None:
    with _connect() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS message_templates (
            key TEXT PRIMARY KEY, channel TEXT NOT NULL, category TEXT NOT NULL,
            title TEXT NOT NULL, body TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        if not c.execute("SELECT COUNT(*) AS t FROM message_templates").fetchone()["t"]:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.executemany("INSERT INTO message_templates VALUES (?,?,?,?,?,1,?,?)",
                [(k,ch,cat,t,b,now,now) for k,ch,cat,t,b in DEFAULTS])
        c.commit()

def list_templates(channel=None, category=None) -> list:
    where, params = ["is_active=1"], []
    if channel: where.append("channel=?"); params.append(channel)
    if category: where.append("category=?"); params.append(category)
    with _connect() as c:
        rows = c.execute(f"SELECT * FROM message_templates WHERE {' AND '.join(where)} ORDER BY category, title", params).fetchall()
    return [dict(r) for r in rows]

def get_template(key: str) -> dict | None:
    with _connect() as c:
        row = c.execute("SELECT * FROM message_templates WHERE key=?", (key,)).fetchone()
    return dict(row) if row else None

def render_template(key: str, vars: dict) -> str:
    t = get_template(key)
    if t is None: raise ValueError(f"Template {key} not found")
    body = t["body"]
    for k, v in vars.items(): body = body.replace("{{"+k+"}}", str(v))
    return body

def save_template(key, channel, category, title, body, active=True, actor=None) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _connect() as c:
        c.execute("""INSERT INTO message_templates VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(key) DO UPDATE SET channel=excluded.channel, category=excluded.category,
            title=excluded.title, body=excluded.body, is_active=excluded.is_active,
            updated_at=excluded.updated_at""",
            (key, channel, category, title, body, 1 if active else 0, now, now))
        c.commit()
    if actor: log_audit_event(actor, "template.save", "template", key,
        {"channel": channel, "title": title}, "templates")

