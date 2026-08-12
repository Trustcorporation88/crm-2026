"""TRUST CRM - persisted CRM with auth, roles and channel intake."""

from __future__ import annotations

import hashlib
import os
from datetime import date
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import brand_assets

from services_catalog import resolve_service_section
from service_guide_ui import open_service_guide_dialog, render_global_assistant
from crm_receita import apply_lookup_to_form, lookup_cnpj
from crm_views import (
    SavedViewError,
    apply_view_to_state,
    capture_filters,
    delete_view,
    get_view,
    load_views,
    save_view,
)
import crm_db
from crm_ux import (
    LOGIN_ENDPOINT,
    login_throttle_subject,
    account_summary_text,
    build_customer_timeline,
    build_day_agenda,
    build_kanban_containers,
    diff_kanban,
    open_deals_for_closing,
    deal_closing_label,
    loss_analysis,
    LOSS_REASONS,
    build_task_queue,
    can_advance_to_stage,
    demo_login_enabled,
    deal_health,
    find_duplicates,
    format_brl,
    format_compact_brl,
    format_date_br,
    global_search,
    format_cpf_cnpj,
    last_activity_by_customer,
    next_best_action,
    onboarding_steps,
    pipeline_totals,
    queue_position_label,
    fill_message_template,
    whatsapp_link,
    render_activity_timeline,
    render_day_agenda,
    render_deal_card,
    render_document_field,
    render_duplicate_warning,
    render_empty_module,
    render_global_search,
    render_next_action,
    render_onboarding_checklist,
    render_related_records,
    render_pipeline_summary,
    render_stage_header,
    summarize_stage,
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
    update_deal_stage,
    close_deal,
    update_deal_fields,
    run_automations,
    bulk_import_customers,
    add_campaign,
    add_interaction,
    complete_task,
    create_access_token,
    verify_access_token,
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
    get_user_preference,
    set_user_preference,
    init_database,
    update_role_permissions,
    verify_login,
    change_own_password,
    accounts_with_default_password,
    consume_auth_attempt,
    data_version,
    register_auth_failure,
    register_auth_success,
    seed_password_for,
)


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
    return f"{icon} {section}" if icon else section



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

st.markdown(
    """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet"
      href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=block">
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<style>
    /* ==================================================================
       TRUST CRM — tema claro profissional
       Linguagem visual dos CRMs líderes (referência: Pipedrive):
       fundo branco, texto quase-preto, barra lateral escura, ação
       primária VERDE, ações e links em AZUL, bordas cinza sutis.
       Paleta: azul, verde, preto e branco.
       ================================================================== */
    :root {
        --bg: #f4f6f8;
        --surface: #ffffff;
        --surface-soft: #f8fafc;
        --ink: #1a1f2b;
        --muted: #5b6472;
        --line: #e3e8ee;
        --line-strong: #cfd7e0;
        --green: #08a742;
        --green-dark: #078c38;
        --blue: #2f6fe4;
        --blue-dark: #2159c4;
        --sidebar: #131a26;
        --success: #15803d;
        --success-soft: #e6f6ec;
        --warning: #b45309;
        --warning-soft: #fdf1de;
        --danger: #dc2626;
        --danger-soft: #fdecec;
        --shadow: 0 1px 3px rgba(16, 24, 40, 0.08);
    }

    .stApp {
        background: var(--bg);
        color: var(--ink);
        font-family: "Inter", "Instrument Sans", "Segoe UI", sans-serif;
    }

    [data-testid="stHeader"] { background: transparent; }

    /* ---- Barra lateral escura (padrão Pipedrive/HubSpot) ---- */
    [data-testid="stSidebarContent"] {
        background: var(--sidebar);
        color: #f4f6f8;
        border-right: 1px solid #0d1420;
    }
    [data-testid="stSidebarContent"] .stRadio label,
    [data-testid="stSidebarContent"] .stSelectbox label,
    [data-testid="stSidebarContent"] p,
    [data-testid="stSidebarContent"] span,
    [data-testid="stSidebarContent"] div {
        color: #eef2f7 !important;
    }
    [data-testid="stSidebar"] .stButton button {
        background: rgba(255, 255, 255, 0.06) !important;
        border: 1px solid rgba(255, 255, 255, 0.18) !important;
        color: #f4f6f8 !important;
        box-shadow: none !important;
    }
    [data-testid="stSidebar"] .stButton button:disabled {
        background: rgba(255, 255, 255, 0.03) !important;
        border-color: rgba(255, 255, 255, 0.10) !important;
        color: rgba(244, 246, 248, 0.4) !important;
    }
    [data-testid="stSidebar"] .stButton button:hover {
        background: rgba(255, 255, 255, 0.12) !important;
        border-color: rgba(255, 255, 255, 0.32) !important;
    }
    [data-testid="stSidebar"] [data-testid="stTextInputRootElement"] {
        background: rgba(255, 255, 255, 0.07) !important;
        border-color: rgba(255, 255, 255, 0.22) !important;
    }
    [data-testid="stSidebar"] .stTextInput input {
        background: rgba(255, 255, 255, 0.08) !important;
        color: #f4f6f8 !important;
        -webkit-text-fill-color: #f4f6f8 !important;
        border: 1px solid rgba(255, 255, 255, 0.22) !important;
    }
    [data-testid="stSidebar"] .stTextInput input::placeholder {
        color: rgba(238, 242, 247, 0.55) !important;
        -webkit-text-fill-color: rgba(238, 242, 247, 0.55) !important;
    }

    /* O componente que declara o idioma não deve ocupar espaço na página. */
    .stElementContainer:has(> iframe[title="streamlit.components.v1.html"][height="0"]),
    div[data-testid="stCustomComponentV1"][height="0"] {
        display: none !important;
        height: 0 !important;
        margin: 0 !important;
    }

    /* ---- Lateral: marca, navegação e rodapé de usuário ---- */
    [data-testid="stSidebar"] div[data-testid="stVerticalBlock"] { gap: 0.55rem; }
    [data-testid="stSidebar"] hr { border-color: rgba(255, 255, 255, 0.12); margin: 6px 0; }

    .side-brand { display: flex; align-items: center; gap: 10px; padding: 4px 2px 8px; }
    .side-brand-logo {
        width: 34px; height: 34px; flex: 0 0 34px; object-fit: contain;
        filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.35));
    }
    .side-brand-name {
        font-size: 1.2rem; letter-spacing: -0.02em; font-weight: 400; color: #f4f6f8 !important;
    }
    .side-brand-name strong { font-weight: 800; }

    .side-label {
        font-size: 0.67rem; font-weight: 700; letter-spacing: 0.12em;
        text-transform: uppercase; color: rgba(238, 242, 247, 0.5) !important;
        margin: 8px 2px 0;
    }

    /* Os ícones do menu são renderizados pelo Streamlit com o NOME da ligadura
       como texto do elemento — enquanto a fonte não chega, o nome aparece na
       tela («support_agent Atendimento»). Zeramos o texto e injetamos o glifo
       pelo codepoint, então não há nome para vazar. */
    [data-testid="stSidebar"] span[role="img"][aria-label="today icon"] { font-size: 0 !important; }
    [data-testid="stSidebar"] span[role="img"][aria-label="today icon"]::before { content: "\\e8df"; font-size: 1.15rem; }
    [data-testid="stSidebar"] span[role="img"][aria-label="apps icon"] { font-size: 0 !important; }
    [data-testid="stSidebar"] span[role="img"][aria-label="apps icon"]::before { content: "\\e5c3"; font-size: 1.15rem; }
    [data-testid="stSidebar"] span[role="img"][aria-label="monitoring icon"] { font-size: 0 !important; }
    [data-testid="stSidebar"] span[role="img"][aria-label="monitoring icon"]::before { content: "\\f190"; font-size: 1.15rem; }
    [data-testid="stSidebar"] span[role="img"][aria-label="support_agent icon"] { font-size: 0 !important; }
    [data-testid="stSidebar"] span[role="img"][aria-label="support_agent icon"]::before { content: "\\f0e2"; font-size: 1.15rem; }
    [data-testid="stSidebar"] span[role="img"][aria-label="group icon"] { font-size: 0 !important; }
    [data-testid="stSidebar"] span[role="img"][aria-label="group icon"]::before { content: "\\ea21"; font-size: 1.15rem; }
    [data-testid="stSidebar"] span[role="img"][aria-label="filter_alt icon"] { font-size: 0 !important; }
    [data-testid="stSidebar"] span[role="img"][aria-label="filter_alt icon"]::before { content: "\\ef4f"; font-size: 1.15rem; }
    [data-testid="stSidebar"] span[role="img"][aria-label="forum icon"] { font-size: 0 !important; }
    [data-testid="stSidebar"] span[role="img"][aria-label="forum icon"]::before { content: "\\e8af"; font-size: 1.15rem; }

    /* Navegação: o st.radio vira um menu — sem círculos, linhas inteiras
       clicáveis, hover suave e item ativo com barra verde (padrão Pipedrive). */
    [data-testid="stSidebar"] [data-testid="stRadioGroup"] {
        display: flex; flex-direction: column; gap: 2px;
    }
    [data-testid="stSidebar"] [data-testid="stRadioOption"] {
        display: flex; align-items: center; margin: 0; padding: 8px 10px;
        border-radius: 8px; cursor: pointer;
        transition: background 0.12s ease;
    }
    [data-testid="stSidebar"] [data-testid="stRadioOption"]:hover {
        background: rgba(255, 255, 255, 0.08);
    }
    /* Esconde o círculo do radio (primeiro filho estrutural; o texto vem no
       stMarkdownContainer ao lado) */
    [data-testid="stSidebar"] [data-testid="stRadioOption"] > div > div > div:first-child:not([data-testid="stMarkdownContainer"]) {
        display: none;
    }
    [data-testid="stSidebar"] [data-testid="stRadioOption"] [data-testid="stMarkdownContainer"] { width: 100%; }
    [data-testid="stSidebar"] [data-testid="stRadioOption"] p {
        font-size: 0.93rem; font-weight: 500; color: #d9e0ea !important;
        display: flex; align-items: center; gap: 10px;
    }
    [data-testid="stSidebar"] [data-testid="stRadioOption"] p span[role="img"] {
        font-size: 1.15rem; opacity: 0.85;
    }
    [data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] {
        background: rgba(8, 167, 66, 0.16);
        box-shadow: inset 3px 0 0 var(--green);
    }
    [data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] p {
        color: #ffffff !important; font-weight: 600;
    }
    [data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] p span[role="img"] {
        opacity: 1; color: #4ade80;
    }

    /* Selectbox e expanders sobre o fundo escuro */
    [data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] > div {
        background: rgba(255, 255, 255, 0.07) !important;
        border-color: rgba(255, 255, 255, 0.2) !important;
        color: #f4f6f8 !important;
    }
    [data-testid="stSidebar"] .stSelectbox svg { fill: #d9e0ea; }
    [data-testid="stSidebar"] [data-testid="stExpander"] details {
        background: transparent;
        border: 1px solid rgba(255, 255, 255, 0.16);
        border-radius: 8px;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary { color: #e8edf4 !important; }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary:hover { color: #ffffff !important; }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary svg { fill: #d9e0ea; }

    /* Rodapé: chip do usuário logado */
    .side-user {
        display: flex; align-items: center; gap: 10px;
        padding: 10px; border-radius: 10px;
        border: 1px solid rgba(255, 255, 255, 0.14);
        background: rgba(255, 255, 255, 0.05);
        margin-top: 6px;
    }
    .side-avatar {
        width: 34px; height: 34px; border-radius: 50%; flex: 0 0 34px;
        background: linear-gradient(135deg, var(--green), var(--blue));
        display: flex; align-items: center; justify-content: center;
        font-weight: 700; font-size: 0.85rem; color: #ffffff !important;
    }
    .side-user-name { font-size: 0.9rem; font-weight: 600; color: #ffffff !important; line-height: 1.25; }
    .side-user-role {
        font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.08em;
        color: rgba(238, 242, 247, 0.6) !important;
    }

    /* ---- Rótulos de campos (área clara) ---- */
    label[data-testid="stWidgetLabel"],
    .stTextInput label, .stTextArea label, .stNumberInput label,
    .stDateInput label, .stSelectbox label, .stMultiSelect label,
    .stRadio label {
        color: #333d4d !important;
        font-weight: 600 !important;
    }

    /* ---- Login ---- */
    .stApp:has(.login-shell) [data-testid="stSidebar"],
    .stApp:has(.login-shell) [data-testid="stSidebarCollapsedControl"],
    .stApp:has(.login-shell) [data-testid="stToolbar"] { display: none !important; }

    .stApp:has(.login-shell) {
        background:
            radial-gradient(ellipse 60% 40% at 85% 0%, rgba(8, 167, 66, 0.07), transparent 55%),
            radial-gradient(ellipse 50% 40% at 10% 10%, rgba(47, 111, 228, 0.08), transparent 50%),
            #f4f6f8 !important;
    }
    .stApp:has(.login-shell) section.main > div.block-container {
        max-width: 980px; padding-top: 2.5rem; padding-bottom: 3rem;
    }
    .login-shell { display: flex; flex-direction: column; gap: 28px; }
    .login-brand { text-align: left; max-width: 36rem; }
    .login-logo {
        display: block; width: clamp(150px, 19vw, 205px); height: auto;
        margin: 0 0 14px -8px;
        filter: drop-shadow(0 6px 18px rgba(16, 24, 40, 0.16));
    }
    .login-brand .eyebrow {
        display: inline-block; font-size: 0.72rem; font-weight: 700;
        letter-spacing: 0.14em; text-transform: uppercase;
        color: var(--green); margin-bottom: 10px;
    }
    .login-brand h1 {
        font-size: clamp(2.2rem, 5vw, 3.2rem); font-weight: 800;
        letter-spacing: -0.04em; line-height: 1.05;
        color: var(--ink); margin: 0 0 12px;
    }
    .login-brand .tagline {
        font-size: 1.05rem; line-height: 1.55; color: var(--muted);
        margin: 0 0 18px; max-width: 40ch;
    }
    .login-signals { display: flex; flex-wrap: wrap; gap: 8px; margin: 0; padding: 0; list-style: none; }
    .login-signals li {
        font-size: 0.78rem; font-weight: 600; letter-spacing: 0.03em;
        color: #333d4d; padding: 5px 0; margin-right: 14px;
        border-bottom: 2px solid var(--green);
    }
    .login-gate-title {
        font-size: 1.12rem; font-weight: 700; color: var(--ink);
        margin: 0 0 4px; letter-spacing: -0.01em;
    }
    .login-gate-hint { color: var(--muted); font-size: 0.88rem; margin: 0 0 14px; line-height: 1.45; }
    .login-note {
        margin-top: 8px; padding: 12px 0 0; border-top: 1px solid var(--line);
        color: var(--muted); font-size: 0.8rem; line-height: 1.5;
    }
    .login-panel label, .login-panel p, .login-panel span, .login-panel small {
        color: #333d4d !important;
    }

    /* ---- Cabeçalho de página ---- */
    .page-head h2 { color: var(--ink); margin: 0 0 4px; font-size: 1.5rem; letter-spacing: -0.02em; }
    .page-head p { color: var(--muted); margin: 0 0 16px; font-size: 0.95rem; }

    .top-nav-strip { display: flex; gap: 10px; flex-wrap: wrap; margin: 2px 0 14px; }
    .top-nav-pill {
        display: inline-flex; align-items: center; gap: 6px; border-radius: 999px;
        padding: 3px 10px; background: #e8effc; border: 1px solid #c4d5f5;
        color: var(--blue-dark); font-size: 10.5px; font-weight: 700;
        text-transform: uppercase; letter-spacing: 0.06em;
    }
    /* Barra superior: breadcrumb fino + ações discretas (padrão dos líderes) */
    .section-crumb {
        display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
        color: var(--muted); font-size: 0.88rem; padding: 4px 0;
    }
    .section-crumb .crumb-root { color: var(--muted); font-weight: 500; }
    .section-crumb .crumb-sep { color: #b6bfca; font-size: 1rem; line-height: 1; }
    .section-crumb strong { color: var(--ink); font-weight: 700; font-size: 0.98rem; }
    .top-rule { height: 1px; background: var(--line); margin: 0 0 16px; }
    .stButton button[kind="tertiary"] {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        color: var(--muted) !important;
        min-height: 34px !important;
        padding: 4px 8px !important;
        border-radius: 8px !important;
    }
    .stButton button[kind="tertiary"]:hover {
        color: var(--blue-dark) !important;
        background: #eef3fb !important;
    }
    .stButton button[kind="tertiary"]:disabled {
        color: #c9d0d9 !important;
        background: transparent !important;
    }
    .nav-secondary-hint { font-size: 0.78rem; color: var(--muted); margin: 4px 0 8px; }

    /* ---- Hero (Visão Executiva) ---- */
    .hero {
        background: var(--sidebar);
        border-radius: 14px; padding: 26px 30px; color: #ffffff;
        box-shadow: var(--shadow); margin-bottom: 18px;
        border: 1px solid #0d1420;
    }
    .hero-grid { display: grid; grid-template-columns: 1.5fr 1fr; gap: 18px; align-items: end; }
    .hero h1 { font-size: 1.55rem; margin-bottom: 0.35rem; letter-spacing: -0.02em; line-height: 1.3; color: #ffffff; }
    .hero p { color: rgba(244, 246, 248, 0.82); font-size: 1rem; max-width: 62ch; margin: 0; }
    .hero-badges { display: flex; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }
    .badge {
        display: inline-flex; align-items: center; gap: 8px; padding: 8px 12px;
        border-radius: 999px; background: rgba(255, 255, 255, 0.08);
        border: 1px solid rgba(255, 255, 255, 0.22); font-size: 0.85rem; color: #ffffff;
    }

    /* ---- Painéis e cartões ---- */
    .panel:empty { display: none; }
    .panel {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 12px;
        padding: 18px;
        box-shadow: var(--shadow);
    }
    div[data-testid="stVerticalBlockBorderWrapper"],
    div[data-testid="stLayoutWrapper"]:has(> div > div[data-testid="stVerticalBlockBorderWrapper"]) {
        background: var(--surface);
        border-color: var(--line) !important;
        border-radius: 12px;
    }
    .section-title {
        font-size: 1.02rem; font-weight: 700; margin-bottom: 0.8rem;
        color: var(--ink); letter-spacing: -0.01em;
    }
    .mini-card {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 10px; padding: 14px 16px; min-height: 110px;
        margin-bottom: 10px; box-shadow: var(--shadow);
        transition: border-color 0.15s ease, box-shadow 0.15s ease;
    }
    .mini-card:hover {
        border-color: var(--blue);
        box-shadow: 0 4px 12px rgba(47, 111, 228, 0.12);
    }
    .mini-label {
        font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.07em;
        color: var(--muted); font-weight: 600;
    }
    .mini-value { font-size: 1.7rem; font-weight: 700; color: var(--ink); margin: 0.2rem 0 0.3rem; }
    .mini-caption { color: var(--muted); font-size: 0.9rem; }

    /* ---- Cards do catálogo de Serviços ---- */
    .svc-head { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
    .svc-icon::before, .cat-icon::before, .svc-ready-icon::before { content: var(--ico); }
    .svc-icon {
        font-family: "Material Symbols Rounded";
        font-size: 1.35rem; line-height: 1; font-weight: 400;
        width: 38px; height: 38px; border-radius: 10px; flex: 0 0 38px;
        display: flex; align-items: center; justify-content: center;
        user-select: none;
    }
    .svc-title {
        font-weight: 700; color: var(--ink); font-size: 1rem;
        line-height: 1.3; letter-spacing: -0.01em;
    }
    .svc-when { color: var(--muted); font-size: 0.85rem; line-height: 1.45; min-height: 2.5em; }
    .svc-stat { display: flex; align-items: baseline; gap: 8px; padding: 6px 0 2px; }
    .svc-stat-num {
        font-size: 1.45rem; font-weight: 800; color: var(--ink); letter-spacing: -0.02em;
    }
    .svc-stat-label { font-size: 0.78rem; color: var(--muted); font-weight: 600; }
    .svc-ready {
        display: inline-flex; align-items: center; gap: 6px;
        font-size: 0.78rem; font-weight: 700; color: var(--success);
        background: var(--success-soft); border: 1px solid #bfe6cd;
        border-radius: 999px; padding: 4px 10px;
    }
    .svc-ready-icon {
        font-family: "Material Symbols Rounded"; font-size: 1rem; line-height: 1;
        --ico: "\\f0be";
    }

    .cat-head { display: flex; align-items: center; gap: 10px; margin: 14px 0 2px; }
    .cat-icon {
        font-family: "Material Symbols Rounded";
        font-size: 1.15rem; line-height: 1;
        width: 32px; height: 32px; border-radius: 9px; flex: 0 0 32px;
        display: flex; align-items: center; justify-content: center;
        user-select: none;
    }
    .cat-title { font-size: 1.18rem; font-weight: 800; color: var(--ink); letter-spacing: -0.02em; }

    /* ---- Pílulas de status ---- */
    .status-pill {
        display: inline-block; padding: 3px 10px; border-radius: 999px;
        font-size: 0.76rem; font-weight: 600;
    }
    .status-open { background: var(--warning-soft); color: var(--warning); border: 1px solid #f5d9a8; }
    .status-progress { background: #e8effc; color: var(--blue-dark); border: 1px solid #c4d5f5; }
    .status-won { background: var(--success-soft); color: var(--success); border: 1px solid #bfe6cd; }
    .status-lost { background: var(--danger-soft); color: var(--danger); border: 1px solid #f4c3c3; }
    .status-active { background: #e8effc; color: var(--blue-dark); border: 1px solid #c4d5f5; }

    .empty-state {
        border-radius: 10px; padding: 15px 16px;
        border: 1px dashed var(--line-strong);
        background: var(--surface-soft); color: #333d4d;
        font-weight: 600; margin: 8px 0;
    }

    /* ---- Linha do tempo (classes legadas) ---- */
    .timeline-item { border-left: 2px solid var(--line-strong); padding-left: 14px; margin-left: 6px; margin-bottom: 14px; }
    .timeline-date { font-size: 0.78rem; color: var(--muted); margin-bottom: 2px; }
    .timeline-title { font-weight: 700; color: var(--ink); margin-bottom: 2px; }
    .timeline-copy { color: var(--muted); font-size: 0.92rem; }

    /* ---- Campos de formulário ---- */
    .stTextInput input, .stTextArea textarea, .stNumberInput input,
    .stDateInput input, .stSelectbox div[data-baseweb="select"] > div {
        background: var(--surface) !important;
        color: var(--ink) !important;
        -webkit-text-fill-color: var(--ink) !important;
        caret-color: var(--blue) !important;
        border: 1px solid var(--line-strong) !important;
        border-radius: 8px !important;
    }
    .stTextInput input::placeholder, .stTextArea textarea::placeholder {
        color: #9aa4b2 !important;
        -webkit-text-fill-color: #9aa4b2 !important;
        opacity: 1 !important;
    }
    .stTextInput input:focus, .stTextArea textarea:focus, .stNumberInput input:focus,
    .stDateInput input:focus, .stSelectbox div[data-baseweb="select"] > div:focus-within {
        border-color: var(--blue) !important;
        box-shadow: 0 0 0 3px rgba(47, 111, 228, 0.15) !important;
    }

    /* ---- Botões ----
       Primário = VERDE (padrão Pipedrive: a ação principal é verde).
       Secundário = branco com borda. Links/ações leves = AZUL. */
    .stButton button, .stFormSubmitButton button {
        border-radius: 8px !important;
        font-weight: 600 !important;
        min-height: 40px !important;
        transition: background 0.15s ease, border-color 0.15s ease !important;
    }
    .stButton button {
        background: var(--surface) !important;
        border: 1px solid var(--line-strong) !important;
        color: var(--ink) !important;
        box-shadow: var(--shadow);
    }
    .stButton button:hover {
        border-color: var(--blue) !important;
        color: var(--blue-dark) !important;
        background: #f6f9ff !important;
    }
    .stButton button[kind="primary"],
    button[data-testid="stBaseButton-primary"],
    .stFormSubmitButton button,
    button[kind="primaryFormSubmit"],
    button[data-testid="stBaseButton-primaryFormSubmit"] {
        background: var(--green) !important;
        border: 1px solid var(--green-dark) !important;
        color: #ffffff !important;
        box-shadow: 0 1px 2px rgba(7, 140, 56, 0.35) !important;
    }
    .stButton button[kind="primary"]:hover,
    .stFormSubmitButton button:hover {
        background: var(--green-dark) !important;
        color: #ffffff !important;
    }
    .stLinkButton a {
        background: var(--blue) !important;
        border: 1px solid var(--blue-dark) !important;
        color: #ffffff !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
    }
    .stLinkButton a:hover { background: var(--blue-dark) !important; }
    .stDownloadButton button {
        background: var(--surface) !important;
        border: 1px solid var(--line-strong) !important;
        color: var(--ink) !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
    }
    .stDownloadButton button:hover { border-color: var(--blue) !important; color: var(--blue-dark) !important; }

    /* ---- Métricas ---- */
    div[data-testid="stMetric"] {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 10px;
        padding: 12px;
        box-shadow: var(--shadow);
    }
    div[data-testid="stMetricLabel"] * { color: var(--muted) !important; }
    div[data-testid="stMetricValue"] * { color: var(--ink) !important; }

    .stAlert { border-radius: 10px; border-width: 1px !important; }

    /* ---- Cards lado a lado com a MESMA altura ---- */
    div[data-testid="stHorizontalBlock"] { align-items: stretch; }
    div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] { height: 100%; }
    div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stLayoutWrapper"],
    div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] {
        flex: 1 1 auto; display: flex; flex-direction: column;
    }
    div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stLayoutWrapper"] > div,
    div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] > div,
    div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div > div[data-testid="stVerticalBlock"] {
        flex: 1 1 auto; height: 100%;
    }
    div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div > div[data-testid="stVerticalBlock"]
        > div:last-child:has(div[data-testid="stHorizontalBlock"]) {
        margin-top: auto;
    }

    /* ---- Responsivo ---- */
    @media (max-width: 980px) {
        .hero-grid { grid-template-columns: 1fr; }
        .hero-badges { justify-content: flex-start; }
    }
    @media (max-width: 640px) {
        .hero { padding: 20px 18px; border-radius: 12px; }
        .hero h1 { font-size: 1.3rem; }
        .panel { padding: 14px; border-radius: 10px; }
        .mini-card { min-height: auto; padding: 12px 14px; }
        .mini-value { font-size: 1.4rem; }
        .page-head h2 { font-size: 1.3rem; }
        .stButton button { min-height: 46px !important; }
        .top-nav-bar .section-crumb { padding-top: 0; font-size: 0.82rem; }
        div[data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
        div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
            flex: 1 1 100% !important; width: 100% !important; min-width: 100% !important;
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
    # Barra superior no padrão dos líderes: breadcrumb como elemento principal,
    # ações discretas (tertiary, só ícone) — nada de botões-caixa antes do conteúdo.
    col_back, col_crumb, col_home = st.columns([0.5, 6.2, 0.5], vertical_alignment="center")
    with col_back:
        can_back = active_section != "Serviços"
        if st.button(
            ":material/arrow_back:",
            key="nav-top-back",
            type="tertiary",
            disabled=not can_back,
            help="Voltar à tela anterior",
        ):
            go_back()
    with col_crumb:
        filter_bits = []
        if st.session_state.get("filter_country", "Todos") != "Todos":
            filter_bits.append(f"Mercado: {st.session_state['filter_country']}")
        if st.session_state.get("filter_owner", "Todos") != "Todos":
            filter_bits.append(f"Responsável: {st.session_state['filter_owner']}")
        filters_html = (
            f' <span class="top-nav-pill">{" · ".join(filter_bits)}</span>' if filter_bits else ""
        )
        st.markdown(
            f'<div class="section-crumb"><span class="crumb-root">Trust CRM</span>'
            f'<span class="crumb-sep">›</span><strong>{active_section}</strong>{filters_html}</div>',
            unsafe_allow_html=True,
        )
    with col_home:
        if st.button(
            ":material/home:",
            key="nav-top-home",
            type="tertiary",
            help="Ir ao catálogo de serviços",
        ):
            navigate_to_section("Serviços")
    st.markdown('<div class="top-rule"></div>', unsafe_allow_html=True)


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


SESSION_TOKEN_TTL_MINUTES = 720  # 12h: usuário não perde a sessão ao atualizar a página.


def start_user_session(user: dict[str, Any]) -> None:
    """Autentica o usuário e grava um token na URL para sobreviver ao refresh (F5)."""
    st.session_state["crm_user"] = user
    try:
        st.query_params["auth"] = create_access_token(user, expires_minutes=SESSION_TOKEN_TTL_MINUTES)
    except Exception:
        pass  # Sem token, o login continua funcionando — só não persiste no refresh.
    st.rerun()


def end_user_session() -> None:
    """Sai da conta com um redirect real para a raiz, removendo o token da URL."""
    st.session_state.pop("crm_user", None)
    # Redirect completo (não st.rerun): garante que o ?auth= saia da URL do navegador.
    st.markdown(
        '<meta http-equiv="refresh" content="0; url=./">',
        unsafe_allow_html=True,
    )
    st.stop()


def restore_session_from_url() -> None:
    """Se a página foi atualizada (F5), restaura o login a partir do token na URL."""
    if "crm_user" in st.session_state:
        return
    token = str(st.query_params.get("auth", "") or "")
    if not token:
        return
    try:
        payload = verify_access_token(token)
        st.session_state["crm_user"] = {
            "username": payload["sub"],
            "full_name": payload.get("full_name") or payload["sub"],
            "role": payload["role"],
        }
    except Exception:
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


def show_login() -> None:
    st.markdown(
        f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=Instrument+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<div class="login-shell">
  <div class="login-brand">
    <img class="login-logo" src="{brand_assets.data_uri("logo")}" alt="Trust Corporation — Património e Legado">
    <h1>TRUST CRM</h1>
    <p class="tagline">
      Vendas, atendimento e marketing em um só lugar — pipeline com previsão ponderada,
      cliente 360 e execução guiada do dia.
    </p>
    <ul class="login-signals">
      <li>PostgreSQL gerenciado</li>
      <li>Acesso por papéis</li>
      <li>WhatsApp, e-mail e formulários</li>
    </ul>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    left, right = st.columns([1, 1], gap="large")
    with left:
        with st.container(border=True):
            st.markdown('<p class="login-gate-title">Entrar</p>', unsafe_allow_html=True)
            st.markdown(
                '<p class="login-gate-hint">Use seu usuário e senha para acessar o workspace.</p>',
                unsafe_allow_html=True,
            )
            with st.form("crm-login"):
                username = st.text_input("Usuario", placeholder="Digite seu usuário")
                password = st.text_input("Senha", type="password", placeholder="Digite sua senha")
                submitted = st.form_submit_button("Acessar", width="stretch", type="primary")
            if submitted:
                # O backend já tinha throttle progressivo com bloqueio, mas ele
                # só estava ligado no serviço de webhook. A tela de login — o
                # caminho que de fato está exposto ao público — chamava
                # verify_login() direto, sem limite algum de tentativas.
                subject = login_throttle_subject(username)
                try:
                    consume_auth_attempt(subject, LOGIN_ENDPOINT)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    user = verify_login(username.strip(), password)
                    if user:
                        register_auth_success(subject, LOGIN_ENDPOINT)
                        start_user_session(user)
                    else:
                        register_auth_failure(subject, LOGIN_ENDPOINT)
                        st.error("Credenciais inválidas.")

    with right:
        with st.container(border=True):
            if demo_login_enabled():
                st.markdown(
                    '<p class="login-gate-title">Entrar com 1 clique (demonstração)</p>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    '<p class="login-gate-hint">Escolha um perfil para explorar o CRM sem digitar credenciais.</p>',
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
            else:
                st.markdown(
                    '<p class="login-gate-title">Acesso restrito</p>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    '<p class="login-gate-hint">Use as credenciais fornecidas pelo administrador. '
                    "Para liberar o acesso de demonstração em um clique, defina "
                    "<code>CRM_DEMO_LOGIN=true</code> no ambiente.</p>",
                    unsafe_allow_html=True,
                )
            st.markdown(
                '<p class="login-note">Sem credenciais reais de WhatsApp ou e-mail, a conexão de canais '
                "entra por intake operacional: formulário interno e importação de mensagem/corpo do atendimento.</p>",
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
.sortable-component { display: flex; gap: 10px; align-items: flex-start;
    font-family: 'Inter', 'Segoe UI', system-ui, sans-serif; }
.sortable-container { flex: 1 1 0; background: #f4f6f8; border: 1px solid #e3e8ee;
    border-radius: 10px; padding: 6px; min-height: 140px; }
.sortable-container-header { font-weight: 700; font-size: 13px; color: #1a1f2b;
    padding: 8px 8px 4px; letter-spacing: -0.01em; }
.sortable-container-body { display: flex; flex-direction: column; gap: 6px; padding: 4px; min-height: 90px; }
.sortable-item { background: #ffffff; border: 1px solid #e3e8ee; border-left: 3px solid #2f6fe4;
    border-radius: 8px; padding: 10px 12px; font-size: 12.5px; font-weight: 600;
    color: #1a1f2b; cursor: grab; box-shadow: 0 1px 2px rgba(16, 24, 40, 0.06); }
.sortable-item:hover { border-color: #2f6fe4; box-shadow: 0 3px 8px rgba(47, 111, 228, 0.15); }
"""


def render_page_header(section: str) -> None:
    hints = {
        "Meu Dia": "O que precisa da sua ação agora: tarefas, negociações paradas e SLA.",
        "Serviços": "Escolha um módulo abaixo ou use o menu à esquerda.",
        "Visão Executiva": "KPIs e leitura rápida da operação.",
        "Atendimento": "Fila de tickets e SLA.",
        "Clientes 360": "Conta, histórico e contexto comercial.",
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
    st.markdown(
        f'<div class="page-head"><h2>{section}</h2><p>{hints.get(section, "Visão consolidada do módulo.")}</p></div>',
        unsafe_allow_html=True,
    )


def render_empty_state(message: str) -> None:
    st.markdown(f'<div class="empty-state">{message}</div>', unsafe_allow_html=True)


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

    with st.container(border=True):
        st.markdown(
            '<div class="section-title">Comparativo Benchmark — o mercado brasileiro</div>',
            unsafe_allow_html=True,
        )
        st.caption(
            f"Preços consultados nas páginas oficiais em {PRICE_CHECKED_AT}. "
            "Valores em dólar estão marcados. Software muda de preço — confira antes de decidir."
        )
        _p = st.columns(3)
        _p[0].metric("Capacidades à frente", _placar["vantagem"])
        _p[1].metric("Equivalentes", _placar["empate"] + _placar["parcial"])
        _p[2].metric("Atrás", _placar["atras"], help="E-mail, ecossistema de integrações e multiempresa.")

        for _titulo, _lista in (
            ("🇧🇷 CRMs brasileiros", brazilian_competitors()),
            ("🌐 Globais que competem no Brasil", global_competitors()),
        ):
            st.markdown(f"**{_titulo}**")
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Concorrente": c["name"],
                            "Origem": c["origin"],
                            "Preço de entrada": c["price"],
                            "Nosso diferencial": c["trust_diff"],
                        }
                        for c in _lista
                    ]
                ),
                width="stretch",
                hide_index=True,
            )

        if not compact:
            for _titulo, _lista in (
                ("🇧🇷 CRMs brasileiros", brazilian_competitors()),
                ("🌐 Globais", global_competitors()),
            ):
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

    st.markdown(" ")
    with st.container(border=True):
        st.markdown('<div class="section-title">Capacidade a capacidade</div>', unsafe_allow_html=True)
        st.dataframe(
            pd.DataFrame(
                [
                    {"Capacidade": m["capability"], "Trust CRM": m["trust"], "Mercado": m["market"]}
                    for m in CAPABILITY_MATRIX
                ]
            ),
            width="stretch",
            hide_index=True,
        )

    st.markdown(" ")
    _pos = st.columns(2)
    with _pos[0], st.container(border=True):
        st.markdown('<div class="section-title">✅ Onde ganhamos</div>', unsafe_allow_html=True)
        for _item in TRUST_POSITION["ganhamos"]:
            st.markdown(f"- {_item}")
    with _pos[1], st.container(border=True):
        st.markdown('<div class="section-title">⚠️ Onde estamos atrás</div>', unsafe_allow_html=True)
        for _item in TRUST_POSITION["atras"]:
            st.markdown(f"- {_item}")
        st.caption("Reconhecer a lacuna é o que permite fechá-la — estas são as próximas frentes.")


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

    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-title">Início — o que você quer fazer?</div>',
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
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown(" ")
        render_benchmark_comparison(compact=True)
        return

    # 3b) Sem busca: serviços agrupados por objetivo, em grade responsiva
    total_shown = 0
    for category in CATEGORIES:
        services = get_services_by_category(str(category["id"]))
        if not services:
            continue
        total_shown += len(services)

        titulo, subtitulo = OBJETIVOS.get(
            str(category["id"]),
            (str(category["title"]), str(category.get("tagline", ""))),
        )
        cat_icon, cat_tone = CATEGORY_HEAD_META.get(str(category["id"]), ("widgets", "#334155"))
        st.markdown(
            f'<div class="cat-head"><span class="cat-icon" translate="no" aria-hidden="true" style="color:{cat_tone};'
            f'background:{cat_tone}1a;--ico:\'{cat_icon}\';"></span><span class="cat-title">{titulo}</span></div>',
            unsafe_allow_html=True,
        )
        st.caption(subtitulo)

        for chunk_start in range(0, len(services), 3):
            chunk = services[chunk_start: chunk_start + 3]
            cols = st.columns(len(chunk))
            for col, service in zip(cols, chunk):
                with col:
                    _render_service_card(service, allowed_sections, live_stats, key_prefix="svc")

    if total_shown == 0:
        st.info("Nenhum serviço disponível para o seu perfil.")

    st.markdown("</div>", unsafe_allow_html=True)

    # Comparativo Benchmark fecha o catálogo: depois de ver o que entregamos,
    # o leitor vê como isso se posiciona contra o mercado.
    st.markdown(" ")
    st.divider()
    render_benchmark_comparison(compact=True)


init_database()

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
data = _dados_da_versao(data_version())
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
  <div class="side-avatar">{_initials}</div>
  <div class="side-user-meta">
    <div class="side-user-name">{user["full_name"]}</div>
    <div class="side-user-role">{user["role"]}</div>
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

render_top_bar(section)

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

if section == "Meu Dia":
    # Superfície de trabalho diário: responde "o que eu faço agora?" sem
    # obrigar o usuário a varrer módulo por módulo.
    agenda_owner = None if selected_owner == "Todos" else selected_owner

    # st.container em vez de <div> aberta num bloco e fechada em outro: o
    # Streamlit sanitiza cada bloco de markdown isoladamente, então a div
    # ficava desbalanceada e o React perdia a referência do nó ao redesenhar
    # (NotFoundError em removeChild). Com colunas e métricas no meio, quebra.
    with st.container(border=True):
        if agenda_owner:
            st.caption(f"Pendências de **{agenda_owner}**. Troque o responsável nos filtros globais.")
        else:
            st.caption("Pendências de **toda a equipe**. Escolha um responsável nos filtros globais para ver só as suas.")

        render_day_agenda(
            build_day_agenda(
                tasks_df,
                filtered_deals,
                filtered_tickets,
                interactions_df,
                owner=agenda_owner,
            )
        )

    # --- Fila de execução (padrão HubSpot Task Queue / Close) ---
    # Modo "trabalhar a fila": uma tarefa por vez, com contexto, sem voltar à
    # lista entre cada item.
    _agenda_fila = build_day_agenda(
        tasks_df, filtered_deals, filtered_tickets, interactions_df, owner=agenda_owner
    )
    _fila = build_task_queue(_agenda_fila)

    st.markdown(" ")
    with st.container(border=True):
        st.markdown('<div class="section-title">Fila de execução</div>', unsafe_allow_html=True)

        if not _fila:
            st.caption("Nenhuma tarefa pendente para trabalhar em fila. 🎉")
            st.session_state.pop("fila_ativa", None)
            st.session_state.pop("fila_indice", None)
        elif not st.session_state.get("fila_ativa"):
            st.caption(
                f"{len(_fila)} tarefa(s) esperando. O modo fila mostra uma por vez, "
                "com contexto, e avança quando você conclui."
            )

            def _entrar_na_fila() -> None:
                st.session_state["fila_ativa"] = True
                st.session_state["fila_indice"] = 0

            st.button("▶ Trabalhar a fila", key="fila_entrar", on_click=_entrar_na_fila)
        else:
            _indice = min(st.session_state.get("fila_indice", 0), len(_fila) - 1)
            _atual = _fila[_indice]

            st.caption(queue_position_label(_indice, len(_fila)))
            st.markdown(f"### {_atual.get('task', '')}")

            _meta_cols = st.columns(3)
            _origem = "🔴 Atrasada" if _atual.get("_origem") == "atrasada" else "📅 Para hoje"
            _meta_cols[0].metric("Situação", _origem.split(" ", 1)[1])
            _meta_cols[1].metric("Prioridade", str(_atual.get("priority", "—")))
            _meta_cols[2].metric("Vencimento", format_date_br(_atual.get("due_date")))

            _entidade = str(_atual.get("entity", "") or "")
            if _entidade:
                st.caption(f"Relacionada a: {_entidade}")

            def _concluir_e_avancar() -> None:
                nome = _atual.get("task", "")
                if complete_task(nome, actor=user):
                    queue_toast(f"Tarefa «{nome}» concluída.", icon="✅")
                # O índice não avança: a tarefa concluída sai da fila no
                # próximo rerun, e a seguinte assume a mesma posição.

            def _pular() -> None:
                st.session_state["fila_indice"] = _indice + 1
                if st.session_state["fila_indice"] >= len(_fila):
                    st.session_state["fila_indice"] = 0

            def _sair() -> None:
                st.session_state.pop("fila_ativa", None)
                st.session_state.pop("fila_indice", None)

            _acao_cols = st.columns(3)
            _acao_cols[0].button(
                "✅ Concluir e avançar", key="fila_concluir",
                type="primary", on_click=_concluir_e_avancar,
            )
            _acao_cols[1].button("⏭ Pular", key="fila_pular", on_click=_pular)
            _acao_cols[2].button("✕ Sair da fila", key="fila_sair", on_click=_sair)

    st.markdown(" ")
    render_onboarding_checklist(
        onboarding_steps(customers_df, deals_df, tickets_df)
    )

elif section == "Serviços":
    render_services_catalog()

elif section == "Visão Executiva":
    left, right = st.columns([1.2, 0.8])
    with left, st.container(border=True):
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
            st.bar_chart(
                owner_load.set_index("owner"),
                horizontal=True,
                color="#2f6fe4",
                height=max(160, 56 * len(owner_load)),
            )
    with right, st.container(border=True):
        st.markdown('<div class="section-title">Proximas acoes</div>', unsafe_allow_html=True)
        for item in tasks_df.sort_values("due_date").head(6).to_dict("records"):
            st.markdown(f"**{item['task']}**  \nResponsavel: {item['owner']}  \nPrazo: {item['due_date']}  \nVinculo: {item['entity']}")
            st.markdown("---")

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
                queue_toast(f"Ticket criado para {customer_name}. Ele já aparece na fila abaixo.")
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
                queue_toast(f"Atendimento registrado! Cliente {customer_id}, ticket {ticket_id}.")
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
        customer_name = st.selectbox("Selecionar conta", filtered_customers["name"].tolist())
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
            st.markdown('<div class="section-title">Linha do tempo</div>', unsafe_allow_html=True)

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
                st.markdown('<div class="section-title">WhatsApp</div>', unsafe_allow_html=True)

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
                st.markdown('<div class="section-title">Relacionados</div>', unsafe_allow_html=True)
                render_related_records(account_deals, account_tickets, stale_ids=account_stale)

            st.markdown(" ")
            st.markdown('<div class="panel">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">Cadastro</div>', unsafe_allow_html=True)
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
                    f"<span style='opacity:0.6;font-size:0.85rem;'>{rotulo}</span>"
                    f"<span style='font-size:0.88rem;text-align:right;'>{valor}</span></div>",
                    unsafe_allow_html=True,
                )
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
                _assinatura = hashlib.md5(
                    repr(sorted((str(d["deal_id"]), str(d["stage"])) for d in _deals_records)).encode()
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
                queue_toast(f"Campanha «{campaign}» salva.")
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
        st.bar_chart(
            channel_conversion,
            horizontal=True,
            color="#08a742",
            height=max(160, 56 * len(channel_conversion)),
        )
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

elif section == "Automações":
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

elif section == "Importar Dados":
    from csv_import import IGNORE, FIELD_SYNONYMS, analyze_import, guess_mapping, sample_csv

    _pode_importar = has_permission(user["role"], "customer.create")

    with st.container(border=True):
        st.markdown('<div class="section-title">1. Enviar planilha de clientes</div>', unsafe_allow_html=True)
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
                st.markdown(
                    '<div class="section-title">2. Conferir o mapeamento das colunas</div>',
                    unsafe_allow_html=True,
                )
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
                st.markdown('<div class="section-title">3. Prévia da importação</div>', unsafe_allow_html=True)
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

elif section == "Manual de Serviços":
    from services_catalog import (
        SERVICE_CATALOG,
        resolve_service_section as _manual_secao,
        services_manual_markdown,
        services_manual_sections,
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
                queue_toast(f"Permissões do role {selected_role} atualizadas com auditoria.")
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
