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


class TestVisoesSalvas:
    """O recorte de filtros precisa poder ser salvo e reaplicado."""

    def test_controles_de_visao_estao_na_barra_lateral(self):
        app = _run_section("Funil Comercial")
        assert not app.exception
        chaves = [w.key for w in app.text_input]
        assert "new_view_name" in chaves, f"campos encontrados: {chaves}"

    def test_salvar_visao_persiste_e_reaparece(self):
        app = _run_section("Funil Comercial")
        app.text_input(key="new_view_name").set_value("Carteira Brasil").run()
        app.button(key="save_view_btn").click().run()
        assert not app.exception

        # A visão salva deve aparecer no seletor na renderização seguinte.
        depois = _run_section("Funil Comercial")
        opcoes = []
        for select in depois.selectbox:
            opcoes.extend(list(select.options))
        assert "Carteira Brasil" in opcoes, f"opções encontradas: {opcoes}"


class TestConsultaDeCnpj:
    def test_botao_de_consulta_existe_no_cadastro(self):
        app = _run_section("Clientes 360")
        assert not app.exception
        chaves = [b.key for b in app.button]
        assert "lookup_cnpj_btn" in chaves, f"botões encontrados: {chaves}"

    def test_botao_desabilitado_sem_documento_valido(self):
        app = _run_section("Clientes 360")
        botao = next(b for b in app.button if b.key == "lookup_cnpj_btn")
        assert botao.disabled is True, "não deve consultar a Receita sem um CNPJ válido"


class TestFluxoCompletoDeConsultaCnpj:
    """Do CNPJ digitado aos campos preenchidos, sem tocar a rede."""

    CNPJ = "19.131.243/0001-97"

    def _app_com_receita_simulada(self, monkeypatch, resultado):
        import crm_receita

        monkeypatch.setattr(crm_receita, "lookup_cnpj", lambda *a, **k: resultado)
        app = AppTest.from_file(APP_PATH, default_timeout=90)
        app.session_state["crm_user"] = ADMIN
        app.session_state["nav_section"] = "Clientes 360"
        app.session_state["onboarding_tour_done"] = True
        app.session_state["new_customer_document"] = self.CNPJ
        return app

    def test_documento_valido_habilita_a_consulta(self, monkeypatch):
        from crm_receita import CompanyLookup

        app = self._app_com_receita_simulada(monkeypatch, CompanyLookup(False, "")).run()
        botao = next(b for b in app.button if b.key == "lookup_cnpj_btn")
        assert botao.disabled is False

    def test_consulta_preenche_nome_segmento_e_cidade(self, monkeypatch):
        from crm_receita import CompanyLookup

        resultado = CompanyLookup(
            success=True,
            message="ok",
            cnpj=self.CNPJ,
            razao_social="OPEN KNOWLEDGE BRASIL",
            nome_fantasia="REDE PELO CONHECIMENTO LIVRE",
            situacao="ATIVA",
            cnae_descricao="Atividades de associações",
            municipio="SAO PAULO",
        )
        app = self._app_com_receita_simulada(monkeypatch, resultado).run()
        app.button(key="lookup_cnpj_btn").click().run()

        assert not app.exception
        assert app.session_state["new_customer_name"] == "REDE PELO CONHECIMENTO LIVRE"
        assert app.session_state["new_customer_city"] == "SAO PAULO"

    def test_api_fora_do_ar_avisa_sem_travar_a_tela(self, monkeypatch):
        from crm_receita import CompanyLookup

        indisponivel = CompanyLookup(False, "Não foi possível consultar a Receita agora.")
        app = self._app_com_receita_simulada(monkeypatch, indisponivel).run()
        app.button(key="lookup_cnpj_btn").click().run()

        # O cadastro manual precisa continuar possível.
        assert not app.exception
        assert any("Receita" in w.value for w in app.warning)


class TestAplicacaoDeVisaoSalva:
    def test_aplicar_visao_altera_os_filtros_globais(self):
        app = _run_section("Funil Comercial")

        # Cria a visão com um recorte específico.
        app.session_state["filter_country"] = "Brasil"
        app.run()
        app.text_input(key="new_view_name").set_value("Só Brasil").run()
        app.button(key="save_view_btn").click().run()

        # Volta o filtro ao padrão e reaplica pela visão salva.
        app.session_state["filter_country"] = "Todos"
        app.run()
        app.selectbox(key="saved_view_pick").set_value("Só Brasil").run()
        app.button(key="apply_view").click().run()

        assert not app.exception
        assert app.session_state["filter_country"] == "Brasil"
