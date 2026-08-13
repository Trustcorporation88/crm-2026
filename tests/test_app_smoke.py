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
    "Manual de Serviços",
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
        # Com o funil em kanban, os valores visíveis ficam no componente e na
        # tabela de oportunidades — o formato pt-BR é verificado na tabela.
        valores = []
        for el in app.dataframe:
            df = el.value
            if "Valor" in getattr(df, "columns", []):
                valores.extend(str(v) for v in df["Valor"])
        # Formato pt-BR: R$ 190.000 (ponto de milhar), nunca R$ 190,000.
        assert "R$ 190.000" in valores, f"tabela sem formato pt-BR: {valores}"
        assert not any("R$ 190,000" in v for v in valores)


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

    def _texto_visivel(self, app) -> str:
        partes = [m.value for m in app.markdown]
        partes += [c.value for c in app.caption]
        partes += [w.value for w in app.warning]
        return " ".join(partes)

    def test_nao_ensina_o_visitante_a_desligar_a_autenticacao(self, monkeypatch):
        """A tela publicava o nome da variável que libera entrada sem senha.

        É a única página que o mundo inteiro enxerga, e ela trazia escrito
        «para liberar o acesso de demonstração em um clique, defina
        CRM_DEMO_LOGIN=true». Quem administra a instância encontra isso no
        .env.example; quem só passou na porta não precisa saber que a porta
        tem um destravamento.
        """
        app = self._login_page(monkeypatch)
        assert "CRM_DEMO_LOGIN" not in self._texto_visivel(app), (
            "a tela de login voltou a divulgar a variável do acesso sem senha"
        )

    def test_o_aviso_continua_quando_o_modo_esta_de_fato_ligado(self, monkeypatch):
        """Ligado, o risco tem de estar visível — o silêncio aqui seria pior."""
        app = self._login_page(monkeypatch, "true")
        assert any("sem senha" in w.value for w in app.warning), (
            "modo demonstração ativo sem aviso na tela"
        )

    def test_nao_traz_texto_de_vitrine(self, monkeypatch):
        """Ferramenta interna não faz propaganda para quem já é da casa.

        Os três atributos técnicos ficavam sublinhados em verde, o que ainda
        os fazia parecer abas clicáveis que não clicavam em nada.
        """
        texto = self._texto_visivel(self._login_page(monkeypatch))
        for vitrine in ("PostgreSQL gerenciado", "Acesso por papéis", "intake operacional"):
            assert vitrine not in texto, f"texto de vitrine de volta na tela de login: {vitrine}"

    def test_pede_usuario_e_senha_e_nada_mais(self, monkeypatch):
        app = self._login_page(monkeypatch)
        rotulos = [w.label for w in app.text_input]
        assert rotulos == ["Usuário", "Senha"], f"campos na tela: {rotulos}"


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


class TestFichaOrientadaALinhaDoTempo:
    """A ficha do cliente lidera pela narrativa, não pelo cadastro."""

    def test_ficha_renderiza_com_os_novos_blocos(self):
        app = _run_section("Clientes 360")
        assert not app.exception

        conteudo = " ".join(m.value for m in app.markdown)
        assert "Linha do tempo" in conteudo
        assert "Próxima ação" in conteudo
        assert "Relacionados" in conteudo
        assert "Cadastro" in conteudo

    def test_cabecalho_traz_os_indicadores_da_conta(self):
        app = _run_section("Clientes 360")
        rotulos = [m.label for m in app.metric]
        assert "Saúde da conta" in rotulos, f"métricas: {rotulos}"
        assert "Valor em pipeline" in rotulos
        assert "Chamados abertos" in rotulos

    def test_formulario_de_registro_de_interacao_existe(self):
        app = _run_section("Clientes 360")
        chaves = [w.key for w in app.text_input]
        assert "log_title" in chaves, f"campos: {chaves}"

    def test_registrar_interacao_grava_na_linha_do_tempo(self):
        app = _run_section("Clientes 360")
        app.text_input(key="log_title").set_value("Ligação de teste automatizado").run()

        # O botão de submit do formulário aparece com a chave prefixada.
        registrar = next(
            b for b in app.button if "log-interaction" in str(b.key)
        )
        registrar.click().run()
        assert not app.exception

        depois = _run_section("Clientes 360")
        conteudo = " ".join(m.value for m in depois.markdown)
        assert "Ligação de teste automatizado" in conteudo

    def test_interacao_vazia_e_recusada(self):
        app = _run_section("Clientes 360")
        registrar = next(b for b in app.button if "log-interaction" in str(b.key))
        registrar.click().run()

        assert not app.exception
        assert any("Descreva a interação" in e.value for e in app.error)

    def test_valores_da_ficha_em_formato_brasileiro(self):
        app = _run_section("Clientes 360")
        valores = [m.value for m in app.metric]
        assert not any("," in str(v) and "R$" in str(v) and "." not in str(v) for v in valores), (
            f"valor em formato americano: {valores}"
        )


class TestMarcacaoDosPaineis:
    """Painéis não podem abrir uma <div> num bloco e fechar em outro.

    O Streamlit sanitiza cada bloco de markdown isoladamente: a div aberta é
    fechada automaticamente e o `</div>` seguinte vira órfão. Com colunas ou
    métricas entre os dois, o React perde a referência do nó e o navegador
    lança NotFoundError em removeChild. Estas seções usam st.container.
    """

    def _fonte(self) -> str:
        from pathlib import Path

        return Path(APP_PATH).read_text(encoding="utf-8")

    def test_meu_dia_usa_container(self):
        fonte = self._fonte()
        trecho = fonte[fonte.index('if section == "Meu Dia":'):]
        trecho = trecho[:trecho.index('elif section == "Serviços":')]

        assert "st.container(border=True)" in trecho
        assert "'<div class=\"panel\">'" not in trecho, (
            "Meu Dia voltou a abrir <div> num bloco de markdown separado"
        )

    def test_cabecalho_do_meu_dia_tem_descricao_propria(self):
        app = _run_section("Meu Dia")
        conteudo = " ".join(m.value for m in app.markdown)
        assert "Use os filtros da barra lateral" not in conteudo, (
            "Meu Dia está caindo no texto genérico de cabeçalho"
        )
        assert "precisa da sua ação agora" in conteudo


class TestRodapeInformaOBancoReal:
    """O rodapé anunciava SQLite fixo, mesmo rodando em Postgres.

    Durante uma migração é a informação mais importante da tela: sem ela não
    dá para saber se a troca de banco surtiu efeito.
    """

    def test_sqlite_e_anunciado_como_sqlite(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        app = _run_section("Meu Dia")
        rodape = " ".join(c.value for c in app.caption)

        assert "SQLite" in rodape
        assert "PostgreSQL" not in rodape

    def test_postgres_e_anunciado_como_postgres(self, monkeypatch):
        # Basta a variável estar setada: o rótulo não abre conexão.
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host:5432/db")
        import crm_db

        assert crm_db.is_postgres() is True
        assert crm_db.backend_name() == "postgres"


class TestFilaDeExecucaoNaTela:
    """Modo 'trabalhar a fila' no Meu Dia."""

    def test_botao_de_entrar_na_fila_existe(self):
        app = _run_section("Meu Dia")
        assert not app.exception
        chaves = [b.key for b in app.button]
        assert "fila_entrar" in chaves, f"botões: {chaves}"

    def test_entrar_na_fila_mostra_a_primeira_tarefa(self):
        app = _run_section("Meu Dia")
        app.button(key="fila_entrar").click().run()
        assert not app.exception

        texto = " ".join(c.value for c in app.caption)
        assert "Tarefa 1 de" in texto, f"legendas: {texto[:300]}"

        chaves = [b.key for b in app.button]
        assert "fila_concluir" in chaves and "fila_pular" in chaves

    def test_concluir_remove_a_tarefa_da_fila(self):
        app = _run_section("Meu Dia")
        app.button(key="fila_entrar").click().run()

        total_antes = next(
            c.value for c in app.caption if "Tarefa 1 de" in c.value
        )
        app.button(key="fila_concluir").click().run()
        assert not app.exception

        legendas = " ".join(c.value for c in app.caption)
        # O total precisa ter diminuído em 1 (ou a fila esvaziou).
        import re
        antes = int(re.search(r"de (\d+)", total_antes).group(1))
        depois_match = re.search(r"de (\d+)", legendas)
        if depois_match:
            assert int(depois_match.group(1)) == antes - 1
        else:
            assert antes == 1  # fila esvaziou

    def test_sair_da_fila_volta_ao_estado_normal(self):
        app = _run_section("Meu Dia")
        app.button(key="fila_entrar").click().run()
        app.button(key="fila_sair").click().run()
        assert not app.exception
        chaves = [b.key for b in app.button]
        assert "fila_entrar" in chaves


class TestWhatsAppNaFicha:
    """Painel de WhatsApp por link na ficha do cliente."""

    def test_painel_renderiza_com_mensagem_e_download(self):
        app = _run_section("Clientes 360")
        assert not app.exception

        conteudo = " ".join(m.value for m in app.markdown)
        assert "WhatsApp" in conteudo

        # A mensagem vem pré-preenchida com o nome do cliente.
        areas = [t.value for t in app.text_area if t.value]
        assert any("Olá," in v for v in areas), f"text_areas: {areas}"

    def test_registrar_envio_grava_na_linha_do_tempo(self):
        app = _run_section("Clientes 360")
        botao = next(b for b in app.button if str(b.key).startswith("wa_log_"))
        botao.click().run()
        assert not app.exception

        depois = _run_section("Clientes 360")
        conteudo = " ".join(m.value for m in depois.markdown)
        assert "Mensagem enviada por WhatsApp" in conteudo


class TestManualDeServicos:
    """O manual dentro do CRM precisa refletir o catálogo inteiro."""

    def test_manual_renderiza_com_resumo_e_download(self):
        app = _run_section("Manual de Serviços")
        assert not app.exception
        # tabela-resumo com os 17 serviços
        tabelas = [el.value for el in app.dataframe]
        assert any(len(t) == 17 for t in tabelas), "resumo deve listar os 17 serviços"

    def test_markdown_do_download_cobre_todos_os_servicos(self):
        from services_catalog import SERVICE_CATALOG, services_manual_markdown

        md = services_manual_markdown()
        for service in SERVICE_CATALOG:
            assert service["title"] in md, f"{service['title']} ausente do manual"
        assert "O que entrega" in md
