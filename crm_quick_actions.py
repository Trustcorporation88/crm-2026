"""Ações rápidas: «＋ Novo» no canto da tela, de qualquer módulo.

Cada ação abre uma janela (``st.dialog``) com o formulário curto e grava pelas
mesmas funções do backend que as telas usam (``add_ticket``, ``add_deal``), com
as mesmas permissões e o mesmo portão de etapa do funil. Criar cliente leva à
ficha de cadastro, que valida CPF/CNPJ e duplicidade.
"""

from __future__ import annotations

from typing import Any

import streamlit as st


def _fechar_menu() -> None:
    """O menu «＋ Novo» não fecha sozinho; trocar a chave o recria fechado."""
    st.session_state["qa_menu_n"] = int(st.session_state.get("qa_menu_n", 0)) + 1


def _ticket_dialog(ctx: dict[str, Any]) -> None:
    from crm_backend import add_ticket

    customers_df = ctx["customers_df"]
    owner_options = ctx["owner_options"]
    user = ctx["user"]
    queue_toast = ctx["queue_toast"]

    @st.dialog("Novo chamado")
    def _abrir() -> None:
        if customers_df.empty:
            st.info("Cadastre um cliente antes de abrir um chamado.")
            return
        cliente = st.selectbox("Cliente", customers_df["name"].tolist(), key="qa_t_cliente")
        assunto = st.text_input("Assunto", key="qa_t_assunto", placeholder="Do que se trata?")
        prioridade = st.segmented_control("Prioridade", ["Baixa", "Media", "Alta", "Critica"], default="Media", key="qa_t_prio") or "Media"
        c1, c2 = st.columns(2)
        canal = c1.selectbox("Canal", ["WhatsApp", "Email", "Telefone", "Portal", "Chat", "Formulario"], key="qa_t_canal")
        categoria = c2.selectbox("Categoria", ["Geral", "Integracao", "Onboarding", "Operacao", "Produto", "Financeiro"], key="qa_t_cat")
        dono = st.selectbox("Responsavel", owner_options, key="qa_t_dono")
        resumo = st.text_area("Resumo do atendimento", key="qa_t_resumo", height=90)
        if st.button("Criar chamado", type="primary", key="qa_t_criar", width="stretch"):
            if not assunto.strip():
                st.error("Informe o assunto do chamado.")
                return
            customer_id = customers_df.loc[customers_df["name"] == cliente, "customer_id"].iloc[0]
            add_ticket(
                {
                    "customer_id": customer_id,
                    "subject": assunto.strip(),
                    "channel": canal,
                    "priority": prioridade,
                    "owner": dono,
                    "category": categoria,
                    "sla_hours": 8,
                    "message": resumo or assunto.strip(),
                },
                actor=user,
                source="ui-acao-rapida",
            )
            queue_toast(f"Chamado criado para {cliente}.", icon="🎫")
            _fechar_menu()
            st.rerun()

    _abrir()


def _deal_dialog(ctx: dict[str, Any]) -> None:
    from crm_backend import add_deal
    from crm_ux import can_advance_to_stage

    customers_df = ctx["customers_df"]
    owner_options = ctx["owner_options"]
    user = ctx["user"]
    queue_toast = ctx["queue_toast"]

    @st.dialog("Nova oportunidade")
    def _abrir() -> None:
        if customers_df.empty:
            st.info("Cadastre um cliente antes de abrir uma oportunidade.")
            return
        cliente = st.selectbox("Cliente", customers_df["name"].tolist(), key="qa_d_cliente")
        nome = st.text_input("Nome da oportunidade", key="qa_d_nome")
        c1, c2 = st.columns(2)
        etapa = c1.selectbox("Etapa", ["Descoberta", "Proposta", "Negociacao", "Fechado ganho"], key="qa_d_etapa")
        valor = c2.number_input("Valor (R$)", min_value=0.0, step=1000.0, key="qa_d_valor")
        prob = st.slider("Probabilidade", 0, 100, 50, key="qa_d_prob")
        c3, c4 = st.columns(2)
        dono = c3.selectbox("Responsavel", owner_options, key="qa_d_dono")
        origem = c4.selectbox("Origem", ["Inbound", "Customer Success", "Upsell", "Renovacao", "Outbound"], key="qa_d_origem")
        fechamento = st.date_input("Fechamento previsto", key="qa_d_fecha")
        if st.button("Criar oportunidade", type="primary", key="qa_d_criar", width="stretch"):
            if not nome.strip():
                st.error("Dê um nome à oportunidade.")
                return
            candidato = {
                "value": valor,
                "close_date": fechamento.isoformat() if fechamento else "",
                "probability": prob,
                "owner": dono,
            }
            permitido, motivo = can_advance_to_stage(candidato, etapa)
            if not permitido:
                st.error(motivo)
                return
            customer_id = customers_df.loc[customers_df["name"] == cliente, "customer_id"].iloc[0]
            add_deal(
                {
                    "customer_id": customer_id,
                    "name": nome.strip(),
                    "stage": etapa,
                    "value": valor,
                    "probability": prob,
                    "owner": dono,
                    "close_date": fechamento.isoformat(),
                    "source": origem,
                },
                actor=user,
                source="ui-acao-rapida",
            )
            queue_toast(f"Oportunidade «{nome.strip()}» criada em {etapa}.", icon="💼")
            _fechar_menu()
            st.rerun()

    _abrir()


def render(ctx: dict[str, Any]) -> None:
    """Desenha o botão «＋ Novo» com as ações a que o perfil do usuário tem direito."""
    can_manage = ctx["can_manage"]
    role = ctx["user"]["role"]
    acoes: list[tuple[str, str, str]] = []
    if can_manage(role, "ticket"):
        acoes.append(("qa_ticket", ":material/confirmation_number: Novo chamado", "ticket"))
    if can_manage(role, "deal"):
        acoes.append(("qa_deal", ":material/handshake: Nova oportunidade", "deal"))
    if can_manage(role, "customer"):
        acoes.append(("qa_customer", ":material/person_add: Novo cliente", "customer"))
    if not acoes:
        return
    escolhida = ""
    with st.popover(":material/add: Novo", key=f"qa_menu_{int(st.session_state.get('qa_menu_n', 0))}"):
        for chave, rotulo, nome in acoes:
            if st.button(rotulo, key=chave, width="stretch"):
                escolhida = nome
    if escolhida == "ticket":
        _ticket_dialog(ctx)
    elif escolhida == "deal":
        _deal_dialog(ctx)
    elif escolhida == "customer":
        ctx["navigate_to_section"]("Clientes 360")
