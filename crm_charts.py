"""Gráficos interativos do Trust CRM (Altair).

Todos respondem ao mouse: a barra/fatia sob o cursor ganha destaque, as demais
ficam esmaecidas, e o balão mostra os valores já formatados em português.
Cada função devolve um ``alt.Chart``; ``show`` desenha no Streamlit.

As cores seguem o tema (azul de ação + semânticas de estado). Nada aqui lê o
banco: quem chama entrega o ``DataFrame`` pronto.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import altair as alt
import pandas as pd

# Paleta única do produto.
BLUE = "#2563eb"
INDIGO = "#6366f1"
TEAL = "#0d9488"
AMBER = "#f59e0b"
RED = "#ef4444"
GREEN = "#22c55e"
SLATE = "#94a3b8"
INK = "#374151"
MUTED = "#6b7280"
GRID = "#eef0f3"

STAGE_COLORS = {
    "Descoberta": SLATE,
    "Proposta": INDIGO,
    "Negociacao": AMBER,
    "Negociação": AMBER,
    "Fechado ganho": GREEN,
    "Fechado perdido": RED,
}
STATUS_COLORS = {
    "Novo": BLUE,
    "Em progresso": AMBER,
    "Aguardando cliente": INDIGO,
    "Resolvido": GREEN,
}
PRIORITY_COLORS = {"Critica": RED, "Alta": AMBER, "Media": BLUE, "Baixa": SLATE}
QUALITATIVE = [BLUE, INDIGO, TEAL, AMBER, "#ec4899", GREEN, SLATE, RED]


def _hover(field: str):
    """Seleção por passagem do mouse (Altair 5+); em versões antigas, sem destaque."""
    if not hasattr(alt, "selection_point"):
        return None
    try:
        return alt.selection_point(on="mouseover", fields=[field], empty=True, clear="mouseout")
    except Exception:  # pragma: no cover - versão sem suporte
        return None


def _emphasis(hover):
    if hover is None:
        return alt.value(1)
    return alt.condition(hover, alt.value(1), alt.value(0.5))


def _style(chart: alt.Chart | alt.LayerChart, height: int) -> alt.Chart:
    return (
        chart.properties(height=height, padding={"left": 4, "right": 12, "top": 6, "bottom": 4})
        .configure(background="#ffffff")
        .configure_view(strokeWidth=0, fill="#ffffff")
        .configure_axis(
            labelColor=MUTED,
            labelFontSize=11,
            titleColor=MUTED,
            gridColor=GRID,
            domain=False,
            ticks=False,
            labelPadding=6,
        )
        .configure_legend(labelColor=INK, labelFontSize=11, titleFontSize=0, symbolType="circle", symbolSize=90, orient="bottom")
        .configure(font="ui-sans-serif, -apple-system, 'Segoe UI', Inter, sans-serif")
    )


def _scale(colors: Mapping[str, str] | None, categories: Sequence[str]):
    if not colors:
        return alt.Scale(range=QUALITATIVE)
    domain = [c for c in categories]
    palette = [colors.get(c, SLATE) for c in domain]
    return alt.Scale(domain=domain, range=palette)


def bar_h(
    df: pd.DataFrame,
    cat: str,
    val: str,
    *,
    label: str | None = None,
    colors: Mapping[str, str] | None = None,
    color: str = BLUE,
    height: int | None = None,
    fmt: str = ",.0f",
    order: Sequence[str] | None = None,
    tooltip_extra: Sequence[str] = (),
    label_col: str | None = None,
) -> alt.Chart:
    """Barras horizontais com cantos arredondados, rótulo de valor e destaque ao passar o mouse."""
    data = df.copy()
    n = max(len(data), 1)
    height = height or max(120, 44 * n + 16)
    hover = _hover(cat)
    sort: Any = list(order) if order else "-x"
    tooltip = [alt.Tooltip(f"{cat}:N", title=label or cat)]
    tooltip.append(alt.Tooltip(f"{val}:Q", title="Valor", format=fmt))
    tooltip += [alt.Tooltip(f"{c}:N") for c in tooltip_extra]

    base = alt.Chart(data).encode(
        y=alt.Y(f"{cat}:N", sort=sort, title=None, axis=alt.Axis(labelLimit=190, labelColor=INK, labelFontSize=12)),
        x=alt.X(f"{val}:Q", title=None, axis=None, scale=alt.Scale(nice=False)),
    )
    if colors:
        color_enc: Any = alt.Color(f"{cat}:N", scale=_scale(colors, data[cat].astype(str).tolist()), legend=None)
    else:
        color_enc = alt.value(color)
    bars = base.mark_bar(cornerRadiusEnd=6, size=18).encode(color=color_enc, opacity=_emphasis(hover), tooltip=tooltip)
    if hover is not None:
        bars = bars.add_params(hover)
    texto = alt.Text(f"{label_col}:N") if label_col else alt.Text(f"{val}:Q", format=fmt)
    text = base.mark_text(align="left", dx=6, fontSize=11.5, fontWeight=600, color=INK).encode(text=texto)
    return _style(bars + text, height)


def column(
    df: pd.DataFrame,
    x: str,
    y: str,
    *,
    label: str | None = None,
    color: str = BLUE,
    colors: Mapping[str, str] | None = None,
    height: int = 230,
    fmt: str = ",.0f",
    order: Sequence[str] | None = None,
) -> alt.Chart:
    """Colunas verticais com destaque ao passar o mouse."""
    data = df.copy()
    hover = _hover(x)
    base = alt.Chart(data).encode(
        x=alt.X(f"{x}:N", sort=list(order) if order else None, title=None, axis=alt.Axis(labelAngle=0, labelLimit=110, labelColor=INK)),
        y=alt.Y(f"{y}:Q", title=None, axis=alt.Axis(grid=True, format=fmt)),
    )
    color_enc: Any = alt.Color(f"{x}:N", scale=_scale(colors, data[x].astype(str).tolist()), legend=None) if colors else alt.value(color)
    bars = base.mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6, size=34).encode(
        color=color_enc,
        opacity=_emphasis(hover),
        tooltip=[alt.Tooltip(f"{x}:N", title=label or x), alt.Tooltip(f"{y}:Q", title="Valor", format=fmt)],
    )
    if hover is not None:
        bars = bars.add_params(hover)
    return _style(bars, height)


def donut(
    df: pd.DataFrame,
    cat: str,
    val: str,
    *,
    colors: Mapping[str, str] | None = None,
    height: int = 230,
    center_label: str = "Total",
) -> alt.Chart:
    """Rosca com total no centro; a fatia sob o mouse sai um pouco do lugar."""
    data = df.copy()
    total = int(round(float(data[val].sum()))) if not data.empty else 0
    hover = _hover(cat)
    theta = alt.Theta(f"{val}:Q", stack=True)
    color_enc = alt.Color(
        f"{cat}:N",
        scale=_scale(colors, data[cat].astype(str).tolist()),
        legend=alt.Legend(title=None, orient="right", labelLimit=150),
    )
    arc = alt.Chart(data).mark_arc(innerRadius=62, outerRadius=100, cornerRadius=5, padAngle=0.03, stroke="#ffffff", strokeWidth=2).encode(
        theta=theta,
        color=color_enc,
        opacity=_emphasis(hover),
        tooltip=[alt.Tooltip(f"{cat}:N", title="Categoria"), alt.Tooltip(f"{val}:Q", title="Quantidade", format=",.0f")],
    )
    if hover is not None:
        arc = arc.add_params(hover)
    centro = alt.Chart(pd.DataFrame({"t": [str(total)], "l": [center_label]}))
    big = centro.mark_text(fontSize=26, fontWeight=700, color="#111827", dy=-6).encode(text="t:N")
    small = centro.mark_text(fontSize=11, color=MUTED, dy=14).encode(text="l:N")
    return _style(arc + big + small, height)


def show(chart: alt.Chart) -> None:
    """Desenha o gráfico ocupando a largura do cartão, sem o tema padrão do Streamlit."""
    import streamlit as st

    st.altair_chart(chart, width="stretch", theme=None)
