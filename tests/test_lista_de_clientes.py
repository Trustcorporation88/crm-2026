"""A lista de clientes, e o nome que a seção mostra na tela.

O sistema não tinha lista de clientes. Chamados tinham tabela, campanhas
tinham, usuários tinham — clientes, não: a seção abria num seletor que mostra
uma conta por vez. Para responder "quantos clientes eu tenho e quem são" era
preciso abrir o seletor e ler as opções.

O achado veio do dono do produto apresentando o sistema, o que é o pior
momento possível para descobrir que a tela não existe.

Dois riscos guiaram estes testes:

1. **A lista furar a visibilidade por login.** Uma tabela é a forma mais fácil
   de vazar a base inteira para quem só deveria ver a própria carteira.
2. **A troca de rótulo virar migração.** O nome interno da seção aparece no
   mapa de permissões por papel, no catálogo de serviços e no roteamento.
   Renomear a chave quebraria permissão; o que muda é só o que se lê na tela.
"""

import pathlib

import pytest
from streamlit.testing.v1 import AppTest

import crm_ux

APP = str(pathlib.Path(__file__).resolve().parent.parent / "crm_app.py")

ADMIN = {"username": "admin", "full_name": "FLAVIO RINALDI", "role": "admin"}
VENDEDOR = {"username": "vendas", "full_name": "Rafael Nogueira", "role": "vendas"}


def _abrir(ator: dict, timeout: int = 90) -> AppTest:
    app = AppTest.from_file(APP, default_timeout=timeout)
    app.session_state["crm_user"] = ator
    app.session_state["nav_section"] = "Clientes 360"
    app.session_state["onboarding_tour_done"] = True
    return app.run()


def _tabela_de_clientes(app):
    for elemento in app.dataframe:
        colunas = list(getattr(elemento.value, "columns", []))
        if "Cliente" in colunas and "Responsável" in colunas:
            return elemento.value
    return None


class TestOQueSeLeNaTela:
    """O rótulo muda; a chave interna não pode mudar."""

    def test_a_secao_se_chama_clientes_na_tela(self):
        assert crm_ux.nome_exibido("Clientes 360") == "Clientes"

    def test_secoes_sem_apelido_aparecem_com_o_proprio_nome(self):
        for secao in ("Meu Dia", "Atendimento", "Funil Comercial", "Administração"):
            assert crm_ux.nome_exibido(secao) == secao

    def test_o_menu_mostra_o_rotulo_e_nao_a_chave(self):
        """O item do menu lateral não pode mais exibir "360"."""
        app = _abrir(ADMIN)
        principal = next(r for r in app.radio if r.key == "nav_primary")
        rotulos = [principal.format_func(o) for o in principal.options]

        de_clientes = [r for r in rotulos if "Cliente" in r]
        assert de_clientes, f"nenhum item de clientes no menu: {rotulos}"
        assert not any("360" in r for r in de_clientes), (
            f"o menu ainda mostra o jargão: {de_clientes}"
        )

    def test_a_chave_interna_continua_intacta(self):
        """Renomear a chave quebraria permissão por papel e roteamento.

        `get_role_sections` devolve nomes de seção, e é o que decide quem
        enxerga o quê no menu. Se a chave mudasse aqui e não lá, a seção
        desapareceria para todos os papéis.
        """
        from crm_backend import get_role_sections

        for papel in ("admin", "vendas", "atendimento", "marketing"):
            assert "Clientes 360" in get_role_sections(papel), (
                f"o papel {papel} perdeu acesso à seção de clientes"
            )

        fonte = pathlib.Path(APP).read_text(encoding="utf-8")
        assert 'elif section == "Clientes 360":' in fonte


class TestListaExiste:
    def test_a_base_aparece_como_tabela(self):
        app = _abrir(ADMIN)
        assert not app.exception

        tabela = _tabela_de_clientes(app)
        assert tabela is not None, (
            "não há tabela de clientes na tela — era o defeito original"
        )
        assert len(tabela) > 0

    def test_a_tabela_traz_o_que_se_precisa_para_agir(self):
        tabela = _tabela_de_clientes(_abrir(ADMIN))
        for coluna in ("Cliente", "Responsável", "Situação", "Saúde", "Próxima ação"):
            assert coluna in tabela.columns, f"a lista não mostra «{coluna}»"

    def test_valores_em_formato_brasileiro(self):
        tabela = _tabela_de_clientes(_abrir(ADMIN))
        valores = [str(v) for v in tabela["Valor de vida"]]

        assert all(v.startswith("R$") for v in valores), valores
        # pt-BR usa ponto de milhar. "R$ 12,500" seria formato americano.
        assert not any("," in v for v in valores), f"valor em formato americano: {valores}"

    def test_quem_esta_em_risco_aparece_primeiro(self):
        """A ordem é a opinião da tela sobre o que importa.

        Uma lista em ordem alfabética obriga a pessoa a procurar o problema.
        Ordenada por saúde, o problema se apresenta.
        """
        tabela = _tabela_de_clientes(_abrir(ADMIN))
        saudes = list(tabela["Saúde"])
        assert saudes == sorted(saudes), f"a lista não abre pelos piores: {saudes}"

    def test_o_seletor_de_conta_continua_existindo(self):
        """A lista soma, não substitui: a ficha individual segue sendo o miolo."""
        app = _abrir(ADMIN)
        rotulos = [s.label for s in app.selectbox]
        assert "Selecionar conta" in rotulos, f"seletores na tela: {rotulos}"


class TestListaRespeitaAVisibilidade:
    """Tabela é a forma mais fácil de vazar a base inteira."""

    def test_vendedor_ve_apenas_a_propria_carteira(self):
        tabela = _tabela_de_clientes(_abrir(VENDEDOR))
        assert tabela is not None and len(tabela) > 0, (
            "o vendedor de teste ficou sem carteira — o teste perde o sentido"
        )

        donos = set(tabela["Responsável"])
        assert donos == {VENDEDOR["full_name"]}, (
            f"a lista mostrou contas de outras pessoas: {donos}"
        )

    def test_o_administrador_ve_mais_que_o_vendedor(self):
        do_admin = _tabela_de_clientes(_abrir(ADMIN))
        do_vendedor = _tabela_de_clientes(_abrir(VENDEDOR))

        assert len(do_admin) > len(do_vendedor), (
            "admin e vendedor veem a mesma coisa — a restrição não está valendo "
            "na lista nova"
        )


class TestFiltroDaLista:
    def test_filtrar_reduz_a_lista(self):
        app = _abrir(ADMIN)
        antes = len(_tabela_de_clientes(app))

        alvo = str(_tabela_de_clientes(app)["Cidade"].iloc[0])
        app.text_input(key="lista_clientes_busca").set_value(alvo).run()
        assert not app.exception

        depois = _tabela_de_clientes(app)
        assert depois is not None
        assert len(depois) <= antes
        assert all(alvo.lower() in str(c).lower() for c in depois["Cidade"])

    def test_filtro_sem_resultado_nao_quebra_a_tela(self):
        app = _abrir(ADMIN)
        app.text_input(key="lista_clientes_busca").set_value("zzz-nao-existe-zzz").run()

        assert not app.exception
        assert _tabela_de_clientes(app) is None

    @pytest.mark.parametrize("campo", ["Cliente", "Segmento", "Responsável"])
    def test_filtra_por_mais_de_um_campo(self, campo):
        app = _abrir(ADMIN)
        alvo = str(_tabela_de_clientes(app)[campo].iloc[0])

        app.text_input(key="lista_clientes_busca").set_value(alvo).run()
        assert not app.exception
        assert _tabela_de_clientes(app) is not None, (
            f"filtrar por {campo} («{alvo}») não encontrou nem a própria linha"
        )
