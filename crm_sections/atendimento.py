"""Seção Atendimento — tickets e SLA.

Extraída de crm_app.py sem mudança de lógica. `ctx` é o namespace do
script principal (dados filtrados, usuário, helpers de tela); as linhas
abaixo deixam explícito o que a seção consome.
"""

from __future__ import annotations

from typing import Any

import streamlit as st


def render(ctx: dict[str, Any]) -> None:
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

    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Fila de atendimento</div>', unsafe_allow_html=True)
    ticket_table = filtered_tickets.copy()
    if not ticket_table.empty:
        ticket_table["cliente"] = ticket_table["customer_id"].map(lambda value: customer_lookup[value]["name"])
        ticket_table["sla_status"] = ticket_table.apply(lambda row: "Em risco" if row["age_hours"] > row["sla_hours"] else "No prazo", axis=1)
        st.dataframe(ticket_table[["ticket_id", "cliente", "subject", "channel", "status", "priority", "owner", "sla_status"]], width="stretch", hide_index=True)
    else:
        render_empty_state("Nenhum ticket para os filtros atuais.")
    st.markdown('</div>', unsafe_allow_html=True)

    if not filtered_tickets.empty:
        selected_ticket = st.selectbox("Detalhar ticket", filtered_tickets["ticket_id"].tolist())
        ticket = filtered_tickets[filtered_tickets["ticket_id"] == selected_ticket].iloc[0].to_dict()
        customer = customer_lookup[ticket["customer_id"]]
        cols = st.columns(3)
        details = [
            ("Cliente", customer["name"]),
            ("Canal", ticket["channel"]),
            ("Categoria", ticket["category"]),
            ("Owner", ticket["owner"]),
            ("Prioridade", ticket["priority"]),
            ("CSAT", ticket["csat"] if ticket["csat"] else "Pendente"),
        ]
        for col, pair in zip(cols * 2, details):
            with col:
                st.markdown(f"<div class='mini-card'><div class='mini-label'>{esc(pair[0])}</div><div class='mini-value' style='font-size:1.2rem;'>{esc(pair[1])}</div></div>", unsafe_allow_html=True)
        st.info(f"Ticket aberto em {ticket['opened_at']} | SLA alvo: {ticket['sla_hours']}h | Tempo corrido: {ticket['age_hours']}h")
        st.markdown(f"**Resumo do caso:** {ticket['subject']}")
        st.markdown(f"**Proxima acao sugerida:** {customer['next_action']}")

        st.divider()
        st.markdown("**Assistente IA para este atendimento**")
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
