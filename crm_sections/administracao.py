"""Seção Administração — usuários, papéis e auditoria.

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
    from crm_backend import (
        DB_PATH,
        create_user,
        get_actions,
        get_permissions,
        get_roles,
        get_webhook_verify_token,
        list_users,
        reset_user_password,
        update_role_permissions,
        update_user,
    )

    audit_df = ctx["audit_df"]
    can_manage = ctx["can_manage"]
    customers_df = ctx["customers_df"]
    interactions_df = ctx["interactions_df"]
    queue_toast = ctx["queue_toast"]
    role_permissions_df = ctx["role_permissions_df"]
    tickets_df = ctx["tickets_df"]
    user = ctx["user"]
    users_df = ctx["users_df"]
    webhook_df = ctx["webhook_df"]

    if not can_manage(user["role"], "admin"):
        st.error("Seu perfil nao possui permissao para area de administracao.")
        st.stop()
    st.markdown(
        ui.kpi_grid(
            [
                {"label": "Usuários ativos", "value": int(users_df[users_df["is_active"] == 1].shape[0]), "caption": "Com acesso liberado.", "icon": "badge", "tone": "ok"},
                {"label": "Contas", "value": int(customers_df.shape[0]), "caption": "Clientes na base.", "icon": "groups", "tone": "gold"},
                {"label": "Tickets", "value": int(tickets_df.shape[0]), "caption": "Atendimentos registrados.", "icon": "support_agent", "tone": "info"},
                {"label": "Interações", "value": int(interactions_df.shape[0]), "caption": "Histórico 360.", "icon": "forum", "tone": "neutral"},
            ]
        ),
        unsafe_allow_html=True,
    )

    aba_geral, aba_contas, aba_perm, aba_audit, aba_hooks = st.tabs(
        ["Visão geral", "Contas de acesso", "Permissões", "Auditoria", "Webhooks"]
    )

    with aba_geral, st.container(border=True):
        st.markdown(ui.card_title("Governança", "shield"), unsafe_allow_html=True)
        st.dataframe(
            pd.DataFrame(
                [
                    {"Item": "Banco", "Valor": DB_PATH},
                    {"Item": "Usuarios ativos", "Valor": int(users_df[users_df["is_active"] == 1].shape[0])},
                    {"Item": "Contas", "Valor": int(customers_df.shape[0])},
                    {"Item": "Tickets", "Valor": int(tickets_df.shape[0])},
                    {"Item": "Interacoes", "Valor": int(interactions_df.shape[0])},
                ]
            ),
            width="stretch",
            hide_index=True,
        )
        st.markdown("**Usuarios e perfis**")
        st.dataframe(users_df, width="stretch", hide_index=True)
        st.caption("Para criar, editar ou redefinir senha, use a aba «Contas de acesso».")

    with aba_contas:
        # ------------------------------------------------------------------
        # Contas de acesso
        #
        # Antes deste painel não havia como criar um usuário: as contas nasciam
        # uma única vez, no seed, quando o banco era criado do zero. Quem perdia a
        # senha também não tinha para onde recorrer.
        # ------------------------------------------------------------------
        if can_manage(user["role"], "admin"):
            with st.container(border=True):
                st.markdown(ui.card_title("Contas de acesso", "manage_accounts"), unsafe_allow_html=True)

                _contas = list_users()
                _papeis = get_roles()

                aba_nova, aba_editar, aba_senha = st.tabs(
                    ["Criar conta", "Editar conta", "Redefinir senha"]
                )

                with aba_nova:
                    with st.form("form-nova-conta"):
                        _login = st.text_input(
                            "Login",
                            placeholder="ex.: joao",
                            help="Só letras, números, hífen ou sublinhado. É o identificador "
                                 "permanente da pessoa — não muda mais depois de criado.",
                        )
                        _nome = st.text_input("Nome completo", placeholder="ex.: João Pereira")
                        _papel = st.selectbox("Papel", _papeis, key="novo-papel")
                        _senha = st.text_input(
                            "Senha inicial", type="password",
                            help="Mínimo de 8 caracteres. Peça para a pessoa trocar no primeiro acesso.",
                        )
                        if st.form_submit_button("Criar conta", type="primary"):
                            try:
                                criado = create_user(
                                    username=_login, full_name=_nome, role=_papel,
                                    password=_senha, actor=user,
                                )
                                queue_toast(f"Conta '{criado['username']}' criada.", icon="✅")
                                st.rerun()
                            except (ValueError, PermissionError) as exc:
                                st.error(str(exc))

                with aba_editar:
                    if not _contas:
                        st.info("Nenhuma conta cadastrada.")
                    else:
                        _rotulos = {
                            f"{c['full_name']} ({c['username']})": c for c in _contas
                        }
                        _escolha = st.selectbox("Conta", list(_rotulos), key="editar-conta")
                        _alvo = _rotulos[_escolha]

                        with st.form("form-editar-conta"):
                            _novo_nome = st.text_input("Nome completo", value=_alvo["full_name"])
                            # A chave carrega o login de propósito.
                            #
                            # Com uma chave fixa ("editar-papel"), o valor guardado na
                            # sessão vence o argumento `index` — regra do Streamlit. Ao
                            # trocar de conta no seletor de cima, o campo continuava
                            # exibindo o papel da conta ANTERIOR, e salvar gravava esse
                            # papel na conta nova. Editar uma pessoa mudava o papel de
                            # outra, sem aviso: quem abrisse a própria conta de admin e
                            # depois fosse desativar um vendedor promovia o vendedor a
                            # administrador. Com a chave por conta, cada uma tem seu
                            # próprio estado e o `index` volta a valer.
                            _novo_papel = st.selectbox(
                                "Papel", _papeis,
                                index=_papeis.index(_alvo["role"]) if _alvo["role"] in _papeis else 0,
                                key=f"editar-papel-{_alvo['username']}",
                            )
                            _ativa = st.checkbox("Conta ativa", value=bool(_alvo["is_active"]))
                            st.caption(
                                "Renomear é seguro: a posse dos registros é ligada ao login, "
                                "não ao nome. O rótulo é atualizado nas telas automaticamente."
                            )
                            if st.form_submit_button("Salvar alterações", type="primary"):
                                try:
                                    update_user(
                                        username=_alvo["username"], full_name=_novo_nome,
                                        role=_novo_papel, is_active=_ativa, actor=user,
                                    )
                                    queue_toast("Conta atualizada.", icon="✅")
                                    st.rerun()
                                except (ValueError, PermissionError) as exc:
                                    st.error(str(exc))

                with aba_senha:
                    if not _contas:
                        st.info("Nenhuma conta cadastrada.")
                    else:
                        _rotulos_senha = {
                            f"{c['full_name']} ({c['username']})": c for c in _contas
                        }
                        _escolha_senha = st.selectbox("Conta", list(_rotulos_senha), key="senha-conta")
                        _alvo_senha = _rotulos_senha[_escolha_senha]

                        with st.form("form-redefinir-senha"):
                            _nova = st.text_input("Nova senha", type="password")
                            st.caption(
                                "Todas as sessões ativas dessa pessoa são encerradas. "
                                "A senha atual não é exigida — é o caminho para quem perdeu a dela."
                            )
                            if st.form_submit_button("Redefinir senha", type="primary"):
                                try:
                                    reset_user_password(
                                        username=_alvo_senha["username"], new_password=_nova, actor=user,
                                    )
                                    queue_toast(
                                        f"Senha de '{_alvo_senha['username']}' redefinida.", icon="🔑"
                                    )
                                    st.rerun()
                                except (ValueError, PermissionError) as exc:
                                    st.error(str(exc))



    with aba_perm:
        with st.container(border=True):
            st.markdown(ui.card_title("Permissões por role", "lock_person"), unsafe_allow_html=True)
            st.dataframe(role_permissions_df, width="stretch", hide_index=True)
        if can_manage(user["role"], "rbac"):
            with st.container(border=True):
                st.markdown(ui.card_title("Editor de matriz RBAC", "admin_panel_settings"), unsafe_allow_html=True)
                roles = get_roles()
                all_actions = get_actions()
                selected_role = st.selectbox("Role para editar", roles)
                current_actions = sorted(get_permissions(selected_role))
                selected_actions = st.multiselect(
                    "Acoes permitidas",
                    all_actions,
                    default=current_actions,
                    help="As mudancas sao persistidas no banco e auditadas com before/after.",
                )
                if st.button("Salvar matriz RBAC", type="primary"):
                    try:
                        update_role_permissions(
                            role=selected_role,
                            actions=selected_actions,
                            actor=user,
                            source="ui-admin-rbac",
                        )
                        queue_toast(f"Permissões do role {selected_role} atualizadas com auditoria.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))


    with aba_audit:
        if can_manage(user["role"], "audit"):
            with st.container(border=True):
                st.markdown(ui.card_title("Trilha de auditoria por usuario", "history"), unsafe_allow_html=True)
                st.dataframe(audit_df, width="stretch", hide_index=True)


    with aba_hooks:
        with st.container(border=True):
            st.markdown(ui.card_title("Token de verificação do webhook", "key"), unsafe_allow_html=True)
            st.code(get_webhook_verify_token())
            st.caption("Use este token no GET de verificação do provedor de webhook.")
        with st.container(border=True):
            st.markdown(ui.card_title("Eventos de webhook", "webhook"), unsafe_allow_html=True)
            st.dataframe(webhook_df, width="stretch", hide_index=True)

