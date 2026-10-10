"""Seção Meu Dia — agenda e fila de execução do vendedor.

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
    from crm_backend import complete_task
    from crm_ux import (
        build_day_agenda,
        build_task_queue,
        format_date_br,
        onboarding_steps,
        queue_position_label,
        render_day_agenda,
        render_onboarding_checklist,
    )

    customers_df = ctx["customers_df"]
    deals_df = ctx["deals_df"]
    filtered_deals = ctx["filtered_deals"]
    filtered_tickets = ctx["filtered_tickets"]
    interactions_df = ctx["interactions_df"]
    queue_toast = ctx["queue_toast"]
    selected_owner = ctx["selected_owner"]
    tasks_df = ctx["tasks_df"]
    tickets_df = ctx["tickets_df"]
    user = ctx["user"]

    # Superfície de trabalho diário: responde "o que eu faço agora?" sem
    # obrigar o usuário a varrer módulo por módulo.
    agenda_owner = None if selected_owner == "Todos" else selected_owner

    # st.container em vez de <div> aberta num bloco e fechada em outro: o
    # Streamlit sanitiza cada bloco de markdown isoladamente, então a div
    # ficava desbalanceada e o React perdia a referência do nó ao redesenhar
    # (NotFoundError em removeChild). Com colunas e métricas no meio, quebra.
    with st.container(border=True):
        if agenda_owner:
            st.caption(f"Pendências de **{agenda_owner}**. Troque o responsável nos filtros globais.")
        else:
            st.caption("Pendências de **toda a equipe**. Escolha um responsável nos filtros globais para ver só as suas.")

        render_day_agenda(
            build_day_agenda(
                tasks_df,
                filtered_deals,
                filtered_tickets,
                interactions_df,
                owner=agenda_owner,
            )
        )

    # --- Fila de execução (padrão HubSpot Task Queue / Close) ---
    # Modo "trabalhar a fila": uma tarefa por vez, com contexto, sem voltar à
    # lista entre cada item.
    _agenda_fila = build_day_agenda(
        tasks_df, filtered_deals, filtered_tickets, interactions_df, owner=agenda_owner
    )
    _fila = build_task_queue(_agenda_fila)

    st.markdown(" ")
    with st.container(border=True):
        st.markdown('<div class="section-title">Fila de execução</div>', unsafe_allow_html=True)

        if not _fila:
            st.caption("Nenhuma tarefa pendente para trabalhar em fila. 🎉")
            st.session_state.pop("fila_ativa", None)
            st.session_state.pop("fila_indice", None)
        elif not st.session_state.get("fila_ativa"):
            st.caption(
                f"{len(_fila)} tarefa(s) esperando. O modo fila mostra uma por vez, "
                "com contexto, e avança quando você conclui."
            )

            def _entrar_na_fila() -> None:
                st.session_state["fila_ativa"] = True
                st.session_state["fila_indice"] = 0

            st.button("▶ Trabalhar a fila", key="fila_entrar", on_click=_entrar_na_fila)
        else:
            _indice = min(st.session_state.get("fila_indice", 0), len(_fila) - 1)
            _atual = _fila[_indice]

            st.caption(queue_position_label(_indice, len(_fila)))
            st.markdown(f"### {_atual.get('task', '')}")

            _meta_cols = st.columns(3)
            _origem = "🔴 Atrasada" if _atual.get("_origem") == "atrasada" else "📅 Para hoje"
            _meta_cols[0].metric("Situação", _origem.split(" ", 1)[1])
            _meta_cols[1].metric("Prioridade", str(_atual.get("priority", "—")))
            _meta_cols[2].metric("Vencimento", format_date_br(_atual.get("due_date")))

            _entidade = str(_atual.get("entity", "") or "")
            if _entidade:
                st.caption(f"Relacionada a: {_entidade}")

            def _concluir_e_avancar() -> None:
                nome = _atual.get("task", "")
                if complete_task(nome, actor=user):
                    queue_toast(f"Tarefa «{nome}» concluída.", icon="✅")
                # O índice não avança: a tarefa concluída sai da fila no
                # próximo rerun, e a seguinte assume a mesma posição.

            def _pular() -> None:
                st.session_state["fila_indice"] = _indice + 1
                if st.session_state["fila_indice"] >= len(_fila):
                    st.session_state["fila_indice"] = 0

            def _sair() -> None:
                st.session_state.pop("fila_ativa", None)
                st.session_state.pop("fila_indice", None)

            _acao_cols = st.columns(3)
            _acao_cols[0].button(
                "✅ Concluir e avançar", key="fila_concluir",
                type="primary", on_click=_concluir_e_avancar,
            )
            _acao_cols[1].button("⏭ Pular", key="fila_pular", on_click=_pular)
            _acao_cols[2].button("✕ Sair da fila", key="fila_sair", on_click=_sair)

    st.markdown(" ")
    render_onboarding_checklist(
        onboarding_steps(customers_df, deals_df, tickets_df)
    )
