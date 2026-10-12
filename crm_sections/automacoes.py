"""Seção Automações — regras que criam tarefas.

Extraída de crm_app.py sem mudança de lógica. `ctx` é o namespace do
script principal (dados filtrados, usuário, helpers de tela); as linhas
abaixo deixam explícito o que a seção consome.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st


def render(ctx: dict[str, Any]) -> None:
    # Imports do projeto resolvidos a cada renderização, como acontecia no
    # script principal (o Streamlit o reexecuta a cada clique). Assim um
    # módulo recarregado ou substituído em teste vale aqui também.
    from crm_backend import has_permission, run_automations
    from crm_ux import format_date_br, last_activity_by_customer

    data = ctx["data"]
    filtered_customers = ctx["filtered_customers"]
    filtered_deals = ctx["filtered_deals"]
    filtered_tickets = ctx["filtered_tickets"]
    queue_toast = ctx["queue_toast"]
    tasks_df = ctx["tasks_df"]
    user = ctx["user"]

    from automation_rules import RULES_CATALOG, evaluate_rules, summarize_proposals

    _pode_automatizar = has_permission(user["role"], "automation.run")
    _ultima_atividade = last_activity_by_customer(data.get("interactions", pd.DataFrame()))

    with st.container(border=True):
        st.markdown('<div class="section-title">Regras ativas</div>', unsafe_allow_html=True)
        st.caption(
            "Estas regras varrem a operação e criam tarefas para quem é responsável. "
            "Rodar de novo **não duplica**: cada tarefa tem nome único por registro."
        )
        _escolhidas = []
        for _regra in RULES_CATALOG:
            _ligada = st.checkbox(
                f"**{_regra['name']}**",
                value=True,
                key=f"regra-{_regra['id']}",
                help=_regra["description"],
            )
            st.caption(_regra["description"])
            if _ligada:
                _escolhidas.append(_regra["id"])

    _todas = evaluate_rules(
        deals=filtered_deals,
        tickets=filtered_tickets,
        customers=filtered_customers,
        last_activity=_ultima_atividade,
        enabled=set(_escolhidas),
    )
    # Já viraram tarefa numa execução anterior: mostrar como "cuidando", não
    # como pendência. Automação que repete o mesmo alerta todo dia vira ruído.
    _ja_criadas = set(tasks_df["task"]) if not tasks_df.empty else set()
    _propostas = [p for p in _todas if p.task not in _ja_criadas]
    _existentes = [p for p in _todas if p.task in _ja_criadas]
    _nomes_regras = {r["id"]: r["name"] for r in RULES_CATALOG}

    st.markdown(" ")
    with st.container(border=True):
        st.markdown('<div class="section-title">Prévia — o que será criado agora</div>', unsafe_allow_html=True)
        if _existentes:
            st.caption(
                f"↻ {len(_existentes)} situação(ões) já tem tarefa aberta — não serão duplicadas."
            )
        if not _propostas:
            st.success("Nada novo: tudo o que as regras encontraram já virou tarefa. 🎉")
        else:
            _resumo = summarize_proposals(_propostas)
            _cols = st.columns(len(_resumo) or 1)
            for _col, (_rid, _qtd) in zip(_cols, _resumo.items()):
                _col.metric(_nomes_regras.get(_rid, _rid).split("→")[0].strip(), _qtd)

            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Tarefa": p.task,
                            "Responsável": p.owner,
                            "Prazo": format_date_br(p.due_date),
                            "Prioridade": p.priority,
                            "Por quê": p.reason,
                        }
                        for p in _propostas
                    ]
                ),
                width="stretch",
                hide_index=True,
            )

            if _pode_automatizar:
                def _executar_automacoes() -> None:
                    resultado = run_automations(_propostas, actor=user, source="ui-automacoes")
                    criadas, puladas = len(resultado["created"]), len(resultado["skipped"])
                    if criadas:
                        queue_toast(
                            f"{criadas} tarefa(s) criada(s)."
                            + (f" {puladas} já existiam." if puladas else ""),
                            icon="⚡",
                        )
                    else:
                        queue_toast("Tudo já estava criado — nada duplicado.", icon="✅")

                st.button(
                    f"⚡ Executar automações ({len(_propostas)})",
                    key="run_automations",
                    type="primary",
                    on_click=_executar_automacoes,
                )
            else:
                st.caption("🔒 Seu perfil não pode executar automações. Fale com um administrador.")
