"""Mr.Holmes CRM - persisted CRM with auth, roles and channel intake."""

from __future__ import annotations

import os
from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from services_catalog import SERVICE_CATALOG, resolve_service_section
from service_guide_ui import open_service_guide_dialog, render_global_assistant
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
    add_campaign,
    add_customer,
    add_deal,
    add_ticket,
    create_channel_ticket,
    get_actions,
    get_permissions,
    get_roles,
    get_webhook_verify_token,
    has_permission,
    get_data,
    get_role_sections,
    get_timeline,
    init_database,
    update_role_permissions,
    verify_login,
)


PRIMARY_NAV_ORDER = [
    "Serviços",
    "Visão Executiva",
    "Atendimento",
    "Clientes 360",
    "Funil Comercial",
    "Canais",
]
MORE_NAV_PLACEHOLDER = "— mais módulos —"


def split_nav_sections(allowed: list[str]) -> tuple[list[str], list[str]]:
    primary = [name for name in PRIMARY_NAV_ORDER if name in allowed]
    secondary = [name for name in allowed if name not in primary]
    return primary, secondary


BENCHMARKS = pd.DataFrame(
    [
        {
            "player": "Salesforce",
            "market": "Estados Unidos",
            "strength": "Customer 360, sales + service + marketing integrados, IA e plataforma escalavel.",
            "what_to_absorb": "Visao unica do cliente, handoff entre times e operacao orientada por dados.",
        },
        {
            "player": "HubSpot",
            "market": "Estados Unidos",
            "strength": "UX simples, onboarding rapido e distribuicao clara entre times.",
            "what_to_absorb": "Baixo atrito de adocao e fluxo claro do lead ao atendimento.",
        },
        {
            "player": "RD Station CRM",
            "market": "Brasil",
            "strength": "Funil comercial, operacao por WhatsApp e relatorios para produtividade.",
            "what_to_absorb": "Historico de interacoes, produtividade comercial e leitura de conversao.",
        },
        {
            "player": "Agendor",
            "market": "Brasil",
            "strength": "Operacao simples para PMEs e linguagem local de vendas.",
            "what_to_absorb": "Clareza operacional e menor friccao de uso.",
        },
    ]
)


st.set_page_config(
    page_title="Mr.Holmes CRM",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(
    """
<style>
    @keyframes rise-in {
        from {
            opacity: 0;
            transform: translateY(10px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    @keyframes pulse-glow {
        0%,
        100% {
            box-shadow: 0 16px 46px rgba(0, 0, 0, 0.28);
        }
        50% {
            box-shadow: 0 18px 52px rgba(229, 9, 20, 0.22);
        }
    }

    :root {
        --bg: #0b0b0f;
        --surface: #12121b;
        --surface-soft: #1a1a27;
        --ink: #f5f7ff;
        --muted: #ccd0df;
        --line: rgba(255, 255, 255, 0.14);
        --brand: #e50914;
        --brand-soft: #ff3b44;
        --accent: #ffcc66;
        --success: #22c55e;
        --success-soft: rgba(34, 197, 94, 0.18);
        --warning: #f59e0b;
        --warning-soft: rgba(245, 158, 11, 0.2);
        --danger: #ef4444;
        --danger-soft: rgba(239, 68, 68, 0.2);
        --shadow: 0 16px 40px rgba(0, 0, 0, 0.34);
    }

    .stApp {
        background:
            radial-gradient(circle at 18% 0%, rgba(229, 9, 20, 0.24), transparent 34%),
            radial-gradient(circle at 82% 2%, rgba(255, 204, 102, 0.12), transparent 24%),
            linear-gradient(180deg, #050507 0%, #0b0b0f 34%, #111119 100%);
        color: var(--ink);
        font-family: "Space Grotesk", "Sora", "Segoe UI", sans-serif;
    }

    [data-testid="stHeader"] {
        background: rgba(5, 5, 7, 0.0);
    }

    [data-testid="stSidebarContent"] {
        background: linear-gradient(180deg, #0a0a10 0%, #11111a 100%);
        color: #f8fafc;
        border-right: 1px solid var(--line);
    }

    [data-testid="stSidebarContent"] .stRadio label,
    [data-testid="stSidebarContent"] .stSelectbox label,
    [data-testid="stSidebarContent"] p,
    [data-testid="stSidebarContent"] span,
    [data-testid="stSidebarContent"] div {
        color: #f5f7ff !important;
    }

    label[data-testid="stWidgetLabel"],
    .stTextInput label,
    .stTextArea label,
    .stNumberInput label,
    .stDateInput label,
    .stSelectbox label,
    .stMultiSelect label,
    .stRadio label {
        color: #e8ecf4 !important;
        font-weight: 600 !important;
    }

    .login-panel label,
    .login-panel p,
    .login-panel span,
    .login-panel small {
        color: #f0f3ff !important;
    }

    .page-head h2 {
        color: #ffffff;
        margin: 0 0 4px;
        font-size: 1.55rem;
    }

    .page-head p {
        color: var(--muted);
        margin: 0 0 16px;
        font-size: 0.95rem;
    }

    .top-nav-strip {
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
        margin: 2px 0 14px;
    }


    .top-nav-pill {
        display: inline-flex;
        align-items: center;
        gap: 7px;
        border-radius: 999px;
        padding: 6px 12px;
        background: rgba(255, 255, 255, 0.06);
        border: 1px solid rgba(255, 255, 255, 0.18);
        color: #f2f4ff;
        font-size: 11px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }

    .hero {
        background: linear-gradient(120deg, rgba(5, 5, 8, 0.96), rgba(29, 5, 8, 0.92));
        border-radius: 24px;
        padding: 28px 30px;
        color: white;
        box-shadow: var(--shadow);
        margin-bottom: 18px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        animation: rise-in 0.45s ease-out both, pulse-glow 6.2s ease-in-out 0.7s infinite;
    }

    .hero-grid {
        display: grid;
        grid-template-columns: 1.5fr 1fr;
        gap: 18px;
        align-items: end;
    }

    .hero h1 {
        font-size: 1.6rem;
        margin-bottom: 0.35rem;
        letter-spacing: -0.02em;
        line-height: 1.3;
    }

    .hero p {
        color: rgba(245, 247, 255, 0.88);
        font-size: 1rem;
        max-width: 62ch;
        margin: 0;
    }

    .hero-badges {
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
        justify-content: flex-end;
    }

    .badge {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 9px 12px;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.08);
        border: 1px solid rgba(255, 255, 255, 0.2);
        font-size: 0.85rem;
    }

    .panel {
        background: linear-gradient(180deg, rgba(26, 26, 39, 0.94), rgba(18, 18, 27, 0.94));
        border: 1px solid var(--line);
        border-radius: 20px;
        padding: 18px;
        box-shadow: var(--shadow);
        animation: rise-in 0.42s ease-out both;
    }

    .section-title {
        font-size: 1.08rem;
        font-weight: 700;
        margin-bottom: 0.8rem;
        color: #f5f7ff;
    }

    .mini-card {
        background: linear-gradient(180deg, rgba(255,255,255,0.06), rgba(255,255,255,0.03));
        border: 1px solid var(--line);
        border-radius: 18px;
        padding: 16px;
        min-height: 120px;
        margin-bottom: 10px;
        transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
        animation: rise-in 0.45s ease-out both;
    }

    .mini-card:hover {
        transform: translateY(-4px);
        border-color: rgba(229, 9, 20, 0.4);
        box-shadow: 0 14px 32px rgba(0, 0, 0, 0.3);
    }

    .mini-label {
        font-size: 0.74rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--muted);
    }

    .mini-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: #ffffff;
        margin: 0.2rem 0 0.35rem;
    }

    .mini-caption {
        color: var(--muted);
        font-size: 0.92rem;
    }

    .status-pill {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 600;
    }

    .status-open { background: var(--warning-soft); color: #ffe2a6; border: 1px solid rgba(245, 158, 11, 0.38); }
    .status-progress { background: rgba(59, 130, 246, 0.2); color: #bfdbfe; border: 1px solid rgba(59, 130, 246, 0.38); }
    .status-won { background: var(--success-soft); color: #bbf7d0; border: 1px solid rgba(34, 197, 94, 0.38); }
    .status-lost { background: var(--danger-soft); color: #fecaca; border: 1px solid rgba(239, 68, 68, 0.38); }
    .status-active { background: rgba(255, 204, 102, 0.18); color: #ffe2a8; border: 1px solid rgba(255, 204, 102, 0.36); }

    .empty-state {
        border-radius: 16px;
        padding: 15px 16px;
        border: 1px dashed rgba(255, 255, 255, 0.26);
        background: rgba(255, 255, 255, 0.05);
        color: #e4e7f5;
        font-weight: 600;
        margin: 8px 0;
    }

    .timeline-item {
        border-left: 2px solid rgba(255, 255, 255, 0.24);
        padding-left: 14px;
        margin-left: 6px;
        margin-bottom: 14px;
    }

    .timeline-date {
        font-size: 0.78rem;
        color: var(--muted);
        margin-bottom: 2px;
    }

    .timeline-title {
        font-weight: 700;
        color: #f5f7ff;
        margin-bottom: 2px;
    }

    .timeline-copy {
        color: var(--muted);
        font-size: 0.92rem;
    }

    .stTextInput input,
    .stTextInput input[data-testid="stTextInputRootElement"],
    .stTextArea textarea,
    .stNumberInput input,
    .stDateInput input,
    .stSelectbox div[data-baseweb="select"] > div {
        background: rgba(12, 12, 20, 0.92) !important;
        color: #f5f7ff !important;
        -webkit-text-fill-color: #f5f7ff !important;
        caret-color: #ffcc66 !important;
        text-shadow: none !important;
        border: 1px solid rgba(255, 255, 255, 0.28) !important;
        border-radius: 12px !important;
    }

    .stTextInput input::placeholder,
    .stTextInput input::-webkit-input-placeholder,
    .stTextInput input::-moz-placeholder,
    .stTextArea textarea::placeholder {
        color: rgba(232, 236, 244, 0.55) !important;
        -webkit-text-fill-color: rgba(232, 236, 244, 0.55) !important;
        opacity: 1 !important;
    }

    .stTextInput input:focus,
    .stTextArea textarea:focus,
    .stNumberInput input:focus,
    .stDateInput input:focus,
    .stSelectbox div[data-baseweb="select"] > div:focus-within {
        border-color: rgba(255, 59, 68, 0.72) !important;
        box-shadow: 0 0 0 3px rgba(229, 9, 20, 0.22) !important;
    }

    .stButton > button {
        border-radius: 12px !important;
        border: none !important;
        background: linear-gradient(90deg, var(--brand), #b20710) !important;
        color: #ffffff !important;
        font-weight: 700 !important;
        min-height: 42px !important;
        box-shadow: 0 8px 20px rgba(229, 9, 20, 0.22);
        transition: transform 0.2s ease, box-shadow 0.2s ease, background 0.2s ease !important;
    }

    [data-testid="stSidebar"] .stButton > button {
        background: rgba(255, 255, 255, 0.08) !important;
        border: 1px solid rgba(255, 255, 255, 0.16) !important;
        box-shadow: none !important;
    }

    .nav-secondary-hint {
        font-size: 0.78rem;
        color: var(--muted);
        margin: 4px 0 8px;
    }

    .top-nav-bar {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 14px;
        padding: 8px 12px;
        margin-bottom: 16px;
    }

    .top-nav-bar .section-crumb {
        color: var(--muted);
        font-size: 0.9rem;
        padding-top: 8px;
    }

    .top-nav-bar .section-crumb strong {
        color: #ffffff;
    }

    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 14px 28px rgba(229, 9, 20, 0.34);
        background: linear-gradient(90deg, var(--brand-soft), #c60d17) !important;
    }

    div[data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.14);
        border-radius: 16px;
        padding: 12px;
    }

    div[data-testid="stMetricLabel"] * {
        color: var(--muted) !important;
    }

    div[data-testid="stMetricValue"] * {
        color: #ffffff !important;
    }

    .stAlert {
        border-radius: 14px;
        border-width: 1px !important;
    }

    .stAlert p,
    .stAlert span,
    .stAlert div {
        color: #f8fafc !important;
    }

    @media (max-width: 980px) {
        .hero-grid {
            grid-template-columns: 1fr;
        }

        .hero-badges {
            justify-content: flex-start;
        }
    }

    @media (prefers-reduced-motion: reduce) {
        .hero,
        .panel,
        .mini-card {
            animation: none !important;
            transition: none !important;
        }
    }
</style>
""",
    unsafe_allow_html=True,
)


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
    st.markdown('<div class="top-nav-bar">', unsafe_allow_html=True)
    col_home, col_back, col_crumb = st.columns([1.1, 1.1, 4.8])
    with col_home:
        if st.button("Início", key="nav-top-home", use_container_width=True, help="Voltar ao catálogo de serviços"):
            navigate_to_section("Serviços")
    with col_back:
        can_back = active_section != "Serviços"
        if st.button(
            "Voltar",
            key="nav-top-back",
            use_container_width=True,
            disabled=not can_back,
            help="Retorna à tela anterior",
        ):
            go_back()
    with col_crumb:
        st.markdown(
            f'<div class="section-crumb">Você está em: <strong>{active_section}</strong></div>',
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)


def render_metric_cards(metrics: list[tuple[str, str, str]]) -> None:
    cols = st.columns(len(metrics))
    for col, (label, value, caption) in zip(cols, metrics):
        with col:
            st.markdown(
                f"""
<div class="mini-card">
    <div class="mini-label">{label}</div>
    <div class="mini-value">{value}</div>
    <div class="mini-caption">{caption}</div>
</div>
""",
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


def show_login() -> None:
    st.markdown(
        """
<div class="hero">
    <div class="hero-grid">
        <div>
            <h1>CRM com persistencia, perfis e intake multicanal</h1>
            <p>
                Esta versao sai do mock estatico e entra em operacao local com SQLite, login, perfis de acesso
                e entrada de canais para WhatsApp, email e formularios.
            </p>
        </div>
        <div class="hero-badges">
            <div class="badge">🗄️ SQLite local</div>
            <div class="badge">🔐 Auth e roles</div>
            <div class="badge">📨 Canais</div>
        </div>
    </div>
</div>
""",
        unsafe_allow_html=True,
    )
    left, right = st.columns([0.9, 1.1])
    with left:
        st.markdown('<div class="login-panel">', unsafe_allow_html=True)
        with st.form("crm-login"):
            st.subheader("Entrar")
            username = st.text_input("Usuario", placeholder="Digite seu usuário")
            password = st.text_input("Senha", type="password", placeholder="Digite sua senha")
            submitted = st.form_submit_button("Acessar", width="stretch", type="primary")
        st.markdown("</div>", unsafe_allow_html=True)
        if submitted:
            user = verify_login(username.strip(), password)
            if user:
                st.session_state["crm_user"] = user
                st.rerun()
            st.error("Credenciais invalidas.")
    with right:
        st.markdown("### Contas de demonstracao")
        st.code(
            "admin / admin123\n"
            "atendimento / atend123\n"
            "vendas / vendas123\n"
            "marketing / mkt123\n"
            "cs / cs123"
        )
        st.info(
            "Sem credenciais reais de WhatsApp ou email, a conexao de canais entra por intake operacional:"
            " formulario interno e importacao de mensagem/corpo do atendimento."
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


def render_page_header(section: str) -> None:
    hints = {
        "Serviços": "Escolha um módulo abaixo ou use o menu à esquerda.",
        "Visão Executiva": "KPIs e leitura rápida da operação.",
        "Atendimento": "Fila de tickets e SLA.",
        "Clientes 360": "Conta, histórico e contexto comercial.",
        "Funil Comercial": "Oportunidades e etapas de venda.",
        "Canais": "Entrada WhatsApp, e-mail e formulários.",
    }
    st.markdown(
        f'<div class="page-head"><h2>{section}</h2><p>{hints.get(section, "Use os filtros da barra lateral.")}</p></div>',
        unsafe_allow_html=True,
    )


def render_empty_state(message: str) -> None:
    st.markdown(f'<div class="empty-state">{message}</div>', unsafe_allow_html=True)


def render_services_catalog() -> None:
    """Catálogo orientado a objetivo: busca, cards clicáveis e desambiguação.

    Substitui a versão antiga que desenhava cada serviço duas vezes
    (card decorativo NÃO clicável em rolagem horizontal + botões abaixo).
    """
    from services_catalog import CATEGORIES, get_services_by_category

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

    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-title">Início — o que você quer fazer?</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Escolha pelo objetivo. Cada serviço mostra **quando usar** e **o que entrega**. "
        "Toque em **ℹ️ Guia** para objetivo, resultado, dados e chat com IA."
    )

    # 1) Busca por objetivo
    query = st.text_input(
        "Buscar por objetivo",
        key="catalog_search",
        placeholder="Ex.: reduzir cancelamento, priorizar leads, prever receita, atender no prazo…",
        label_visibility="collapsed",
    )
    q = (query or "").strip().lower()

    # 2) Desambiguação dos serviços que mais confundem
    with st.expander("Confuso entre serviços parecidos? Veja a diferença"):
        st.markdown(
            "- **Cliente 360** = ficha consolidada agora · **Histórico 360** = linha do tempo cronológica\n"
            "- **Saúde da Conta** = risco de *cancelamento* · **Qualificação de Leads** = potencial de *compra*\n"
            "- **Insights com IA** = recomenda a ação · **Visão Executiva** = mostra os KPIs"
        )

    st.divider()

    # 3) Serviços agrupados por objetivo, em grade responsiva (sem rolagem horizontal)
    total_shown = 0
    for category in CATEGORIES:
        services = get_services_by_category(str(category["id"]))
        if q:
            services = [
                s for s in services
                if q in " ".join([
                    str(s.get("title", "")),
                    str(s.get("tagline", "")),
                    str(s.get("summary", "")),
                    str(s.get("resultado_esperado", "")),
                    str(s.get("description", "")),
                ]).lower()
            ]
        if not services:
            continue
        total_shown += len(services)

        titulo, subtitulo = OBJETIVOS.get(
            str(category["id"]),
            (str(category["title"]), str(category.get("tagline", ""))),
        )
        st.markdown(f"#### {category['icon']} {titulo}")
        st.caption(subtitulo)

        for chunk_start in range(0, len(services), 3):
            chunk = services[chunk_start: chunk_start + 3]
            cols = st.columns(len(chunk))
            for col, service in zip(cols, chunk):
                with col:
                    with st.container(border=True):
                        st.markdown(f"**{service['title']}**")
                        st.caption(f"🔹 Use quando: {service['tagline']}")
                        st.caption(f"✅ Resultado: {service.get('resultado_esperado', '')}")
                        b_open, b_guide = st.columns(2)
                        with b_open:
                            if st.button(
                                "Abrir",
                                key=f"svc-open-{service['id']}",
                                type="primary",
                                use_container_width=True,
                            ):
                                navigate_to_section(
                                    resolve_service_section(str(service["id"]))
                                )
                        with b_guide:
                            if st.button(
                                "ℹ️ Guia",
                                key=f"svc-guide-{service['id']}",
                                use_container_width=True,
                                help="Objetivo, resultado, dados, resumo e chat IA",
                            ):
                                open_service_guide_dialog(
                                    service,
                                    navigate_to_section,
                                    resolve_service_section,
                                )

    if total_shown == 0:
        st.info(
            f'Nenhum serviço corresponde a "{query}". '
            "Tente outro termo (ex.: vendas, atendimento, leads, churn)."
        )

    st.markdown("</div>", unsafe_allow_html=True)


init_database()

if "crm_user" not in st.session_state:
    show_login()
    st.stop()


user = st.session_state["crm_user"]
data = get_data()
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

owner_options = sorted(
    {
        *users_df["full_name"].dropna().tolist(),
        *customers_df["owner"].dropna().tolist(),
        *tickets_df["owner"].dropna().tolist(),
        *deals_df["owner"].dropna().tolist(),
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
    st.markdown("## Mr.Holmes CRM")
    st.caption("Menu simples: principais abaixo, demais em «mais módulos».")
    st.success(f"{user['full_name']} | {user['role']}")
    if st.button("Início", use_container_width=True):
        navigate_to_section("Serviços")
    if st.button("Sair", use_container_width=True):
        st.session_state.pop("crm_user", None)
        st.rerun()

    st.markdown("**Menu principal**")
    st.radio(
        "Principal",
        primary_sections,
        key="nav_primary",
        on_change=on_primary_nav_change,
        label_visibility="collapsed",
    )

    if secondary_sections:
        st.markdown("**Outras áreas**")
        st.caption("Cadências, marketing, admin e ferramentas avançadas.")
        st.selectbox(
            "Mais módulos",
            [MORE_NAV_PLACEHOLDER, *secondary_sections],
            key="nav_more_select",
            on_change=on_more_nav_change,
            label_visibility="collapsed",
        )

    if (
        secondary_sections
        and st.session_state.get("nav_more_select", MORE_NAV_PLACEHOLDER) != MORE_NAV_PLACEHOLDER
    ):
        section = str(st.session_state["nav_more_select"])
    else:
        section = str(st.session_state["nav_primary"])
    st.session_state["nav_section"] = section

    st.markdown("---")
    selected_country = st.selectbox("Mercado", ["Todos", "Brasil", "Estados Unidos"])
    selected_owner = st.selectbox("Responsavel", ["Todos"] + owner_options)
    with st.expander("Assistente IA (DeepSeek)", expanded=False):
        render_global_assistant()

    with st.expander("Sistema", expanded=False):
        st.caption(f"Banco: {DB_PATH}")
        public_url = os.getenv("CRM_PUBLIC_URL", "").strip()
        if public_url:
            st.markdown(f"[URL produção]({public_url})")
        if not os.getenv("DEEPSEEK_API_KEY", "").strip():
            st.caption("Defina DEEPSEEK_API_KEY para o chat.")


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
pipeline_open = filtered_deals[filtered_deals["stage"] != "Fechado ganho"]["value"].sum() if not filtered_deals.empty else 0
won_value = filtered_deals[filtered_deals["stage"] == "Fechado ganho"]["value"].sum() if not filtered_deals.empty else 0

render_top_bar(section)

if section == "Visão Executiva":
    st.markdown(
        """
<div class="hero">
    <div class="hero-grid">
        <div>
            <h1>Visão executiva</h1>
            <p>Indicadores da operação no recorte de mercado e responsável selecionados na barra lateral.</p>
        </div>
    </div>
</div>
""",
        unsafe_allow_html=True,
    )
    render_metric_cards(
        [
            ("Clientes monitorados", str(len(filtered_customers)), "Base com owner e saúde."),
            ("Tickets abertos", str(len(open_tickets)), "Fila de atendimento."),
            ("Funil aberto", currency(pipeline_open), "Oportunidades em curso."),
            ("Saúde média", f"{avg_health}/100", "Carteira filtrada."),
        ]
    )
elif section != "Serviços":
    render_page_header(section)

if section == "Serviços":
    render_services_catalog()

elif section == "Visão Executiva":
    left, right = st.columns([1.2, 0.8])
    with left:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Panorama operacional</div>', unsafe_allow_html=True)
        summary = pd.DataFrame(
            [
                {"KPI": "CSAT medio", "Valor": avg_csat, "Leitura": "Experiencia atual do atendimento"},
                {"KPI": "SLA em risco", "Valor": len(sla_breached), "Leitura": "Tickets acima do prazo alvo"},
                {"KPI": "Receita ganha", "Valor": currency(won_value), "Leitura": "Negocios ganhos no recorte"},
                {"KPI": "Interacoes", "Valor": len(filtered_interactions), "Leitura": "Historico 360 registrado"},
            ]
        )
        st.dataframe(summary, width="stretch", hide_index=True)
        owner_load = filtered_tickets.groupby("owner").size().reset_index(name="tickets") if not filtered_tickets.empty else pd.DataFrame(columns=["owner", "tickets"])
        if not owner_load.empty:
            st.bar_chart(owner_load.set_index("owner"))
        st.markdown('</div>', unsafe_allow_html=True)
    with right:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Proximas acoes</div>', unsafe_allow_html=True)
        for item in tasks_df.sort_values("due_date").head(6).to_dict("records"):
            st.markdown(f"**{item['task']}**  \nResponsavel: {item['owner']}  \nPrazo: {item['due_date']}  \nVinculo: {item['entity']}")
            st.markdown("---")
        st.markdown('</div>', unsafe_allow_html=True)

elif section == "Atendimento":
    if can_manage(user["role"], "ticket"):
        with st.expander("Novo ticket manual", expanded=False):
            with st.form("new-ticket-form"):
                customer_name = st.selectbox("Cliente", filtered_customers["name"].tolist() if not filtered_customers.empty else customers_df["name"].tolist())
                subject = st.text_input("Assunto")
                category = st.selectbox("Categoria", ["Geral", "Integracao", "Onboarding", "Operacao", "Produto", "Financeiro"])
                priority = st.selectbox("Prioridade", ["Baixa", "Media", "Alta", "Critica"])
                owner = st.selectbox("Responsavel", owner_options)
                channel = st.selectbox("Canal", ["WhatsApp", "Email", "Telefone", "Portal", "Chat", "Formulario"])
                message = st.text_area("Resumo do atendimento")
                submitted = st.form_submit_button("Criar ticket", type="primary")
            if submitted and subject:
                customer_id = customers_df.loc[customers_df["name"] == customer_name, "customer_id"].iloc[0]
                add_ticket(
                    {
                        "customer_id": customer_id,
                        "subject": subject,
                        "channel": channel,
                        "priority": priority,
                        "owner": owner,
                        "category": category,
                        "sla_hours": 8,
                        "message": message or subject,
                    },
                    actor=user,
                    source="ui-atendimento-manual",
                )
                st.success("Ticket criado com persistencia em SQLite.")
                st.rerun()

    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Fila de atendimento</div>', unsafe_allow_html=True)
    ticket_table = filtered_tickets.copy()
    if not ticket_table.empty:
        ticket_table["cliente"] = ticket_table["customer_id"].map(lambda value: customer_lookup[value]["name"])
        ticket_table["sla_status"] = ticket_table.apply(lambda row: "Em risco" if row["age_hours"] > row["sla_hours"] else "No prazo", axis=1)
        st.dataframe(ticket_table[["ticket_id", "cliente", "subject", "channel", "status", "priority", "owner", "sla_status"]], width="stretch", hide_index=True)
    else:
        render_empty_state("Nenhum ticket para os filtros atuais.")
    st.markdown('</div>', unsafe_allow_html=True)

    if not filtered_tickets.empty:
        selected_ticket = st.selectbox("Detalhar ticket", filtered_tickets["ticket_id"].tolist())
        ticket = filtered_tickets[filtered_tickets["ticket_id"] == selected_ticket].iloc[0].to_dict()
        customer = customer_lookup[ticket["customer_id"]]
        cols = st.columns(3)
        details = [
            ("Cliente", customer["name"]),
            ("Canal", ticket["channel"]),
            ("Categoria", ticket["category"]),
            ("Owner", ticket["owner"]),
            ("Prioridade", ticket["priority"]),
            ("CSAT", ticket["csat"] if ticket["csat"] else "Pendente"),
        ]
        for col, pair in zip(cols * 2, details):
            with col:
                st.markdown(f"<div class='mini-card'><div class='mini-label'>{pair[0]}</div><div class='mini-value' style='font-size:1.2rem;'>{pair[1]}</div></div>", unsafe_allow_html=True)
        st.info(f"Ticket aberto em {ticket['opened_at']} | SLA alvo: {ticket['sla_hours']}h | Tempo corrido: {ticket['age_hours']}h")
        st.markdown(f"**Resumo do caso:** {ticket['subject']}")
        st.markdown(f"**Proxima acao sugerida:** {customer['next_action']}")

elif section == "Canais":
    if not can_manage(user["role"], "channel"):
        st.error("Seu perfil nao possui permissao para intake de canais.")
        st.stop()
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Registrar atendimento recebido</div>', unsafe_allow_html=True)
    st.caption("Cliente falou com você por WhatsApp, e-mail ou formulário? Registre aqui e vira um atendimento.")
    st.info("ℹ️ O recebimento automático de WhatsApp e e-mail ainda não está conectado. Por enquanto: escolha a aba do canal por onde o cliente falou, cole a mensagem que ele enviou e clique em «Abrir atendimento». Nada se perde — o contato vira um ticket ligado ao cliente.")
    tabs = st.tabs(["WhatsApp", "Email", "Formulario"])
    channel_config = {
        "WhatsApp": {"sla": 4, "category": "Relacionamento"},
        "Email": {"sla": 12, "category": "Atendimento"},
        "Formulario": {"sla": 8, "category": "Inbound"},
    }
    for tab, channel in zip(tabs, ["WhatsApp", "Email", "Formulario"]):
        with tab:
            with st.form(f"intake-{channel.lower()}"):
                existing_customer = st.selectbox("Cliente já cadastrado (opcional)", [""] + customers_df["name"].tolist(), key=f"existing-{channel}")
                customer_name = st.text_input("Ou cadastre um novo cliente (nome)", key=f"new-customer-{channel}")
                subject = st.text_input("Assunto (do que se trata)", key=f"subject-{channel}")
                owner = st.selectbox("Responsável pelo atendimento", owner_options, key=f"owner-{channel}")
                priority = st.selectbox("Prioridade", ["Baixa", "Media", "Alta", "Critica"], key=f"priority-{channel}")
                city = st.text_input("Cidade", value="Sao Paulo" if channel != "Email" else "Austin", key=f"city-{channel}")
                country = st.selectbox("Pais", ["Brasil", "Estados Unidos"], key=f"country-{channel}")
                note = st.text_area("Mensagem que o cliente enviou (cole aqui)", key=f"message-{channel}")
                uploaded = st.file_uploader("Anexar conversa (opcional: .txt, .csv, .json, .eml)", type=["txt", "csv", "json", "eml"], key=f"upload-{channel}")
                submitted = st.form_submit_button(f"Abrir atendimento ({channel})", type="primary")
            if submitted and subject and (existing_customer or customer_name):
                uploaded_text = ingest_message(uploaded)
                payload = {
                    "customer_id": customers_df.loc[customers_df["name"] == existing_customer, "customer_id"].iloc[0] if existing_customer else "",
                    "customer_name": customer_name or existing_customer,
                    "subject": subject,
                    "channel": channel,
                    "priority": priority,
                    "owner": owner,
                    "sla_hours": channel_config[channel]["sla"],
                    "category": channel_config[channel]["category"],
                    "message": note or uploaded_text or subject,
                    "city": city,
                    "country": country,
                    "segment": "Lead inbound",
                }
                customer_id, ticket_id = create_channel_ticket(
                    payload,
                    actor=user,
                    source=f"ui-canal-{channel.lower()}",
                )
                st.success(f"✅ Atendimento registrado! Cliente {customer_id}, ticket {ticket_id}.")
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(" ")
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Últimos atendimentos registrados</div>', unsafe_allow_html=True)
    latest = tickets_df.sort_values("opened_at", ascending=False).head(8).copy()
    latest["cliente"] = latest["customer_id"].map(lambda value: customer_lookup.get(value, {}).get("name", value))
    st.dataframe(latest[["ticket_id", "cliente", "channel", "subject", "owner", "opened_at"]], width="stretch", hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)

elif section == "Clientes 360":
    if can_manage(user["role"], "customer"):
        with st.expander("Nova conta", expanded=False):
            with st.form("new-customer-form"):
                name = st.text_input("Nome da conta")
                segment = st.text_input("Segmento", value="Servicos")
                city = st.text_input("Cidade", value="Sao Paulo")
                country = st.selectbox("Pais", ["Brasil", "Estados Unidos"])
                owner = st.selectbox("Owner da conta", owner_options)
                channel = st.selectbox("Canal preferencial", ["WhatsApp", "Email", "Telefone", "Portal", "Campanha"])
                next_action = st.text_input("Proxima acao", value="Agendar qualificacao inicial")
                submitted = st.form_submit_button("Criar conta", type="primary")
            if submitted and name:
                add_customer(
                    {
                        "name": name,
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
                st.success("Conta criada com persistencia local.")
                st.rerun()

    if filtered_customers.empty:
        render_empty_state("Nenhuma conta encontrada para os filtros atuais.")
    else:
        customer_name = st.selectbox("Selecionar conta", filtered_customers["name"].tolist())
        customer = filtered_customers[filtered_customers["name"] == customer_name].iloc[0].to_dict()
        left, right = st.columns([1.15, 0.85])
        with left:
            st.markdown('<div class="panel">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">Conta e relacionamento</div>', unsafe_allow_html=True)
            info_cols = st.columns(3)
            items = [
                ("Segmento", customer["segment"]),
                ("Mercado", customer["country"]),
                ("Canal preferencial", customer["channel"]),
                ("Owner", customer["owner"]),
                ("Status", customer["status"]),
                ("Ultima compra", customer["last_purchase"]),
            ]
            for col, pair in zip(info_cols * 2, items):
                with col:
                    st.markdown(f"<div class='mini-card'><div class='mini-label'>{pair[0]}</div><div class='mini-value' style='font-size:1.15rem;'>{pair[1]}</div></div>", unsafe_allow_html=True)
            st.markdown(f"**Lifetime value:** {currency(customer['lifetime_value'])}")
            st.markdown(f"**Proxima acao recomendada:** {customer['next_action']}")
            st.markdown('</div>', unsafe_allow_html=True)

            st.markdown(" ")
            st.markdown('<div class="panel">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">Histórico 360</div>', unsafe_allow_html=True)
            render_timeline(timeline, customer["customer_id"])
            st.markdown('</div>', unsafe_allow_html=True)

        with right:
            st.markdown('<div class="panel">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">Atendimentos e oportunidades</div>', unsafe_allow_html=True)
            account_tickets = filtered_tickets[filtered_tickets["customer_id"] == customer["customer_id"]]
            account_deals = filtered_deals[filtered_deals["customer_id"] == customer["customer_id"]]
            st.metric("Health score", f"{customer['health_score']}/100")
            st.metric("Tickets relacionados", len(account_tickets))
            st.metric("Valor em pipeline", currency(account_deals["value"].sum() if not account_deals.empty else 0))
            for item in account_tickets.head(5).to_dict("records"):
                st.markdown(f"<span class='status-pill {status_class(item['status'])}'>{item['status']}</span> {item['subject']}", unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

elif section == "Funil Comercial":
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
                st.success("Oportunidade persistida em SQLite.")
                st.rerun()

    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Funil comercial</div>', unsafe_allow_html=True)
    ordered_stages = ["Descoberta", "Proposta", "Negociacao", "Fechado ganho"]
    stage_columns = st.columns(len(ordered_stages))
    for col, stage in zip(stage_columns, ordered_stages):
        with col:
            stage_items = filtered_deals[filtered_deals["stage"] == stage]
            st.markdown(f"**{stage}**")
            st.caption(f"{len(stage_items)} oportunidade(s)")
            for item in stage_items.to_dict("records"):
                customer = customer_lookup[item["customer_id"]]
                st.markdown(f"<div class='mini-card'><div class='mini-label'>{customer['name']}</div><div class='mini-value' style='font-size:1.05rem;'>{item['name']}</div><div class='mini-caption'>{currency(item['value'])} • {item['probability']}% • {item['owner']}</div></div>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(" ")
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Tabela de oportunidades</div>', unsafe_allow_html=True)
    deals_table = filtered_deals.copy()
    if not deals_table.empty:
        deals_table["cliente"] = deals_table["customer_id"].map(lambda value: customer_lookup[value]["name"])
        st.dataframe(deals_table[["deal_id", "cliente", "name", "stage", "value", "probability", "close_date", "owner"]], width="stretch", hide_index=True)
    else:
        render_empty_state("Nenhuma oportunidade encontrada.")
    st.markdown('</div>', unsafe_allow_html=True)

elif section == "Cadências":
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    render_cadences(user, customers_df)
    st.markdown('</div>', unsafe_allow_html=True)

elif section == "Saúde da Conta":
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    render_health()
    st.markdown('</div>', unsafe_allow_html=True)

elif section == "Modelos de Mensagem":
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    render_templates(user, customers_df, can_manage(user["role"], "admin"))
    st.markdown('</div>', unsafe_allow_html=True)

elif section == "Previsão de Receita":
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    render_forecast(selected_owner)
    st.markdown('</div>', unsafe_allow_html=True)

elif section == "Produtividade":
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    render_productivity()
    st.markdown('</div>', unsafe_allow_html=True)

elif section == "Qualificação de Leads":
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    render_lead_scoring(user, can_manage(user["role"], "admin"))
    st.markdown('</div>', unsafe_allow_html=True)

elif section == "Segmentação":
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    render_segmentation(filtered_customers if not filtered_customers.empty else customers_df)
    st.markdown('</div>', unsafe_allow_html=True)

elif section == "Insights com IA":
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    render_ai_insights(filtered_customers if not filtered_customers.empty else customers_df)
    st.markdown('</div>', unsafe_allow_html=True)

elif section == "Marketing":
    if can_manage(user["role"], "campaign"):
        with st.expander("Nova campanha", expanded=False):
            with st.form("new-campaign-form"):
                campaign = st.text_input("Campanha")
                channel = st.selectbox("Canal", ["Email", "WhatsApp", "Eventos", "Formulario", "Ads"])
                leads = st.number_input("Leads", min_value=0, step=1)
                qualified = st.number_input("Qualificados", min_value=0, step=1)
                conversion_rate = st.number_input("Taxa de conversao (%)", min_value=0.0, max_value=100.0, step=0.1)
                revenue = st.number_input("Receita atribuida", min_value=0.0, step=1000.0)
                submitted = st.form_submit_button("Salvar campanha", type="primary")
            if submitted and campaign:
                add_campaign(
                    {
                        "campaign": campaign,
                        "channel": channel,
                        "leads": leads,
                        "qualified": qualified,
                        "conversion_rate": conversion_rate,
                        "revenue": revenue,
                    },
                    actor=user,
                    source="ui-marketing-campanha",
                )
                st.success("Campanha persistida em SQLite.")
                st.rerun()

    left, right = st.columns([1.05, 0.95])
    with left:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Campanhas e contribuicao de receita</div>', unsafe_allow_html=True)
        st.dataframe(campaigns_df.astype(str), width="stretch", hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown(" ")
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Conversao por canal</div>', unsafe_allow_html=True)
        channel_conversion = campaigns_df[["channel", "conversion_rate"]].groupby("channel").mean()
        st.bar_chart(channel_conversion)
        st.markdown('</div>', unsafe_allow_html=True)
    with right:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Segmentos recomendados</div>', unsafe_allow_html=True)
        segments = [
            "Clientes em risco com ticket aberto nos ultimos 7 dias",
            "Contas ativas com health score acima de 80 e potencial de upsell",
            "Novos clientes de campanha com onboarding ainda em aberto",
            "Base Brasil com preferencia por WhatsApp e LTV acima de R$ 100 mil",
        ]
        for segment in segments:
            st.markdown(f"- {segment}")
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown(" ")
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Leitura de negocio</div>', unsafe_allow_html=True)
        best = campaigns_df.sort_values("conversion_rate", ascending=False).iloc[0]
        st.success(f"Melhor campanha atual: {best['campaign']} com {best['conversion_rate']}% de conversao e {currency(best['revenue'])} em receita atribuida.")
        st.warning("Proximo passo recomendado: conectar campanhas de reativacao aos tickets de churn e abrir handoff automatico para atendimento e vendas.")
        st.markdown('</div>', unsafe_allow_html=True)

elif section == "Comparativo de Mercado":
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Comparativo de mercado — Brasil e EUA</div>', unsafe_allow_html=True)
    st.dataframe(BENCHMARKS, width="stretch", hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown(" ")
    tabs = st.tabs(["Pilares absorvidos", "Ja entregue", "Proxima camada"])
    with tabs[0]:
        st.markdown("- customer 360 com historico consolidado\n- atendimento first com SLA e fila operacional\n- pipeline comercial ligado ao contexto do cliente\n- leitura de marketing com origem, conversao e receita")
    with tabs[1]:
        st.markdown("- persistencia em SQLite local\n- login e perfis por area\n- intake de WhatsApp, Email e Formularios\n- criacao persistida de contas, tickets, deals e campanhas")
    with tabs[2]:
        st.markdown("- automacoes por evento\n- integrações externas reais com provedores\n- trilha de auditoria e permissoes mais finas\n- IA para resumo, priorizacao e resposta assistida")

elif section == "Administração":
    if not can_manage(user["role"], "admin"):
        st.error("Seu perfil nao possui permissao para area de administracao.")
        st.stop()
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Governanca</div>', unsafe_allow_html=True)
    admin_summary = pd.DataFrame(
        [
            {"Item": "Banco", "Valor": DB_PATH},
            {"Item": "Usuarios ativos", "Valor": int(users_df[users_df["is_active"] == 1].shape[0])},
            {"Item": "Contas", "Valor": int(customers_df.shape[0])},
            {"Item": "Tickets", "Valor": int(tickets_df.shape[0])},
            {"Item": "Interacoes", "Valor": int(interactions_df.shape[0])},
        ]
    )
    st.dataframe(admin_summary, width="stretch", hide_index=True)
    st.markdown("**Usuarios e perfis**")
    st.dataframe(users_df, width="stretch", hide_index=True)
    st.markdown("**Permissoes por role (RBAC por acao)**")
    st.dataframe(role_permissions_df, width="stretch", hide_index=True)
    st.markdown("**Token de verificacao do webhook WhatsApp**")
    st.code(get_webhook_verify_token())
    st.caption("Use este token no GET de verificacao do provedor de webhook.")
    st.markdown('</div>', unsafe_allow_html=True)

    if can_manage(user["role"], "rbac"):
        st.markdown(" ")
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Editor de matriz RBAC</div>', unsafe_allow_html=True)
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
                st.success(f"Permissoes do role {selected_role} atualizadas com auditoria.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
        st.markdown('</div>', unsafe_allow_html=True)

    if can_manage(user["role"], "audit"):
        st.markdown(" ")
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Trilha de auditoria por usuario</div>', unsafe_allow_html=True)
        st.dataframe(audit_df, width="stretch", hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(" ")
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Eventos de webhook</div>', unsafe_allow_html=True)
    st.dataframe(webhook_df, width="stretch", hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)


st.markdown(" ")
st.caption(f"Build date: {date.today().isoformat()} | Persistencia: SQLite | Auth: ativa | Canais: WhatsApp, Email, Formularios")
