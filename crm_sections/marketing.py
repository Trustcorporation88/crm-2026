"""Seção Marketing — campanhas e segmentos.

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
    from crm_backend import add_campaign

    campaigns_df = ctx["campaigns_df"]
    can_manage = ctx["can_manage"]
    currency = ctx["currency"]
    queue_toast = ctx["queue_toast"]
    user = ctx["user"]

    if can_manage(user["role"], "campaign"):
        with st.expander("Nova campanha", expanded=False):
            with st.form("new-campaign-form"):
                campaign = st.text_input("Campanha")
                channel = st.selectbox("Canal", ["Email", "WhatsApp", "Eventos", "Formulario", "Ads"])
                leads = st.number_input("Leads", min_value=0, step=1)
                qualified = st.number_input("Qualificados", min_value=0, step=1)
                conversion_rate = st.number_input("Taxa de conversao (%)", min_value=0.0, max_value=100.0, step=0.1)
                revenue = st.number_input("Receita atribuida", min_value=0.0, step=1000.0)
                submitted = st.form_submit_button("Salvar campanha", type="primary")
            if submitted and campaign:
                add_campaign(
                    {
                        "campaign": campaign,
                        "channel": channel,
                        "leads": leads,
                        "qualified": qualified,
                        "conversion_rate": conversion_rate,
                        "revenue": revenue,
                    },
                    actor=user,
                    source="ui-marketing-campanha",
                )
                queue_toast(f"Campanha «{campaign}» salva.")
                st.rerun()

    _leads = int(campaigns_df["leads"].sum()) if not campaigns_df.empty else 0
    _qual = int(campaigns_df["qualified"].sum()) if not campaigns_df.empty else 0
    _rev = float(campaigns_df["revenue"].sum()) if not campaigns_df.empty else 0.0
    _conv = float(campaigns_df["conversion_rate"].mean()) if not campaigns_df.empty else 0.0
    st.markdown(
        ui.kpi_grid(
            [
                {"label": "Campanhas", "value": len(campaigns_df), "caption": "Ativas na base.", "icon": "campaign", "tone": "info"},
                {"label": "Leads gerados", "value": f"{_leads:,}".replace(",", "."), "caption": f"{_qual} qualificados.", "icon": "person_add", "tone": "gold"},
                {"label": "Conversão média", "value": f"{_conv:.1f}%", "caption": "Entre as campanhas.", "icon": "swap_vert", "tone": "ok"},
                {"label": "Receita atribuída", "value": currency(_rev), "caption": "Contribuição das campanhas.", "icon": "payments", "tone": "ok"},
            ]
        ),
        unsafe_allow_html=True,
    )

    left, right = st.columns([1.05, 0.95])
    with left:
        with st.container(border=True):
            st.markdown(ui.card_title("Campanhas e contribuicao de receita", "campaign"), unsafe_allow_html=True)
            st.dataframe(campaigns_df.astype(str), width="stretch", hide_index=True)
        st.markdown(" ")
        with st.container(border=True):
            st.markdown(ui.card_title("Conversao por canal", "swap_vert"), unsafe_allow_html=True)
            channel_conversion = campaigns_df[["channel", "conversion_rate"]].groupby("channel").mean()
            st.bar_chart(
                channel_conversion,
                horizontal=True,
                color="#08a742",
                height=max(160, 56 * len(channel_conversion)),
            )
    with right:
        with st.container(border=True):
            st.markdown(ui.card_title("Segmentos recomendados", "category"), unsafe_allow_html=True)
            segments = [
                "Clientes em risco com ticket aberto nos ultimos 7 dias",
                "Contas ativas com health score acima de 80 e potencial de upsell",
                "Novos clientes de campanha com onboarding ainda em aberto",
                "Base Brasil com preferencia por WhatsApp e LTV acima de R$ 100 mil",
            ]
            st.markdown(
                ui.list_block([ui.agenda_row(seg, "", "gold", ico="group_work") for seg in segments]),
                unsafe_allow_html=True,
            )
        st.markdown(" ")
        with st.container(border=True):
            st.markdown(ui.card_title("Leitura de negocio", "insights"), unsafe_allow_html=True)
            best = campaigns_df.sort_values("conversion_rate", ascending=False).iloc[0]
            st.success(f"Melhor campanha atual: {best['campaign']} com {best['conversion_rate']}% de conversao e {currency(best['revenue'])} em receita atribuida.")
            st.warning("Proximo passo recomendado: conectar campanhas de reativacao aos tickets de churn e abrir handoff automatico para atendimento e vendas.")
