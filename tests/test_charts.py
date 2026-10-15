"""Gráficos interativos: montam sem erro, carregam tooltip e destaque ao mouse."""

from __future__ import annotations

import pandas as pd

import crm_charts as charts


def _spec(chart) -> dict:
    return chart.to_dict()


def test_bar_h_monta_com_tooltip_e_rotulo() -> None:
    df = pd.DataFrame({"etapa": ["Descoberta", "Proposta"], "valor": [72000, 68000]})
    spec = _spec(charts.bar_h(df, "etapa", "valor", label="Etapa", colors=charts.STAGE_COLORS, fmt=",.0f"))
    texto = str(spec)
    assert "tooltip" in texto
    assert "mark_text" in texto or "'text'" in texto, "falta o rótulo de valor ao fim da barra"


def test_bar_h_aceita_base_vazia() -> None:
    df = pd.DataFrame({"etapa": [], "valor": []})
    assert _spec(charts.bar_h(df, "etapa", "valor"))


def test_donut_mostra_total_no_centro() -> None:
    df = pd.DataFrame({"status": ["Novo", "Resolvido"], "qtd": [3, 2]})
    spec = _spec(charts.donut(df, "status", "qtd", colors=charts.STATUS_COLORS, center_label="tickets"))
    assert "'5'" in str(spec), "o total (5) deve aparecer no centro da rosca"


def test_column_monta() -> None:
    df = pd.DataFrame({"canal": ["Email", "Chat"], "taxa": [39.6, 53.1]})
    assert _spec(charts.column(df, "canal", "taxa", fmt=".1f"))


def test_destaque_ao_mouse_quando_altair_suporta() -> None:
    df = pd.DataFrame({"etapa": ["A", "B"], "valor": [1, 2]})
    spec = _spec(charts.bar_h(df, "etapa", "valor"))
    if hasattr(charts.alt, "selection_point"):
        assert "params" in str(spec) or "selection" in str(spec)
