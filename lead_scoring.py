"""Lead scoring engine."""
from __future__ import annotations
import json, sqlite3
from datetime import datetime, timedelta
from typing import Any
from crm_backend import _connect, log_audit_event

DEFAULT_RULES = {
    "has_email": 5, "has_whatsapp": 8, "responded_recently": 15,
    "has_active_ticket": 12, "has_open_deal": 25, "high_lifetime_value": 20,
    "premium_segment": 10, "country_match": 5, "has_owner": 5, "recent_purchase": 15,
}
PREMIUM_SEGMENTS = {"SaaS", "Industria", "Saude", "Food Service", "Enterprise"}
PRIMARY_MARKETS = {"Brasil"}

def init_lead_scoring_schema() -> None:
    with _connect() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS lead_scores (
                customer_id TEXT PRIMARY KEY, score INTEGER NOT NULL,
                tier TEXT NOT NULL, signals_json TEXT NOT NULL, calculated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS lead_scoring_rules (
                rule_key TEXT PRIMARY KEY, points INTEGER NOT NULL,
                description TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 1);
        """)
        if not c.execute("SELECT COUNT(*) AS t FROM lead_scoring_rules").fetchone()["t"]:
            descs = {"has_email": "Email cadastrado", "has_whatsapp": "WhatsApp ativo",
                "responded_recently": "Interagiu em 7d", "has_active_ticket": "Ticket aberto",
                "has_open_deal": "Deal aberto", "high_lifetime_value": "LTV >= 100k",
                "premium_segment": "Segmento premium", "country_match": "Mercado primario",
                "has_owner": "Tem owner", "recent_purchase": "Compra em 90d"}
            c.executemany("INSERT INTO lead_scoring_rules VALUES (?, ?, ?, 1)",
                [(k, p, descs.get(k, "")) for k, p in DEFAULT_RULES.items()])
        c.commit()

def get_active_rules() -> dict[str, int]:
    with _connect() as c:
        rows = c.execute("SELECT rule_key, points FROM lead_scoring_rules WHERE is_active=1").fetchall()
    return {r["rule_key"]: int(r["points"]) for r in rows}

def _signals(c: sqlite3.Connection, cust: dict) -> dict[str, bool]:
    cid = cust["customer_id"]
    now = datetime.now()
    d7 = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M")
    d90 = (now - timedelta(days=90)).strftime("%Y-%m-%d")
    rec = c.execute("SELECT COUNT(*) AS t FROM interactions WHERE customer_id=? AND event_at>=?", (cid, d7)).fetchone()
    ot = c.execute("SELECT COUNT(*) AS t FROM tickets WHERE customer_id=? AND status NOT IN ('Resolvido','Fechado')", (cid,)).fetchone()
    od = c.execute("SELECT COUNT(*) AS t FROM deals WHERE customer_id=? AND stage NOT IN ('Fechado ganho','Perdido')", (cid,)).fetchone()
    return {
        "has_email": cust.get("channel") == "Email",
        "has_whatsapp": cust.get("channel") == "WhatsApp",
        "responded_recently": bool(rec["t"]),
        "has_active_ticket": bool(ot["t"]),
        "has_open_deal": bool(od["t"]),
        "high_lifetime_value": float(cust.get("lifetime_value", 0)) >= 100000,
        "premium_segment": cust.get("segment") in PREMIUM_SEGMENTS,
        "country_match": cust.get("country") in PRIMARY_MARKETS,
        "has_owner": bool(cust.get("owner")),
        "recent_purchase": str(cust.get("last_purchase", "")) >= d90,
    }

def _tier(score: int) -> str:
    if score >= 80: return "A"
    if score >= 60: return "B"
    if score >= 40: return "C"
    return "D"

def calculate_lead_score(cid: str) -> dict:
    rules = get_active_rules()
    with _connect() as c:
        row = c.execute("SELECT * FROM customers WHERE customer_id=?", (cid,)).fetchone()
        if row is None: raise ValueError(f"Customer {cid} not found")
        cust = dict(row)
        sigs = _signals(c, cust)
        score = min(100, max(0, sum(rules[k] for k, f in sigs.items() if f and k in rules)))
        tier = _tier(score)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""INSERT INTO lead_scores VALUES (?,?,?,?,?)
            ON CONFLICT(customer_id) DO UPDATE SET score=excluded.score, tier=excluded.tier,
            signals_json=excluded.signals_json, calculated_at=excluded.calculated_at""",
            (cid, score, tier, json.dumps(sigs), now))
        c.commit()
    return {"customer_id": cid, "score": score, "tier": tier, "signals": sigs, "calculated_at": now}

def recalculate_all_scores(actor=None) -> dict:
    with _connect() as c:
        rows = c.execute("SELECT customer_id FROM customers").fetchall()
    results = []
    for r in rows:
        try: results.append(calculate_lead_score(r["customer_id"]))
        except Exception: pass
    s = {"total": len(results),
        "tier_a": len([r for r in results if r["tier"] == "A"]),
        "tier_b": len([r for r in results if r["tier"] == "B"]),
        "tier_c": len([r for r in results if r["tier"] == "C"]),
        "tier_d": len([r for r in results if r["tier"] == "D"]),
        "avg_score": int(sum(r["score"] for r in results) / max(1, len(results)))}
    if actor: log_audit_event(actor, "lead_scoring.recalc", "lead_scores", "all", s, "lead-scoring")
    return s

def get_lead_scores(limit=100, tier_filter=None) -> list:
    where, params = "", []
    if tier_filter and tier_filter in {"A","B","C","D"}:
        where = "WHERE ls.tier = ?"
        params.append(tier_filter)
    params.append(max(1, min(limit, 1000)))
    with _connect() as c:
        rows = c.execute(f"""SELECT ls.customer_id, ls.score, ls.tier, ls.calculated_at,
            c.name, c.segment, c.country, c.owner, c.lifetime_value, c.channel, c.status
            FROM lead_scores ls JOIN customers c ON c.customer_id=ls.customer_id
            {where} ORDER BY ls.score DESC, c.name ASC LIMIT ?""", params).fetchall()
    return [dict(r) for r in rows]

def update_rule(key: str, pts: int, active: bool, actor=None) -> None:
    with _connect() as c:
        c.execute("UPDATE lead_scoring_rules SET points=?, is_active=? WHERE rule_key=?",
            (int(pts), 1 if active else 0, key))
        c.commit()
    if actor: log_audit_event(actor, "lead_scoring.rule", "rules", key,
        {"points": pts, "active": active}, "lead-scoring")
