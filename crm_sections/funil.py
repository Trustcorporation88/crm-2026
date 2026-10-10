"""Seção Funil Comercial — kanban, negócios e fechamento.

Extraída de crm_app.py sem mudança de lógica. `ctx` é o namespace do
script principal (dados filtrados, usuário, helpers de tela); as linhas
abaixo deixam explícito o que a seção consome.
"""

from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd
import streamlit as st


def render(ctx: dict[str, Any]) -> None:
    # Imports do projeto resolvidos a cada renderização, como acontecia no
    # script principal (o Streamlit o reexecuta a cada clique). Assim um
    # módulo recarregado ou substituído em teste vale aqui também.
    from crm_backend import add_deal, close_deal, update_deal_fields, update_deal_stage
    from crm_ux import (
        LOSS_REASONS,
        build_kanban_containers,
        can_advance_to_stage,
        deal_closing_label,
        deal_health,
        diff_kanban,
        format_brl,
        format_compact_brl,
        format_date_br,
        last_activity_by_customer,
        loss_analysis,
        open_deals_for_closing,
        pipeline_totals,
        render_deal_card,
        render_empty_module,
        render_pipeline_summary,
        render_stage_header,
        summarize_stage,
    )

    KANBAN_STYLE = ctx["KANBAN_STYLE"]
    can_manage = ctx["can_manage"]
    customer_lookup = ctx["customer_lookup"]
    customers_df = ctx["customers_df"]
    data = ctx["data"]
    filtered_deals = ctx["filtered_deals"]
    owner_options = ctx["owner_options"]
    queue_toast = ctx["queue_toast"]
    sort_items = ctx["sort_items"]
    user = ctx["user"]

    if can_manage(user["role"], "deal"):
        with st.expander("Nova oportunidade", expanded=False):
            with st.form("new-deal-form"):
                customer_name = st.selectbox("Cliente da oportunidade", customers_df["name"].tolist())
                name = st.text_input("Nome da oportunidade")
                stage = st.selectbox("Etapa", ["Descoberta", "Proposta", "Negociacao", "Fechado ganho"])
                value = st.number_input("Valor", min_value=0.0, step=1000.0)
                probability = st.slider("Probabilidade", 0, 100, 50)
                owner = st.selectbox("Owner", owner_options)
                source = st.selectbox("Origem", ["Inbound", "Customer Success", "Upsell", "Renovacao", "Outbound"])
                close_date = st.date_input("Fechamento previsto")
                submitted = st.form_submit_button("Criar oportunidade", type="primary")
            if submitted and name:
                # Portão de etapa: cada etapa cobra apenas o que ela pressupõe.
                _candidate = {
                    "value": value,
                    "close_date": close_date.isoformat() if close_date else "",
                    "probability": probability,
                    "owner": owner,
                }
                _allowed, _reason = can_advance_to_stage(_candidate, stage)
            if submitted and name and not _allowed:
                st.error(_reason)
            elif submitted and name:
                customer_id = customers_df.loc[customers_df["name"] == customer_name, "customer_id"].iloc[0]
                add_deal(
                    {
                        "customer_id": customer_id,
                        "name": name,
                        "stage": stage,
                        "value": value,
                        "probability": probability,
                        "owner": owner,
                        "close_date": close_date.isoformat(),
                        "source": source,
                    },
                    actor=user,
                    source="ui-pipeline-novo",
                )
                queue_toast(f"Oportunidade «{name}» criada na etapa {stage}.")
                st.rerun()

    ordered_stages = ["Descoberta", "Proposta", "Negociacao", "Fechado ganho", "Fechado perdido"]
    open_stages = ["Descoberta", "Proposta", "Negociacao"]

    # Última interação por cliente alimenta o indicador de estagnação.
    last_activity = last_activity_by_customer(data.get("interactions", pd.DataFrame()))
    health_by_deal = {
        item["deal_id"]: deal_health(item["stage"], last_activity.get(item["customer_id"]))
        for item in filtered_deals.to_dict("records")
    } if not filtered_deals.empty else {}
    stale_ids = {deal_id for deal_id, health in health_by_deal.items() if health.is_stale}

    with st.container(border=True):
        st.markdown('<div class="section-title">Resumo do funil</div>', unsafe_allow_html=True)
        render_pipeline_summary(pipeline_totals(filtered_deals, open_stages=open_stages))
        if stale_ids:
            st.warning(
                f"{len(stale_ids)} negociação(ões) sem contato além do limite da etapa. "
                "Elas aparecem com marca vermelha no funil."
            )

    st.markdown(" ")
    with st.container(border=True):
        st.markdown('<div class="section-title">Funil comercial</div>', unsafe_allow_html=True)
        _erro_kanban = st.session_state.pop("kanban_error", "")
        if _erro_kanban:
            st.error(_erro_kanban)

        _pode_arrastar = (
            can_manage(user["role"], "deal")
            and sort_items is not None
            and not filtered_deals.empty
        )
        _kanban_ok = False
        if _pode_arrastar:
            # Kanban arrastável (padrão Pipedrive): soltar o cartão em outra
            # coluna muda a etapa na hora — com portão de etapa no drop.
            try:
                st.caption(
                    "Arraste um cartão para outra coluna para mudar a etapa — salva na hora. "
                    "🔴 = sem contato além do limite da etapa."
                )
                _deals_records = filtered_deals.to_dict("records")
                _nomes = {cid: str(info["name"]) for cid, info in customer_lookup.items()}
                containers, _header_etapa, _rotulo_deal = build_kanban_containers(
                    _deals_records, _nomes, ordered_stages, stale_ids=stale_ids
                )
                _assinatura = hashlib.md5(  # assinatura do quadro para invalidar o componente; não é uso criptográfico
                    repr(sorted((str(d["deal_id"]), str(d["stage"])) for d in _deals_records)).encode(),
                    usedforsecurity=False,
                ).hexdigest()[:10]
                _nonce = int(st.session_state.get("kanban_nonce", 0))
                _resultado = sort_items(
                    containers,
                    multi_containers=True,
                    direction="horizontal",
                    custom_style=KANBAN_STYLE,
                    key=f"kanban-{_assinatura}-{_nonce}",
                )
                _kanban_ok = True
                for _deal_id, _etapa_de, _etapa_para in diff_kanban(
                    containers, _resultado, _header_etapa, _rotulo_deal
                ):
                    _registro = next(
                        (d for d in _deals_records if str(d["deal_id"]) == _deal_id), None
                    )
                    if _registro is None:
                        continue
                    _ok, _motivo = can_advance_to_stage(_registro, _etapa_para)
                    # Nonce novo remonta o board: ou com o dado salvo, ou de
                    # volta ao original quando o portão de etapa barrar.
                    st.session_state["kanban_nonce"] = _nonce + 1
                    if not _ok:
                        st.session_state["kanban_error"] = _motivo
                    else:
                        update_deal_stage(_deal_id, _etapa_para, actor=user, source="ui-kanban")
                        queue_toast(
                            f"«{_registro['name']}» movida: {_etapa_de} → {_etapa_para}.",
                            icon="✅",
                        )
                    st.rerun()
            except Exception:
                _kanban_ok = False

        if not _kanban_ok:
            # Perfis sem edição (ou ambiente sem o componente): visão estática.
            stage_columns = st.columns(len(ordered_stages))
            for col, stage in zip(stage_columns, ordered_stages):
                with col:
                    render_stage_header(summarize_stage(filtered_deals, stage, stale_ids=stale_ids))
                    stage_items = filtered_deals[filtered_deals["stage"] == stage] if not filtered_deals.empty else filtered_deals
                    for item in stage_items.to_dict("records"):
                        customer = customer_lookup[item["customer_id"]]
                        render_deal_card(item, customer["name"], health_by_deal[item["deal_id"]])

    # Ganho/Perdido em um clique (padrão Pipedrive). O «perdido» exige o motivo
    # — é o dado que ensina por que os negócios morrem.
    if can_manage(user["role"], "deal"):
        _abertos = (
            open_deals_for_closing(filtered_deals.to_dict("records"))
            if not filtered_deals.empty
            else []
        )
        st.markdown(" ")
        with st.container(border=True):
            st.markdown('<div class="section-title">Fechar negócio</div>', unsafe_allow_html=True)
            if not _abertos:
                st.caption("Nenhuma negociação aberta — tudo já foi ganho ou perdido.")
            else:
                _rotulos = {
                    deal_closing_label(d, customer_lookup[d["customer_id"]]["name"]): str(d["deal_id"])
                    for d in _abertos
                }
                st.session_state["_close_labels"] = _rotulos
                _escolha = st.selectbox(
                    "Negociação",
                    list(_rotulos.keys()),
                    key="close_deal_pick",
                )
                _deal_sel = _rotulos.get(_escolha)

                def _fechar_ganho() -> None:
                    did = st.session_state.get("_close_labels", {}).get(
                        st.session_state.get("close_deal_pick")
                    )
                    if not did:
                        return
                    try:
                        close_deal(did, "ganho", actor=user, source="ui-funil")
                        st.session_state.pop("closing_lost", None)
                        queue_toast("Negócio marcado como GANHO! 🎉", icon="✅")
                    except Exception as exc:  # noqa: BLE001
                        st.session_state["close_deal_error"] = str(exc)

                def _abrir_perdido() -> None:
                    st.session_state["closing_lost"] = st.session_state.get("_close_labels", {}).get(
                        st.session_state.get("close_deal_pick")
                    )

                _acoes = st.columns(2)
                _acoes[0].button(
                    "✅ Marcar ganho",
                    key="btn_ganho",
                    type="primary",
                    use_container_width=True,
                    on_click=_fechar_ganho,
                )
                _acoes[1].button(
                    "❌ Marcar perdido",
                    key="btn_perdido",
                    use_container_width=True,
                    on_click=_abrir_perdido,
                )

                # Fluxo do «perdido»: só aparece após pedir para marcar perda,
                # e exige um motivo antes de confirmar.
                if st.session_state.get("closing_lost") == _deal_sel and _deal_sel:
                    st.markdown("---")
                    st.caption("Por que perdemos? O motivo alimenta a análise de perdas.")
                    st.selectbox("Motivo da perda", LOSS_REASONS, key="loss_reason_pick")
                    st.text_input(
                        "Detalhe (opcional — obrigatório se «Outro»)",
                        key="loss_reason_detail",
                        placeholder="Ex.: perdeu para a Concorrente X por prazo de entrega",
                    )

                    def _confirmar_perdido() -> None:
                        did = st.session_state.get("closing_lost")
                        motivo = st.session_state.get("loss_reason_pick", "")
                        detalhe = (st.session_state.get("loss_reason_detail") or "").strip()
                        if motivo == "Outro":
                            motivo_final = detalhe
                        elif detalhe:
                            motivo_final = f"{motivo} — {detalhe}"
                        else:
                            motivo_final = motivo
                        if not motivo_final:
                            st.session_state["close_deal_error"] = "Descreva o motivo da perda."
                            return
                        try:
                            close_deal(did, "perdido", reason=motivo_final, actor=user, source="ui-funil")
                            st.session_state.pop("closing_lost", None)
                            st.session_state["loss_reason_detail"] = ""
                            queue_toast("Negócio marcado como perdido. Motivo registrado.", icon="📝")
                        except Exception as exc:  # noqa: BLE001
                            st.session_state["close_deal_error"] = str(exc)

                    def _cancelar_perdido() -> None:
                        st.session_state.pop("closing_lost", None)

                    _conf = st.columns(2)
                    _conf[0].button(
                        "Confirmar perda",
                        key="btn_confirma_perdido",
                        type="primary",
                        use_container_width=True,
                        on_click=_confirmar_perdido,
                    )
                    _conf[1].button(
                        "Cancelar",
                        key="btn_cancela_perdido",
                        use_container_width=True,
                        on_click=_cancelar_perdido,
                    )

            if st.session_state.get("close_deal_error"):
                st.error(st.session_state.pop("close_deal_error"))

    # Análise de perdas: agrega os motivos que o fechamento coleta.
    _perdas = loss_analysis(filtered_deals)
    if _perdas["lost_count"] > 0:
        st.markdown(" ")
        with st.container(border=True):
            st.markdown('<div class="section-title">Análise de perdas</div>', unsafe_allow_html=True)
            _m = st.columns(3)
            _m[0].metric("Negócios perdidos", _perdas["lost_count"])
            _m[1].metric("Valor perdido", format_compact_brl(_perdas["lost_value"]))
            _m[2].metric(
                "Taxa de perda",
                f"{_perdas['loss_rate']:.0f}%".replace(".", ","),
                help="Perdidos ÷ (ganhos + perdidos). Quanto menor, melhor.",
            )
            if _perdas["by_reason"]:
                st.caption("Por que perdemos — motivo × quantidade (o custo de cada motivo ao lado)")
                _mot_df = pd.DataFrame(_perdas["by_reason"]).set_index("reason")
                st.bar_chart(
                    _mot_df[["count"]].rename(columns={"count": "negócios"}),
                    horizontal=True,
                    color="#dc2626",
                    height=max(140, 52 * len(_mot_df)),
                )
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "Motivo": item["reason"],
                                "Negócios": item["count"],
                                "Valor perdido": format_brl(item["value"]),
                                "% das perdas": f"{item['pct']:.0f}%".replace(".", ","),
                            }
                            for item in _perdas["by_reason"]
                        ]
                    ),
                    width="stretch",
                    hide_index=True,
                )

    # Edição inline + ações em massa (estilo Attio/HubSpot)
    if can_manage(user["role"], "deal") and not filtered_deals.empty:
        st.markdown(" ")
        with st.container(border=True):
            st.markdown('<div class="section-title">Edição rápida e ações em massa</div>', unsafe_allow_html=True)
            st.caption(
                "Edite direto na célula — salva sozinho. Marque a coluna ✓ para agir em massa nos selecionados."
            )
            _grade_base = filtered_deals[
                ["deal_id", "name", "value", "probability", "owner", "close_date"]
            ].copy()
            _grade_base["close_date"] = pd.to_datetime(_grade_base["close_date"], errors="coerce").dt.date
            _grade_base.insert(0, "✓", False)

            _grade = st.data_editor(
                _grade_base,
                key="deals_editor",
                hide_index=True,
                width="stretch",
                disabled=["deal_id"],
                column_config={
                    "✓": st.column_config.CheckboxColumn("✓", help="Selecionar para ação em massa", width="small"),
                    "deal_id": st.column_config.TextColumn("Código", width="small"),
                    "name": st.column_config.TextColumn("Oportunidade", required=True),
                    "value": st.column_config.NumberColumn("Valor (R$)", min_value=0.0, step=1000.0, format="%.0f"),
                    "probability": st.column_config.NumberColumn("Prob. (%)", min_value=0, max_value=100, step=5),
                    "owner": st.column_config.SelectboxColumn("Responsável", options=owner_options, required=True),
                    "close_date": st.column_config.DateColumn("Fechamento", format="DD/MM/YYYY"),
                },
            )

            # Autosave: compara a grade editada com o banco e aplica a diferença.
            _erros_edicao: list[str] = []
            _salvos = 0
            for _orig, _novo in zip(_grade_base.to_dict("records"), _grade.to_dict("records")):
                _mudancas: dict[str, Any] = {}
                if str(_novo.get("name", "")) != str(_orig.get("name", "")):
                    _mudancas["name"] = _novo.get("name")
                if float(_novo.get("value") or 0) != float(_orig.get("value") or 0):
                    _mudancas["value"] = _novo.get("value")
                if int(_novo.get("probability") or 0) != int(_orig.get("probability") or 0):
                    _mudancas["probability"] = _novo.get("probability")
                if str(_novo.get("owner", "")) != str(_orig.get("owner", "")):
                    _mudancas["owner"] = _novo.get("owner")
                if _novo.get("close_date") != _orig.get("close_date") and _novo.get("close_date"):
                    _mudancas["close_date"] = _novo["close_date"].isoformat()
                if not _mudancas:
                    continue
                try:
                    if update_deal_fields(str(_orig["deal_id"]), _mudancas, actor=user, source="ui-inline"):
                        _salvos += 1
                except (ValueError, PermissionError) as exc:
                    _erros_edicao.append(f"{_orig['deal_id']}: {exc}")
            if _erros_edicao:
                st.error(" · ".join(_erros_edicao))
            if _salvos:
                queue_toast(
                    f"{_salvos} oportunidade(s) atualizada(s)." if _salvos > 1 else "Oportunidade atualizada.",
                    icon="💾",
                )
                st.rerun()

            # Barra de ações em massa
            _selecionados = [str(r["deal_id"]) for r in _grade.to_dict("records") if r.get("✓")]
            if _selecionados:
                st.markdown(f"**{len(_selecionados)} selecionada(s)** — aplicar em massa:")
                _b1, _b2, _b3 = st.columns([1.4, 1.4, 0.9])
                _acao_massa = _b1.selectbox(
                    "Ação",
                    ["Mudar responsável", "Mudar etapa"],
                    key="bulk_action",
                    label_visibility="collapsed",
                )
                if _acao_massa == "Mudar responsável":
                    _alvo_massa = _b2.selectbox(
                        "Novo responsável", owner_options, key="bulk_owner", label_visibility="collapsed"
                    )
                else:
                    _alvo_massa = _b2.selectbox(
                        "Nova etapa", open_stages, key="bulk_stage", label_visibility="collapsed"
                    )

                def _aplicar_massa() -> None:
                    ids = list(_selecionados)
                    acao = st.session_state.get("bulk_action")
                    ok, barradas = 0, []
                    registros = {str(d["deal_id"]): d for d in filtered_deals.to_dict("records")}
                    for did in ids:
                        try:
                            if acao == "Mudar responsável":
                                update_deal_fields(
                                    did, {"owner": st.session_state.get("bulk_owner")},
                                    actor=user, source="ui-massa",
                                )
                                ok += 1
                            else:
                                destino = st.session_state.get("bulk_stage")
                                registro = registros.get(did, {})
                                pode, motivo = can_advance_to_stage(registro, str(destino))
                                if not pode:
                                    barradas.append(f"{did}: {motivo}")
                                    continue
                                update_deal_stage(did, str(destino), actor=user, source="ui-massa")
                                ok += 1
                        except (ValueError, PermissionError) as exc:
                            barradas.append(f"{did}: {exc}")
                    if ok:
                        queue_toast(f"Ação aplicada a {ok} oportunidade(s).", icon="⚡")
                    if barradas:
                        st.session_state["bulk_error"] = " · ".join(barradas)

                _b3.button(
                    f"Aplicar ({len(_selecionados)})",
                    key="bulk_apply",
                    type="primary",
                    use_container_width=True,
                    on_click=_aplicar_massa,
                )
            if st.session_state.get("bulk_error"):
                st.error(st.session_state.pop("bulk_error"))

    st.markdown(" ")
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Tabela de oportunidades</div>', unsafe_allow_html=True)
    deals_table = filtered_deals.copy()
    if not deals_table.empty:
        # Rótulos e formatos em pt-BR: "190000" não é como um vendedor lê valor.
        deals_table["Cliente"] = deals_table["customer_id"].map(lambda value: customer_lookup[value]["name"])
        deals_table["Situação"] = deals_table["deal_id"].map(
            lambda deal_id: health_by_deal[deal_id].label
        )
        deals_table["Valor"] = deals_table["value"].map(format_brl)
        deals_table["Fechamento"] = deals_table["close_date"].map(format_date_br)
        deals_table["Probabilidade"] = deals_table["probability"].map(lambda p: f"{p}%")
        deals_table["Motivo da perda"] = (
            deals_table["loss_reason"] if "loss_reason" in deals_table.columns else ""
        )
        st.dataframe(
            deals_table.rename(columns={
                "deal_id": "Código",
                "name": "Oportunidade",
                "stage": "Etapa",
                "owner": "Responsável",
            })[[
                "Código", "Cliente", "Oportunidade", "Etapa",
                "Valor", "Probabilidade", "Fechamento", "Responsável", "Situação",
                "Motivo da perda",
            ]],
            width="stretch",
            hide_index=True,
        )
    else:
        render_empty_module(
            "Nenhuma oportunidade no funil",
            "O funil comercial acompanha cada negociação da descoberta ao fechamento, "
            "mostrando valor previsto e sinalizando quem está sem contato há tempo demais.",
            action_label="abra «Nova oportunidade» acima para cadastrar a primeira.",
        )
    st.markdown('</div>', unsafe_allow_html=True)
