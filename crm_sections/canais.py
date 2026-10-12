"""Seção Canais — conversas e mensagens recebidas.

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
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Registrar atendimento recebido</div>', unsafe_allow_html=True)
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
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(" ")
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Últimos atendimentos registrados</div>', unsafe_allow_html=True)
    latest = tickets_df.sort_values("opened_at", ascending=False).head(8).copy()
    latest["cliente"] = latest["customer_id"].map(lambda value: customer_lookup.get(value, {}).get("name", value))
    st.dataframe(latest[["ticket_id", "cliente", "channel", "subject", "owner", "opened_at"]], width="stretch", hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)
