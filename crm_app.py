"""TRUST CRM - persisted CRM with auth, roles and channel intake."""

from __future__ import annotations

import io
import os
from datetime import date
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import qrcode
import streamlit as st
import streamlit.components.v1 as components

import brand_assets
import demo_meishop

from services_catalog import resolve_service_section
from service_guide_ui import open_service_guide_dialog, render_global_assistant
from crm_views import (
    SavedViewError,
    apply_view_to_state,
    capture_filters,
    delete_view,
    get_view,
    load_views,
    save_view,
)
import crm_backend as crm_backend_module
import crm_components as ui
import crm_db
from crm_ux import (
    LOGIN_ENDPOINT,
    TOTP_LOGIN_ENDPOINT,
    esc,
    login_throttle_subject,
    nome_exibido,
    demo_login_enabled,
    format_compact_brl,
    global_search,
    last_activity_by_customer,
    render_global_search,
)
try:
    from streamlit_sortables import sort_items
except Exception:  # pragma: no cover - ambiente sem o componente
    sort_items = None

from crm_ui_extensions import (
    render_ai_insights,
    render_cadences,
    render_forecast,
    render_health,
    render_lead_scoring,
    render_productivity,
    render_segmentation,
    render_templates,
)
from crm_backend import (
    DB_PATH,
    create_ui_session,
    resolve_ui_session,
    revoke_ui_session,
    has_permission,
    get_data,
    get_role_sections,
    get_timeline,
    get_user_preference,
    set_user_preference,
    init_database,
    verify_login,
    change_own_password,
    accounts_with_default_password,
    consume_auth_attempt,
    data_version,
    aplicar_visibilidade,
    ve_tudo,
    register_auth_failure,
    register_auth_success,
    seed_password_for,
    totp_is_enabled,
    verify_totp_login,
    start_totp_enrollment,
    confirm_totp_enrollment,
    disable_totp,
    get_exec_report_config,
    EXEC_REPORT_DEFAULT_KPIS,
)
from crm_sections import (
    administracao,
    atendimento,
    automacoes,
    canais,
    clientes_360,
    funil,
    importar_dados,
    manual_servicos,
    marketing,
    meu_dia,
    visao_executiva,
)

@st.cache_resource(show_spinner=False)
def _tema_css() -> str:
    """CSS do tema (lido uma vez por processo)."""
    return (Path(__file__).resolve().parent / "static" / "crm_app.css").read_text(encoding="utf-8")



PRIMARY_NAV_ORDER = [
    "Meu Dia",
    "Serviços",
    "Visão Executiva",
    "Atendimento",
    "Clientes 360",
    "Funil Comercial",
    "Canais",
]
MORE_NAV_PLACEHOLDER = "— mais módulos —"

# Ícones por seção (exibição apenas: o valor do widget segue sendo o nome puro,
# então nada de estado, permissão ou roteamento muda).
NAV_ICONS = {
    "Meu Dia": ":material/today:",
    "Serviços": ":material/apps:",
    "Visão Executiva": ":material/monitoring:",
    "Atendimento": ":material/support_agent:",
    "Clientes 360": ":material/group:",
    "Funil Comercial": ":material/filter_alt:",
    "Canais": ":material/forum:",
}


def nav_option_label(section: str) -> str:
    icon = NAV_ICONS.get(section)
    rotulo = nome_exibido(section)
    return f"{icon} {rotulo}" if icon else rotulo



def split_nav_sections(allowed: list[str]) -> tuple[list[str], list[str]]:
    primary = [name for name in PRIMARY_NAV_ORDER if name in allowed]
    secondary = [name for name in allowed if name not in primary]
    return primary, secondary




# Ícone da aba: o brasão da Trust, com o emoji como reserva.
_FAVICON = brand_assets.favicon_image()

st.set_page_config(
    page_title="TRUST CRM",
    page_icon=_FAVICON if _FAVICON is not None else "📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


# A fonte de ícones precisa começar a carregar JUNTO com a página.
# O Streamlit só a injeta quando monta o primeiro componente com ícone —
# até lá, qualquer <span> nosso com font-family Material Symbols mostra o
# NOME do ícone em texto («bolt», «inbox»). Com display=block o texto fica
# invisível durante o carregamento, então não há flash de nome cru.
# O Streamlit serve <html lang="en"> fixo. Com a página em português, o Chrome
# entende que é inglês e traduz sozinho — foi o que transformou a marca
# «TrustCRM» em «CRM de confiança» e os nomes dos ícones em «PARAFUSO».
# Declarar o idioma correto elimina o gatilho da tradução automática.
components.html(
    """
<script>
  const doc = window.parent.document;
  doc.documentElement.lang = "pt-BR";
  doc.documentElement.setAttribute("translate", "no");
</script>
""",
    height=0,
)

# PWA: manifest, ícone de tela inicial e registro do service worker.
# Os arquivos vêm da pasta static/ (server.enableStaticServing=true no
# config.toml), servida pelo Streamlit em "/app/static/...". O CRM segue
# sendo uma página só: isso não cria funcionamento offline (o Streamlit
# depende de WebSocket vivo para cada interação) — o objetivo é só deixar
# o app "instalável" no celular/desktop, com ícone e janela próprios.
# Ver o comentário no topo de static/service-worker.js para o porquê da
# limitação de escopo do service worker.
components.html(
    """
<script>
  const doc = window.parent.document;
  const head = doc.head;

  function ensureLink(rel, href, extra) {
    let el = head.querySelector(`link[rel="${rel}"]`);
    if (!el) {
      el = doc.createElement("link");
      el.rel = rel;
      head.appendChild(el);
    }
    el.href = href;
    if (extra) Object.entries(extra).forEach(([k, v]) => el.setAttribute(k, v));
  }

  ensureLink("manifest", "/app/static/manifest.json");
  ensureLink("apple-touch-icon", "/app/static/icons/icon-180.png");
  ensureLink("icon", "/app/static/icons/icon-32.png", {sizes: "32x32"});

  let themeColor = head.querySelector('meta[name="theme-color"]');
  if (!themeColor) {
    themeColor = doc.createElement("meta");
    themeColor.name = "theme-color";
    head.appendChild(themeColor);
  }
  themeColor.content = "#2563eb";

  let appleCapable = head.querySelector('meta[name="apple-mobile-web-app-capable"]');
  if (!appleCapable) {
    appleCapable = doc.createElement("meta");
    appleCapable.name = "apple-mobile-web-app-capable";
    appleCapable.content = "yes";
    head.appendChild(appleCapable);
  }

  const parentNav = window.parent.navigator;
  if (parentNav && "serviceWorker" in parentNav) {
    parentNav.serviceWorker
      .register("/app/static/service-worker.js")
      .catch(() => {});
  }
</script>
""",
    height=0,
)

st.markdown(
    """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet"
      href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=block">
""",
    unsafe_allow_html=True,
)

# Tema visual do app. Fica em static/crm_app.css (antes eram ~660 linhas de
# CSS dentro deste arquivo). O conteúdo é injetado exatamente como antes.
st.markdown(_tema_css(), unsafe_allow_html=True)


def currency(value: float) -> str:
    return f"R$ {float(value):,.0f}".replace(",", ".")


def status_class(label: str) -> str:
    mapping = {
        "Novo": "status-open",
        "Aguardando cliente": "status-open",
        "Em progresso": "status-progress",
        "Resolvido": "status-won",
        "Fechado ganho": "status-won",
        "Perdido": "status-lost",
        "Ativo": "status-active",
        "Expansao": "status-progress",
        "Risco": "status-lost",
    }
    return mapping.get(label, "status-active")


def _allowed_sections_for_user() -> list[str]:
    user = st.session_state.get("crm_user") or {}
    sections = get_role_sections(str(user.get("role", "admin")))
    if "Serviços" not in sections:
        sections = ["Serviços", *sections]
    return sections


def on_primary_nav_change() -> None:
    st.session_state["nav_section"] = st.session_state["nav_primary"]
    if "nav_more_select" in st.session_state:
        st.session_state["nav_more_select"] = MORE_NAV_PLACEHOLDER


def on_more_nav_change() -> None:
    choice = st.session_state.get("nav_more_select", MORE_NAV_PLACEHOLDER)
    if choice != MORE_NAV_PLACEHOLDER:
        st.session_state["nav_section"] = choice


def sync_nav_widgets_from_section(
    allowed: list[str],
    primary: list[str],
    secondary: list[str],
) -> None:
    """Atualiza widgets de navegação antes de instanciá-los (evita erro do Streamlit)."""
    section = st.session_state.get("nav_section")
    if section not in allowed:
        section = primary[0] if primary else allowed[0]
        st.session_state["nav_section"] = section

    if section in primary:
        st.session_state["nav_primary"] = section
        if secondary:
            st.session_state["nav_more_select"] = MORE_NAV_PLACEHOLDER
    elif section in secondary:
        st.session_state["nav_more_select"] = section
        if primary and st.session_state.get("nav_primary") not in primary:
            st.session_state["nav_primary"] = primary[0]


def navigate_to_section(target_section: str) -> None:
    allowed = _allowed_sections_for_user()
    if target_section not in allowed:
        return
    current = st.session_state.get("nav_section")
    if current and current != target_section:
        st.session_state["nav_previous"] = current
    st.session_state["nav_section"] = target_section
    st.rerun()


def go_back() -> None:
    previous = st.session_state.get("nav_previous")
    allowed = _allowed_sections_for_user()
    if previous and previous in allowed and previous != st.session_state.get("nav_section"):
        navigate_to_section(previous)
    elif "Serviços" in allowed:
        navigate_to_section("Serviços")


def render_top_bar(active_section: str) -> None:
    # Faixa mínima: voltar / início à esquerda e o recorte de filtros ativo à
    # direita. O título e a descrição vivem no cabeçalho da página.
    col_back, col_home, col_new, col_filters = st.columns([0.45, 0.45, 1.3, 8], vertical_alignment="center")
    with col_back:
        if st.button(
            ":material/arrow_back:",
            key="nav-top-back",
            type="tertiary",
            disabled=active_section == "Serviços",
            help="Voltar à tela anterior",
        ):
            go_back()
    with col_home:
        if st.button(
            ":material/home:",
            key="nav-top-home",
            type="tertiary",
            help="Ir ao catálogo de serviços",
        ):
            navigate_to_section("Serviços")
    with col_new:
        import crm_quick_actions

        crm_quick_actions.render(globals())
    with col_filters:
        bits = []
        if st.session_state.get("filter_country", "Todos") != "Todos":
            bits.append(f"Mercado: {st.session_state['filter_country']}")
        if st.session_state.get("filter_owner", "Todos") != "Todos":
            bits.append(f"Responsável: {st.session_state['filter_owner']}")
        if bits:
            st.markdown(
                '<div class="filter-strip">'
                + "".join(f'<span class="chip chip--filter">{ui.icon("filter_alt")}{esc(b)}</span>' for b in bits)
                + "</div>",
                unsafe_allow_html=True,
            )


def render_metric_cards(metrics: list[tuple[str, str, str]]) -> None:
    st.markdown(
        ui.kpi_grid({"label": label, "value": value, "caption": caption} for label, value, caption in metrics),
        unsafe_allow_html=True,
    )


def render_timeline(timeline: dict[str, list[tuple[str, str, str]]], customer_id: str) -> None:
    items = timeline.get(customer_id, [])
    if not items:
        st.markdown('<div class="empty-state">Sem eventos na timeline para esta conta.</div>', unsafe_allow_html=True)
        return
    for item_date, title, copy in items:
        st.markdown(
            f"""
<div class="timeline-item">
    <div class="timeline-date">{item_date}</div>
    <div class="timeline-title">{title}</div>
    <div class="timeline-copy">{copy}</div>
</div>
""",
            unsafe_allow_html=True,
        )


def _client_ip_do_streamlit() -> str | None:
    """IP do cliente, quando o runtime expõe (Streamlit >= 1.45).

    Atrás de proxy confiável, o primeiro X-Forwarded-For; senão, o IP direto.
    Só devolve algo que valide como IP de verdade: no AppTest dos testes,
    st.context é um mock e devolveria um objeto cujo repr muda a cada run —
    o que fragmentaria o subject do throttle e desligaria o bloqueio.
    Falha em silêncio: sem IP, o throttle continua funcionando só por usuário.
    """
    import ipaddress

    def _valido(valor: object) -> str | None:
        if not isinstance(valor, str):
            return None
        candidato = valor.strip()
        try:
            ipaddress.ip_address(candidato)
        except ValueError:
            return None
        return candidato

    try:
        headers = getattr(st.context, "headers", None) or {}
        forwarded = headers.get("X-Forwarded-For") or headers.get("x-forwarded-for")
        if isinstance(forwarded, str) and forwarded:
            return _valido(forwarded.split(",", 1)[0])
        return _valido(getattr(st.context, "ip_address", None))
    except Exception:
        return None


def start_user_session(user: dict[str, Any]) -> None:
    """Autentica o usuário e grava um token OPACO na URL para sobreviver ao F5.

    O token não é o JWT: é um identificador aleatório de sessão registrado no
    servidor (ver crm_backend.create_ui_session), revogável no logout e sem
    nenhum claim dentro. O JWT nunca vai para a URL.
    """
    st.session_state["crm_user"] = user
    try:
        st.query_params["auth"] = create_ui_session(user["username"])
    except Exception:
        pass  # Sem token, o login continua funcionando — só não persiste no refresh.
    st.rerun()


def end_user_session() -> None:
    """Sai da conta: revoga a sessão no servidor e redireciona limpando a URL."""
    st.session_state.pop("crm_user", None)
    try:
        revoke_ui_session(str(st.query_params.get("auth", "") or ""))
    except Exception:
        pass  # A revogação é defesa extra; o logout local acontece de todo modo.
    # Redirect completo (não st.rerun): garante que o ?auth= saia da URL do navegador.
    st.markdown(
        '<meta http-equiv="refresh" content="0; url=./">',
        unsafe_allow_html=True,
    )
    st.stop()


def restore_session_from_url() -> None:
    """Se a página foi atualizada (F5), restaura o login a partir da sessão opaca."""
    if "crm_user" in st.session_state:
        return
    token = str(st.query_params.get("auth", "") or "")
    if not token:
        return
    try:
        user = resolve_ui_session(token)
    except Exception:
        user = None
    if user is not None:
        st.session_state["crm_user"] = user
    else:
        try:
            del st.query_params["auth"]
        except Exception:
            pass


def queue_toast(message: str, icon: str = "✅") -> None:
    """Agenda um toast que sobrevive ao st.rerun() (senão a mensagem some na hora)."""
    st.session_state["pending_toast"] = (message, icon)


def flush_pending_toast() -> None:
    pending = st.session_state.pop("pending_toast", None)
    if pending:
        message, icon = pending
        st.toast(message, icon=icon)


# Perfis do login de demonstração. A senha não fica mais escrita aqui: é
# resolvida em tempo de execução por seed_password_for(), que respeita as
# variáveis CRM_SEED_PASSWORD_* e, na ausência delas, usa a senha aleatória
# gerada na inicialização. Assim o botão de demo continua funcionando sem
# reintroduzir credenciais públicas no código.
DEMO_ACCOUNTS = [
    ("Admin (visão completa)", "admin"),
    ("Vendas", "vendas"),
    ("Atendimento", "atendimento"),
    ("Marketing", "marketing"),
    ("Customer Success", "cs"),
]



# ---------------------------------------------------------------------------
# Tour guiado no primeiro acesso
# ---------------------------------------------------------------------------
TOUR_STEPS = [
    {
        "title": "Bem-vindo(a) ao TRUST CRM",
        "body": (
            "Este é o seu CRM completo: atendimento, vendas, marketing e gestão de "
            "clientes em um só lugar.\n\n"
            "Este tour rápido de 4 passos mostra como tudo funciona. "
            "Você pode pular a qualquer momento e rever depois pelo menu lateral."
        ),
    },
    {
        "title": "Passo 1 · Comece pelo Catálogo",
        "body": (
            "A tela inicial é o **Catálogo de Serviços**, organizado por objetivo: "
            "*Resolver o dia a dia*, *Conhecer e cuidar dos clientes*, *Vender mais* e outros.\n\n"
            "Não sabe onde clicar? Use a **busca no topo** e descreva com suas palavras "
            "(ex.: «cliente quer cancelar») — o sistema indica o serviço certo.\n\n"
            "Cada cartão tem dois botões: **Abrir** vai direto para a tela, e "
            "**Guia** explica o serviço com exemplo prático e passo a passo."
        ),
    },
    {
        "title": "Passo 2 · Navegue pelo menu lateral",
        "body": (
            "À esquerda fica o **menu com os módulos** disponíveis para o seu perfil: "
            "Atendimento, Funil de Vendas, Clientes 360 e mais.\n\n"
            "Logo abaixo estão os **Filtros globais** (Mercado e Responsável). "
            "Quando ativos, eles afetam todas as telas e aparecem indicados no topo.\n\n"
            "No topo de qualquer tela, o botão **Início** traz você de volta ao catálogo."
        ),
    },
    {
        "title": "Passo 3 · Fluxo típico do dia a dia",
        "body": (
            "1. Chegou mensagem de cliente? Registre em **Canais** (WhatsApp, e-mail, site).\n"
            "2. Acompanhe e responda na **Central de Atendimento**.\n"
            "3. Antes de falar com alguém, consulte a **Ficha 360** do cliente.\n"
            "4. Oportunidade de venda? Crie no **Funil de Vendas**.\n"
            "5. Prometeu retorno? Agende em **Follow-up** e nada se perde."
        ),
    },
    {
        "title": "Pronto para começar!",
        "body": (
            "Dicas finais:\n\n"
            "- Toda ação importante mostra uma **confirmação** no canto da tela.\n"
            "- Sua sessão **continua ativa** mesmo se você atualizar a página.\n"
            "- Dúvida em qualquer serviço? Clique em **Guia** e use a aba **Chat IA**.\n\n"
            "Bom trabalho! Você pode rever este tour no menu lateral em «Minha conta»."
        ),
    },
]


@st.dialog("Tour guiado", width="large")
def show_onboarding_tour() -> None:
    step = int(st.session_state.get("tour_step", 0))
    step = max(0, min(step, len(TOUR_STEPS) - 1))
    data = TOUR_STEPS[step]

    st.progress((step + 1) / len(TOUR_STEPS), text=f"Etapa {step + 1} de {len(TOUR_STEPS)}")
    st.markdown(f"### {data['title']}")
    st.markdown(data["body"])
    st.divider()

    col_skip, col_back, col_next = st.columns([1, 1, 1])
    username = str(st.session_state.get("crm_user", {}).get("username", ""))

    def _finish_tour() -> None:
        if username:
            try:
                set_user_preference(username, "onboarding_tour", "done")
            except Exception:
                pass
        st.session_state["tour_done_session"] = True
        st.session_state.pop("tour_step", None)
        st.session_state.pop("show_tour", None)

    with col_skip:
        if st.button("Pular tour", use_container_width=True, key="tour-skip"):
            _finish_tour()
            st.rerun()
    with col_back:
        if step > 0 and st.button("Voltar", use_container_width=True, key="tour-back"):
            st.session_state["tour_step"] = step - 1
            st.rerun()
    with col_next:
        is_last = step == len(TOUR_STEPS) - 1
        label = "Concluir" if is_last else "Avançar"
        if st.button(label, type="primary", use_container_width=True, key="tour-next"):
            if is_last:
                _finish_tour()
                queue_toast("Tour concluído! Explore o catálogo à vontade.", icon="🎉")
            else:
                st.session_state["tour_step"] = step + 1
            st.rerun()


def maybe_show_onboarding_tour() -> None:
    """Abre o tour no primeiro acesso do usuário (persistido em SQLite)."""
    if st.session_state.get("tour_done_session"):
        return
    if st.session_state.get("show_tour"):
        show_onboarding_tour()
        return
    username = str(st.session_state.get("crm_user", {}).get("username", ""))
    if not username:
        return
    try:
        already_done = get_user_preference(username, "onboarding_tour", "") == "done"
    except Exception:
        already_done = True  # Em caso de erro no banco, não bloqueia o uso.
    if already_done:
        st.session_state["tour_done_session"] = True
        return
    st.session_state["show_tour"] = True
    show_onboarding_tour()


def faixa_de_demonstracao() -> None:
    """Diz, na tela, que aquele ambiente não é o CRM da operação.

    Sem isso a vitrine é indistinguível do sistema real: mesma marca, mesmas
    telas, mesmo endereço de terceiro nível. Dois estragos possíveis, os dois
    caros e os dois evitáveis por um aviso — alguém da equipe trabalhar horas
    dentro da demonstração achando que está no CRM, e um cliente em prospecção
    achar que está vendo dados de clientes reais da Trust.
    """
    if not demo_meishop.modo_demonstracao():
        return
    st.info(
        "**Ambiente de demonstração.** Clientes, contratos e chamados desta tela "
        "são fictícios, criados para apresentar o sistema. Nada aqui é dado real "
        "de cliente. As alterações são apagadas a cada atualização do ambiente.",
        icon="🎭",
    )


def _show_totp_challenge(user: dict[str, Any]) -> None:
    """Segunda etapa do login, quando a conta tem 2FA ativo.

    Fica numa tela própria, separada do formulário de senha: assim a senha
    já validada não fica boiando em `st.session_state` como texto, e um
    `Cancelar` aqui sempre volta pro início limpo, sem sessão nenhuma aberta.
    """
    with st.container(border=True):
        st.markdown('<p class="login-gate-title">Confirmação em duas etapas</p>', unsafe_allow_html=True)
        st.markdown(
            '<p class="login-gate-hint">Digite o código de 6 dígitos do seu app '
            f"autenticador para entrar como <strong>{esc(user.get('full_name') or user['username'])}</strong>.</p>",
            unsafe_allow_html=True,
        )
        with st.form("crm-login-2fa"):
            code = st.text_input("Código", placeholder="000000", max_chars=12)
            col_confirm, col_cancel = st.columns(2)
            with col_confirm:
                confirmed = st.form_submit_button("Confirmar", width="stretch", type="primary")
            with col_cancel:
                cancelled = st.form_submit_button("Cancelar", width="stretch")
        st.caption(
            "Sem acesso ao app agora? Use um dos seus códigos de backup no lugar "
            "do código de 6 dígitos."
        )

    if cancelled:
        st.session_state.pop("pending_2fa_user", None)
        st.rerun()

    if confirmed:
        subject = login_throttle_subject(user["username"], _client_ip_do_streamlit())
        try:
            consume_auth_attempt(subject, TOTP_LOGIN_ENDPOINT)
        except ValueError as exc:
            st.error(str(exc))
        else:
            if verify_totp_login(user["username"], code):
                register_auth_success(subject, TOTP_LOGIN_ENDPOINT)
                st.session_state.pop("pending_2fa_user", None)
                start_user_session(user)
            else:
                register_auth_failure(subject, TOTP_LOGIN_ENDPOINT)
                st.error("Código inválido.")


def _render_totp_settings(user: dict[str, Any]) -> None:
    """Ativação e desativação de 2FA (TOTP) dentro de "Minha conta".

    Quatro estados possíveis, nesta ordem de prioridade: já ativado (mostra
    como desativar); acabou de confirmar agora mesmo (mostra os códigos de
    backup, a única vez que existem em texto puro); ativação em andamento
    (mostra o QR code e pede o primeiro código para confirmar); ou nada disso,
    e então só o botão para começar.
    """
    st.markdown("**Autenticação em duas etapas (2FA)**")

    # Prioridade máxima: os códigos de backup recém-gerados. Nesse instante
    # `totp_is_enabled` já é True (a ativação acabou de ser confirmada), então
    # esta checagem tem que vir ANTES da checagem de "já ativado" — senão a
    # tela "já ativado" toma a frente e os códigos somem sem nunca aparecer.
    backup_codes_pending = st.session_state.get("totp_new_backup_codes")
    if backup_codes_pending:
        st.warning(
            "2FA ativado! Anote estes códigos de backup agora, eles não "
            "aparecem de novo. Cada um funciona uma única vez, para o caso "
            "de você perder o acesso ao app autenticador.",
            icon="⚠️",
        )
        st.code("\n".join(backup_codes_pending))
        if st.button("Já anotei, fechar", key="totp-ack-backup", use_container_width=True):
            st.session_state.pop("totp_new_backup_codes", None)
            st.rerun()
        return

    if totp_is_enabled(user["username"]):
        st.success("2FA ativado nesta conta.", icon="🔒")
        with st.form("totp-disable-form"):
            pw = st.text_input("Confirme sua senha para desativar", type="password")
            disable_clicked = st.form_submit_button("Desativar 2FA", use_container_width=True)
        if disable_clicked:
            try:
                disable_totp(user, pw)
            except ValueError as exc:
                st.error(str(exc))
            else:
                queue_toast("2FA desativado.", icon="🔓")
                st.rerun()
        return

    if st.session_state.get("totp_enroll_secret"):
        secret = st.session_state["totp_enroll_secret"]
        uri = st.session_state["totp_enroll_uri"]
        qr_buffer = io.BytesIO()
        qrcode.make(uri).save(qr_buffer, format="PNG")
        st.image(qr_buffer.getvalue(), caption="Escaneie com o app autenticador", width=200)
        st.caption(f"Ou digite o segredo manualmente: `{secret}`")
        with st.form("totp-confirm-form"):
            code = st.text_input("Código de 6 dígitos do app", max_chars=12)
            col_confirm, col_cancel = st.columns(2)
            with col_confirm:
                confirm_clicked = st.form_submit_button(
                    "Confirmar ativação", use_container_width=True, type="primary"
                )
            with col_cancel:
                cancel_clicked = st.form_submit_button("Cancelar", use_container_width=True)
        if cancel_clicked:
            st.session_state.pop("totp_enroll_secret", None)
            st.session_state.pop("totp_enroll_uri", None)
            st.rerun()
        if confirm_clicked:
            try:
                backup_codes = confirm_totp_enrollment(user, code)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state.pop("totp_enroll_secret", None)
                st.session_state.pop("totp_enroll_uri", None)
                st.session_state["totp_new_backup_codes"] = backup_codes
                st.rerun()
        return

    st.caption(
        "Desativado. Ativar exige um app autenticador no celular "
        "(Google Authenticator, Authy, 1Password ou similar)."
    )
    if st.button("Ativar 2FA agora", key="totp-start-enroll", use_container_width=True):
        secret, uri = start_totp_enrollment(user)
        st.session_state["totp_enroll_secret"] = secret
        st.session_state["totp_enroll_uri"] = uri
        st.rerun()


def show_login() -> None:
    """Porta de entrada do CRM.

    Duas coisas foram deliberadamente retiradas da versão anterior desta tela.

    A primeira é a lista de atributos técnicos ("PostgreSQL gerenciado",
    "Acesso por papéis"). Era texto de vitrine numa ferramenta interna: quem
    chega aqui já trabalha na empresa e só quer entrar. Sublinhados em verde
    ainda faziam os três itens parecerem abas clicáveis.

    A segunda é o painel que instruía o visitante a definir
    `CRM_DEMO_LOGIN=true` para entrar sem senha. Era o manual do desvio de
    autenticação publicado na única página que o mundo inteiro enxerga.
    Quem administra a instância encontra a variável no `.env.example` e na
    documentação, que é onde ela pertence.
    """
    st.markdown(
        f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=Instrument+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<div class="login-shell">
  <div class="login-brand">
    <img class="login-logo" src="{brand_assets.data_uri("logo")}" alt="Trust Corporation — Patrimônio e Legado">
    <h1>Trust CRM</h1>
    <p class="tagline">Clientes, atendimento e funil comercial em um só lugar.</p>
    <div class="login-rule"></div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    pending_2fa_user = st.session_state.get("pending_2fa_user")

    if pending_2fa_user is not None:
        _show_totp_challenge(pending_2fa_user)
    else:
        with st.container(border=True):
            st.markdown('<p class="login-gate-title">Entrar</p>', unsafe_allow_html=True)
            st.markdown(
                '<p class="login-gate-hint">Acesso restrito. Use as credenciais fornecidas '
                "pela administração.</p>",
                unsafe_allow_html=True,
            )
            # A vitrine se anuncia antes de pedir credencial: é a primeira tela que
            # um cliente em prospecção vê, e é onde o aviso custa menos.
            faixa_de_demonstracao()
            with st.form("crm-login"):
                username = st.text_input("Usuário", placeholder="Digite seu usuário")
                password = st.text_input("Senha", type="password", placeholder="Digite sua senha")
                submitted = st.form_submit_button("Acessar", width="stretch", type="primary")
            if submitted:
                # O backend já tinha throttle progressivo com bloqueio, mas ele
                # só estava ligado no serviço de webhook. A tela de login — o
                # caminho que de fato está exposto ao público — chamava
                # verify_login() direto, sem limite algum de tentativas.
                subject = login_throttle_subject(username, _client_ip_do_streamlit())
                try:
                    consume_auth_attempt(subject, LOGIN_ENDPOINT)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    user = verify_login(username.strip(), password)
                    if user:
                        register_auth_success(subject, LOGIN_ENDPOINT)
                        if totp_is_enabled(user["username"]):
                            st.session_state["pending_2fa_user"] = user
                            st.rerun()
                        else:
                            start_user_session(user)
                    else:
                        register_auth_failure(subject, LOGIN_ENDPOINT)
                        st.error("Credenciais inválidas.")

        # O acesso de demonstração aparece apenas quando está de fato ligado.
        # Desligado, a tela não deve sequer mencionar que ele existe.
        if demo_login_enabled():
            with st.container(border=True):
                st.markdown(
                    '<p class="login-gate-title">Entrar sem senha (demonstração)</p>',
                    unsafe_allow_html=True,
                )
                st.warning(
                    "Modo demonstração ativo: qualquer visitante entra sem senha. "
                    "Não use em ambiente com dado real.",
                    icon="⚠️",
                )
                for label, demo_username in DEMO_ACCOUNTS:
                    if st.button(label, key=f"demo-login-{demo_username}", use_container_width=True):
                        demo_user = verify_login(demo_username, seed_password_for(demo_username))
                        if demo_user:
                            queue_toast(f"Bem-vindo(a), {demo_user['full_name']}!", icon="👋")
                            start_user_session(demo_user)
                        else:
                            st.error("Conta de demonstração indisponível.")

    st.markdown(
        '<p class="login-foot"><strong>Trust Corporation</strong><br>'
        "Sistema interno · uso autorizado apenas</p>",
        unsafe_allow_html=True,
    )


def can_manage(user_role: str, area: str) -> bool:
    action_map = {
        "ticket": "ticket.create",
        "customer": "customer.create",
        "deal": "deal.create",
        "campaign": "campaign.create",
        "channel": "channel.intake",
        "admin": "admin.view",
        "audit": "audit.view",
        "rbac": "rbac.manage",
    }
    action = action_map.get(area, "")
    return has_permission(user_role, action) if action else False


def build_customer_lookup(customers_df: pd.DataFrame) -> dict[str, dict[Any, Any]]:
    return {str(row["customer_id"]): dict(row) for row in customers_df.to_dict("records")}


def ingest_message(uploaded_file) -> str:
    if uploaded_file is None:
        return ""
    try:
        return uploaded_file.getvalue().decode("utf-8", errors="ignore")[:4000]
    except Exception:
        return ""


# CSS injetado no iframe do kanban (o tema da página não alcança lá dentro).
KANBAN_STYLE = """
.sortable-component { display: flex; gap: 12px; align-items: flex-start;
    font-family: ui-sans-serif, -apple-system, 'Segoe UI', Inter, system-ui, sans-serif; }
.sortable-container { flex: 1 1 0; background: #f3f4f6; border: 1px solid #e5e7eb; border-top: 3px solid #9ca3af;
    border-radius: 12px; padding: 6px; min-height: 160px; }
.sortable-container:nth-child(1) { border-top-color: #9ca3af; }
.sortable-container:nth-child(2) { border-top-color: #2563eb; }
.sortable-container:nth-child(3) { border-top-color: #d97706; }
.sortable-container:nth-child(4) { border-top-color: #16a34a; }
.sortable-container:nth-child(5) { border-top-color: #dc2626; }
.sortable-container-header { font-weight: 650; font-size: 12px; color: #374151;
    padding: 8px 8px 6px; letter-spacing: -0.005em; }
.sortable-container-body { display: flex; flex-direction: column; gap: 8px; padding: 4px; min-height: 100px; }
.sortable-item { background: #ffffff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 10px 12px;
    font-size: 12.5px; font-weight: 600; line-height: 1.35; color: #111827; cursor: grab;
    box-shadow: 0 1px 2px rgba(16, 24, 40, 0.05); transition: box-shadow .12s, border-color .12s; }
.sortable-item:hover { border-color: #93b4f5; box-shadow: 0 6px 16px -8px rgba(37, 99, 235, 0.4); }
"""


def render_page_header(section: str) -> None:
    hints = {
        "Meu Dia": "O que precisa da sua ação agora: tarefas, negociações paradas e SLA.",
        "Serviços": "Escolha um módulo abaixo ou use o menu à esquerda.",
        "Visão Executiva": "KPIs e leitura rápida da operação.",
        "Atendimento": "Fila de tickets e SLA.",
        "Clientes 360": "Sua base de clientes e a ficha completa de cada um.",
        "Funil Comercial": "Oportunidades e etapas de venda.",
        "Canais": "Entrada WhatsApp, e-mail e formulários.",
        "Administração": "Governança, usuários, permissões e auditoria.",
        "Marketing": "Campanhas, conversão por canal e segmentos.",
        "Cadências": "Sequências de contato para não deixar lead esfriar.",
        "Saúde da Conta": "Risco de churn e sinais de expansão.",
        "Modelos de Mensagem": "Textos prontos para WhatsApp e e-mail.",
        "Previsão de Receita": "Projeção ponderada do funil.",
        "Produtividade": "Carga e resultado por responsável.",
        "Qualificação de Leads": "Priorize quem tem mais chance de fechar.",
        "Segmentação": "Recortes de clientes para ação dirigida.",
        "Insights com IA": "Leituras automáticas da operação.",
        "Comparativo de Mercado": "Trust CRM lado a lado com os líderes.",
        "Manual de Serviços": "O que cada serviço faz, entrega e como usar — com exemplos.",
        "Automações": "Regras que criam tarefas sozinhas a partir do que está parado.",
        "Importar Dados": "Traga sua base de clientes de outro sistema por planilha.",
    }
    subtitle = hints.get(section, "Visão consolidada do módulo.")
    title, eyebrow = nome_exibido(section), "Trust CRM"
    if section == "Meu Dia":
        nome = ui.primeiro_nome((st.session_state.get("crm_user") or {}).get("full_name"))
        title = f"{ui.saudacao()}, {nome}" if nome else ui.saudacao()
        eyebrow = "Meu Dia"
    st.markdown(ui.page_header(title, subtitle, eyebrow=eyebrow), unsafe_allow_html=True)


def render_empty_state(message: str) -> None:
    # esc(): o texto pode carregar termo digitado pelo usuário.
    st.markdown(f'<div class="empty-state">{esc(message)}</div>', unsafe_allow_html=True)


# Ícone e tom por serviço — paleta azul/verde/grafite.
# Guardamos o CODEPOINT da Material Symbols, não o nome da ligadura: nome é
# texto legível no DOM, que o navegador mostra enquanto a fonte carrega e que
# a tradução automática do Chrome chega a traduzir («bolt» virava «PARAFUSO»).
# Com o codepoint injetado por CSS, não existe texto para vazar nem traduzir.
SERVICE_CARD_META = {
    "ticketing-sla": ("\\f0e2", "#2f6fe4"),
    "channel-intake": ("\\e156", "#2f6fe4"),
    "tasks-cadences": ("\\e7f7", "#2f6fe4"),
    "customer-360": ("\\f106", "#08a742"),
    "timeline": ("\\e8b3", "#08a742"),
    "health-score": ("\\eaa2", "#08a742"),
    "templates": ("\\e745", "#08a742"),
    "pipeline": ("\\ef4f", "#0a7d44"),
    "forecast": ("\\e8e5", "#0a7d44"),
    "productivity": ("\\f20c", "#0a7d44"),
    "marketing-campaigns": ("\\ef49", "#2159c4"),
    "lead-scoring": ("\\e743", "#2159c4"),
    "segmentation": ("\\e72c", "#2159c4"),
    "executive-view": ("\\f190", "#334155"),
    "ai-insights": ("\\e65f", "#334155"),
    "rbac-admin": ("\\ef3d", "#334155"),
    "benchmark": ("\\e915", "#334155"),
}


CATEGORY_HEAD_META = {
    "operacao": ("\\ea0b", "#2f6fe4"),
    "relacionamento": ("\\ea21", "#08a742"),
    "comercial": ("\\ef63", "#0a7d44"),
    "growth": ("\\ef49", "#2159c4"),
    "governanca": ("\\e8b8", "#334155"),
}


def build_service_live_stats() -> dict[str, tuple[str, str]]:
    """Contador ao vivo por serviço: (valor, rótulo).

    Lê os mesmos dataframes das telas — o número do card é o número
    que o usuário encontra ao abrir o serviço.
    """
    stats: dict[str, tuple[str, str]] = {}

    def _n(count: int, singular: str, plural: str) -> tuple[str, str]:
        return (str(count), singular if count == 1 else plural)

    try:
        abertos = tickets_df[tickets_df["status"] != "Resolvido"]
        stats["ticketing-sla"] = _n(len(abertos), "ticket aberto", "tickets abertos")
        stats["channel-intake"] = _n(len(tickets_df), "atendimento registrado", "atendimentos registrados")
        pendentes = tasks_df[tasks_df.get("status", "aberta") != "concluida"] if not tasks_df.empty else tasks_df
        stats["tasks-cadences"] = _n(len(pendentes), "tarefa pendente", "tarefas pendentes")
        stats["customer-360"] = _n(len(customers_df), "conta na base", "contas na base")
        stats["timeline"] = _n(len(interactions_df), "interação registrada", "interações registradas")
        em_risco = customers_df[customers_df["health_score"] < 60] if not customers_df.empty else customers_df
        stats["health-score"] = _n(len(em_risco), "conta em risco", "contas em risco")
        deals_abertos = deals_df[deals_df["stage"] != "Fechado ganho"] if not deals_df.empty else deals_df
        stats["pipeline"] = _n(len(deals_abertos), "negócio em aberto", "negócios em aberto")
        if not deals_abertos.empty:
            ponderada = float((deals_abertos["value"] * deals_abertos["probability"] / 100).sum())
            stats["forecast"] = (format_compact_brl(ponderada), "previsão ponderada")
        ativos = users_df[users_df["is_active"] == 1] if not users_df.empty else users_df
        stats["productivity"] = _n(len(ativos), "pessoa no time", "pessoas no time")
        stats["rbac-admin"] = _n(len(ativos), "usuário ativo", "usuários ativos")
        stats["marketing-campaigns"] = _n(len(campaigns_df), "campanha ativa", "campanhas ativas")
        if not campaigns_df.empty and "qualified" in campaigns_df.columns:
            _q = int(campaigns_df["qualified"].sum())
            stats["lead-scoring"] = _n(_q, "lead qualificado", "leads qualificados")
        if not customers_df.empty:
            stats["executive-view"] = (f"{int(customers_df['health_score'].mean())}/100", "saúde média da carteira")
    except Exception:
        # Contador é decoração informativa: nunca pode derrubar o catálogo.
        pass
    return stats


def _render_service_card(
    service: dict[str, Any],
    allowed_sections: list[str],
    live_stats: dict[str, tuple[str, str]] | None = None,
    key_prefix: str = "svc",
) -> None:
    """Card de serviço: ícone, quando usar, contador ao vivo e ações."""
    icon, tone = SERVICE_CARD_META.get(str(service["id"]), ("widgets", "#334155"))
    with st.container(border=True):
        st.markdown(
            f"""
<div class="svc-head">
  <span class="svc-icon" translate="no" aria-hidden="true"
        style="color:{tone};background:{tone}1a;--ico:'{icon}';"></span>
  <div class="svc-title">{service['title']}</div>
</div>
<div class="svc-when">{service['tagline']}</div>
""",
            unsafe_allow_html=True,
        )
        stat = (live_stats or {}).get(str(service["id"]))
        if stat:
            st.markdown(
                f'<div class="svc-stat"><span class="svc-stat-num">{stat[0]}</span>'
                f'<span class="svc-stat-label">{stat[1]}</span></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="svc-stat"><span class="svc-ready">'
                '<span class="svc-ready-icon" translate="no" aria-hidden="true"></span> Pronto para usar</span></div>',
                unsafe_allow_html=True,
            )
        target_section = resolve_service_section(str(service["id"]))
        has_access = target_section in allowed_sections
        if not has_access:
            st.caption("🔒 Disponível para outro perfil de acesso")
        b_open, b_guide = st.columns(2)
        with b_open:
            if has_access:
                if st.button(
                    "Abrir",
                    key=f"{key_prefix}-open-{service['id']}",
                    type="primary",
                    use_container_width=True,
                ):
                    navigate_to_section(target_section)
            else:
                st.button(
                    "🔒 Sem acesso",
                    key=f"{key_prefix}-open-{service['id']}",
                    disabled=True,
                    use_container_width=True,
                    help=f"Seu perfil não tem acesso a «{target_section}». Fale com um administrador para liberar.",
                )
        with b_guide:
            if st.button(
                "Guia",
                key=f"{key_prefix}-guide-{service['id']}",
                use_container_width=True,
                help="Objetivo, exemplo prático, passo a passo e chat IA",
            ):
                open_service_guide_dialog(
                    service,
                    navigate_to_section,
                    resolve_service_section,
                )


def render_benchmark_comparison(compact: bool = False) -> None:
    """Comparativo Benchmark: quem disputa o mercado brasileiro e onde estamos.

    Usado no fim do catálogo de Serviços e na tela «Comparativo de Mercado».
    Mostra também as três frentes em que estamos atrás — comparativo que só
    elogia a casa não ajuda ninguém a decidir.
    """
    from benchmark_market import (
        CAPABILITY_MATRIX,
        PRICE_CHECKED_AT,
        TRUST_POSITION,
        brazilian_competitors,
        capability_score,
        global_competitors,
    )

    _placar = capability_score()

    def _tabela_concorrentes(lista) -> None:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Concorrente": c["name"],
                        "Origem": c["origin"],
                        "Preço de entrada": c["price"],
                        "Nosso diferencial": c["trust_diff"],
                    }
                    for c in lista
                ]
            ),
            width="stretch",
            hide_index=True,
            height=min(38 + 35 * len(lista), 300),
        )

    def _painel() -> None:
        st.markdown(
            '<div class="section-title">Comparativo Benchmark — o mercado brasileiro</div>',
            unsafe_allow_html=True,
        )
        st.caption(
            f"Preços consultados nas páginas oficiais em {PRICE_CHECKED_AT}. "
            "Valores em dólar estão marcados. Software muda de preço — confira antes de decidir."
        )
        st.markdown(
            ui.kpi_grid(
                [
                    {"label": "Capacidades à frente", "value": _placar["vantagem"], "icon": "emoji_events", "tone": "ok"},
                    {"label": "Equivalentes", "value": _placar["empate"] + _placar["parcial"], "icon": "balance", "tone": "info"},
                    {"label": "Atrás", "value": _placar["atras"], "caption": "E-mail, ecossistema de integrações e multiempresa.", "icon": "flag", "tone": "warn"},
                ]
            ),
            unsafe_allow_html=True,
        )
        _abas = ["Concorrentes", "Capacidade a capacidade", "Onde ganhamos e onde estamos atrás"]
        if not compact:
            _abas.append("Detalhe por concorrente")
        _tabs = st.tabs(_abas)
        with _tabs[0]:
            _col_br, _col_gl = st.columns(2)
            with _col_br:
                st.markdown("**🇧🇷 CRMs brasileiros**")
                _tabela_concorrentes(brazilian_competitors())
            with _col_gl:
                st.markdown("**🌐 Globais que competem no Brasil**")
                _tabela_concorrentes(global_competitors())
        with _tabs[1]:
            st.dataframe(
                pd.DataFrame(
                    [
                        {"Capacidade": m["capability"], "Trust CRM": m["trust"], "Mercado": m["market"]}
                        for m in CAPABILITY_MATRIX
                    ]
                ),
                width="stretch",
                hide_index=True,
                height=min(38 + 35 * len(CAPABILITY_MATRIX), 460),
            )
        with _tabs[2]:
            _pos = st.columns(2)
            with _pos[0], st.container(border=True):
                st.markdown(ui.card_title("Onde ganhamos", "emoji_events"), unsafe_allow_html=True)
                for _item in TRUST_POSITION["ganhamos"]:
                    st.markdown(f"- {_item}")
            with _pos[1], st.container(border=True):
                st.markdown(ui.card_title("Onde estamos atrás", "flag"), unsafe_allow_html=True)
                for _item in TRUST_POSITION["atras"]:
                    st.markdown(f"- {_item}")
                st.caption("Reconhecer a lacuna é o que permite fechá-la — estas são as próximas frentes.")
        if not compact:
            with _tabs[3]:
                _col_br, _col_gl = st.columns(2)
                for _col, _titulo, _lista in (
                    (_col_br, "🇧🇷 CRMs brasileiros", brazilian_competitors()),
                    (_col_gl, "🌐 Globais", global_competitors()),
                ):
                    with _col:
                        st.markdown(f"**Detalhe — {_titulo}**")
                        for _c in _lista:
                            with st.expander(f"{_c['name']} · {_c['origin']}"):
                                st.markdown(f"**Público-alvo:** {_c['audience']}")
                                st.markdown(f"**Preço:** {_c['price']}  \n*Fonte: {_c['price_source']}*")
                                st.markdown("**Pontos fortes:**")
                                for _f in _c["strengths"]:
                                    st.markdown(f"- {_f}")
                                st.markdown("**Limitações conhecidas:**")
                                for _l in _c["limitations"]:
                                    st.markdown(f"- {_l}")
                                st.markdown(f"**Adequação ao Brasil:** {_c['brasil']}")
                                st.info(f"**Nosso diferencial:** {_c['trust_diff']}")

    if compact:
        # No catálogo de Serviços o comparativo fica recolhido: quem quer, abre.
        with st.expander("📊 Comparativo Benchmark — como a Trust se posiciona contra o mercado", expanded=False):
            _painel()
    else:
        _painel()


def render_services_catalog() -> None:
    """Catálogo orientado a objetivo: busca, cards clicáveis e desambiguação.

    Substitui a versão antiga que desenhava cada serviço duas vezes
    (card decorativo NÃO clicável em rolagem horizontal + botões abaixo).
    """
    from services_catalog import CATEGORIES, get_services_by_category, search_services

    allowed_sections = _allowed_sections_for_user()
    live_stats = build_service_live_stats()

    # Rótulos orientados a objetivo (só exibição; não altera services_catalog.py).
    OBJETIVOS = {
        "operacao":      ("Resolver o dia a dia",
                          "Atender, receber demandas e dar conta da operação."),
        "relacionamento": ("Conhecer e cuidar dos clientes",
                          "Contexto completo e prevenção de cancelamento."),
        "comercial":     ("Vender e prever receita",
                          "Gerir o funil, projetar resultado e medir o time."),
        "growth":        ("Atrair e qualificar leads",
                          "Encher e priorizar o topo do funil."),
        "governanca":    ("Acompanhar e administrar",
                          "Visão de cima, IA e controle de acesso."),
    }

    st.markdown(
        ui.page_header(
            "O que você quer fazer?",
            "Escolha pelo objetivo. Cada cartão mostra quando usar e um número ao vivo da sua operação.",
            eyebrow="Início",
        ),
        unsafe_allow_html=True,
    )
    st.caption(
        "Escolha pelo objetivo. Cada card mostra **quando usar** e um **número ao vivo** da sua operação. "
        "Toque em **Guia** para objetivo, resultado, dados e chat com IA."
    )

    # 1) Assistente de busca: entenda o que o usuário precisa em linguagem natural
    query = st.text_input(
        "O que você precisa fazer?",
        key="catalog_search",
        placeholder="Descreva com suas palavras: «cliente quer cancelar», «esqueci de dar retorno», «quanto vou faturar»…",
        label_visibility="collapsed",
    )
    q = (query or "").strip()

    # 2) Desambiguação dos serviços que mais confundem
    with st.expander("Confuso entre serviços parecidos? Veja a diferença"):
        st.markdown(
            "- **Cliente 360** = ficha consolidada agora · **Histórico 360** = linha do tempo cronológica\n"
            "- **Saúde da Conta** = risco de *cancelamento* · **Qualificação de Leads** = potencial de *compra*\n"
            "- **Insights com IA** = recomenda a ação · **Visão Executiva** = mostra os KPIs"
        )

    st.divider()

    # 3a) Com busca: mostra os resultados ranqueados por relevância e para aqui.
    if q:
        results = search_services(q)
        if not results:
            st.info(
                f'Não encontrei nada para "{query}". '
                "Tente outras palavras (ex.: «cancelamento», «lembrete», «vendas») "
                "ou navegue pelas categorias apagando a busca."
            )
        else:
            s_label = "serviço" if len(results) == 1 else "serviços"
            st.markdown(f"#### Encontrei {len(results)} {s_label} para você")
            st.caption("Ordenados do mais indicado para o menos. Apague a busca para ver o catálogo completo.")
            for chunk_start in range(0, len(results), 3):
                chunk = results[chunk_start: chunk_start + 3]
                cols = st.columns(len(chunk))
                for col, service in zip(cols, chunk):
                    with col:
                        _render_service_card(service, allowed_sections, live_stats, key_prefix="search")
        st.markdown(" ")
        render_benchmark_comparison(compact=True)
        return

    # 3b) Sem busca: uma aba por objetivo, cartões em grade
    _grupos = []
    for category in CATEGORIES:
        services = get_services_by_category(str(category["id"]))
        if services:
            titulo, subtitulo = OBJETIVOS.get(
                str(category["id"]),
                (str(category["title"]), str(category.get("tagline", ""))),
            )
            _grupos.append((titulo, subtitulo, services))

    if not _grupos:
        st.info("Nenhum serviço disponível para o seu perfil.")
    else:
        _abas = st.tabs([f"{titulo} · {len(servs)}" for titulo, _, servs in _grupos])
        for _aba, (titulo, subtitulo, services) in zip(_abas, _grupos):
            with _aba:
                st.caption(subtitulo)
                for chunk_start in range(0, len(services), 3):
                    chunk = services[chunk_start: chunk_start + 3]
                    cols = st.columns(3)
                    for col, service in zip(cols, chunk):
                        with col:
                            _render_service_card(service, allowed_sections, live_stats, key_prefix="svc")

    # Comparativo Benchmark fecha o catálogo: depois de ver o que entregamos,
    # o leitor vê como isso se posiciona contra o mercado.
    st.markdown(" ")
    render_benchmark_comparison(compact=True)



@st.cache_resource(show_spinner=False)
def _inicializar_banco(identidade: str) -> str:
    """Cria/migra o schema uma vez por processo e por banco.

    `init_database()` executa dezenas de DDL e migrações idempotentes. Chamada
    no corpo do script, rodava a cada rerun do Streamlit — a cada clique —
    abrindo conexões e percorrendo o catálogo do Postgres à toa. A chave é a
    identidade do banco (URL, schema e arquivo SQLite), então trocar de banco
    no mesmo processo (como os testes fazem) inicializa de novo. Exceção não
    entra no cache: se falhar, a próxima execução tenta outra vez.
    """
    return init_database()


_inicializar_banco(
    "|".join((crm_db.database_url(), crm_db.pg_schema(), str(getattr(crm_backend_module, "DB_PATH", ""))))
)

# Vitrine pública (democrm.trustcorp.com.br).
#
# Ligada por CRM_DEMO_DATASET=meishop, apenas no serviço de demonstração do
# Railway. Esse serviço roda sem DATABASE_URL, em SQLite dentro do contêiner:
# a carga acontece na primeira sessão depois de cada deploy e o ambiente se
# restaura sozinho, o que é a propriedade que se quer numa vitrine — visitante
# pode desarrumar à vontade.
#
# A produção não define a variável, e mesmo que definisse a carga se recusa a
# rodar quando existe DATABASE_URL. São duas travas para o mesmo acidente,
# porque o acidente apagaria a base real.
if demo_meishop.modo_demonstracao():
    demo_meishop.preparar_demonstracao_no_arranque()

restore_session_from_url()
flush_pending_toast()

if "crm_user" not in st.session_state:
    show_login()
    st.stop()

maybe_show_onboarding_tour()


@st.cache_data(show_spinner=False)
def _dados_da_versao(versao: str) -> dict:
    """Carrega o banco inteiro, memorizado por versão dos dados.

    `get_data()` lê todas as tabelas para DataFrames. Sem cache isso
    acontecia a cada rerun do Streamlit — ou seja, a cada clique, filtro ou
    tecla digitada num campo. Num CRM com histórico acumulado, essa é a
    origem dominante de lentidão.

    A chave é o carimbo `data_version()`, que o backend avança dentro da
    mesma transação de qualquer escrita. Enquanto ninguém grava, o cache
    serve; assim que alguém grava, a chave muda e a próxima leitura vai ao
    banco. Não existe janela de dado velho — que é justamente o risco de um
    cache baseado em TTL.
    """
    return get_data()


user = st.session_state["crm_user"]

# O cache é da base inteira, por versão dos dados; o recorte por usuário é
# aplicado depois. Fazer o contrário — cachear já filtrado — geraria uma cópia
# do banco por pessoa logada, multiplicando memória sem necessidade.
data = aplicar_visibilidade(_dados_da_versao(data_version()), user)
customers_df = data["customers"]
tickets_df = data["tickets"]
deals_df = data["deals"]
campaigns_df = data["campaigns"]
tasks_df = data["tasks"]
interactions_df = data["interactions"]
users_df = data["users"]
audit_df = data["audit_log"]
role_permissions_df = data["role_permissions"]
webhook_df = data["webhook_events"]
timeline = get_timeline(interactions_df)
customer_lookup = build_customer_lookup(customers_df)


def aviso_de_visibilidade() -> None:
    """Deixa explícito quando a tela mostra um recorte, não a base inteira.

    Sem este aviso, quem não é administrador abre o CRM, vê menos clientes do
    que esperava e conclui que houve perda de dados. Filtro silencioso é
    indistinguível de defeito para quem está do outro lado da tela.
    """
    if ve_tudo(user):
        return
    st.caption(
        f"Exibindo apenas os registros sob responsabilidade de {user['full_name']}. "
        "Para ver a base completa, fale com um administrador."
    )

# Responsáveis possíveis vêm apenas de contas existentes.
#
# Antes esta lista somava os donos já gravados nos registros, o que
# perpetuava o problema: um nome sem conta aparecia como opção e podia ser
# atribuído a novos registros para sempre. Com visibilidade por login, um
# registro assim ficaria invisível para todo mundo.
owner_options = sorted(
    {
        *users_df["full_name"].dropna().tolist(),
    }
)

selected_country = "Todos"
selected_owner = "Todos"

allowed_sections = get_role_sections(user["role"])
if "Serviços" not in allowed_sections:
    allowed_sections = ["Serviços", *allowed_sections]
primary_sections, secondary_sections = split_nav_sections(allowed_sections)

if "nav_section" not in st.session_state or st.session_state["nav_section"] not in allowed_sections:
    st.session_state["nav_section"] = primary_sections[0] if primary_sections else allowed_sections[0]
sync_nav_widgets_from_section(allowed_sections, primary_sections, secondary_sections)

with st.sidebar:
    # ------------------------------------------------------------------
    # Lateral no padrão dos CRMs líderes: marca compacta, busca no topo,
    # navegação como menu (não formulário) e conta do usuário no rodapé.
    # ------------------------------------------------------------------
    st.markdown(
        f"""
<div class="side-brand">
  <img class="side-brand-logo" src="{brand_assets.data_uri("emblema")}" alt="" aria-hidden="true">
  <span class="side-brand-name" translate="no">Trust<strong>CRM</strong></span>
</div>
""",
        unsafe_allow_html=True,
    )

    # Busca global no topo (HubSpot/Attio): um campo para cliente,
    # oportunidade e chamado — sem adivinhar em qual módulo o registro mora.
    _search_term = st.text_input(
        "Buscar",
        key="global_search_term",
        placeholder="Buscar cliente, negócio, chamado…",
        label_visibility="collapsed",
        help="Busca em Clientes 360, Funil Comercial e Atendimento ao mesmo tempo.",
    )
    if _search_term:
        _results = global_search(_search_term, customers_df, deals_df, tickets_df)

        def _go_to_result(item: dict[str, Any]) -> None:
            navigate_to_section(item["section"])

        render_global_search(_results, on_select=_go_to_result)

    st.markdown('<div class="side-label">Navegação</div>', unsafe_allow_html=True)
    st.radio(
        "Principal",
        primary_sections,
        key="nav_primary",
        format_func=nav_option_label,
        on_change=on_primary_nav_change,
        label_visibility="collapsed",
    )

    if secondary_sections:
        st.markdown('<div class="side-label">Mais módulos</div>', unsafe_allow_html=True)
        st.selectbox(
            "Mais módulos",
            [MORE_NAV_PLACEHOLDER, *secondary_sections],
            key="nav_more_select",
            on_change=on_more_nav_change,
            label_visibility="collapsed",
            help="Cadências, marketing, admin e ferramentas avançadas.",
        )

    if (
        secondary_sections
        and st.session_state.get("nav_more_select", MORE_NAV_PLACEHOLDER) != MORE_NAV_PLACEHOLDER
    ):
        section = str(st.session_state["nav_more_select"])
    else:
        section = str(st.session_state["nav_primary"])
    st.session_state["nav_section"] = section
    if section in secondary_sections:
        # Módulo fora do trilho principal: o CSS apaga o destaque do último item
        # principal e acende o ícone de «mais módulos».
        st.markdown('<span class="rail-secondary-active"></span>', unsafe_allow_html=True)

    st.markdown('<div class="side-label">Ferramentas</div>', unsafe_allow_html=True)
    _filters_active = (
        st.session_state.get("filter_country", "Todos") != "Todos"
        or st.session_state.get("filter_owner", "Todos") != "Todos"
    )
    _filters_label = "🔎 Filtros globais — ATIVOS" if _filters_active else "🔎 Filtros globais"
    with st.expander(_filters_label, expanded=_filters_active):
        st.caption("Estes filtros afetam TODAS as telas (KPIs, tickets, funil, clientes).")
        selected_country = st.selectbox("Mercado", ["Todos", "Brasil", "Estados Unidos"], key="filter_country")
        selected_owner = st.selectbox("Responsavel", ["Todos"] + owner_options, key="filter_owner")
        def _clear_global_filters() -> None:
            st.session_state["filter_country"] = "Todos"
            st.session_state["filter_owner"] = "Todos"
            queue_toast("Filtros globais limpos.", icon="🔎")

        # Visões salvas: o mesmo recorte de filtros reaplicado em um clique,
        # em vez de refeito toda sessão.
        _view_module = "filtros-globais"
        _view_keys = ["filter_country", "filter_owner"]
        _reader = lambda key: get_user_preference(user["username"], key, "")  # noqa: E731
        _writer = lambda key, value: set_user_preference(user["username"], key, value)  # noqa: E731

        # As ações rodam em callbacks (on_click): o Streamlit proíbe alterar o
        # valor de um widget já instanciado, e os seletores de filtro acima já
        # foram criados neste ponto. Callbacks executam antes da próxima
        # renderização, que é justamente onde essa escrita é permitida.
        def _apply_saved_view() -> None:
            chosen = st.session_state.get("saved_view_pick", "")
            view = get_view(_reader, _view_module, chosen)
            if not view:
                return
            apply_view_to_state(view, st.session_state, _view_keys)
            queue_toast(f"Visão «{view.name}» aplicada.", icon="🔖")

        def _delete_saved_view() -> None:
            chosen = st.session_state.get("saved_view_pick", "")
            delete_view(_reader, _writer, _view_module, chosen)
            st.session_state["saved_view_pick"] = "— escolher —"
            queue_toast("Visão removida.", icon="🗑️")

        def _save_current_view() -> None:
            name = st.session_state.get("new_view_name", "")
            try:
                save_view(
                    _reader,
                    _writer,
                    _view_module,
                    name,
                    capture_filters(st.session_state, _view_keys),
                )
            except SavedViewError as exc:
                st.session_state["_view_error"] = str(exc)
                return
            st.session_state["_view_error"] = ""
            st.session_state["new_view_name"] = ""
            queue_toast(f"Visão «{name}» salva.", icon="🔖")

        _saved_views = load_views(_reader, _view_module)
        if _saved_views:
            _chosen = st.selectbox(
                "Visões salvas",
                ["— escolher —", *[v.name for v in _saved_views]],
                key="saved_view_pick",
            )
            if _chosen != "— escolher —":
                pick_cols = st.columns(2)
                pick_cols[0].button(
                    "Aplicar", key="apply_view", width="stretch", on_click=_apply_saved_view
                )
                pick_cols[1].button(
                    "Excluir", key="delete_view", width="stretch", on_click=_delete_saved_view
                )

        _new_view_name = st.text_input(
            "Salvar recorte atual como",
            key="new_view_name",
            placeholder="Ex.: Minha carteira Brasil",
        )
        st.button(
            "Salvar visão",
            key="save_view_btn",
            width="stretch",
            disabled=not _new_view_name,
            on_click=_save_current_view,
        )
        if st.session_state.get("_view_error"):
            st.error(st.session_state["_view_error"])

        if _filters_active:
            st.button(
                "Limpar filtros",
                use_container_width=True,
                key="clear-filters",
                on_click=_clear_global_filters,
            )
    with st.expander("Assistente IA (DeepSeek)", expanded=False):
        render_global_assistant()

    with st.expander(":material/manage_accounts: Minha conta", expanded=False):
        st.caption("Altere sua senha de acesso ao CRM.")
        with st.form("change-password-form"):
            current_pw = st.text_input("Senha atual", type="password")
            new_pw = st.text_input("Nova senha", type="password")
            confirm_pw = st.text_input("Confirmar nova senha", type="password")
            submitted_change = st.form_submit_button("Atualizar senha", use_container_width=True)

        if submitted_change:
            if not current_pw or not new_pw or not confirm_pw:
                st.error("Preencha todos os campos.")
            elif new_pw != confirm_pw:
                st.error("A nova senha e a confirmação não conferem.")
            elif len(new_pw) < 8:
                st.error("Use uma senha com pelo menos 8 caracteres.")
            else:
                try:
                    change_own_password(user, current_pw, new_pw)
                except ValueError as exc:
                    st.error(str(exc))
                except Exception:
                    st.error("Não foi possível atualizar a senha agora.")
                else:
                    queue_toast("Senha atualizada com sucesso.", icon="✅")
                    # Opcionalmente, força novo login
                    # end_user_session()
        st.divider()
        _render_totp_settings(user)
        st.divider()
        if st.button("Rever tour de boas-vindas", use_container_width=True, key="rever-tour"):
            st.session_state["tour_step"] = 0
            st.session_state["show_tour"] = True
            st.session_state.pop("tour_done_session", None)
            st.rerun()
    with st.expander("Sistema", expanded=False):
        st.caption(f"Banco: {DB_PATH}")
        public_url = os.getenv("CRM_PUBLIC_URL", "").strip()
        if public_url:
            st.markdown(f"[URL produção]({public_url})")
        if not os.getenv("DEEPSEEK_API_KEY", "").strip():
            st.caption("Defina DEEPSEEK_API_KEY para o chat.")

    # Rodapé: usuário logado (como nos líderes: conta embaixo, navegação em cima)
    _name_parts = [p for p in str(user.get("full_name", "")).split() if p]
    _initials = (
        (_name_parts[0][0] + (_name_parts[-1][0] if len(_name_parts) > 1 else "")).upper()
        if _name_parts
        else "?"
    )
    st.markdown(
        f"""
<div class="side-user">
  <div class="side-avatar">{esc(_initials)}</div>
  <div class="side-user-meta">
    <div class="side-user-name">{esc(user["full_name"])}</div>
    <div class="side-user-role">{esc(user["role"])}</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )
    if st.button("Sair", use_container_width=True, key="sidebar-logout"):
        end_user_session()

filtered_customers = customers_df.copy()
if selected_country != "Todos":
    filtered_customers = filtered_customers[filtered_customers["country"] == selected_country]
if selected_owner != "Todos":
    filtered_customers = filtered_customers[filtered_customers["owner"] == selected_owner]

selected_customer_ids = filtered_customers["customer_id"].tolist()
filtered_tickets = tickets_df[tickets_df["customer_id"].isin(selected_customer_ids)]
filtered_deals = deals_df[deals_df["customer_id"].isin(selected_customer_ids)]
filtered_interactions = interactions_df[interactions_df["customer_id"].isin(selected_customer_ids)]

open_tickets = filtered_tickets[filtered_tickets["status"] != "Resolvido"]
sla_breached = open_tickets[open_tickets["age_hours"] > open_tickets["sla_hours"]]
avg_health = int(filtered_customers["health_score"].mean()) if not filtered_customers.empty else 0
avg_csat = round(filtered_tickets[filtered_tickets["csat"] > 0]["csat"].mean(), 1) if not filtered_tickets[filtered_tickets["csat"] > 0].empty else 0
pipeline_open = filtered_deals[~filtered_deals["stage"].isin(["Fechado ganho", "Fechado perdido"])]["value"].sum() if not filtered_deals.empty else 0
won_value = filtered_deals[filtered_deals["stage"] == "Fechado ganho"]["value"].sum() if not filtered_deals.empty else 0

# Catálogo de KPIs da Visão Executiva: cada usuário escolhe quais aparecem e
# em que ordem (ver `_render_exec_report_settings`), em vez de um recorte
# fixo igual para todo mundo. As funções são lazy (lambda) porque nem todo
# KPI precisa ser calculado sempre — só os que a pessoa escolheu mostrar.
EXEC_KPI_CATALOG: dict[str, tuple[str, Callable[[], str], str]] = {
    "clientes": ("Clientes monitorados", lambda: str(len(filtered_customers)), "Base com owner e saúde."),
    "tickets_abertos": ("Tickets abertos", lambda: str(len(open_tickets)), "Fila de atendimento."),
    "funil_aberto": ("Funil aberto", lambda: currency(pipeline_open), "Oportunidades em curso."),
    "saude_media": ("Saúde média", lambda: f"{avg_health}/100", "Carteira filtrada."),
    "csat_medio": ("CSAT médio", lambda: str(avg_csat), "Experiência atual do atendimento."),
    "sla_risco": ("SLA em risco", lambda: str(len(sla_breached)), "Tickets acima do prazo alvo."),
    "receita_ganha": ("Receita ganha", lambda: currency(won_value), "Negócios ganhos no recorte."),
    "interacoes": ("Interações", lambda: str(len(filtered_interactions)), "Histórico 360 registrado."),
}
EXEC_GROUP_BY_OPTIONS: dict[str, tuple[str, str]] = {
    "owner": ("Responsável", "owner"),
    "channel": ("Canal", "channel"),
    "category": ("Categoria", "category"),
    "priority": ("Prioridade", "priority"),
}

render_top_bar(section)

# O aviso acompanha o visitante para dentro: quem entrou pela vitrine precisa
# continuar sabendo que é vitrine, em qualquer tela.
faixa_de_demonstracao()

# Senha padrão em ambiente exposto é acesso aberto. O aviso fica visível para o
# admin até que as contas sejam trocadas.
if user.get("role") == "admin":
    try:
        _weak_accounts = accounts_with_default_password()
    except Exception:
        _weak_accounts = []
    if _weak_accounts:
        st.error(
            "**Risco de segurança:** as contas "
            + ", ".join(f"`{name}`" for name in _weak_accounts)
            + " ainda usam a senha padrão publicada no repositório. "
            "Troque em «Minha conta / Trocar senha» — enquanto isso, qualquer pessoa "
            "com o endereço do sistema consegue entrar.",
            icon="🔓",
        )

# Avisa uma vez, antes de qualquer seção desenhar, que a tela pode estar
# mostrando um recorte da base.
aviso_de_visibilidade()

if section == "Visão Executiva":
    render_page_header(section)
    _exec_report_config = get_exec_report_config(user["username"])
    _exec_selected_kpis = [
        kpi_id for kpi_id in _exec_report_config["kpis"] if kpi_id in EXEC_KPI_CATALOG
    ] or list(EXEC_REPORT_DEFAULT_KPIS)
    render_metric_cards(
        [
            (EXEC_KPI_CATALOG[kpi_id][0], EXEC_KPI_CATALOG[kpi_id][1](), EXEC_KPI_CATALOG[kpi_id][2])
            for kpi_id in _exec_selected_kpis
        ]
    )
elif section != "Serviços":
    render_page_header(section)

if section == "Meu Dia":
    meu_dia.render(globals())

elif section == "Serviços":
    render_services_catalog()

elif section == "Visão Executiva":
    visao_executiva.render(globals())

elif section == "Atendimento":
    atendimento.render(globals())

elif section == "Canais":
    canais.render(globals())

elif section == "Clientes 360":
    clientes_360.render(globals())

elif section == "Funil Comercial":
    funil.render(globals())

elif section == "Cadências":
    with st.container(border=True):
        _cad_last_activity = last_activity_by_customer(data.get("interactions", pd.DataFrame()))
        render_cadences(user, customers_df, deals_df, _cad_last_activity)

elif section == "Saúde da Conta":
    with st.container(border=True):
        render_health(user, can_manage(user["role"], "admin"))

elif section == "Modelos de Mensagem":
    with st.container(border=True):
        render_templates(user, customers_df, can_manage(user["role"], "admin"))

elif section == "Previsão de Receita":
    with st.container(border=True):
        render_forecast(selected_owner)

elif section == "Produtividade":
    with st.container(border=True):
        render_productivity()

elif section == "Qualificação de Leads":
    with st.container(border=True):
        render_lead_scoring(user, can_manage(user["role"], "admin"))

elif section == "Segmentação":
    with st.container(border=True):
        render_segmentation(filtered_customers if not filtered_customers.empty else customers_df)

elif section == "Insights com IA":
    with st.container(border=True):
        render_ai_insights(filtered_customers if not filtered_customers.empty else customers_df)

elif section == "Marketing":
    marketing.render(globals())

elif section == "Automações":
    automacoes.render(globals())

elif section == "Importar Dados":
    importar_dados.render(globals())

elif section == "Manual de Serviços":
    manual_servicos.render(globals())

elif section == "Comparativo de Mercado":
    from benchmark_market import benchmark_markdown

    render_benchmark_comparison(compact=False)
    st.markdown(" ")
    st.download_button(
        "⬇️ Baixar comparativo (.md)",
        data=benchmark_markdown(),
        file_name="Trust_CRM_Comparativo_Benchmark.md",
        mime="text/markdown",
        help="Para levar a uma reunião ou compartilhar com a diretoria",
    )

elif section == "Administração":
    administracao.render(globals())


st.markdown(" ")

# O rodapé é o termômetro da migração: diz qual banco o processo REALMENTE
# enxerga. Os três estados cobrem os três diagnósticos possíveis:
#   - PostgreSQL............. DATABASE_URL chegou e é válida
#   - "definida, mas inválida" a variável chega ao processo com valor errado
#   - "arquivo local"........ a variável NEM CHEGA ao processo (serviço ou
#                              ambiente errado no painel)
_db_url = crm_db.database_url()
if crm_db.is_postgres():
    _backend_label = "PostgreSQL"
elif _db_url:
    _backend_label = (
        "SQLite — DATABASE_URL definida, mas inválida "
        "(o VALOR deve começar com postgresql://)"
    )
else:
    _backend_label = "SQLite (arquivo local — DATABASE_URL não chega ao app)"
st.caption(
    f"Build date: {date.today().isoformat()} | Persistência: {_backend_label} "
    "| Auth: ativa | Canais: WhatsApp, Email, Formularios"
)
