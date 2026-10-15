"""Seção Clientes 360 — lista, ficha e linha do tempo.

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
    from crm_backend import add_customer, add_interaction, get_lead_research_history
    from crm_receita import apply_lookup_to_form, lookup_cnpj
    from crm_ux import (
        account_summary_text,
        build_customer_timeline,
        deal_health,
        esc,
        fill_message_template,
        find_duplicates,
        format_brl,
        format_cpf_cnpj,
        format_date_br,
        last_activity_by_customer,
        next_best_action,
        render_activity_timeline,
        render_document_field,
        render_duplicate_warning,
        render_next_action,
        render_related_records,
        whatsapp_link,
    )
    from deepseek_assistant import deepseek_configured
    from lead_research import research_lead, serper_configured

    can_manage = ctx["can_manage"]
    currency = ctx["currency"]
    customers_df = ctx["customers_df"]
    filtered_customers = ctx["filtered_customers"]
    filtered_deals = ctx["filtered_deals"]
    filtered_tickets = ctx["filtered_tickets"]
    interactions_df = ctx["interactions_df"]
    owner_options = ctx["owner_options"]
    queue_toast = ctx["queue_toast"]
    render_empty_state = ctx["render_empty_state"]
    render_metric_cards = ctx["render_metric_cards"]
    user = ctx["user"]

    if can_manage(user["role"], "customer"):
        with st.expander("Nova conta", expanded=False):
            # Documento fora do st.form para validar o dígito verificador
            # enquanto o usuário digita — dentro do form só haveria feedback
            # depois do submit, quando o erro já custou o preenchimento inteiro.
            new_name = st.text_input("Nome da conta", key="new_customer_name")
            doc_col, lookup_col = st.columns([0.72, 0.28])
            with doc_col:
                new_document, document_valid = render_document_field(
                    "CPF / CNPJ",
                    key="new_customer_document",
                    help_text="Validado pelo dígito verificador antes de gravar.",
                )
            def _fill_from_receita() -> None:
                """Consulta a Receita e preenche o formulário.

                Roda como callback porque escreve em chaves de widgets já
                instanciados — o que só é permitido antes da renderização
                seguinte.
                """
                lookup = lookup_cnpj(st.session_state.get("new_customer_document", ""))
                if not lookup.success:
                    st.session_state["_receita_error"] = lookup.message
                    return
                st.session_state["_receita_error"] = ""
                for field_name, field_value in apply_lookup_to_form(lookup).items():
                    st.session_state[f"new_customer_{field_name}"] = field_value
                aviso = "" if lookup.is_active else f" Atenção: situação cadastral {lookup.situacao}."
                queue_toast(f"Dados de «{lookup.display_name}» preenchidos.{aviso}", icon="🏢")

            with lookup_col:
                st.markdown("<div style='height:1.8rem'></div>", unsafe_allow_html=True)
                st.button(
                    "Buscar na Receita",
                    key="lookup_cnpj_btn",
                    width="stretch",
                    help="Preenche nome, segmento e cidade a partir do CNPJ.",
                    disabled=not document_valid,
                    on_click=_fill_from_receita,
                )

            if st.session_state.get("_receita_error"):
                st.warning(st.session_state["_receita_error"])

            # Duplicado detectado na criação custa muito menos que deduplicar depois.
            duplicates = find_duplicates(customers_df, name=new_name, document=new_document)
            render_duplicate_warning(duplicates)

            with st.form("new-customer-form"):
                # As chaves permitem que a consulta de CNPJ preencha os campos.
                st.session_state.setdefault("new_customer_segment", "Servicos")
                st.session_state.setdefault("new_customer_city", "Sao Paulo")
                new_phone = st.text_input(
                    "Telefone / WhatsApp (com DDD)", key="new_customer_phone",
                    placeholder="(11) 98765-4321",
                )
                segment = st.text_input("Segmento", key="new_customer_segment")
                city = st.text_input("Cidade", key="new_customer_city")
                country = st.selectbox("Pais", ["Brasil", "Estados Unidos"])
                owner = st.selectbox("Owner da conta", owner_options)
                channel = st.selectbox("Canal preferencial", ["WhatsApp", "Email", "Telefone", "Portal", "Campanha"])
                next_action = st.text_input("Proxima acao", value="Agendar qualificacao inicial")
                confirm_duplicate = (
                    st.checkbox("Já verifiquei: não é duplicado, pode criar assim mesmo.")
                    if duplicates
                    else True
                )
                submitted = st.form_submit_button("Criar conta", type="primary")

            if submitted:
                if not new_name:
                    st.error("Informe o nome da conta.")
                elif new_document and not document_valid:
                    st.error("Corrija o CPF/CNPJ antes de criar a conta.")
                elif duplicates and not confirm_duplicate:
                    st.error("Confirme que não é duplicado para prosseguir.")
                else:
                    add_customer(
                        {
                            "name": new_name,
                            "document": new_document,
                            "phone": new_phone,
                            "segment": segment,
                            "city": city,
                            "country": country,
                            "owner": owner,
                            "status": "Novo",
                            "health_score": 72,
                            "lifetime_value": 0,
                            "channel": channel,
                            "next_action": next_action,
                            "source": "Manual",
                        },
                        actor=user,
                        source="ui-cliente-novo",
                    )
                    queue_toast(f"Conta «{new_name}» criada. Selecione-a abaixo para ver a ficha 360.")
                    st.rerun()

    if filtered_customers.empty:
        render_empty_state("Nenhuma conta encontrada para os filtros atuais.")
    else:
        # ------------------------------------------------------------------
        # Lista da base
        #
        # Esta tela só tinha o seletor abaixo, que mostra uma conta por vez.
        # Não havia, em nenhum lugar do sistema, uma lista de clientes:
        # chamados tinham tabela, campanhas tinham, usuários tinham — clientes
        # não. Para responder "quantos clientes eu tenho e quem são" era
        # preciso abrir o seletor e ler as opções uma a uma.
        #
        # A lista sai de `filtered_customers`, então respeita a visibilidade
        # por login: um vendedor vê a própria carteira, o administrador vê a
        # base inteira.
        # ------------------------------------------------------------------
        aba_lista, aba_ficha = st.tabs(["Base de clientes", "Ficha da conta"])

        with aba_lista:
            with st.container(border=True):
                st.markdown(ui.card_title("Sua base", "groups"), unsafe_allow_html=True)

                _busca_conta = st.text_input(
                    "Filtrar a lista",
                    key="lista_clientes_busca",
                    placeholder="Filtrar por nome, cidade, segmento ou responsável…",
                    label_visibility="collapsed",
                )

                _lista = filtered_customers.copy()
                if _busca_conta.strip():
                    _termo = _busca_conta.strip().lower()
                    _mascara = None
                    for _coluna in ("name", "city", "segment", "owner", "status"):
                        _parcial = _lista[_coluna].astype(str).str.lower().str.contains(
                            _termo, regex=False
                        )
                        _mascara = _parcial if _mascara is None else (_mascara | _parcial)
                    _lista = _lista[_mascara]

                render_metric_cards([
                    ("Clientes", str(len(_lista)), "No recorte atual."),
                    (
                        "Carteira",
                        currency(_lista["lifetime_value"].sum() if not _lista.empty else 0),
                        "Soma do valor de vida.",
                    ),
                    (
                        "Saúde média",
                        f"{int(_lista['health_score'].mean())}/100" if not _lista.empty else "—",
                        "Quanto menor, mais risco.",
                    ),
                ])

                if _lista.empty:
                    render_empty_state(f'Nenhum cliente encontrado para «{_busca_conta}».')
                else:
                    _tabela = pd.DataFrame({
                        "Cliente": _lista["name"],
                        "Segmento": _lista["segment"],
                        "Cidade": _lista["city"],
                        "Responsável": _lista["owner"],
                        "Situação": _lista["status"],
                        "Saúde": _lista["health_score"],
                        "Valor de vida": _lista["lifetime_value"].map(currency),
                        "Próxima ação": _lista["next_action"],
                    })
                    _tabela_ord = _tabela.sort_values("Saúde").reset_index(drop=True)
                    _evento = st.dataframe(
                        _tabela_ord,
                        width="stretch",
                        hide_index=True,
                        on_select="rerun",
                        selection_mode="single-row",
                        key="clientes_tabela",
                        column_config={
                            "Saúde": st.column_config.ProgressColumn("Saúde", format="%d", min_value=0, max_value=100),
                        },
                    )
                    _linhas_sel = list(_evento.selection.rows) if _evento is not None else []
                    if _linhas_sel:
                        _nome_sel = str(_tabela_ord.iloc[_linhas_sel[0]]["Cliente"])
                        st.session_state["ficha_conta"] = _nome_sel
                        st.success(f"**{_nome_sel}** selecionada. Abra a aba «Ficha da conta» para ver a ficha completa.")
                    st.caption(
                        "Ordenada pela saúde da conta — quem está em risco aparece primeiro. "
                        "Clique numa linha para pré-carregar a ficha; clique no título de uma coluna para reordenar."
                    )


        with aba_ficha:
            if st.session_state.get("ficha_conta") not in filtered_customers["name"].tolist():
                st.session_state.pop("ficha_conta", None)
            customer_name = st.selectbox("Selecionar conta", filtered_customers["name"].tolist(), key="ficha_conta")
            customer = filtered_customers[filtered_customers["name"] == customer_name].iloc[0].to_dict()
            account_id = customer["customer_id"]
            account_tickets = filtered_tickets[filtered_tickets["customer_id"] == account_id]
            account_deals = filtered_deals[filtered_deals["customer_id"] == account_id]

            account_last_activity = last_activity_by_customer(interactions_df).get(account_id)
            account_stale = {
                row["deal_id"]
                for row in account_deals.to_dict("records")
                if deal_health(row["stage"], account_last_activity).is_stale
            } if not account_deals.empty else set()

            _tom_status = {"Ativo": "ok", "Risco": "danger", "Novo": "info", "Expansao": "gold"}.get(str(customer.get("status")), "neutral")
            st.markdown(
                ui.profile_header(
                    customer["name"],
                    f"{customer.get('segment', '')} · {customer.get('city', '')} · {customer.get('country', '')} · Responsável: {customer.get('owner', '')}",
                    [(customer.get("status"), _tom_status), (customer.get("channel"), "neutral")],
                ),
                unsafe_allow_html=True,
            )

            # A conta abre pelo que exige decisão, não pelo cadastro.
            render_next_action(
                next_best_action(
                    customer,
                    account_deals,
                    account_tickets,
                    last_activity=account_last_activity,
                )
            )

            header_cols = st.columns(4)
            header_cols[0].metric("Saúde da conta", f"{customer['health_score']}/100")
            header_cols[1].metric("Valor em pipeline", format_brl(
                account_deals["value"].sum() if not account_deals.empty else 0
            ))
            header_cols[2].metric("Lifetime value", format_brl(customer["lifetime_value"]))
            header_cols[3].metric("Chamados abertos", int(
                (account_tickets["status"] != "Resolvido").sum() if not account_tickets.empty else 0
            ))

            st.markdown(" ")
            # Linha do tempo como conteúdo principal; cadastro em painel lateral.
            left, right = st.columns([1.35, 0.65])

            with left, st.container(border=True):
                st.markdown(ui.card_title("Linha do tempo", "timeline"), unsafe_allow_html=True)

                if can_manage(user["role"], "customer"):
                    with st.form(f"log-interaction-{account_id}", clear_on_submit=True):
                        note_cols = st.columns([0.28, 0.72])
                        note_channel = note_cols[0].selectbox(
                            "Canal", ["Nota", "Telefone", "WhatsApp", "Email", "Reunião"],
                            key="log_channel",
                        )
                        note_title = note_cols[1].text_input(
                            "Registrar interação", placeholder="O que aconteceu com este cliente?",
                            key="log_title",
                        )
                        note_body = st.text_area("Detalhes (opcional)", key="log_body", height=68)
                        logged = st.form_submit_button("Registrar", type="primary")

                    if logged and note_title.strip():
                        add_interaction(
                            account_id,
                            note_title.strip(),
                            note_body.strip(),
                            channel=note_channel,
                            owner=user.get("full_name", user["username"]),
                            event_type="note" if note_channel == "Nota" else note_channel.lower(),
                        )
                        queue_toast("Interação registrada na linha do tempo.", icon="📝")
                        st.rerun()
                    elif logged:
                        st.error("Descreva a interação antes de registrar.")

                render_activity_timeline(
                    build_customer_timeline(interactions_df, account_id),
                    empty_message=(
                        "Nenhuma interação registrada ainda. Use o campo acima para começar "
                        "o histórico desta conta."
                    ),
                )

            with right:
                # --- WhatsApp sem API da Meta ---
                # O fluxo da operação: preparar a mensagem aqui, abrir o WhatsApp
                # com ela pronta (link wa.me) e anexar o resumo baixado.
                with st.container(border=True):
                    st.markdown(ui.card_title("WhatsApp", "chat"), unsafe_allow_html=True)

                    _tel = str(customer.get("phone", "") or "")
                    if not _tel:
                        _tel = st.text_input(
                            "Telefone (com DDD)",
                            key=f"wa_phone_{account_id}",
                            placeholder="(11) 98765-4321",
                            help="A conta ainda não tem telefone. Informe para abrir a conversa.",
                        )

                    _modelo = st.text_area(
                        "Mensagem",
                        key=f"wa_msg_{account_id}",
                        value=fill_message_template(
                            "Olá, {nome}! Aqui é {responsavel}, da Trust. Tudo bem?",
                            customer,
                            sender=user.get("full_name", ""),
                        ),
                        height=80,
                    )

                    _link = whatsapp_link(_tel, _modelo)
                    if _link:
                        st.link_button("💬 Abrir conversa no WhatsApp", _link, width="stretch")
                    elif _tel:
                        st.caption("⚠️ Telefone inválido — confira o DDD e o número.")
                    else:
                        st.caption("Informe o telefone para habilitar a conversa.")

                    st.download_button(
                        "⬇️ Baixar resumo da conta (.txt)",
                        data=account_summary_text(
                            customer,
                            account_deals,
                            account_tickets,
                            build_customer_timeline(interactions_df, account_id),
                        ),
                        file_name=f"resumo-{account_id}.txt",
                        mime="text/plain",
                        width="stretch",
                        help="Texto pronto para anexar ou colar na conversa.",
                    )

                    def _registrar_envio_wa() -> None:
                        add_interaction(
                            account_id,
                            "Mensagem enviada por WhatsApp",
                            st.session_state.get(f"wa_msg_{account_id}", ""),
                            channel="WhatsApp",
                            owner=user.get("full_name", user["username"]),
                            event_type="whatsapp",
                        )
                        queue_toast("Envio registrado na linha do tempo.", icon="💬")

                    st.button(
                        "Registrar envio no histórico",
                        key=f"wa_log_{account_id}",
                        on_click=_registrar_envio_wa,
                        width="stretch",
                    )

                st.markdown(" ")
                with st.container(border=True):
                    st.markdown(ui.card_title("Agente de pesquisa", "travel_explore"), unsafe_allow_html=True)
                    st.caption(
                        "Pesquisa pública sobre este lead antes de alguém do time falar com ele. "
                        "Só registra o que confirmar, sempre com a fonte. Se não achar nada "
                        "confiável, diz isso em vez de inventar."
                    )
                    # Cita só a chave que realmente falta: mandar configurar uma que já
                    # existe faz a pessoa perder tempo procurando problema onde não há.
                    _faltando = [
                        _nome
                        for _nome, _ok in (
                            ("SERPER_API_KEY", serper_configured()),
                            ("DEEPSEEK_API_KEY", deepseek_configured()),
                        )
                        if not _ok
                    ]
                    if _faltando:
                        st.caption(
                            f"Configure {' e '.join(_faltando)} para habilitar a pesquisa."
                        )
                    else:
                        if st.button(
                            "Pesquisar este lead", key=f"agent-research-btn-{account_id}", width="stretch"
                        ):
                            with st.spinner("Pesquisando fontes públicas..."):
                                _resultado = research_lead(account_id, name=customer["name"])
                            if _resultado["error"]:
                                st.error(_resultado["error"])
                            elif not _resultado["facts"]:
                                st.info("Nada confiável encontrado nas fontes públicas para este lead.")
                            else:
                                queue_toast(f"{len(_resultado['facts'])} fato(s) confirmado(s).", icon="🔎")
                            st.rerun()

                    _historico_pesquisa = get_lead_research_history(account_id)
                    if _historico_pesquisa:
                        for _run in _historico_pesquisa[:5]:
                            _quando = format_date_br(_run["created_at"][:10]) if _run.get("created_at") else ""
                            if _run["facts"]:
                                with st.expander(f"{_quando} · {_run['facts_count']} fato(s) confirmado(s)"):
                                    for _fato in _run["facts"]:
                                        st.markdown(f"- {esc(_fato['fact'])}")
                                        if _fato.get("source_url"):
                                            st.caption(f"Fonte: {_fato['source_url']}")
                            elif _run["status"] == "erro":
                                st.caption(f"{_quando} · pesquisa falhou: {_run.get('error_message', '')}")
                            else:
                                st.caption(f"{_quando} · nada confiável encontrado")

                st.markdown(" ")
                with st.container(border=True):
                    st.markdown(ui.card_title("Relacionados", "link"), unsafe_allow_html=True)
                    render_related_records(account_deals, account_tickets, stale_ids=account_stale)

                st.markdown(" ")
                with st.container(border=True):
                    st.markdown(ui.card_title("Cadastro", "badge"), unsafe_allow_html=True)
                    cadastro = [
                        ("CPF / CNPJ", format_cpf_cnpj(customer.get("document", "")) or "—"),
                        ("Segmento", customer["segment"]),
                        ("Mercado", customer["country"]),
                        ("Cidade", customer["city"]),
                        ("Canal preferencial", customer["channel"]),
                        ("Responsável", customer["owner"]),
                        ("Status", customer["status"]),
                        ("Última compra", format_date_br(customer["last_purchase"])),
                    ]
                    for rotulo, valor in cadastro:
                        st.markdown(
                            f"<div style='display:flex;justify-content:space-between;gap:1rem;"
                            f"padding:0.35rem 0;border-bottom:1px solid #eceff3;'>"
                            f"<span style='opacity:0.6;font-size:0.85rem;'>{esc(rotulo)}</span>"
                            f"<span style='font-size:0.88rem;text-align:right;'>{esc(valor)}</span></div>",
                            unsafe_allow_html=True,
                        )
