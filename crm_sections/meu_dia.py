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
    import crm_components as ui
    from crm_backend import complete_task
    from crm_ux import (
        build_day_agenda,
        build_task_queue,
        format_brl,
        format_date_br,
        onboarding_steps,
        queue_position_label,
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

    agenda = build_day_agenda(
        tasks_df,
        filtered_deals,
        filtered_tickets,
        interactions_df,
        owner=agenda_owner,
    )

    # Indicadores do dia numa faixa só, no topo.
    st.markdown(
        ui.kpi_grid(
            [
                {"label": "Tarefas atrasadas", "value": len(agenda.overdue_tasks), "caption": "Já passaram do prazo.", "icon": "alarm", "tone": "danger"},
                {"label": "Tarefas de hoje", "value": len(agenda.today_tasks), "caption": "Vencem hoje.", "icon": "task_alt", "tone": "info"},
                {"label": "Negociações paradas", "value": len(agenda.stale_deals), "caption": "Sem contato além do limite.", "icon": "hourglass_top", "tone": "warn"},
                {"label": "Chamados no limite do SLA", "value": len(agenda.sla_risk_tickets), "caption": "Precisam de resposta.", "icon": "support_agent", "tone": "gold"},
            ]
        ),
        unsafe_allow_html=True,
    )

    # st.container em vez de <div> aberta num bloco e fechada em outro: o
    # Streamlit sanitiza cada bloco de markdown isoladamente, então a div
    # ficava desbalanceada e o React perdia a referência do nó ao redesenhar
    # (NotFoundError em removeChild). Com colunas e métricas no meio, quebra.
    col_main, col_side = st.columns([1.6, 1], gap="medium")

    with col_main, st.container(border=True):
        st.markdown(ui.card_title("Prioridades do dia", "flag"), unsafe_allow_html=True)
        if agenda_owner:
            st.caption(f"Pendências de **{agenda_owner}**. Troque o responsável nos filtros globais.")
        else:
            st.caption("Pendências de **toda a equipe**. Escolha um responsável nos filtros globais para ver só as suas.")

        if agenda.is_empty:
            st.success("Nada pendente para hoje. Seu funil está em dia.")
        else:
            rows_overdue = [
                ui.agenda_row(
                    t.get("task", ""),
                    f"venceu há {t.get('days_late', 0)} dia(s)",
                    ui.priority_tone(t.get("priority")),
                    ui.pill(t.get("priority", ""), ui.priority_tone(t.get("priority"))),
                )
                for t in agenda.overdue_tasks
            ]
            rows_today = [
                ui.agenda_row(
                    t.get("task", ""),
                    "vence hoje",
                    ui.priority_tone(t.get("priority")),
                    ui.pill(t.get("priority", ""), ui.priority_tone(t.get("priority"))),
                )
                for t in agenda.today_tasks
            ]
            rows_sla = []
            for tk in agenda.sla_risk_tickets:
                consumido = float(tk.get("sla_consumed", 0) or 0)
                estourado = bool(tk.get("sla_breached"))
                rows_sla.append(
                    ui.agenda_row(
                        tk.get("subject", ""),
                        f"{int(consumido * 100)}% do prazo consumido",
                        "danger" if estourado else "warn",
                        ui.pill("Estourado" if estourado else "No limite", "danger" if estourado else "warn"),
                        progress=consumido,
                    )
                )
            rows_stale = [
                ui.agenda_row(
                    d.get("name", ""),
                    f"{d.get('stage', '')} · {d.get('health_label', '')}",
                    "warn",
                    ui.pill(format_brl(d.get("value")), "neutral"),
                )
                for d in agenda.stale_deals
            ]
            tab_over, tab_today, tab_sla, tab_stale = st.tabs(
                [
                    f"Atrasadas · {len(rows_overdue)}",
                    f"Hoje · {len(rows_today)}",
                    f"SLA · {len(rows_sla)}",
                    f"Sem contato · {len(rows_stale)}",
                ]
            )
            with tab_over:
                st.markdown(ui.list_block(rows_overdue, "Nenhuma tarefa atrasada."), unsafe_allow_html=True)
            with tab_today:
                st.markdown(ui.list_block(rows_today, "Nada vence hoje."), unsafe_allow_html=True)
            with tab_sla:
                st.markdown(ui.list_block(rows_sla, "Nenhum chamado perto do limite."), unsafe_allow_html=True)
            with tab_stale:
                st.markdown(ui.list_block(rows_stale, "Nenhuma negociação parada."), unsafe_allow_html=True)

    # --- Fila de execução (padrão HubSpot Task Queue / Close) ---
    # Modo "trabalhar a fila": uma tarefa por vez, com contexto, sem voltar à
    # lista entre cada item.
    _fila = build_task_queue(agenda)

    with col_side, st.container(border=True):
        st.markdown(ui.card_title("Fila de execução", "bolt", f"{len(_fila)} na fila"), unsafe_allow_html=True)

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

    with col_side:
        render_onboarding_checklist(
            onboarding_steps(customers_df, deals_df, tickets_df)
        )
