"""Componentes visuais do Trust CRM (layout v2).

HTML simples, sempre com dados escapados, desenhado pelas classes de
``static/crm_app.css``. Cada função emite UM bloco de markdown autocontido —
nunca abre uma tag num bloco e fecha em outro (o Streamlit sanitiza cada bloco
isoladamente).
"""

from __future__ import annotations

import html
from datetime import date, datetime
from typing import Any, Iterable, Sequence

_MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]
_DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]

TONES = ("danger", "warn", "info", "ok", "gold", "neutral")


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def icon(name: str, extra: str = "") -> str:
    """Ícone Material Symbols (a fonte já é carregada pelo próprio Streamlit)."""
    return f'<span class="ms {extra}" aria-hidden="true" translate="no">{_e(name)}</span>'


def data_por_extenso(hoje: date | None = None) -> str:
    hoje = hoje or date.today()
    dia = _DIAS[hoje.weekday()]
    return f"{dia[0].upper()}{dia[1:]}, {hoje.day} de {_MESES[hoje.month - 1]}"


def saudacao(agora: datetime | None = None) -> str:
    hora = (agora or datetime.now()).hour
    if hora < 12:
        return "Bom dia"
    if hora < 18:
        return "Boa tarde"
    return "Boa noite"


def primeiro_nome(nome: str | None, fallback: str = "") -> str:
    partes = (nome or "").strip().split()
    return partes[0].capitalize() if partes else fallback


# ---------------------------------------------------------------------------
# Cabeçalho da página
# ---------------------------------------------------------------------------
def page_header(title: str, subtitle: str = "", eyebrow: str = "", chips: Sequence[str] = (), show_date: bool = True) -> str:
    chips_html = "".join(f'<span class="chip">{_e(c)}</span>' for c in chips)
    date_html = f'<span class="chip chip--date">{icon("calendar_today")}{_e(data_por_extenso())}</span>' if show_date else ""
    eyebrow_html = f'<div class="ph-eyebrow">{_e(eyebrow)}</div>' if eyebrow else ""
    sub_html = f"<p>{_e(subtitle)}</p>" if subtitle else ""
    return (
        f'<header class="ph"><div class="ph-text">{eyebrow_html}<h1>{_e(title)}</h1>{sub_html}</div>'
        f'<div class="ph-meta">{chips_html}{date_html}</div></header>'
    )


# ---------------------------------------------------------------------------
# Cartões de indicador
# ---------------------------------------------------------------------------
_ICON_RULES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("atras", "venc"), "alarm", "danger"),
    (("sla", "chamado", "ticket"), "support_agent", "warn"),
    (("parad", "sem contato", "risco"), "hourglass_top", "warn"),
    (("hoje", "tarefa"), "task_alt", "info"),
    (("receita", "valor", "carteira", "previs", "funil aberto", "ticket médio", "faturamento"), "payments", "ok"),
    (("negocia", "oportunidade"), "handshake", "info"),
    (("saúde", "csat", "satisf"), "favorite", "ok"),
    (("cliente", "conta"), "groups", "gold"),
    (("intera", "mensagem", "canal"), "forum", "info"),
)


def _icon_for(label: str, index: int) -> tuple[str, str]:
    low = label.lower()
    for keys, name, tone in _ICON_RULES:
        if any(k in low for k in keys):
            return name, tone
    return "insights", TONES[index % len(TONES)]


def kpi_grid(items: Iterable[dict[str, Any]]) -> str:
    """items: label, value, caption (opcional), icon/tone (opcionais)."""
    cards = []
    for i, it in enumerate(items):
        name, tone = _icon_for(str(it.get("label", "")), i)
        name, tone = it.get("icon", name), it.get("tone", tone)
        cap = f'<div class="kpi-cap">{_e(it["caption"])}</div>' if it.get("caption") else ""
        cards.append(
            f'<div class="kpi kpi--{tone}"><div class="kpi-head"><span class="kpi-ico">{icon(name)}</span>'
            f'<span class="kpi-label">{_e(it.get("label", ""))}</span></div>'
            f'<div class="kpi-value">{_e(it.get("value", ""))}</div>{cap}</div>'
        )
    return f'<div class="kpi-grid kpi-grid--{min(max(len(cards), 1), 6)}">{"".join(cards)}</div>'


# ---------------------------------------------------------------------------
# Linhas de lista (agenda, fila, alertas)
# ---------------------------------------------------------------------------
_PRIORITY_TONE = {"critica": "danger", "crítica": "danger", "alta": "warn", "media": "info", "média": "info", "baixa": "neutral"}


def priority_tone(priority: Any) -> str:
    return _PRIORITY_TONE.get(str(priority or "").strip().lower(), "neutral")


def pill(text: Any, tone: str = "neutral") -> str:
    return f'<span class="pill pill--{tone}">{_e(text)}</span>'


def agenda_row(title: Any, meta: Any = "", tone: str = "neutral", right: str = "", progress: float | None = None, ico: str = "") -> str:
    """Uma linha de lista. ``right`` já deve vir como HTML seguro (use pill())."""
    bar = ""
    if progress is not None:
        pct = max(0, min(100, int(round(progress * 100))))
        bar = f'<div class="sbar sbar--{tone}"><i style="width:{pct}%"></i></div>'
    lead = f'<span class="arow-ico arow-ico--{tone}">{icon(ico)}</span>' if ico else f'<span class="adot adot--{tone}"></span>'
    meta_html = f'<div class="ameta">{_e(meta)}</div>' if meta else ""
    return (
        f'<div class="arow">{lead}<div class="abody"><div class="atitle">{_e(title)}</div>{meta_html}{bar}</div>'
        f'<div class="aright">{right}</div></div>'
    )


def list_block(rows: Sequence[str], empty: str = "Nada por aqui.") -> str:
    if not rows:
        return f'<div class="empty-state">{icon("check_circle")}<span>{_e(empty)}</span></div>'
    return f'<div class="alist">{"".join(rows)}</div>'


def card_title(text: str, ico: str = "", aside: str = "") -> str:
    lead = f'<span class="ct-ico">{icon(ico)}</span>' if ico else ""
    aside_html = f'<span class="ct-aside">{_e(aside)}</span>' if aside else ""
    return f'<div class="ct">{lead}<span class="ct-text">{_e(text)}</span>{aside_html}</div>'


def stepper(steps: Sequence[str], current: int) -> str:
    """Indicador de etapas: concluídas em verde, atual em destaque."""
    items = []
    for i, label in enumerate(steps):
        state = "done" if i < current else "now" if i == current else "todo"
        mark = icon("check") if state == "done" else str(i + 1)
        items.append(f'<li class="step step--{state}"><span class="step-n">{mark}</span><span class="step-l">{_e(label)}</span></li>')
    return f'<ol class="stepper">{"".join(items)}</ol>'


def profile_header(name: Any, subtitle: str = "", pills: Sequence[tuple[str, str]] = ()) -> str:
    """Cabeçalho de ficha: avatar com iniciais, nome, linha de contexto e selos."""
    partes = [p for p in str(name or "").split() if p]
    iniciais = (partes[0][0] + (partes[-1][0] if len(partes) > 1 else "")).upper() if partes else "?"
    pills_html = "".join(pill(text, tone) for text, tone in pills if text)
    sub = f'<div class="pf-sub">{_e(subtitle)}</div>' if subtitle else ""
    return (
        f'<div class="pf"><div class="pf-avatar">{_e(iniciais)}</div>'
        f'<div class="pf-body"><div class="pf-name">{_e(name)}</div>{sub}</div>'
        f'<div class="pf-pills">{pills_html}</div></div>'
    )
