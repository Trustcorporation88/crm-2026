"""UI das secoes novas com helps. Isolado para nao quebrar crm_app.py."""
from __future__ import annotations
from datetime import date
import pandas as pd
import streamlit as st


def _currency(v):
    try:
        return ("R$ {:,.0f}".format(float(v or 0))).replace(",", ".")
    except Exception:
        return "R$ 0"


def render_cadences(user, customers_df):
    from cadences import (list_cadences, list_active_enrollments, list_pending_actions,
                          enroll, mark_action_done)
    owner_options = sorted([o for o in customers_df["owner"].dropna().unique().tolist() if o])
    st.subheader("Cadencias de follow-up automatico")
    st.caption("Sequencias programadas de toques (mensagens, ligacoes, emails) para nao deixar lead esfriar.")

    cadlist = list_cadences()
    if cadlist:
        cols = st.columns(min(len(cadlist), 4))
        for i, cd in enumerate(cadlist):
            with cols[i % len(cols)]:
                with st.container(border=True):
                    st.caption(cd["key"])
                    st.markdown("**" + cd["title"] + "**")
                    st.caption(str(cd["step_count"]) + " toques")

    st.divider()
    st.subheader("Inscrever cliente em uma cadencia")
    st.caption("Escolha o cliente, a sequencia e quem fica responsavel pelos toques.")
    if not customers_df.empty and cadlist and owner_options:
        with st.form("cad-enroll"):
            sc = st.selectbox("Cliente", customers_df["name"].tolist(),
                              help="Cliente que recebera a sequencia de mensagens.")
            sk = st.selectbox("Cadencia", [c["key"] for c in cadlist],
                              format_func=lambda k: next((c["title"] for c in cadlist if c["key"] == k), k),
                              help="Modelo de sequencia. Cada um tem N toques em datas e canais especificos.")
            so = st.selectbox("Owner", owner_options,
                              help="Vendedor ou SDR que vai executar os toques.")
            if st.form_submit_button("Inscrever", type="primary"):
                try:
                    cid = customers_df.loc[customers_df["name"] == sc, "customer_id"].iloc[0]
                    eid = enroll(sk, cid, so, actor=user); st.success("Inscrito #" + str(eid)); st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    st.divider()
    st.subheader("Acoes pendentes")
    st.caption("Toques agendados para hoje ou atrasados. Marque como feita apos executar.")
    pend = list_pending_actions(limit=50)
    if pend:
        st.dataframe(pd.DataFrame(pend)[["id", "customer_name", "channel", "template_key", "scheduled_at", "owner"]],
                     width="stretch", hide_index=True)
        aid = st.number_input("ID da acao para marcar feita", min_value=0, step=1, key="cad_aid",
                              help="Copie o ID da coluna `id` da tabela acima.")
        if st.button("Marcar feita") and aid > 0:
            mark_action_done(int(aid), actor=user); st.success("OK"); st.rerun()
    else:
        st.info("Nenhuma acao pendente.")

    st.divider()
    st.subheader("Inscricoes ativas")
    enr = list_active_enrollments()
    if enr:
        st.dataframe(pd.DataFrame(enr)[["id", "customer_name", "cadence_title", "current_step", "total_steps", "owner", "paused"]],
                     width="stretch", hide_index=True)
    else:
        st.info("Nenhuma inscricao ativa.")


def render_templates(user, customers_df, can_admin):
    from message_templates import list_templates, render_template, save_template
    st.subheader("Templates de mensagem")
    st.caption("Modelos prontos para WhatsApp, email e SMS com variaveis dinamicas.")
    c1, c2 = st.columns(2)
    with c1: fch = st.selectbox("Canal", ["Todos", "WhatsApp", "Email", "SMS"],
                                help="Filtra os templates pelo canal de envio.")
    with c2: fct = st.selectbox("Categoria", ["Todas", "Onboarding", "Follow-up", "Atendimento", "Retencao", "Pesquisa", "Reativacao"],
                                help="Tipo de comunicacao. Onboarding = boas-vindas, Retencao = evitar churn.")
    tpl = list_templates(channel=None if fch == "Todos" else fch, category=None if fct == "Todas" else fct)
    if tpl:
        st.dataframe(pd.DataFrame(tpl)[["key", "channel", "category", "title", "is_active"]], width="stretch", hide_index=True)
        st.markdown("**Preview com dados reais**")
        sk = st.selectbox("Template", [t["key"] for t in tpl],
                          format_func=lambda k: next((t["title"] for t in tpl if t["key"] == k), k),
                          help="Escolha o template para ver como fica com dados de um cliente real.")
        if not customers_df.empty:
            sc = st.selectbox("Cliente para variaveis", customers_df["name"].tolist(), key="tpl_cust",
                              help="Os dados desse cliente vao preencher {{customer_name}} e similares.")
            cust = customers_df[customers_df["name"] == sc].iloc[0].to_dict()
            r = render_template(sk, {"customer_name": cust["name"], "owner": cust.get("owner", ""), "ticket_id": "EX-001"})
            st.text_area("Mensagem renderizada", r, height=180)
    else:
        st.info("Nenhum template para os filtros.")
    if can_admin:
        st.divider()
        st.subheader("Criar ou editar template")
        with st.form("tpl_form"):
            tk = st.text_input("Key (identificador unico)", value="custom_template",
                               help="Use snake_case. Ex: welcome_email_v2. Nao pode ter espaco.")
            ch = st.selectbox("Canal", ["WhatsApp", "Email", "SMS"], key="tpl_ch",
                              help="Onde a mensagem sera enviada.")
            ct = st.selectbox("Categoria", ["Onboarding", "Follow-up", "Atendimento", "Retencao", "Pesquisa", "Reativacao"], key="tpl_cat",
                              help="Categoriza para facilitar busca e relatorios.")
            tt = st.text_input("Titulo (visivel para o time)",
                               help="Nome amigavel. Ex: Email de boas-vindas - SaaS.")
            tb = st.text_area("Corpo da mensagem", height=160,
                              value="Ola {{customer_name}}, aqui e {{owner}}.",
                              help="Use {{customer_name}}, {{owner}}, {{ticket_id}} como variaveis. Elas serao trocadas em tempo de envio.")
            ta = st.checkbox("Ativo", value=True,
                             help="Inativos ficam ocultos do uso diario mas permanecem salvos.")
            if st.form_submit_button("Salvar", type="primary"):
                try:
                    save_template(tk, ch, ct, tt, tb, ta, actor=user); st.success("Salvo."); st.rerun()
                except Exception as exc:
                    st.error(str(exc))


def render_health():
    from health_score import recalculate_all_health, get_at_risk_customers, get_health_overview
    st.subheader("Health Score e risco de churn")
    st.caption("Score 0-100 por cliente baseado em uso, suporte, NPS e tempo de relacionamento.")
    if st.button("Recalcular saude da carteira", type="primary",
                 help="Recalcula o score de todos os clientes. Pode demorar com base grande."):
        s = recalculate_all_health()
        st.success("Recalculado " + str(s["total"]) + " contas. Critico:" + str(s["critical"])
                   + " Alto:" + str(s["high_risk"]) + " Medio:" + str(s["medium_risk"])
                   + " Saudavel:" + str(s["healthy"]) + ". Score medio: " + str(s["avg_score"]) + "/100")
    overview = get_health_overview()
    if overview:
        cols = st.columns(4)
        for col, level in zip(cols, ["Critico", "Alto", "Medio", "Baixo"]):
            d = overview.get(level, {"total": 0, "avg_score": 0})
            with col:
                with st.container(border=True):
                    st.caption("Risco " + level)
                    st.metric("Contas", d["total"])
                    st.caption("Score medio: " + str(d["avg_score"]))
    st.divider()
    st.subheader("Contas em risco")
    sev = st.selectbox("Severidade minima", ["Alto", "Critico", "Medio", "Baixo"],
                       help="Critico = churn iminente. Alto = atencao em 30 dias. Medio = monitorar.")
    risk = get_at_risk_customers(min_severity=sev)
    if risk:
        for it in risk[:30]:
            with st.container(border=True):
                st.markdown("**" + it["name"] + "** - Risco " + it["churn_risk"] + " - Score " + str(it["health_score"]) + "/100")
                st.caption(it["segment"] + " - " + it["country"] + " - Owner: " + str(it["owner"]))
                st.write("**Proxima acao:** " + it["next_best_action"])
                st.caption("LTV: " + _currency(it["lifetime_value"]) + " - Canal: " + str(it["channel"]))
    else:
        st.info("Nenhuma conta nesse nivel.")


def render_lead_scoring(user, can_admin):
    from lead_scoring import recalculate_all_scores, get_lead_scores, get_active_rules, update_rule
    st.subheader("Lead Scoring")
    st.caption("Pontuacao 0-100 que prioriza onde o time deve focar. Tier A = quente, D = frio.")
    if st.button("Recalcular scores", type="primary",
                 help="Roda as regras ativas para todos os leads. Use apos editar regras."):
        s = recalculate_all_scores(actor=user)
        st.success(str(s["total"]) + " contas. A:" + str(s["tier_a"]) + " B:" + str(s["tier_b"])
                   + " C:" + str(s["tier_c"]) + " D:" + str(s["tier_d"]) + ". Medio:" + str(s["avg_score"]) + "/100")
    st.divider()
    st.subheader("Carteira priorizada")
    tier = st.selectbox("Filtrar tier", ["Todos", "A", "B", "C", "D"],
                        help="A = abordar agora. B = aquecer. C = nutrir. D = passivo.")
    scores = get_lead_scores(limit=200, tier_filter=None if tier == "Todos" else tier)
    if scores:
        for it in scores[:50]:
            with st.container(border=True):
                st.markdown("**Tier " + it["tier"] + "** - **" + it["name"] + "** - Score " + str(it["score"]) + "/100")
                st.caption(it["segment"] + " - " + it["country"] + " - Owner: " + str(it["owner"]) + " - Canal: " + str(it["channel"]))
    else:
        st.info("Sem score. Recalcular acima.")
    if can_admin:
        st.divider()
        st.subheader("Regras de pontuacao")
        st.caption("Cada regra atribui pontos. A soma vira o score do lead.")
        rules = get_active_rules()
        df = pd.DataFrame([{"regra": k, "pontos": v} for k, v in rules.items()]).sort_values("pontos", ascending=False)
        st.dataframe(df, width="stretch", hide_index=True)
        with st.form("rule_form"):
            rk = st.selectbox("Regra", list(rules.keys()),
                              help="Selecione qual regra editar.")
            rp = st.number_input("Pontos atribuidos", 0, 100, rules.get(rk, 0),
                                 help="Quanto vale o atendimento dessa regra (0 a 100).")
            ra = st.checkbox("Ativa", value=True,
                             help="Desative para parar de aplicar essa regra sem deletar.")
            if st.form_submit_button("Salvar", type="primary"):
                update_rule(rk, int(rp), ra, actor=user); st.success("Atualizada."); st.rerun()


def render_forecast(selected_owner="Todos"):
    from forecast import get_pipeline_forecast, get_forecast_by_owner, get_velocity_metrics
    st.subheader("Forecast de receita")
    st.caption("Projecao de receita ponderada pela probabilidade de cada deal fechar.")
    f1, f2 = st.columns(2)
    with f1: ps = st.date_input("Inicio do periodo", value=date.today().replace(day=1),
                                help="Data inicial para considerar deals.")
    with f2: pe = st.date_input("Fim do periodo",
                                help="Data final. Use fim do trimestre para forecast Q.")
    fc = get_pipeline_forecast(period_start=ps.isoformat(), period_end=pe.isoformat(),
                               owner=None if selected_owner == "Todos" else selected_owner)
    cols = st.columns(4)
    metrics = [("Pipeline bruto", fc["raw_pipeline_value"], str(fc["deal_count"]) + " deals"),
               ("Forecast ponderado", fc["weighted_forecast"], "valor x probabilidade"),
               ("Commit (>=80%)", fc["commit_value"], "alta certeza de fechar"),
               ("Best case (50-79%)", fc["best_case_value"], "upside se tudo der certo")]
    for col, (lab, val, cap) in zip(cols, metrics):
        with col:
            with st.container(border=True):
                st.caption(lab); st.markdown("### " + _currency(val)); st.caption(cap)
    st.divider()
    st.subheader("Por vendedor")
    bo = get_forecast_by_owner(ps.isoformat(), pe.isoformat())
    if bo:
        df = pd.DataFrame(bo)
        df["pipe"] = df["pipeline_value"].apply(lambda v: _currency(v or 0))
        df["fcst"] = df["weighted_forecast"].apply(lambda v: _currency(v or 0))
        df["won"] = df["won_value"].apply(lambda v: _currency(v or 0))
        st.dataframe(df[["owner", "deal_count", "pipe", "fcst", "won"]], width="stretch", hide_index=True)
    else:
        st.info("Sem dados.")
    st.divider()
    st.subheader("Velocity")
    v = get_velocity_metrics()
    vc = st.columns(4)
    with vc[0]: st.metric("Win rate", str(v["win_rate_pct"]) + "%", help="% de deals ganhos vs total fechado.")
    with vc[1]: st.metric("Ticket medio", _currency(v["avg_deal_size"]), help="Valor medio dos deals fechados.")
    with vc[2]: st.metric("Ganhos", v["won_count"], help="Quantos deals foram fechados ganhando.")
    with vc[3]: st.metric("Pipeline aberto", _currency(v["open_value"]), help="Valor total dos deals em aberto.")


def render_productivity():
    from productivity import get_owner_productivity, get_team_summary, get_channel_breakdown
    st.subheader("Produtividade do time")
    st.caption("Metricas por vendedor e por canal de atendimento.")
    period = st.selectbox("Periodo (dias)", [7, 14, 30, 60, 90], index=2,
                          help="Janela de analise. 30d = mes, 90d = trimestre.")
    summ = get_team_summary(period_days=period)
    cs = st.columns(4)
    with cs[0]: st.metric("Owners ativos", summ["active_owners"])
    with cs[1]: st.metric("Resolvidos", str(summ["total_resolved"]) + "/" + str(summ["total_tickets"]),
                          str(summ.get("resolution_rate_pct", 0)) + "%")
    with cs[2]: st.metric("Receita", _currency(summ["total_revenue"]))
    with cs[3]: st.metric("CSAT medio", str(summ["avg_csat"]) + "/5")
    st.divider()
    st.subheader("Performance individual")
    od = get_owner_productivity(period_days=period)
    if od:
        df = pd.DataFrame(od)
        df["receita"] = df["revenue_won"].apply(lambda v: _currency(v))
        df["pipe"] = df["pipeline_value"].apply(lambda v: _currency(v))
        st.dataframe(df[["owner", "tickets_total", "tickets_resolved", "avg_csat", "deals_won",
                         "win_rate_pct", "receita", "pipe", "interactions_total"]],
                     width="stretch", hide_index=True)
    else:
        st.info("Sem atividade no periodo.")
    st.divider()
    st.subheader("Tickets por canal")
    chb = get_channel_breakdown(period_days=period)
    if chb:
        st.dataframe(pd.DataFrame(chb), width="stretch", hide_index=True)
    else:
        st.info("Sem tickets.")


def render_segmentation(customers_df):
    st.subheader("Segmentacao inteligente")
    st.caption("Filtre a base por multiplos criterios e exporte para campanhas dirigidas.")
    g1 = st.columns(3)
    with g1[0]: sco = st.multiselect("Mercado", customers_df["country"].unique().tolist(),
                                     help="Pais ou regiao do cliente.")
    with g1[1]: sst = st.multiselect("Status", customers_df["status"].unique().tolist(),
                                     help="Estado atual: ativo, churn, prospect, etc.")
    with g1[2]: sow = st.multiselect("Owner", customers_df["owner"].dropna().unique().tolist(),
                                     help="Vendedor responsavel.")
    g2 = st.columns(3)
    with g2[0]: sch = st.multiselect("Canal preferido", customers_df["channel"].unique().tolist(),
                                     help="Canal mais usado pelo cliente para falar com voce.")
    with g2[1]: sl = st.number_input("LTV minimo (R$)", 0, value=0, step=10000,
                                     help="Lifetime value: receita total acumulada com o cliente.")
    with g2[2]: sh = st.number_input("Health score minimo", 0, 100, 0,
                                     help="0-100. Quanto maior, mais saudavel a conta.")
    seg = customers_df.copy()
    if sco: seg = seg[seg["country"].isin(sco)]
    if sst: seg = seg[seg["status"].isin(sst)]
    if sow: seg = seg[seg["owner"].isin(sow)]
    if sch: seg = seg[seg["channel"].isin(sch)]
    if sl > 0: seg = seg[seg["lifetime_value"] >= sl]
    if sh > 0 and "health_score" in seg.columns: seg = seg[seg["health_score"] >= sh]
    st.markdown("**" + str(len(seg)) + " contas no segmento**")
    if not seg.empty:
        cols = ["customer_id", "name", "segment", "country", "owner", "status", "channel", "lifetime_value"]
        if "health_score" in seg.columns: cols.append("health_score")
        st.dataframe(seg[cols], width="stretch", hide_index=True)
        st.download_button("Exportar CSV", seg.to_csv(index=False).encode("utf-8"),
                           "segmento.csv", "text/csv", type="primary",
                           help="Baixa em CSV para usar em ferramentas de campanha externa.")
    else:
        st.info("Nenhuma conta no segmento.")


def render_ai_insights(customers_df):
    from ai_insights import (summarize_customer_timeline, suggest_next_action,
                             classify_ticket, detect_anomalies)
    st.subheader("Insights automaticos")
    st.caption("Resumos, recomendacoes e deteccao de anomalias com regras inteligentes.")
    anomalies = detect_anomalies(period_days=7)
    if anomalies:
        st.markdown("**Anomalias detectadas (ultimos 7 dias)**")
        for a in anomalies:
            with st.container(border=True):
                st.markdown("**[" + a["severity"] + "] " + a["title"] + "**")
                st.write(a["description"])
    else:
        st.success("Nenhuma anomalia. Operacao saudavel.")
    st.divider()
    st.subheader("Resumo do cliente e proxima acao")
    if not customers_df.empty:
        ac = st.selectbox("Cliente", customers_df["name"].tolist(), key="ai_cust",
                          help="Escolha um cliente para ver resumo automatico do historico.")
        cid = customers_df.loc[customers_df["name"] == ac, "customer_id"].iloc[0]
        with st.container(border=True):
            st.markdown("**Resumo automatico**")
            st.write(summarize_customer_timeline(cid))
        action = suggest_next_action(cid)
        with st.container(border=True):
            st.markdown("**[" + action["priority"] + "] Proxima acao recomendada**")
            st.write("**" + action["action"] + "**")
            st.caption(action["reason"])
            st.caption("Canal: " + str(action.get("channel_suggestion", "-"))
                       + " | Template: " + str(action.get("template_suggestion", "-")))
    st.divider()
    st.subheader("Classificar ticket automaticamente")
    st.caption("Cole um ticket novo e veja categoria, prioridade e SLA sugeridos.")
    cs = st.text_input("Assunto",
                       help="Titulo curto do ticket. Ex: Erro ao gerar relatorio mensal.")
    cb = st.text_area("Descricao", height=100,
                      help="Detalhes do problema relatado pelo cliente.")
    if st.button("Classificar"):
        if cs:
            r = classify_ticket(cs, cb)
            rc = st.columns(3)
            with rc[0]: st.metric("Categoria", r["suggested_category"])
            with rc[1]: st.metric("Prioridade", r["suggested_priority"])
            with rc[2]: st.metric("SLA", str(r["suggested_sla_hours"]) + "h")
            st.caption("Confianca: " + r["confidence"])
        else:
            st.warning("Preencha o assunto.")


def render_services_catalog_tabs(navigate_fn, resolve_fn):
    st.info("Catalogo de servicos em desenvolvimento. Use a barra de navegacao para acessar as secoes.")


@st.dialog("Como funciona este servico", width="large")
def _show_guide_dialog(service, navigate_fn, resolve_fn):
    from services_catalog import get_service_by_id
    st.markdown("### " + service["title"])
    st.caption(service["category"] + " - " + service["tagline"])
    st.markdown("**Resumo executivo**")
    st.info(service.get("summary", service["tagline"]))
    st.markdown("**O que entrega**")
    st.markdown(service["description"])
    ca, cb = st.columns(2)
    with ca:
        st.markdown("**Dados necessarios**")
        for it in service["inputs"]: st.markdown("- " + it)
    with cb:
        st.markdown("**Como usar**")
        for i, s in enumerate(service["steps"], 1): st.markdown(str(i) + ". " + s)
    st.markdown("**Resultado esperado**")
    st.success(service["outcome"])
    if service.get("benchmark"):
        st.markdown("**Benchmark de mercado**")
        st.markdown("_" + service["benchmark"] + "_")
    if service.get("integrations"):
        related = []
        for x in service["integrations"]:
            r = get_service_by_id(x)
            if r: related.append(r["title"])
        if related:
            st.markdown("**Servicos relacionados**")
            st.markdown(", ".join(related))
    st.divider()
    b1, b2 = st.columns(2)
    with b1:
        if st.button("Abrir modulo agora", key="dlg-mo-" + service["id"], type="primary", width="stretch"):
            st.session_state.pop("_show_guide", None)
            navigate_fn(resolve_fn(str(service["id"])))
    with b2:
        if st.button("Fechar", key="dlg-mc-" + service["id"], width="stretch"):
            st.session_state.pop("_show_guide", None)
            st.rerun()
