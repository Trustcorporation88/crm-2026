"""Customer health score."""
from __future__ import annotations
import json
from datetime import datetime, timedelta
from typing import Any
from crm_backend import _connect

POS = {"recent_interaction":20,"no_open_critical_ticket":15,"csat_above_4":15,
    "active_pipeline":10,"owner_assigned":5,"recent_purchase":15,
    "uses_premium_channel":10,"ltv_growing":10}
NEG = {"no_interaction_60_days":-25,"open_critical_ticket":-20,"csat_below_3":-20,
    "no_pipeline_no_purchase":-10,"no_owner":-5}

def init_health_schema() -> None:
    with _connect() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS health_snapshots (
            customer_id TEXT PRIMARY KEY, health_score INTEGER NOT NULL,
            churn_risk TEXT NOT NULL, positive_signals_json TEXT NOT NULL,
            negative_signals_json TEXT NOT NULL, next_best_action TEXT NOT NULL,
            calculated_at TEXT NOT NULL)""")
        c.commit()

def _signals(c, cust):
    cid = cust["customer_id"]
    now = datetime.now()
    d14 = (now-timedelta(days=14)).strftime("%Y-%m-%d %H:%M")
    d60 = (now-timedelta(days=60)).strftime("%Y-%m-%d %H:%M")
    d90 = (now-timedelta(days=90)).strftime("%Y-%m-%d")
    rec = c.execute("SELECT COUNT(*) AS t FROM interactions WHERE customer_id=? AND event_at>=?",(cid,d14)).fetchone()
    no60 = c.execute("SELECT COUNT(*) AS t FROM interactions WHERE customer_id=? AND event_at>=?",(cid,d60)).fetchone()
    crit = c.execute("""SELECT COUNT(*) AS t FROM tickets WHERE customer_id=?
        AND status NOT IN ('Resolvido','Fechado') AND priority IN ('Alta','Critica')""",(cid,)).fetchone()
    cs = c.execute("SELECT AVG(csat) AS a FROM tickets WHERE customer_id=? AND csat>0",(cid,)).fetchone()
    ac = cs["a"] or 0.0
    op = c.execute("SELECT COUNT(*) AS t FROM deals WHERE customer_id=? AND stage NOT IN ('Fechado ganho','Perdido')",(cid,)).fetchone()
    p = {"recent_interaction":bool(rec["t"]),"no_open_critical_ticket":not bool(crit["t"]),
        "csat_above_4":ac>=4.0,"active_pipeline":bool(op["t"]),
        "owner_assigned":bool(cust.get("owner")),
        "recent_purchase":str(cust.get("last_purchase",""))>=d90,
        "uses_premium_channel":cust.get("channel") in {"WhatsApp","Portal"},
        "ltv_growing":float(cust.get("lifetime_value",0))>=50000}
    n = {"no_interaction_60_days":not bool(no60["t"]),"open_critical_ticket":bool(crit["t"]),
        "csat_below_3":0<ac<3.0,
        "no_pipeline_no_purchase":not bool(op["t"]) and str(cust.get("last_purchase",""))<d90,
        "no_owner":not bool(cust.get("owner"))}
    return p, n

def _action(cust, p, n):
    if n.get("open_critical_ticket"): return "Resolver ticket critico aberto urgentemente"
    if n.get("no_interaction_60_days"): return "Reativar conta com cadencia win_back"
    if n.get("csat_below_3"): return "Agendar call de feedback"
    if n.get("no_owner"): return "Atribuir owner para esta conta"
    if p.get("active_pipeline") and p.get("recent_interaction"): return "Acelerar fechamento de oportunidade"
    if p.get("csat_above_4") and p.get("ltv_growing"): return "Explorar upsell ou cross-sell"
    if p.get("recent_purchase"): return "Check-in pos-venda e CSAT"
    return "Agendar contato de relacionamento"

def calculate_health(cid: str) -> dict:
    with _connect() as c:
        row = c.execute("SELECT * FROM customers WHERE customer_id=?",(cid,)).fetchone()
        if row is None: raise ValueError(f"Customer {cid} not found")
        cust = dict(row)
        p, n = _signals(c, cust)
        score = 50
        for k, f in p.items():
            if f and k in POS: score += POS[k]
        for k, f in n.items():
            if f and k in NEG: score += NEG[k]
        mx = 50 + sum(POS.values())
        norm = max(0, min(100, int((score/mx)*100) if mx else score))
        if norm >= 75: risk = "Baixo"
        elif norm >= 50: risk = "Medio"
        elif norm >= 30: risk = "Alto"
        else: risk = "Critico"
        act = _action(cust, p, n)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""INSERT INTO health_snapshots VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(customer_id) DO UPDATE SET health_score=excluded.health_score,
            churn_risk=excluded.churn_risk, positive_signals_json=excluded.positive_signals_json,
            negative_signals_json=excluded.negative_signals_json,
            next_best_action=excluded.next_best_action, calculated_at=excluded.calculated_at""",
            (cid, norm, risk, json.dumps(p), json.dumps(n), act, now))
        c.commit()
    return {"customer_id":cid,"health_score":norm,"churn_risk":risk,
        "positive_signals":p,"negative_signals":n,"next_best_action":act,"calculated_at":now}

def recalculate_all_health() -> dict:
    with _connect() as c:
        rows = c.execute("SELECT customer_id FROM customers").fetchall()
    results = []
    for r in rows:
        try: results.append(calculate_health(r["customer_id"]))
        except Exception: pass
    return {"total":len(results),
        "critical":len([r for r in results if r["churn_risk"]=="Critico"]),
        "high_risk":len([r for r in results if r["churn_risk"]=="Alto"]),
        "medium_risk":len([r for r in results if r["churn_risk"]=="Medio"]),
        "healthy":len([r for r in results if r["churn_risk"]=="Baixo"]),
        "avg_score":int(sum(r["health_score"] for r in results)/max(1,len(results)))}

def get_at_risk_customers(min_severity="Alto") -> list:
    order = ["Baixo","Medio","Alto","Critico"]
    if min_severity not in order: min_severity = "Alto"
    allowed = order[order.index(min_severity):]
    ph = ",".join(["?"]*len(allowed))
    with _connect() as c:
        rows = c.execute(f"""SELECT h.customer_id, h.health_score, h.churn_risk, h.next_best_action,
            h.calculated_at, c.name, c.segment, c.country, c.owner, c.lifetime_value, c.channel, c.status
            FROM health_snapshots h JOIN customers c ON c.customer_id=h.customer_id
            WHERE h.churn_risk IN ({ph}) ORDER BY h.health_score ASC""", allowed).fetchall()
    return [dict(r) for r in rows]

def get_health_overview() -> dict:
    with _connect() as c:
        rows = c.execute("SELECT churn_risk, COUNT(*) AS total, AVG(health_score) AS avg_score FROM health_snapshots GROUP BY churn_risk").fetchall()
    return {r["churn_risk"]:{"total":r["total"],"avg_score":int(r["avg_score"] or 0)} for r in rows}
