"""AI-style insights with deterministic heuristics."""
from __future__ import annotations
import os
from collections import Counter
from datetime import datetime, timedelta
from typing import Any
from crm_backend import _connect

USE_LLM = bool(os.getenv("CRM_OPENAI_API_KEY","").strip())

def summarize_customer_timeline(cid: str, max_events=20) -> str:
    with _connect() as c:
        cust = c.execute("SELECT * FROM customers WHERE customer_id=?",(cid,)).fetchone()
        if not cust: return "Cliente nao encontrado."
        events = c.execute("""SELECT event_at, event_type, title, body, channel, owner
            FROM interactions WHERE customer_id=? ORDER BY event_at DESC LIMIT ?""",(cid,max_events)).fetchall()
        tk = c.execute("""SELECT COUNT(*) AS total,
            SUM(CASE WHEN status NOT IN ('Resolvido') THEN 1 ELSE 0 END) AS open
            FROM tickets WHERE customer_id=?""",(cid,)).fetchone()
        dl = c.execute("""SELECT COUNT(*) AS total, SUM(value) AS pipeline
            FROM deals WHERE customer_id=? AND stage NOT IN ('Fechado ganho','Perdido')""",(cid,)).fetchone()
    if not events: return f"Conta {cust['name']} sem interacoes registradas. Vale fazer o primeiro contato."
    types = Counter(e["event_type"] for e in events)
    chans = Counter(e["channel"] for e in events)
    last = events[0]
    parts = [f"Conta {cust['name']} ({cust['segment']}, {cust['country']}) tem {len(events)} interacoes recentes,",
        f"com predominancia de '{types.most_common(1)[0][0]}' em '{chans.most_common(1)[0][0]}'."]
    if tk["open"]: parts.append(f"Tem {tk['open']} ticket(s) aberto(s) de {tk['total']} total.")
    if dl["total"]:
        pl = float(dl["pipeline"] or 0)
        parts.append(f"Tem {dl['total']} oportunidade(s) abertas somando R$ {pl:,.0f}.")
    parts.append(f"Ultimo evento ({last['event_at']}): {last['title']}.")
    parts.append(f"Status: {cust['status']}, owner: {cust['owner']}.")
    return " ".join(parts)

def suggest_next_action(cid: str) -> dict:
    with _connect() as c:
        cust = c.execute("SELECT * FROM customers WHERE customer_id=?",(cid,)).fetchone()
        if not cust: return {"action":"N/A","reason":"Cliente nao encontrado","priority":"Baixa"}
        last = c.execute("SELECT event_at FROM interactions WHERE customer_id=? ORDER BY event_at DESC LIMIT 1",(cid,)).fetchone()
        crit = c.execute("""SELECT ticket_id, subject FROM tickets WHERE customer_id=?
            AND status NOT IN ('Resolvido') AND priority IN ('Alta','Critica') LIMIT 1""",(cid,)).fetchone()
        deal = c.execute("""SELECT deal_id, name, stage FROM deals WHERE customer_id=?
            AND stage NOT IN ('Fechado ganho','Perdido') ORDER BY value DESC LIMIT 1""",(cid,)).fetchone()
    cust = dict(cust)
    if crit: return {"action":f"Atualizar ticket {crit['ticket_id']}: {crit['subject']}",
        "reason":"Ticket critico aberto.","priority":"Alta",
        "channel_suggestion":cust.get("channel","WhatsApp"),"template_suggestion":"ticket_received"}
    if last:
        try: ds = (datetime.now()-datetime.strptime(last["event_at"][:10],"%Y-%m-%d")).days
        except ValueError: ds = 0
        if ds > 60: return {"action":"Reativar com cadencia win_back",
            "reason":f"Sem interacao ha {ds} dias.","priority":"Alta",
            "channel_suggestion":cust.get("channel","Email"),"template_suggestion":"abandoned_cart"}
        if ds > 21: return {"action":"Check-in de relacionamento",
            "reason":f"Ultima interacao ha {ds} dias.","priority":"Media",
            "channel_suggestion":cust.get("channel","WhatsApp"),"template_suggestion":"follow_up_d3"}
    if deal: return {"action":f"Avancar oportunidade {deal['deal_id']}",
        "reason":f"Negocio em '{deal['stage']}' precisa proximo passo.","priority":"Alta",
        "channel_suggestion":cust.get("channel","Email"),"template_suggestion":"follow_up_d1"}
    if float(cust.get("lifetime_value",0))>=100000:
        return {"action":"Explorar upsell","reason":"LTV alto sem oportunidade aberta.","priority":"Media",
            "channel_suggestion":cust.get("channel","Email"),"template_suggestion":"renewal_reminder"}
    return {"action":"Agendar contato de relacionamento","reason":"Manter cadencia.","priority":"Baixa",
        "channel_suggestion":cust.get("channel","WhatsApp"),"template_suggestion":"welcome_whatsapp"}

def classify_ticket(subject: str, body="") -> dict:
    text = f"{subject} {body}".lower()
    cats = {"Integracao":["integra","api","webhook","conecta"],
        "Onboarding":["onboard","treinamento","kickoff"],
        "Operacao":["lento","falha","erro","travou","down"],
        "Produto":["funcionalidade","feature","melhoria"],
        "Financeiro":["fatura","boleto","cobranca","pagamento"],
        "Configuracao":["configura","ajusta","permiss"]}
    prios = {"Critica":["urgente","critico","parou","down","imediato"],
        "Alta":["importante","rapido","hoje"],"Baixa":["duvida","quando puder"]}
    cs = {c: sum(1 for w in ws if w in text) for c, ws in cats.items()}
    cat = max(cs, key=cs.get) if max(cs.values())>0 else "Geral"
    pr = "Media"
    for p, ws in prios.items():
        if any(w in text for w in ws): pr = p; break
    sla = {"Critica":2,"Alta":4,"Media":8,"Baixa":24}
    return {"suggested_category":cat,"suggested_priority":pr,
        "suggested_sla_hours":sla[pr],"confidence":"media" if max(cs.values())>=1 else "baixa"}

def detect_anomalies(period_days=7) -> list:
    cutoff = (datetime.now()-timedelta(days=period_days)).strftime("%Y-%m-%d %H:%M:%S")
    a = []
    with _connect() as c:
        sla = c.execute("""SELECT COUNT(*) AS t FROM tickets WHERE opened_at>=?
            AND age_hours>sla_hours AND status NOT IN ('Resolvido')""",(cutoff,)).fetchone()
        if sla["t"]>=3: a.append({"type":"sla_breach","severity":"Alta",
            "title":f"{sla['t']} tickets fora do SLA","description":"Volume acima do normal."})
        un = c.execute("SELECT COUNT(*) AS t FROM tickets WHERE opened_at>=? AND (owner IS NULL OR owner='')",(cutoff,)).fetchone()
        if un["t"]>=1: a.append({"type":"unassigned","severity":"Media",
            "title":f"{un['t']} ticket(s) sem owner","description":"Distribuir agora."})
        ch = c.execute("SELECT COUNT(*) AS t FROM customers WHERE status='Risco'").fetchone()
        if ch["t"]>=2: a.append({"type":"churn_risk","severity":"Alta",
            "title":f"{ch['t']} contas em risco","description":"Acionar customer success."})
        st = c.execute("""SELECT COUNT(*) AS t FROM deals WHERE stage NOT IN ('Fechado ganho','Perdido')
            AND close_date < date('now','-7 day')""").fetchone()
        if st["t"]>=1: a.append({"type":"stalled","severity":"Media",
            "title":f"{st['t']} oportunidade(s) atrasada(s)","description":"Replanejar ou perder."})
    return a
