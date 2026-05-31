"""Follow-up cadences."""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Any
from crm_backend import _connect, log_audit_event

DEFAULTS = [
    ("new_lead_outbound","Novo lead - 5 toques em 14d","Qualificar lead novo.",
     [(1,0,"WhatsApp","welcome_whatsapp"),(2,1,"Email","welcome_email"),
      (3,3,"WhatsApp","follow_up_d1"),(4,7,"Email","follow_up_d3"),(5,14,"Email","follow_up_d7")]),
    ("post_proposal","Pos-proposta - 3 toques","Acompanhamento pos-proposta.",
     [(1,1,"WhatsApp","follow_up_d1"),(2,3,"Email","follow_up_d3"),(3,7,"Email","follow_up_d7")]),
    ("client_onboarding","Onboarding cliente novo","Boas-vindas estruturadas.",
     [(1,0,"Email","welcome_email"),(2,1,"WhatsApp","welcome_whatsapp"),(3,7,"Email","csat_request")]),
    ("win_back","Reativacao inativo","Recupera cliente sem contato 60d+.",
     [(1,0,"Email","abandoned_cart"),(2,5,"WhatsApp","follow_up_d3"),(3,14,"Email","follow_up_d7")]),
]

def init_cadences_schema() -> None:
    with _connect() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS cadences (key TEXT PRIMARY KEY, title TEXT NOT NULL,
                description TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS cadence_steps (id INTEGER PRIMARY KEY AUTOINCREMENT,
                cadence_key TEXT NOT NULL, step_order INTEGER NOT NULL, delay_days INTEGER NOT NULL,
                channel TEXT NOT NULL, template_key TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS cadence_enrollments (id INTEGER PRIMARY KEY AUTOINCREMENT,
                cadence_key TEXT NOT NULL, customer_id TEXT NOT NULL, deal_id TEXT,
                current_step INTEGER NOT NULL DEFAULT 0, enrolled_at TEXT NOT NULL,
                next_action_at TEXT, completed_at TEXT, paused INTEGER NOT NULL DEFAULT 0,
                owner TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS cadence_actions (id INTEGER PRIMARY KEY AUTOINCREMENT,
                enrollment_id INTEGER NOT NULL, step_order INTEGER NOT NULL,
                channel TEXT NOT NULL, template_key TEXT NOT NULL,
                scheduled_at TEXT NOT NULL, executed_at TEXT, status TEXT NOT NULL DEFAULT 'pending');
        """)
        if not c.execute("SELECT COUNT(*) AS t FROM cadences").fetchone()["t"]:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for key, title, desc, steps in DEFAULTS:
                c.execute("INSERT INTO cadences VALUES (?,?,?,1,?)", (key, title, desc, now))
                for o, d, ch, tk in steps:
                    c.execute("INSERT INTO cadence_steps (cadence_key, step_order, delay_days, channel, template_key) VALUES (?,?,?,?,?)",
                        (key, o, d, ch, tk))
        c.commit()

def list_cadences() -> list:
    with _connect() as c:
        rows = c.execute("""SELECT c.key, c.title, c.description, c.is_active, c.created_at,
            COUNT(s.id) AS step_count FROM cadences c LEFT JOIN cadence_steps s ON s.cadence_key=c.key
            WHERE c.is_active=1 GROUP BY c.key ORDER BY c.title""").fetchall()
    return [dict(r) for r in rows]

def get_cadence_steps(key: str) -> list:
    with _connect() as c:
        rows = c.execute("SELECT * FROM cadence_steps WHERE cadence_key=? ORDER BY step_order", (key,)).fetchall()
    return [dict(r) for r in rows]

def enroll(key, cid, owner, deal_id=None, actor=None) -> int:
    now = datetime.now()
    nstr = now.strftime("%Y-%m-%d %H:%M:%S")
    steps = get_cadence_steps(key)
    if not steps: raise ValueError(f"Cadence {key} has no steps")
    with _connect() as c:
        cur = c.execute("""INSERT INTO cadence_enrollments
            (cadence_key, customer_id, deal_id, current_step, enrolled_at, next_action_at, owner)
            VALUES (?,?,?,0,?,?,?)""", (key, cid, deal_id, nstr, nstr, owner))
        eid = int(cur.lastrowid)
        for s in steps:
            sched = (now + timedelta(days=int(s["delay_days"]))).strftime("%Y-%m-%d %H:%M:%S")
            c.execute("""INSERT INTO cadence_actions
                (enrollment_id, step_order, channel, template_key, scheduled_at, status)
                VALUES (?,?,?,?,?,'pending')""",
                (eid, s["step_order"], s["channel"], s["template_key"], sched))
        c.commit()
    if actor: log_audit_event(actor, "cadence.enroll", "enrollment", str(eid),
        {"cadence_key": key, "customer_id": cid}, "cadences")
    return eid

def list_pending_actions(owner=None, limit=50) -> list:
    nstr = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    where, params = ["a.status='pending'", "a.scheduled_at<=?", "e.paused=0"], [nstr]
    if owner: where.append("e.owner=?"); params.append(owner)
    params.append(max(1, min(limit, 500)))
    with _connect() as c:
        rows = c.execute(f"""SELECT a.id, a.enrollment_id, a.step_order, a.channel, a.template_key,
            a.scheduled_at, a.status, e.cadence_key, e.customer_id, e.owner, e.deal_id,
            cust.name AS customer_name FROM cadence_actions a
            JOIN cadence_enrollments e ON e.id=a.enrollment_id
            JOIN customers cust ON cust.customer_id=e.customer_id
            WHERE {' AND '.join(where)} ORDER BY a.scheduled_at ASC LIMIT ?""", params).fetchall()
    return [dict(r) for r in rows]

def list_active_enrollments(owner=None) -> list:
    where, params = ["e.completed_at IS NULL"], []
    if owner: where.append("e.owner=?"); params.append(owner)
    with _connect() as c:
        rows = c.execute(f"""SELECT e.id, e.cadence_key, e.customer_id, e.deal_id, e.current_step,
            e.enrolled_at, e.next_action_at, e.paused, e.owner, c.name AS customer_name,
            cad.title AS cadence_title,
            (SELECT COUNT(*) FROM cadence_steps WHERE cadence_key=e.cadence_key) AS total_steps
            FROM cadence_enrollments e JOIN customers c ON c.customer_id=e.customer_id
            JOIN cadences cad ON cad.key=e.cadence_key
            WHERE {' AND '.join(where)} ORDER BY e.enrolled_at DESC""", params).fetchall()
    return [dict(r) for r in rows]

def mark_action_done(aid: int, actor=None) -> None:
    nstr = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _connect() as c:
        a = c.execute("SELECT * FROM cadence_actions WHERE id=?", (aid,)).fetchone()
        if a is None: raise ValueError(f"Action {aid} not found")
        c.execute("UPDATE cadence_actions SET executed_at=?, status='done' WHERE id=?", (nstr, aid))
        c.execute("UPDATE cadence_enrollments SET current_step=? WHERE id=?",
            (a["step_order"], a["enrollment_id"]))
        rem = c.execute("SELECT COUNT(*) AS t FROM cadence_actions WHERE enrollment_id=? AND status='pending'",
            (a["enrollment_id"],)).fetchone()
        if rem["t"] == 0:
            c.execute("UPDATE cadence_enrollments SET completed_at=? WHERE id=?", (nstr, a["enrollment_id"]))
        c.commit()
    if actor: log_audit_event(actor, "cadence.done", "action", str(aid), {}, "cadences")

def pause_enrollment(eid: int, actor=None) -> None:
    with _connect() as c:
        c.execute("UPDATE cadence_enrollments SET paused=1 WHERE id=?", (eid,))
        c.commit()
    if actor: log_audit_event(actor, "cadence.pause", "enrollment", str(eid), {}, "cadences")

def resume_enrollment(eid: int, actor=None) -> None:
    with _connect() as c:
        c.execute("UPDATE cadence_enrollments SET paused=0 WHERE id=?", (eid,))
        c.commit()
    if actor: log_audit_event(actor, "cadence.resume", "enrollment", str(eid), {}, "cadences")
