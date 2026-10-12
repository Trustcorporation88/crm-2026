"""Seção Atendimento — tickets e SLA.

Extraída de crm_app.py sem mudança de lógica. `ctx` é o namespace do
script principal (dados filtrados, usuário, helpers de tela); as linhas
abaixo deixam explícito o que a seção consome.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st


def render(ctx: dict[str, Any]) -> None:
    import crm_components as ui

    # Imports do projeto resolvidos a cada renderização, como acontecia no
    # script principal (o Streamlit o reexecuta a cada clique). Assim um
    # módulo recarregado ou substituído em teste vale aqui também.
    from crm_backend import add_ticket
    from crm_ux import esc
    from deepseek_assistant import deepseek_configured, draft_ticket_reply, summarize_ticket_interaction

    can_manage = ctx["can_manage"]
    customer_lookup = ctx["customer_lookup"]
    customers_df = ctx["customers_df"]
    filtered_customers = ctx["filtered_customers"]
    filtered_tickets = ctx["filtered_tickets"]
    interactions_df = ctx["interactions_df"]
    owner_options = ctx["owner_options"]
    queue_toast = ctx["queue_toast"]
    render_empty_state = ctx["render_empty_state"]
    user = ctx["user"]

    if can_manage(user["role"], "ticket"):
        with st.expander("Novo ticket manual", expanded=False):
            with st.form("new-ticket-form"):
                customer_name = st.selectbox("Cliente", filtered_customers["name"].tolist() if not filtered_customers.empty else customers_df["name"].tolist())
                subject = st.text_input("Assunto")
                category = st.selectbox("Categoria", ["Geral", "Integracao", "Onboarding", "Operacao", "Produto", "Financeiro"])
                priority = st.selectbox("Prioridade", ["Baixa", "Media", "Alta", "Critica"])
                owner = st.selectbox("Responsavel", owner_options)
                channel = st.selectbox("Canal", ["WhatsApp", "Email", "Telefone", "Portal", "Chat", "Formulario"])
                message = st.text_area("Resumo do atendimento")
                submitted = st.form_submit_button("Criar ticket", type="primary")
            if submitted and subject:
                customer_id = customers_df.loc[customers_df["name"] == customer_name, "customer_id"].iloc[0]
                add_ticket(
                    {
                        "customer_id": customer_id,
                        "subject": subject,
                        "channel": channel,
                        "priority": priority,
                        "owner": owner,
                        "category": category,
                        "sla_hours": 8,
                        "message": message or subject,
                    },
                    actor=user,
                    source="ui-atendimento-manual",
                )
                queue_toast(f"Ticket criado para {customer_name}. Ele já aparece na fila abaixo.")
                st.rerun()

    # --- Indicadores da fila ---
    _tk = filtered_tickets.copy()
    if not _tk.empty:
        _tk["_risco"] = _tk["age_hours"] > _tk["sla_hours"]
        _abertos = int((_tk["status"].astype(str).str.lower() != "resolvido").sum())
        _risco = int(_tk["_risco"].sum())
        _resolvidos = int((_tk["status"].astype(str).str.lower() == "resolvido").sum())
        _csat = pd.to_numeric(_tk["csat"], errors="coerce").dropna()
        _csat_txt = f"{_csat.mean():.1f}/5" if not _csat.empty else "—"
    else:
        _abertos = _risco = _resolvidos = 0
        _csat_txt = "—"
    st.markdown(
        ui.kpi_grid(
            [
                {"label": "Tickets abertos", "value": _abertos, "caption": "Na fila agora.", "icon": "inbox", "tone": "info"},
                {"label": "SLA em risco", "value": _risco, "caption": "Acima do prazo alvo.", "icon": "timer_off", "tone": "danger" if _risco else "ok"},
                {"label": "Resolvidos", "value": _resolvidos, "caption": "No recorte atual.", "icon": "task_alt", "tone": "ok"},
                {"label": "CSAT médio", "value": _csat_txt, "caption": "Satisfação medida.", "icon": "favorite", "tone": "gold"},
            ]
        ),
        unsafe_allow_html=True,
    )

    if filtered_tickets.empty:
        with st.container(border=True):
            render_empty_state("Nenhum ticket para os filtros atuais.")
        return

    col_fila, col_det = st.columns([1.15, 1], gap="medium")

    # --- Coluna da fila ---
    with col_fila, st.container(border=True):
        st.markdown(ui.card_title("Fila de atendimento", "list_alt", f"{len(_tk)} tickets"), unsafe_allow_html=True)
        _prio_ordem = {"critica": 0, "alta": 1, "media": 2, "baixa": 3}
        _fila = _tk.sort_values(
            by=["_risco", "priority"],
            key=lambda c: c.map(lambda v: _prio_ordem.get(str(v).lower(), 9)) if c.name == "priority" else ~c,
        )
        _linhas = []
        for _, _r in _fila.iterrows():
            _tom = ui.priority_tone(_r["priority"])
            _estourou = bool(_r["_risco"])
            _linhas.append(
                ui.agenda_row(
                    _r["subject"],
                    f"{_r['ticket_id']} · {customer_lookup[_r['customer_id']]['name']} · {_r['channel']} · {_r['owner']}",
                    "danger" if _estourou else _tom,
                    ui.pill("SLA estourado" if _estourou else _r["status"], "danger" if _estourou else "neutral"),
                    progress=min(1.0, float(_r["age_hours"]) / max(float(_r["sla_hours"]), 1.0)),
                )
            )
        st.markdown(ui.list_block(_linhas), unsafe_allow_html=True)

    # --- Coluna do detalhe ---
    with col_det, st.container(border=True):
        st.markdown(ui.card_title("Detalhe do ticket", "confirmation_number"), unsafe_allow_html=True)
        selected_ticket = st.selectbox("Detalhar ticket", filtered_tickets["ticket_id"].tolist())
        ticket = filtered_tickets[filtered_tickets["ticket_id"] == selected_ticket].iloc[0].to_dict()
        customer = customer_lookup[ticket["customer_id"]]
        _estourado = float(ticket["age_hours"]) > float(ticket["sla_hours"])
        st.markdown(
            f"<div class='ticket-title'>{esc(ticket['subject'])}</div>"
            f"<div class='ameta'>{esc(customer['name'])} · aberto em {esc(ticket['opened_at'])}</div>"
            f"<div class='chip-row'>{ui.pill(ticket['priority'], ui.priority_tone(ticket['priority']))}"
            f"{ui.pill(ticket['status'], 'neutral')}{ui.pill(ticket['channel'], 'info')}"
            f"{ui.pill(ticket['category'], 'gold')}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            ui.kpi_grid(
                [
                    {"label": "SLA alvo", "value": f"{ticket['sla_hours']}h", "caption": "Prazo combinado.", "icon": "flag", "tone": "info"},
                    {"label": "Tempo corrido", "value": f"{ticket['age_hours']}h", "caption": "Estourado." if _estourado else "Dentro do prazo.", "icon": "schedule", "tone": "danger" if _estourado else "ok"},
                    {"label": "Responsável", "value": ticket["owner"], "caption": "Dono do caso.", "icon": "person", "tone": "gold"},
                    {"label": "CSAT", "value": ticket["csat"] if ticket["csat"] else "Pendente", "caption": "Avaliação do cliente.", "icon": "favorite", "tone": "warn"},
                ]
            ),
            unsafe_allow_html=True,
        )
        st.markdown(f"**Próxima ação sugerida:** {customer['next_action']}")

        with st.expander("Assistente IA para este atendimento", expanded=False):
            if not deepseek_configured():
                st.caption(
                    "Configure DEEPSEEK_API_KEY para resumir o atendimento ou gerar "
                    "sugestão de resposta automaticamente."
                )
            else:
                # A IA olha para o histórico DESTE cliente, não só deste ticket — o
                # atendimento raramente é uma troca isolada, e o contexto de
                # interações anteriores (outros tickets, negócios, contatos) ajuda
                # a IA a responder de forma coerente com o relacionamento inteiro.
                _ticket_history = (
                    interactions_df[interactions_df["customer_id"] == ticket["customer_id"]]
                    .sort_values("event_at")
                    .to_dict("records")
                )
                _summary_key = f"ai_ticket_summary_{selected_ticket}"
                _draft_key = f"ai_ticket_draft_{selected_ticket}"

                ai_col1, ai_col2 = st.columns(2)
                with ai_col1:
                    if st.button(
                        "Resumir atendimento", key=f"ai-summary-btn-{selected_ticket}", use_container_width=True
                    ):
                        with st.spinner("Resumindo com IA..."):
                            _summary, _summary_err = summarize_ticket_interaction(
                                ticket, customer, _ticket_history
                            )
                        if _summary_err:
                            st.error(_summary_err)
                        else:
                            st.session_state[_summary_key] = _summary
                with ai_col2:
                    if st.button(
                        "Sugerir resposta ao cliente", key=f"ai-draft-btn-{selected_ticket}", use_container_width=True
                    ):
                        with st.spinner("Gerando sugestão de resposta..."):
                            _draft, _draft_err = draft_ticket_reply(ticket, customer, _ticket_history)
                        if _draft_err:
                            st.error(_draft_err)
                        else:
                            st.session_state[_draft_key] = _draft

                if st.session_state.get(_summary_key):
                    st.info(st.session_state[_summary_key])
                if st.session_state.get(_draft_key):
                    st.text_area(
                        "Rascunho sugerido — revise antes de enviar ao cliente",
                        value=st.session_state[_draft_key],
                        height=180,
                        key=f"ai-draft-area-{selected_ticket}",
                    )
                    st.caption("A IA pode errar. Confira dados, prazos e promessas antes de enviar.")
