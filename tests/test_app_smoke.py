"""Smoke tests de renderização do app Streamlit.

Os testes unitários cobrem a lógica, mas não garantem que a tela desenha. Estes
testes executam crm_app.py de verdade com o AppTest do Streamlit e falham se
qualquer seção levantar exceção durante a renderização — que é exatamente o
tipo de defeito que só aparece em produção.
"""

import os
import pathlib
import tempfile

import pytest

# O app precisa de um diretório de dados isolado antes de ser importado.
_TMP = pathlib.Path(tempfile.mkdtemp(prefix="crm-app-smoke-"))
os.environ.setdefault("CRM_DATA_DIR", str(_TMP))

from streamlit.testing.v1 import AppTest  # noqa: E402

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "crm_app.py")

ADMIN = {"username": "admin", "full_name": "Admin Teste", "role": "admin"}

# Seções administradas pelo papel admin. "Serviços" é o catálogo inicial.
SECTIONS = [
    "Meu Dia",
    "Serviços",
    "Visão Executiva",
    "Atendimento",
    "Clientes 360",
    "Funil Comercial",
    "Canais",
]


def _run_section(section: str, timeout: int = 60) -> AppTest:
    app = AppTest.from_file(APP_PATH, default_timeout=timeout)
    app.session_state["crm_user"] = ADMIN
    app.session_state["nav_section"] = section
    app.session_state["onboarding_tour_done"] = True
    return app.run()


@pytest.mark.parametrize("section", SECTIONS)
def test_secao_renderiza_sem_excecao(section):
    app = _run_section(section)
    assert not app.exception, (
        f"A seção «{section}» quebrou ao renderizar: "
        + "; ".join(str(e.value) for e in app.exception)
    )


class TestMeuDia:
    """A superfície de trabalho diário precisa existir e responder."""

    def test_meu_dia_esta_disponivel_e_renderiza(self):
        app = _run_section("Meu Dia")
        assert not app.exception
        texto = " ".join(m.value for m in app.markdown) + " ".join(c.value for c in app.caption)
        assert "responsável" in texto.lower() or "pendências" in texto.lower()


class TestFunilComercial:
    """Melhorias do funil: totais por etapa e formatação pt-BR."""

    def test_resumo_do_funil_aparece(self):
        app = _run_section("Funil Comercial")
        assert not app.exception
        rotulos = [m.label for m in app.metric]
        assert "Previsão ponderada" in rotulos, f"métricas encontradas: {rotulos}"
        assert "Oportunidades abertas" in rotulos

    def test_valores_usam_formato_brasileiro(self):
        app = _run_section("Funil Comercial")
        conteudo = " ".join(m.value for m in app.markdown)
        # Formato pt-BR: R$ 190.000 (ponto de milhar), nunca R$ 190,000.
        assert "R$ 190.000" in conteudo or "R$ " in conteudo
        assert "R$ 190,000" not in conteudo


class TestBuscaGlobal:
    def test_campo_de_busca_esta_na_barra_lateral(self):
        app = _run_section("Meu Dia")
        chaves = [w.key for w in app.text_input]
        assert "global_search_term" in chaves


class TestTelaDeLogin:
    """A tela pública não pode oferecer acesso administrativo sem credencial."""

    def _login_page(self, monkeypatch, demo_value=None):
        if demo_value is None:
            monkeypatch.delenv("CRM_DEMO_LOGIN", raising=False)
        else:
            monkeypatch.setenv("CRM_DEMO_LOGIN", demo_value)
        app = AppTest.from_file(APP_PATH, default_timeout=60)
        # Sem crm_user na sessão, o app renderiza a tela de login.
        return app.run()

    def test_sem_a_variavel_nao_ha_botao_de_entrar_como_admin(self, monkeypatch):
        app = self._login_page(monkeypatch)
        assert not app.exception
        chaves = [b.key for b in app.button]
        assert not any(str(k).startswith("demo-login-") for k in chaves), (
            f"login de demonstração exposto sem a flag: {chaves}"
        )

    def test_com_a_variavel_os_botoes_voltam(self, monkeypatch):
        app = self._login_page(monkeypatch, "true")
        assert not app.exception
        chaves = [str(b.key) for b in app.button]
        assert any(k.startswith("demo-login-") for k in chaves)
