"""Seção Importar Dados — planilhas de outros sistemas.

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
    from crm_backend import bulk_import_customers, has_permission

    customers_df = ctx["customers_df"]
    owner_options = ctx["owner_options"]
    queue_toast = ctx["queue_toast"]
    user = ctx["user"]

    from csv_import import FIELD_SYNONYMS, IGNORE, analyze_import, guess_mapping, sample_csv

    _pode_importar = has_permission(user["role"], "customer.create")

    _etapa = 0 if st.session_state.get("import_csv") is None else 2
    st.markdown(ui.stepper(["Enviar planilha", "Mapear colunas", "Conferir e importar"], _etapa), unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown(ui.card_title("1. Enviar planilha de clientes", "upload_file"), unsafe_allow_html=True)
        st.caption(
            "Arquivo .csv com uma linha por cliente. A primeira linha deve ser o cabeçalho "
            "com os nomes das colunas — o sistema reconhece nomes comuns automaticamente."
        )
        st.download_button(
            "⬇️ Baixar planilha modelo",
            data=sample_csv(),
            file_name="modelo_importacao_clientes.csv",
            mime="text/csv",
        )
        _arquivo = st.file_uploader("Planilha (.csv)", type=["csv"], key="import_csv")

    if _arquivo is not None:
        try:
            _bruto = pd.read_csv(_arquivo, dtype=str, keep_default_na=False)
        except Exception:
            _arquivo.seek(0)
            try:
                _bruto = pd.read_csv(_arquivo, dtype=str, sep=";", keep_default_na=False)
            except Exception as exc:  # noqa: BLE001
                _bruto = pd.DataFrame()
                st.error(f"Não consegui ler o arquivo: {exc}")

        if not _bruto.empty:
            st.markdown(" ")
            with st.container(border=True):
                st.markdown(ui.card_title("2. Conferir o mapeamento das colunas", "compare_arrows"), unsafe_allow_html=True)
                st.caption(f"{len(_bruto)} linha(s) lida(s). Ajuste se alguma coluna foi para o campo errado.")
                _sugerido = guess_mapping(list(_bruto.columns))
                _opcoes = [IGNORE, *list(_bruto.columns)]
                _mapa: dict[str, str] = {}
                _map_cols = st.columns(2)
                for _i, _campo in enumerate(FIELD_SYNONYMS):
                    _rotulo = _campo.replace("name", "Nome").replace("document", "CPF/CNPJ")
                    _rotulo = _rotulo.replace("phone", "Telefone").replace("segment", "Segmento")
                    _rotulo = _rotulo.replace("city", "Cidade").replace("country", "País")
                    _rotulo = _rotulo.replace("owner", "Responsável").replace("status", "Status")
                    _atual = _sugerido.get(_campo, IGNORE)
                    _mapa[_campo] = _map_cols[_i % 2].selectbox(
                        _rotulo + (" *" if _campo == "name" else ""),
                        _opcoes,
                        index=_opcoes.index(_atual) if _atual in _opcoes else 0,
                        key=f"map-{_campo}",
                    )

                _resp_padrao = st.selectbox(
                    "Responsável para linhas sem responsável",
                    owner_options or [user["full_name"]],
                    key="import_owner_default",
                )

            _relatorio = analyze_import(
                _bruto,
                {k: v for k, v in _mapa.items() if v != IGNORE},
                existing_customers=customers_df,
                defaults={"owner": _resp_padrao, "country": "Brasil", "status": "Novo"},
            )
            _sumario = _relatorio.summary()

            st.markdown(" ")
            with st.container(border=True):
                st.markdown(ui.card_title("3. Prévia da importação", "preview"), unsafe_allow_html=True)
                _m = st.columns(4)
                _m[0].metric("Linhas", _sumario["total"])
                _m[1].metric("Prontas para importar", _sumario["validos"])
                _m[2].metric("Já existem", _sumario["duplicados"])
                _m[3].metric("Com erro", _sumario["invalidos"])

                if _relatorio.invalid:
                    with st.expander(f"❌ {len(_relatorio.invalid)} linha(s) recusada(s) — ver motivos", expanded=True):
                        st.dataframe(
                            pd.DataFrame(
                                [
                                    {"Linha": r.line, "Nome": r.data.get("name", ""), "Motivo": "; ".join(r.errors)}
                                    for r in _relatorio.invalid
                                ]
                            ),
                            width="stretch",
                            hide_index=True,
                        )
                if _relatorio.duplicates:
                    with st.expander(f"⚠️ {len(_relatorio.duplicates)} já existe(m) na base — serão ignoradas"):
                        st.dataframe(
                            pd.DataFrame(
                                [
                                    {
                                        "Linha": r.line,
                                        "Nome": r.data.get("name", ""),
                                        "Cliente existente": r.duplicate_of,
                                        "Motivo": "; ".join(r.warnings),
                                    }
                                    for r in _relatorio.duplicates
                                ]
                            ),
                            width="stretch",
                            hide_index=True,
                        )
                if _relatorio.valid:
                    st.caption("Estas entram no CRM:")
                    st.dataframe(
                        pd.DataFrame([r.data for r in _relatorio.valid]),
                        width="stretch",
                        hide_index=True,
                    )

            if _relatorio.valid and _pode_importar:
                _linhas_ok = [dict(r.data, _line=r.line) for r in _relatorio.valid]

                def _confirmar_importacao() -> None:
                    resultado = bulk_import_customers(_linhas_ok, actor=user, source="importacao-csv")
                    if resultado["created"]:
                        queue_toast(f"{len(resultado['created'])} cliente(s) importado(s).", icon="📥")
                    if resultado["failed"]:
                        st.session_state["import_error"] = " · ".join(
                            f"linha {f['linha']}: {f['erro']}" for f in resultado["failed"][:5]
                        )

                st.button(
                    f"📥 Importar {len(_relatorio.valid)} cliente(s)",
                    key="confirm_import",
                    type="primary",
                    on_click=_confirmar_importacao,
                )
            elif _relatorio.valid:
                st.caption("🔒 Seu perfil não pode criar clientes. Fale com um administrador.")

            if st.session_state.get("import_error"):
                st.error(st.session_state.pop("import_error"))
