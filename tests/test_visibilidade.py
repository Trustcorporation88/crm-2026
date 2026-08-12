"""Visibilidade dos registros por login.

Antes, qualquer pessoa autenticada lia qualquer cliente, ticket ou negócio.
A decisão do dono do produto foi restringir: administrador vê tudo, os demais
veem apenas o que está sob sua responsabilidade.

Dois riscos guiaram estes testes, e nenhum deles é "o filtro funciona?":

1. **Sumiço silencioso.** Se um registro tem dono que não corresponde a
   nenhuma conta, ele fica invisível para todo mundo. Era o estado do banco
   antes desta mudança: 44% dos registros pertenciam a nomes sem conta.
2. **Leitura restrita com escrita livre.** Esconder na tela e permitir a
   alteração pela API seria uma falsa sensação de controle — a permissão do
   RBAC diz que o papel pode editar aquele TIPO de registro, não aquele
   registro específico.
"""

import importlib
import os
import sys

import pytest


@pytest.fixture
def backend(tmp_path):
    os.environ["CRM_DATA_DIR"] = str(tmp_path / "data")
    os.environ["CRM_DB_PATH"] = str(tmp_path / "crm.sqlite3")
    os.environ["CRM_SEED_PASSWORD_ADMIN"] = "senha-de-teste-2026"
    sys.modules.pop("crm_backend", None)
    modulo = importlib.import_module("crm_backend")
    modulo.init_database()
    return modulo


ADMIN = {"username": "admin", "full_name": "FLAVIO RINALDI", "role": "admin"}
VENDEDOR = {"username": "vendas", "full_name": "Rafael Nogueira", "role": "vendas"}
OUTRO = {"username": "bruna", "full_name": "Bruna Melo", "role": "vendas"}


class TestTodoRegistroTemDonoComConta:
    """O pré-requisito da restrição: ninguém pode ficar sem enxergar nada."""

    def test_nenhum_registro_semeado_fica_orfao(self, backend):
        with backend._connect() as c:
            contas = {r["full_name"] for r in c.execute("SELECT full_name FROM users").fetchall()}

            orfaos = []
            for tabela in ("customers", "tickets", "deals", "tasks"):
                for linha in c.execute(f"SELECT owner FROM {tabela}").fetchall():
                    dono = (linha["owner"] or "").strip()
                    if dono and dono not in contas:
                        orfaos.append((tabela, dono))

        assert not orfaos, (
            "registros com dono sem conta ficariam invisíveis para todos: "
            f"{sorted(set(orfaos))}"
        )

    def test_soma_das_visoes_individuais_cobre_a_base(self, backend):
        """Nenhum registro pode escapar de todas as visões.

        É o teste que pega o sumiço silencioso: se um dono deixar de ter conta,
        a soma do que cada pessoa vê fica menor que o total.
        """
        dados = backend.get_data()
        total = len(dados["customers"])

        vistos = set()
        for linha in dados["users"].to_dict("records"):
            ator = {
                "username": linha["username"],
                "full_name": linha["full_name"],
                "role": "vendas",  # papel sem visão total, de propósito
            }
            recorte = backend.aplicar_visibilidade(dados, ator)
            vistos.update(recorte["customers"]["customer_id"])

        assert len(vistos) == total, (
            f"{total - len(vistos)} cliente(s) não aparecem para ninguém"
        )


class TestRegraDeVisibilidade:
    def test_admin_ve_tudo(self, backend):
        dados = backend.get_data()
        recorte = backend.aplicar_visibilidade(dados, ADMIN)

        assert len(recorte["customers"]) == len(dados["customers"])
        assert len(recorte["deals"]) == len(dados["deals"])

    def test_vendedor_ve_so_o_que_e_dele(self, backend):
        dados = backend.get_data()
        recorte = backend.aplicar_visibilidade(dados, VENDEDOR)

        assert not recorte["customers"].empty, "o vendedor de teste ficou sem carteira"
        donos = set(recorte["customers"]["owner"])
        assert donos == {VENDEDOR["full_name"]}

    def test_vendedores_diferentes_veem_conjuntos_diferentes(self, backend):
        dados = backend.get_data()
        um = set(backend.aplicar_visibilidade(dados, VENDEDOR)["customers"]["customer_id"])
        outro = set(backend.aplicar_visibilidade(dados, OUTRO)["customers"]["customer_id"])

        assert um and outro
        assert not (um & outro), "as carteiras se sobrepõem"

    def test_chamada_interna_sem_ator_recebe_tudo(self, backend):
        """Automação, webhook e migração não têm dono e precisam da base."""
        dados = backend.get_data()

        assert len(backend.aplicar_visibilidade(dados, None)["customers"]) == len(dados["customers"])

    def test_linha_do_tempo_acompanha_a_visibilidade_do_cliente(self, backend):
        dados = backend.get_data()
        recorte = backend.aplicar_visibilidade(dados, VENDEDOR)

        clientes_visiveis = set(recorte["customers"]["customer_id"])
        for cid in recorte["interactions"]["customer_id"]:
            assert cid in clientes_visiveis, (
                "vazou histórico de um cliente que este usuário não pode ver"
            )


class TestEscritaRespeitaAPosse:
    """Esconder na leitura e liberar na escrita seria controle de fachada."""

    def _cliente_de(self, backend, nome_do_dono: str) -> str:
        with backend._connect() as c:
            linha = c.execute(
                "SELECT customer_id FROM customers WHERE owner = ? LIMIT 1", (nome_do_dono,)
            ).fetchone()
        assert linha is not None, f"nenhum cliente de {nome_do_dono} no seed"
        return str(linha["customer_id"])

    def test_nao_altera_cliente_de_outro(self, backend):
        alheio = self._cliente_de(backend, OUTRO["full_name"])

        with pytest.raises(PermissionError):
            backend.update_entity("customer", alheio, {"city": "Invadida"}, actor=VENDEDOR)

    def test_altera_o_proprio_cliente(self, backend):
        meu = self._cliente_de(backend, VENDEDOR["full_name"])

        depois = backend.update_entity("customer", meu, {"city": "Curitiba"}, actor=VENDEDOR)
        assert depois["city"] == "Curitiba"

    def test_nao_apaga_cliente_de_outro(self, backend):
        alheio = self._cliente_de(backend, OUTRO["full_name"])

        with pytest.raises(PermissionError):
            backend.delete_entity("customer", alheio, actor=VENDEDOR)

    def test_admin_altera_qualquer_registro(self, backend):
        alheio = self._cliente_de(backend, OUTRO["full_name"])

        depois = backend.update_entity("customer", alheio, {"city": "Belo Horizonte"}, actor=ADMIN)
        assert depois["city"] == "Belo Horizonte"


class TestResponsaveisDisponiveis:
    def test_opcoes_de_responsavel_saem_apenas_de_contas(self, backend):
        """A lista da interface não pode ressuscitar donos sem conta.

        Ela somava os donos já gravados nos registros, então um nome sem conta
        virava opção selecionável — e novos registros nasciam invisíveis.
        """
        from pathlib import Path

        fonte = (Path(__file__).resolve().parent.parent / "crm_app.py").read_text(encoding="utf-8")
        trecho = fonte.split("owner_options = sorted(", 1)[1].split(")", 1)[0]

        assert "users_df" in trecho
        for proibido in ("customers_df", "tickets_df", "deals_df"):
            assert proibido not in trecho, (
                f"owner_options voltou a incluir {proibido}, o que recria donos sem conta"
            )
