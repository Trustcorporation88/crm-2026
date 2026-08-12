"""Gestão de contas de acesso e posse ligada ao login.

Duas lacunas foram fechadas juntas, porque uma dependia da outra.

**Não havia como criar uma conta.** As contas nasciam uma única vez, no seed,
quando o banco era criado do zero. Não existia décima conta possível, e quem
perdia a senha não tinha para onde recorrer.

**A posse dos registros era ligada pelo nome completo.** Assim que existisse
uma tela de edição, renomear alguém desligaria a pessoa dos próprios registros
— um efeito colateral invisível, que só apareceria quando o usuário reclamasse
que "sumiram meus clientes". Por isso a posse passou a ser ligada ao login,
que não muda.
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


# ---------------------------------------------------------------------------
# O motivo de tudo: renomear não pode tirar acesso
# ---------------------------------------------------------------------------

class TestRenomearPreservaAcesso:
    def test_pessoa_continua_vendo_seus_registros_apos_renomear(self, backend):
        backend.create_user("joao", "Joao Pereira", "vendas", "senha-forte-123", actor=ADMIN)
        joao = {"username": "joao", "full_name": "Joao Pereira", "role": "vendas"}

        backend.add_customer(
            {
                "name": "Cliente do Joao", "segment": "SMB", "city": "Recife",
                "country": "Brasil", "owner": "Joao Pereira",
            },
            actor=ADMIN,
        )

        antes = len(backend.aplicar_visibilidade(backend.get_data(), joao)["customers"])
        assert antes == 1

        backend.update_user("joao", full_name="João Pereira da Silva", actor=ADMIN)

        joao_renomeado = dict(joao, full_name="João Pereira da Silva")
        depois = len(
            backend.aplicar_visibilidade(backend.get_data(), joao_renomeado)["customers"]
        )
        assert depois == antes, "renomear a pessoa desligou-a dos próprios registros"

    def test_rotulo_exibido_acompanha_o_novo_nome(self, backend):
        """A chave não muda, mas o que aparece na tela precisa mudar."""
        backend.create_user("ana", "Ana Lima", "vendas", "senha-forte-123", actor=ADMIN)
        cid = backend.add_customer(
            {
                "name": "Cliente da Ana", "segment": "SMB", "city": "Recife",
                "country": "Brasil", "owner": "Ana Lima",
            },
            actor=ADMIN,
        )

        backend.update_user("ana", full_name="Ana Lima Souza", actor=ADMIN)

        with backend._connect() as c:
            linha = c.execute(
                "SELECT owner, owner_username FROM customers WHERE customer_id = ?", (cid,)
            ).fetchone()

        assert linha["owner"] == "Ana Lima Souza", "a tela mostraria o nome antigo"
        assert linha["owner_username"] == "ana", "a chave de acesso não deveria mudar"


class TestColunasDePosseNaoDivergem:
    """O preço de manter rótulo e chave separados é o risco de divergirem."""

    def test_nenhum_registro_semeado_tem_chave_vazia(self, backend):
        with backend._connect() as c:
            for tabela in backend.TABELAS_COM_DONO:
                vazios = c.execute(
                    f"SELECT COUNT(*) AS t FROM {tabela} "
                    "WHERE owner <> '' AND owner IS NOT NULL AND owner_username = ''"
                ).fetchone()["t"]
                assert vazios == 0, f"{tabela}: {vazios} registro(s) sem chave de posse"

    def test_rotulo_e_chave_apontam_para_a_mesma_pessoa(self, backend):
        """Varre o banco exigindo que as duas colunas concordem."""
        with backend._connect() as c:
            contas = {
                r["username"]: r["full_name"]
                for r in c.execute("SELECT username, full_name FROM users").fetchall()
            }
            divergentes = []
            for tabela in backend.TABELAS_COM_DONO:
                for linha in c.execute(
                    f"SELECT owner, owner_username FROM {tabela} WHERE owner_username <> ''"
                ).fetchall():
                    esperado = contas.get(linha["owner_username"])
                    if esperado != linha["owner"]:
                        divergentes.append((tabela, linha["owner"], linha["owner_username"]))

        assert not divergentes, f"rótulo e chave discordam: {divergentes}"

    def test_criar_registro_preenche_as_duas_colunas(self, backend):
        cid = backend.add_customer(
            {
                "name": "Novo", "segment": "SMB", "city": "Recife",
                "country": "Brasil", "owner": "Rafael Nogueira",
            },
            actor=ADMIN,
        )
        with backend._connect() as c:
            linha = c.execute(
                "SELECT owner, owner_username FROM customers WHERE customer_id = ?", (cid,)
            ).fetchone()

        assert linha["owner"] == "Rafael Nogueira"
        assert linha["owner_username"] == "vendas"

    def test_responsavel_inexistente_e_recusado(self, backend):
        """Registro sem dono identificável fica invisível para todos."""
        with pytest.raises(ValueError, match="não corresponde a nenhuma conta"):
            backend.add_customer(
                {
                    "name": "Órfão", "segment": "SMB", "city": "Recife",
                    "country": "Brasil", "owner": "Fantasma Silva",
                },
                actor=ADMIN,
            )

    def test_trocar_responsavel_move_as_duas_colunas(self, backend):
        cid = backend.add_customer(
            {
                "name": "Vai Trocar", "segment": "SMB", "city": "Recife",
                "country": "Brasil", "owner": "Rafael Nogueira",
            },
            actor=ADMIN,
        )
        backend.update_entity("customer", cid, {"owner": "Camila Costa"}, actor=ADMIN)

        with backend._connect() as c:
            linha = c.execute(
                "SELECT owner, owner_username FROM customers WHERE customer_id = ?", (cid,)
            ).fetchone()

        assert linha["owner"] == "Camila Costa"
        assert linha["owner_username"] == "cs"


# ---------------------------------------------------------------------------
# Criação de contas
# ---------------------------------------------------------------------------

class TestCriarConta:
    def test_conta_criada_consegue_entrar(self, backend):
        backend.create_user("maria", "Maria Souza", "atendimento", "senha-forte-123", actor=ADMIN)

        assert backend.verify_login("maria", "senha-forte-123") is not None

    def test_login_e_normalizado(self, backend):
        criado = backend.create_user(
            "  PEDRO  ", "Pedro Alves", "vendas", "senha-forte-123", actor=ADMIN
        )
        assert criado["username"] == "pedro"

    @pytest.mark.parametrize(
        "login", ["joão", "com espaço", "com@arroba", "", "x" * 41]
    )
    def test_login_invalido_e_recusado(self, backend, login):
        """O login circula em cabeçalho HTTP e em nome de variável de ambiente."""
        with pytest.raises(ValueError):
            backend.create_user(login, "Alguem", "vendas", "senha-forte-123", actor=ADMIN)

    def test_login_duplicado_e_recusado(self, backend):
        with pytest.raises(ValueError, match="já existe|Já existe"):
            backend.create_user("admin", "Outro Admin", "admin", "senha-forte-123", actor=ADMIN)

    def test_nome_duplicado_e_recusado(self, backend):
        """O nome é o rótulo do responsável — duplicado tornaria ambíguo."""
        with pytest.raises(ValueError, match="nome"):
            backend.create_user(
                "outro", "Rafael Nogueira", "vendas", "senha-forte-123", actor=ADMIN
            )

    def test_senha_curta_e_recusada(self, backend):
        with pytest.raises(ValueError, match="8 caracteres"):
            backend.create_user("curta", "Senha Curta", "vendas", "1234", actor=ADMIN)

    def test_papel_desconhecido_e_recusado(self, backend):
        with pytest.raises(ValueError, match="Papel desconhecido"):
            backend.create_user("x", "Fulano X", "diretoria", "senha-forte-123", actor=ADMIN)

    def test_nao_admin_nao_cria_conta(self, backend):
        with pytest.raises(PermissionError):
            backend.create_user("y", "Fulano Y", "vendas", "senha-forte-123", actor=VENDEDOR)

    def test_criacao_fica_registrada_na_auditoria(self, backend):
        backend.create_user("auditado", "Conta Auditada", "vendas", "senha-forte-123", actor=ADMIN)

        with backend._connect() as c:
            evento = c.execute(
                "SELECT action, entity_id FROM audit_log WHERE action = 'user.create' "
                "ORDER BY id DESC LIMIT 1"
            ).fetchone()

        assert evento is not None and evento["entity_id"] == "auditado"


# ---------------------------------------------------------------------------
# Edição
# ---------------------------------------------------------------------------

class TestEditarConta:
    def test_desativar_impede_o_login(self, backend):
        backend.create_user("temp", "Conta Temporaria", "vendas", "senha-forte-123", actor=ADMIN)
        assert backend.verify_login("temp", "senha-forte-123") is not None

        backend.update_user("temp", is_active=False, actor=ADMIN)

        assert backend.verify_login("temp", "senha-forte-123") is None

    def test_mudar_papel_muda_as_permissoes(self, backend):
        backend.create_user("promovido", "Vai Subir", "vendas", "senha-forte-123", actor=ADMIN)
        backend.update_user("promovido", role="admin", actor=ADMIN)

        assert backend.get_user_by_username("promovido")["role"] == "admin"

    def test_conta_inexistente_falha_claramente(self, backend):
        with pytest.raises(ValueError, match="não encontrada"):
            backend.update_user("fantasma", role="vendas", actor=ADMIN)

    def test_nao_admin_nao_edita(self, backend):
        with pytest.raises(PermissionError):
            backend.update_user("admin", role="vendas", actor=VENDEDOR)


class TestTravaDoUltimoAdmin:
    """Sem esta trava, um clique deixa o sistema sem quem gerencie contas.

    E não há como voltar pela interface: só administrador acessa o painel.
    """

    def test_nao_rebaixa_o_ultimo_admin(self, backend):
        with pytest.raises(ValueError, match="última conta de administrador"):
            backend.update_user("admin", role="vendas", actor=ADMIN)

    def test_nao_desativa_o_ultimo_admin(self, backend):
        with pytest.raises(ValueError, match="última conta de administrador"):
            backend.update_user("admin", is_active=False, actor=ADMIN)

    def test_com_outro_admin_a_troca_e_permitida(self, backend):
        backend.create_user("admin2", "Segundo Admin", "admin", "senha-forte-123", actor=ADMIN)

        backend.update_user("admin", role="vendas", actor=ADMIN)

        assert backend.get_user_by_username("admin")["role"] == "vendas"


# ---------------------------------------------------------------------------
# Redefinição de senha
# ---------------------------------------------------------------------------

class TestRedefinirSenha:
    def test_senha_nova_vale_e_a_antiga_nao(self, backend):
        backend.create_user("esquecido", "Esqueci Minha", "vendas", "senha-antiga-1", actor=ADMIN)

        backend.reset_user_password("esquecido", "senha-nova-999", actor=ADMIN)

        assert backend.verify_login("esquecido", "senha-nova-999") is not None
        assert backend.verify_login("esquecido", "senha-antiga-1") is None

    def test_nao_exige_a_senha_atual(self, backend):
        """É justamente o caso de quem não sabe mais a senha."""
        backend.create_user("perdido", "Perdi A Senha", "vendas", "sei-la-qual-1", actor=ADMIN)

        backend.reset_user_password("perdido", "definida-pelo-admin", actor=ADMIN)

        assert backend.verify_login("perdido", "definida-pelo-admin") is not None

    def test_senha_curta_e_recusada(self, backend):
        with pytest.raises(ValueError, match="8 caracteres"):
            backend.reset_user_password("admin", "123", actor=ADMIN)

    def test_nao_admin_nao_redefine(self, backend):
        with pytest.raises(PermissionError):
            backend.reset_user_password("admin", "senha-invasor-1", actor=VENDEDOR)

    def test_fica_registrada_na_auditoria(self, backend):
        backend.reset_user_password("vendas", "senha-nova-123", actor=ADMIN)

        with backend._connect() as c:
            evento = c.execute(
                "SELECT entity_id FROM audit_log WHERE action = 'user.password_reset' "
                "ORDER BY id DESC LIMIT 1"
            ).fetchone()

        assert evento is not None and evento["entity_id"] == "vendas"


class TestListagem:
    def test_lista_todas_as_contas(self, backend):
        contas = backend.list_users()

        assert contas
        assert {"username", "full_name", "role", "is_active"} <= set(contas[0])

    def test_conta_nova_aparece_na_lista(self, backend):
        backend.create_user("novata", "Conta Novata", "vendas", "senha-forte-123", actor=ADMIN)

        assert any(c["username"] == "novata" for c in backend.list_users())
