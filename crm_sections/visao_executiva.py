"""Seção Visão Executiva — KPIs e relatório configurável.

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
    from crm_backend import EXEC_REPORT_DEFAULT_GROUP_BY, EXEC_REPORT_DEFAULT_KPIS, set_exec_report_config

    EXEC_GROUP_BY_OPTIONS = ctx["EXEC_GROUP_BY_OPTIONS"]
    EXEC_KPI_CATALOG = ctx["EXEC_KPI_CATALOG"]
    _exec_report_config = ctx["_exec_report_config"]
    _exec_selected_kpis = ctx["_exec_selected_kpis"]
    filtered_tickets = ctx["filtered_tickets"]
    queue_toast = ctx["queue_toast"]
    tasks_df = ctx["tasks_df"]
    user = ctx["user"]

    with st.expander("⚙️ Personalizar relatório", expanded=False):
        st.caption(
            "Escolha quais indicadores aparecem em destaque no topo da tela e por "
            "qual campo agrupar o gráfico de carga. Fica salvo na sua conta."
        )
        _kpi_labels = {kpi_id: catalog_entry[0] for kpi_id, catalog_entry in EXEC_KPI_CATALOG.items()}
        _group_labels = {key: entry[0] for key, entry in EXEC_GROUP_BY_OPTIONS.items()}
        with st.form("exec-report-settings"):
            _chosen_kpi_labels = st.multiselect(
                "Indicadores em destaque",
                options=list(_kpi_labels.values()),
                default=[_kpi_labels[k] for k in _exec_selected_kpis if k in _kpi_labels],
            )
            _current_group_label = _group_labels.get(
                _exec_report_config["group_by"], _group_labels["owner"]
            )
            _chosen_group_label = st.selectbox(
                "Agrupar gráfico de carga por",
                options=list(_group_labels.values()),
                index=list(_group_labels.values()).index(_current_group_label),
            )
            _save_clicked = st.form_submit_button("Salvar preferências", type="primary")
        if _save_clicked:
            _label_to_kpi_id = {label: kpi_id for kpi_id, label in _kpi_labels.items()}
            _new_kpis = [_label_to_kpi_id[label] for label in _chosen_kpi_labels] or list(
                EXEC_REPORT_DEFAULT_KPIS
            )
            _group_label_to_key = {label: key for key, label in _group_labels.items()}
            _new_group_by = _group_label_to_key.get(_chosen_group_label, EXEC_REPORT_DEFAULT_GROUP_BY)
            set_exec_report_config(user, _new_kpis, _new_group_by)
            queue_toast("Preferências da Visão Executiva salvas.", icon="⚙️")
            st.rerun()

    left, right = st.columns([1.2, 0.8])
    with left, st.container(border=True):
        st.markdown(ui.card_title("Panorama operacional", "dashboard"), unsafe_allow_html=True)
        summary = pd.DataFrame(
            [
                {"KPI": label, "Valor": compute(), "Leitura": caption}
                for label, compute, caption in EXEC_KPI_CATALOG.values()
            ]
        )
        st.dataframe(summary, width="stretch", hide_index=True)
        _group_label, _group_field = EXEC_GROUP_BY_OPTIONS.get(
            _exec_report_config["group_by"], EXEC_GROUP_BY_OPTIONS["owner"]
        )
        st.caption(f"Carga de tickets por {_group_label.lower()}")
        owner_load = (
            filtered_tickets.groupby(_group_field).size().reset_index(name="tickets")
            if not filtered_tickets.empty and _group_field in filtered_tickets.columns
            else pd.DataFrame(columns=[_group_field, "tickets"])
        )
        if not owner_load.empty:
            st.bar_chart(
                owner_load.set_index(_group_field),
                horizontal=True,
                color="#2563eb",
                height=max(160, 56 * len(owner_load)),
            )
    with right, st.container(border=True):
        st.markdown(ui.card_title("Proximas acoes", "event"), unsafe_allow_html=True)
        _prox = tasks_df.sort_values("due_date").head(6).to_dict("records")
        st.markdown(
            ui.list_block(
                [
                    ui.agenda_row(
                        item["task"],
                        f"{item['owner']} · {item['entity']}",
                        ui.priority_tone(item.get("priority")),
                        ui.pill(str(item["due_date"]), "neutral"),
                        ico="event",
                    )
                    for item in _prox
                ],
                "Nenhuma ação agendada.",
            ),
            unsafe_allow_html=True,
        )
