"""Guia completo do serviço (4 blocos) + chat DeepSeek."""
from __future__ import annotations

from typing import Any, Callable

import streamlit as st

from deepseek_assistant import (
    build_general_system_prompt,
    build_service_system_prompt,
    chat_completion,
    deepseek_configured,
)
from services_catalog import service_guide_payload


def _chat_history_key(scope: str, service_id: str | None = None) -> str:
    if service_id:
        return f"deepseek_chat_{scope}_{service_id}"
    return f"deepseek_chat_{scope}_global"


def render_chat_panel(
    *,
    scope: str,
    service: dict[str, Any] | None = None,
    system_prompt: str | None = None,
) -> None:
    service_id = str(service["id"]) if service else None
    hist_key = _chat_history_key(scope, service_id)

    if hist_key not in st.session_state:
        st.session_state[hist_key] = []

    if not deepseek_configured():
        st.warning(
            "Configure **DEEPSEEK_API_KEY** no Render (Environment) para ativar o chat. "
            "Enquanto isso, use as abas Objetivo, Dados e Resultado deste guia."
        )
        return

    for msg in st.session_state[hist_key]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    placeholder = (
        f"Pergunte sobre «{service['title']}»..."
        if service
        else "Tire dúvidas sobre o CRM..."
    )
    if prompt := st.chat_input(placeholder, key=f"chat_input_{hist_key}"):
        st.session_state[hist_key].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        sys_prompt = system_prompt or (
            build_service_system_prompt(service) if service else build_general_system_prompt()
        )
        api_messages = [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state[hist_key]
        ]
        with st.chat_message("assistant"):
            with st.spinner("Consultando DeepSeek..."):
                answer, err = chat_completion(api_messages, system_prompt=sys_prompt)
            if err:
                st.error(err)
            else:
                st.markdown(answer or "")
                st.session_state[hist_key].append({"role": "assistant", "content": answer or ""})

    if st.session_state[hist_key] and st.button(
        "Limpar conversa", key=f"clear_{hist_key}", use_container_width=True
    ):
        st.session_state[hist_key] = []
        st.rerun()


@st.dialog("Guia do serviço", width="large")
def open_service_guide_dialog(
    service: dict[str, Any],
    navigate_fn: Callable[[str], None],
    resolve_fn: Callable[[str], str],
) -> None:
    guide = service_guide_payload(service)
    st.markdown(f"### {guide['title']}")
    st.caption(f"{guide['category']} · {guide['tagline']}")

    tab_obj, tab_exemplo, tab_dados, tab_resumo, tab_chat = st.tabs(
        [
            "1 · Objetivo",
            "2 · Exemplo prático",
            "3 · Como usar",
            "4 · Resumo geral",
            "Chat IA",
        ]
    )

    with tab_obj:
        st.markdown("#### 1) Para que serve")
        st.success(guide["objetivo"])
        st.markdown("**O que você ganha com isso**")
        st.info(guide["resultado_esperado"])

    with tab_exemplo:
        st.markdown("#### 2) Exemplo prático (situação real)")
        exemplo = guide.get("exemplo_pratico", "")
        if exemplo:
            st.success(exemplo)
        else:
            st.info(guide["resumo_geral"])
        st.caption(
            "Se a sua situação for parecida com essa, este é o serviço certo. "
            "Dúvidas? Use a aba «Chat IA»."
        )

    with tab_dados:
        st.markdown("#### 3) Como usar e quais dados informar")
        st.markdown("**Passo a passo no sistema**")
        for index, step in enumerate(guide["como_usar"], start=1):
            st.markdown(f"{index}. {step}")
        st.markdown("**Dados de entrada (obrigatórios ou recomendados)**")
        for item in guide["dados_input"]:
            st.markdown(f"- {item}")

    with tab_resumo:
        st.markdown("#### 4) Resumo geral do serviço")
        st.info(guide["resumo_geral"])
        if service.get("benchmark"):
            st.markdown("**Referência de mercado**")
            st.caption(str(service["benchmark"]))

    with tab_chat:
        st.markdown("#### Tire dúvidas com IA (DeepSeek)")
        st.caption("Perguntas sobre este serviço, campos e boas práticas.")
        render_chat_panel(scope="service", service=service)

    st.divider()
    action1, action2, action3 = st.columns(3)
    with action1:
        if st.button("Abrir módulo", type="primary", use_container_width=True):
            navigate_fn(resolve_fn(str(service["id"])))
    with action2:
        if st.button("Fechar", use_container_width=True):
            st.rerun()
    with action3:
        st.caption("Use ℹ️ em qualquer card do catálogo para reabrir este guia.")


def render_global_assistant() -> None:
    st.markdown("**Assistente Mr.Holmes**")
    st.caption("Dúvidas gerais sobre o CRM e como usar os módulos.")
    render_chat_panel(scope="global", service=None)
