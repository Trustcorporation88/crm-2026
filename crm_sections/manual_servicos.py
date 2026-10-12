"""Seção Manual de Serviços — guia de cada serviço.

Extraída de crm_app.py sem mudança de lógica. `ctx` é o namespace do
script principal (dados filtrados, usuário, helpers de tela); as linhas
abaixo deixam explícito o que a seção consome.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st


def render(ctx: dict[str, Any]) -> None:
    allowed_sections = ctx["allowed_sections"]
    navigate_to_section = ctx["navigate_to_section"]

    from services_catalog import (
        SERVICE_CATALOG,
        services_manual_markdown,
        services_manual_sections,
    )
    from services_catalog import (
        resolve_service_section as _manual_secao,
    )

    with st.container(border=True):
        st.markdown('<div class="section-title">Resumo rápido — 17 serviços e suas entregas</div>', unsafe_allow_html=True)
        _resumo = pd.DataFrame(
            [
                {
                    "Serviço": item["title"],
                    "Onde abre no menu": _manual_secao(str(item["id"])),
                    "O que entrega": item.get("resultado_esperado", ""),
                }
                for item in SERVICE_CATALOG
            ]
        )
        st.dataframe(_resumo, width="stretch", hide_index=True)
        st.download_button(
            "⬇️ Baixar manual completo (.md)",
            data=services_manual_markdown(),
            file_name="Trust_CRM_Catalogo_de_Servicos.md",
            mime="text/markdown",
            help="Versão em texto para compartilhar com a equipe",
        )

    for _categoria in services_manual_sections():
        st.markdown(" ")
        with st.container(border=True):
            st.markdown(
                f'<div class="section-title">{_categoria["icon"]} {_categoria["title"]}</div>',
                unsafe_allow_html=True,
            )
            st.caption(_categoria["tagline"])
            for _guia in _categoria["services"]:
                with st.expander(f'{_guia["title"]} — {_guia.get("resultado_esperado", "")}'):
                    st.markdown(f"**Quando usar:** {_guia.get('tagline', '')}")
                    st.markdown(f"**Objetivo:** {_guia.get('objetivo', '')}")
                    st.markdown(f"**Como funciona:** {_guia.get('resumo_geral', '')}")
                    st.success(f"✅ O que entrega: {_guia.get('resultado_esperado', '')}")
                    _passos = " → ".join(_guia.get("como_usar", []) or [])
                    _dados = ", ".join(_guia.get("dados_input", []) or [])
                    st.markdown(f"**Passo a passo:** {_passos}")
                    st.markdown(f"**Dados que usa:** {_dados}")
                    st.markdown(f"**Referência de mercado:** {_guia.get('benchmark', '')}")
                    if _guia.get("exemplo_pratico"):
                        st.info(f"💡 **Exemplo prático:** {_guia['exemplo_pratico']}")
                    if str(_guia["section"]) in allowed_sections:
                        if st.button(
                            f"Abrir {_guia['section']}",
                            key=f"manual-abrir-{_guia['id']}",
                            type="primary",
                        ):
                            navigate_to_section(str(_guia["section"]))
                    else:
                        st.caption("🔒 Disponível para outro perfil de acesso")
