"""Revenue forecast."""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Any
from crm_backend import _connect

STAGE_PROB = {"Descoberta":20,"Proposta":50,"Negociacao":70,"Fechado ganho":100,"Perdido":0}

def _categorize(p):
    if p >= 80: return "commit"
    if p >= 50: return "best_case"
    if p >= 20: return "pipeline"
    return "longshot"

def _default_period():
    today = datetime.now().date()
    s = today.replace(day=1).isoformat()
    nm = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
    e = (nm - timedelta(days=1)).isoformat()
    return s, e

def get_pipeline_forecast(period_start=None, period_end=None, owner=None) -> dict:
    if not period_start or not period_end:
        period_start, period_end = _default_period()
    where, params = ["close_date BETWEEN ? AND ?", "stage NOT IN ('Perdido')"], [period_start, period_end]
    if owner: where.append("owner=?"); params.append(owner)
    with _connect() as c:
        rows = c.execute(f"""SELECT * FROM deals WHERE {' AND '.join(where)}
            ORDER BY close_date ASC, value DESC""", params).fetchall()
    deals = [dict(r) for r in rows]
    by = {"commit":[],"best_case":[],"pipeline":[],"longshot":[]}
    wt, rt, won = 0.0, 0.0, 0.0
    for d in deals:
        prob = int(d["probability"]) if d["probability"] is not None else STAGE_PROB.get(d["stage"], 0)
        cat = _categorize(prob)
        d["effective_probability"] = prob
        d["forecast_category"] = cat
        d["weighted_value"] = float(d["value"]) * prob / 100.0
        by[cat].append(d)
        wt += d["weighted_value"]; rt += float(d["value"])
        if d["stage"] == "Fechado ganho": won += float(d["value"])
    return {"period_start": period_start, "period_end": period_end,
        "owner_filter": owner or "Todos", "deal_count": len(deals),
        "raw_pipeline_value": rt, "weighted_forecast": wt, "won_value": won,
        "commit_value": sum(d["value"] for d in by["commit"]),
        "best_case_value": sum(d["value"] for d in by["best_case"]),
        "pipeline_value": sum(d["value"] for d in by["pipeline"]),
        "longshot_value": sum(d["value"] for d in by["longshot"]),
        "by_category": by, "deals": deals}

def get_forecast_by_owner(period_start=None, period_end=None) -> list:
    if not period_start or not period_end:
        period_start, period_end = _default_period()
    with _connect() as c:
        rows = c.execute("""SELECT owner, COUNT(*) AS deal_count, SUM(value) AS pipeline_value,
            SUM(value*probability/100.0) AS weighted_forecast,
            SUM(CASE WHEN stage='Fechado ganho' THEN value ELSE 0 END) AS won_value
            FROM deals WHERE close_date BETWEEN ? AND ? AND stage!='Perdido'
            GROUP BY owner ORDER BY weighted_forecast DESC""", (period_start, period_end)).fetchall()
    return [dict(r) for r in rows]

def get_velocity_metrics() -> dict:
    with _connect() as c:
        won = c.execute("SELECT COUNT(*) AS cnt, AVG(value) AS avg_value, SUM(value) AS sum_value FROM deals WHERE stage='Fechado ganho'").fetchone()
        tc = c.execute("SELECT COUNT(*) AS cnt FROM deals WHERE stage IN ('Fechado ganho','Perdido')").fetchone()
        op = c.execute("SELECT COUNT(*) AS cnt, SUM(value) AS sum_value FROM deals WHERE stage NOT IN ('Fechado ganho','Perdido')").fetchone()
    wr = (won["cnt"] / tc["cnt"] * 100) if tc["cnt"] else 0.0
    return {"won_count": won["cnt"] or 0, "won_value": won["sum_value"] or 0.0,
        "avg_deal_size": won["avg_value"] or 0.0, "win_rate_pct": round(wr, 1),
        "open_deals": op["cnt"] or 0, "open_value": op["sum_value"] or 0.0}
