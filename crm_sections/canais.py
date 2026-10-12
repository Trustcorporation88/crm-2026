"""Seção Canais — conversas e mensagens recebidas.

Extraída de crm_app.py sem mudança de lógica. `ctx` é o namespace do
script principal (dados filtrados, usuário, helpers de tela); as linhas
abaixo deixam explícito o que a seção consome.
"""

from __future__ import annotations

from typing import Any

import streamlit as st


def render(ctx: dict[str, Any]) -> None:
    import crm_components as ui

    # Imports do projeto resolvidos a cada renderização, como acontecia no
    # script principal (o Streamlit o reexecuta a cada clique). Assim um
    # módulo recarregado ou substituído em teste vale aqui também.
    from crm_backend import create_channel_ticket

    can_manage = ctx["can_manage"]
    customer_lookup = ctx["customer_lookup"]
    customers_df = ctx["customers_df"]
    ingest_message = ctx["ingest_message"]
    owner_options = ctx["owner_options"]
    queue_toast = ctx["queue_toast"]
    tickets_df = ctx["tickets_df"]
    user = ctx["user"]

    if not can_manage(user["role"], "channel"):
        st.error("Seu perfil nao possui permissao para intake de canais.")
        st.stop()
    _por_canal = tickets_df["channel"].value_counts() if not tickets_df.empty else {}
    st.markdown(
        ui.kpi_grid(
            [
                {"label": "WhatsApp", "value": int(_por_canal.get("WhatsApp", 0)), "caption": "Atendimentos recebidos.", "icon": "chat", "tone": "ok"},
                {"label": "E-mail", "value": int(_por_canal.get("Email", 0)), "caption": "Atendimentos recebidos.", "icon": "mail", "tone": "info"},
                {"label": "Formulário", "value": int(_por_canal.get("Formulario", 0)), "caption": "Atendimentos recebidos.", "icon": "assignment", "tone": "gold"},
                {"label": "Todos os canais", "value": len(tickets_df), "caption": "Total registrado.", "icon": "forum", "tone": "neutral"},
            ]
        ),
        unsafe_allow_html=True,
    )

    col_form, col_last = st.columns([1.35, 1], gap="medium")

    with col_form, st.container(border=True):
        st.markdown(ui.card_title("Registrar atendimento recebido", "edit_note"), unsafe_allow_html=True)
        st.caption("Cliente falou com você por WhatsApp, e-mail ou formulário? Registre aqui e vira um atendimento.")
        st.info("ℹ️ O recebimento automático de WhatsApp e e-mail ainda não está conectado. Por enquanto: escolha a aba do canal por onde o cliente falou, cole a mensagem que ele enviou e clique em «Abrir atendimento». Nada se perde — o contato vira um ticket ligado ao cliente.")
        tabs = st.tabs(["WhatsApp", "Email", "Formulario"])
        channel_config = {
            "WhatsApp": {"sla": 4, "category": "Relacionamento"},
            "Email": {"sla": 12, "category": "Atendimento"},
            "Formulario": {"sla": 8, "category": "Inbound"},
        }
        for tab, channel in zip(tabs, ["WhatsApp", "Email", "Formulario"]):
            with tab:
                with st.form(f"intake-{channel.lower()}"):
                    existing_customer = st.selectbox("Cliente já cadastrado (opcional)", [""] + customers_df["name"].tolist(), key=f"existing-{channel}")
                    customer_name = st.text_input("Ou cadastre um novo cliente (nome)", key=f"new-customer-{channel}")
                    subject = st.text_input("Assunto (do que se trata)", key=f"subject-{channel}")
                    owner = st.selectbox("Responsável pelo atendimento", owner_options, key=f"owner-{channel}")
                    priority = st.selectbox("Prioridade", ["Baixa", "Media", "Alta", "Critica"], key=f"priority-{channel}")
                    city = st.text_input("Cidade", value="Sao Paulo" if channel != "Email" else "Austin", key=f"city-{channel}")
                    country = st.selectbox("Pais", ["Brasil", "Estados Unidos"], key=f"country-{channel}")
                    note = st.text_area("Mensagem que o cliente enviou (cole aqui)", key=f"message-{channel}")
                    uploaded = st.file_uploader("Anexar conversa (opcional: .txt, .csv, .json, .eml)", type=["txt", "csv", "json", "eml"], key=f"upload-{channel}")
                    submitted = st.form_submit_button(f"Abrir atendimento ({channel})", type="primary")
                if submitted and subject and (existing_customer or customer_name):
                    uploaded_text = ingest_message(uploaded)
                    payload = {
                        "customer_id": customers_df.loc[customers_df["name"] == existing_customer, "customer_id"].iloc[0] if existing_customer else "",
                        "customer_name": customer_name or existing_customer,
                        "subject": subject,
                        "channel": channel,
                        "priority": priority,
                        "owner": owner,
                        "sla_hours": channel_config[channel]["sla"],
                        "category": channel_config[channel]["category"],
                        "message": note or uploaded_text or subject,
                        "city": city,
                        "country": country,
                        "segment": "Lead inbound",
                    }
                    customer_id, ticket_id = create_channel_ticket(
                        payload,
                        actor=user,
                        source=f"ui-canal-{channel.lower()}",
                    )
                    queue_toast(f"Atendimento registrado! Cliente {customer_id}, ticket {ticket_id}.")
                    st.rerun()

    with col_last, st.container(border=True):
        st.markdown(ui.card_title("Últimos atendimentos", "history"), unsafe_allow_html=True)
        latest = tickets_df.sort_values("opened_at", ascending=False).head(8)
        _icons = {"WhatsApp": "chat", "Email": "mail", "Formulario": "assignment"}
        st.markdown(
            ui.list_block(
                [
                    ui.agenda_row(
                        r["subject"],
                        f"{customer_lookup.get(r['customer_id'], {}).get('name', r['customer_id'])} · {r['owner']}",
                        ui.priority_tone(r["priority"]),
                        ui.pill(r["channel"], "neutral"),
                        ico=_icons.get(r["channel"], "forum"),
                    )
                    for _, r in latest.iterrows()
                ],
                "Nenhum atendimento ainda.",
            ),
            unsafe_allow_html=True,
        )
