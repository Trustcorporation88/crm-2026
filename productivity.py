"""Productivity reports per owner."""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Any
from crm_backend import _connect

def get_owner_productivity(period_days=30) -> list:
    cutoff = (datetime.now()-timedelta(days=period_days)).strftime("%Y-%m-%d %H:%M:%S")
    with _connect() as c:
        tr = c.execute("""SELECT owner, COUNT(*) AS tickets_total,
            SUM(CASE WHEN status='Resolvido' THEN 1 ELSE 0 END) AS tickets_resolved,
            AVG(CASE WHEN csat>0 THEN csat END) AS avg_csat,
            AVG(CASE WHEN status='Resolvido' THEN age_hours END) AS avg_resolution_hours
            FROM tickets WHERE opened_at>=? GROUP BY owner""", (cutoff,)).fetchall()
        dr = c.execute("""SELECT owner, COUNT(*) AS deals_total,
            SUM(CASE WHEN stage='Fechado ganho' THEN 1 ELSE 0 END) AS deals_won,
            SUM(CASE WHEN stage='Fechado ganho' THEN value ELSE 0 END) AS revenue_won,
            SUM(value) AS pipeline_value FROM deals GROUP BY owner""").fetchall()
        ir = c.execute("SELECT owner, COUNT(*) AS interactions_total FROM interactions WHERE event_at>=? GROUP BY owner",(cutoff,)).fetchall()
    od = {}
    for r in tr:
        o = r["owner"]
        if not o: continue
        od.setdefault(o, {"owner": o})
        od[o].update({"tickets_total":int(r["tickets_total"] or 0),
            "tickets_resolved":int(r["tickets_resolved"] or 0),
            "avg_csat":round(float(r["avg_csat"] or 0),1),
            "avg_resolution_hours":round(float(r["avg_resolution_hours"] or 0),1)})
    for r in dr:
        o = r["owner"]
        if not o: continue
        od.setdefault(o, {"owner": o})
        dt = int(r["deals_total"] or 0); dw = int(r["deals_won"] or 0)
        od[o].update({"deals_total":dt,"deals_won":dw,
            "win_rate_pct":round((dw/dt*100) if dt else 0,1),
            "revenue_won":float(r["revenue_won"] or 0),
            "pipeline_value":float(r["pipeline_value"] or 0)})
    for r in ir:
        o = r["owner"]
        if not o: continue
        od.setdefault(o, {"owner": o})
        od[o]["interactions_total"] = int(r["interactions_total"] or 0)
    defaults = {"tickets_total":0,"tickets_resolved":0,"avg_csat":0.0,"avg_resolution_hours":0.0,
        "deals_total":0,"deals_won":0,"win_rate_pct":0.0,"revenue_won":0.0,
        "pipeline_value":0.0,"interactions_total":0}
    for o, d in od.items():
        for k, v in defaults.items(): d.setdefault(k, v)
    return sorted(od.values(), key=lambda x: x.get("revenue_won",0), reverse=True)

def get_team_summary(period_days=30) -> dict:
    rows = get_owner_productivity(period_days)
    if not rows:
        return {"period_days":period_days,"active_owners":0,"total_tickets":0,
            "total_resolved":0,"total_revenue":0.0,"avg_csat":0.0,"avg_win_rate":0.0}
    tt = sum(r["tickets_total"] for r in rows)
    tr = sum(r["tickets_resolved"] for r in rows)
    rev = sum(r["revenue_won"] for r in rows)
    cs = [r["avg_csat"] for r in rows if r["avg_csat"]>0]
    wr = [r["win_rate_pct"] for r in rows if r["deals_total"]>0]
    return {"period_days":period_days,"active_owners":len(rows),
        "total_tickets":tt,"total_resolved":tr,
        "resolution_rate_pct":round((tr/tt*100) if tt else 0,1),
        "total_revenue":rev,
        "avg_csat":round(sum(cs)/len(cs),1) if cs else 0.0,
        "avg_win_rate":round(sum(wr)/len(wr),1) if wr else 0.0}

def get_channel_breakdown(period_days=30) -> list:
    cutoff = (datetime.now()-timedelta(days=period_days)).strftime("%Y-%m-%d %H:%M:%S")
    with _connect() as c:
        rows = c.execute("""SELECT channel, COUNT(*) AS total,
            SUM(CASE WHEN status='Resolvido' THEN 1 ELSE 0 END) AS resolved,
            AVG(CASE WHEN status='Resolvido' THEN age_hours END) AS avg_resolution_hours,
            AVG(CASE WHEN csat>0 THEN csat END) AS avg_csat FROM tickets WHERE opened_at>=?
            GROUP BY channel ORDER BY total DESC""", (cutoff,)).fetchall()
    return [dict(r) for r in rows]
