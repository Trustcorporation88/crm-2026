"""Anel de progresso e ações rápidas."""

from __future__ import annotations

import crm_components as ui


def test_anel_mostra_percentual_e_escapa_texto() -> None:
    html = ui.ring(0.75, "Tarefas <em dia>", "3 de 4", tone="ok")
    assert "75%" in html
    assert "&lt;em dia&gt;" in html and "<em dia>" not in html
    assert "stroke-dashoffset" in html


def test_anel_limita_valores_fora_da_faixa() -> None:
    assert "100%" in ui.ring(7, "x")
    assert "0%" in ui.ring(-3, "x")


def test_acoes_rapidas_respeitam_permissao(monkeypatch) -> None:
    """Perfil sem permissão de criar nada não ganha o botão «Novo»."""
    import crm_quick_actions as qa

    chamadas: list[str] = []
    monkeypatch.setattr(qa.st, "popover", lambda *a, **k: chamadas.append("popover") or _Ctx())

    qa.render({"can_manage": lambda role, area: False, "user": {"role": "leitor"}})
    assert chamadas == [], "sem permissão nenhuma, o menu «Novo» não deve aparecer"


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False
