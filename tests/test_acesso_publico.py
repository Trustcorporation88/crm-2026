"""Testes do endurecimento de acesso.

Contexto: o ambiente de produção (crm.trustcorp.com.br) servia botões de
"entrar com 1 clique" que autenticavam como administrador sem nenhuma
credencial, e as contas usavam as senhas padrão publicadas no repositório.
Qualquer visitante virava admin. Estes testes fixam o comportamento seguro.
"""

import importlib
import os
import sys

import pytest


@pytest.fixture
def backend(tmp_path):
    """Instância limpa do backend, com banco próprio e schema semeado."""
    os.environ["CRM_DATA_DIR"] = str(tmp_path / "data")
    os.environ["CRM_DB_PATH"] = str(tmp_path / "crm.sqlite3")
    for name in ["crm_backend"]:
        sys.modules.pop(name, None)
    module = importlib.import_module("crm_backend")
    module.init_database()
    return module


class TestGateDoLoginDeDemonstracao:
    """O acesso sem credencial só existe quando explicitamente habilitado."""

    def test_desligado_por_padrao(self, monkeypatch):
        monkeypatch.delenv("CRM_DEMO_LOGIN", raising=False)
        import crm_ux

        assert crm_ux.demo_login_enabled() is False

    @pytest.mark.parametrize("valor", ["1", "true", "TRUE", " yes ", "on"])
    def test_liga_com_valores_afirmativos(self, monkeypatch, valor):
        monkeypatch.setenv("CRM_DEMO_LOGIN", valor)
        import crm_ux

        assert crm_ux.demo_login_enabled() is True

    @pytest.mark.parametrize("valor", ["0", "false", "no", "", "talvez"])
    def test_permanece_desligado_com_qualquer_outro_valor(self, monkeypatch, valor):
        monkeypatch.setenv("CRM_DEMO_LOGIN", valor)
        import crm_ux

        assert crm_ux.demo_login_enabled() is False


def _forcar_senha_fraca(backend, username: str, senha: str) -> None:
    """Grava direto no banco uma senha fraca, simulando instalação legada.

    Instalações criadas antes do endurecimento nasceram com admin/admin123 e
    continuam assim até alguém trocar. É esse estado que a detecção precisa
    enxergar — e ele não é mais produzido pelo seed, então o teste o constrói.
    """
    hash_fraco = backend.hash_password(senha)
    with backend._connect() as connection:
        connection.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (hash_fraco, username),
        )
        connection.commit()


class TestSenhaPadrao:
    """Senha padrão publicada é acesso aberto — precisa ser detectada."""

    def test_instalacao_nova_nao_nasce_com_senha_publica(self, backend):
        """A correção em si: seed novo não pode cair numa senha conhecida."""
        assert backend.uses_default_password("admin") is False
        assert backend.accounts_with_default_password() == []

    def test_instalacao_legada_e_sinalizada(self, backend):
        _forcar_senha_fraca(backend, "admin", "admin123")
        _forcar_senha_fraca(backend, "vendas", "vendas123")

        assert backend.uses_default_password("admin") is True
        sinalizadas = backend.accounts_with_default_password()
        assert "admin" in sinalizadas
        assert "vendas" in sinalizadas

    def test_trocar_a_senha_remove_do_alerta(self, backend):
        _forcar_senha_fraca(backend, "admin", "admin123")
        _forcar_senha_fraca(backend, "vendas", "vendas123")

        backend.change_own_password(
            {"username": "admin", "role": "admin"},
            "admin123",
            "Senha-Muito-Mais-Forte-2026",
        )

        assert backend.uses_default_password("admin") is False
        assert "admin" not in backend.accounts_with_default_password()
        # As demais contas continuam sinalizadas.
        assert "vendas" in backend.accounts_with_default_password()

    def test_usuario_inexistente_nao_quebra(self, backend):
        assert backend.uses_default_password("fantasma") is False


class TestSenhaSemente:
    """Instalação nova deve poder nascer sem a senha padrão pública."""

    def test_ambiente_sobrescreve_a_senha_inicial(self, backend, monkeypatch):
        monkeypatch.setenv("CRM_SEED_PASSWORD_ADMIN", "definida-no-deploy")
        assert backend.seed_password_for("admin") == "definida-no-deploy"

    def test_sem_variavel_gera_senha_aleatoria(self, backend, monkeypatch):
        """Sem variável definida, a senha inicial não pode ser previsível.

        Antes esta função devolvia "admin123", e o teste anterior fixava esse
        retorno — ou seja, protegia a vulnerabilidade contra correção.
        """
        monkeypatch.delenv("CRM_SEED_PASSWORD_ADMIN", raising=False)
        backend._GENERATED_SEED_PASSWORDS.clear()

        senha = backend.seed_password_for("admin")

        assert senha not in backend.KNOWN_WEAK_SEED_PASSWORDS.values()
        assert len(senha) >= 20
        # Estável dentro do mesmo processo: caso contrário o hash gravado no
        # seed não corresponderia à senha informada ao operador no log.
        assert backend.seed_password_for("admin") == senha

    def test_senhas_geradas_diferem_entre_contas(self, backend, monkeypatch):
        for conta in ("admin", "vendas"):
            monkeypatch.delenv(f"CRM_SEED_PASSWORD_{conta.upper()}", raising=False)
        backend._GENERATED_SEED_PASSWORDS.clear()

        assert backend.seed_password_for("admin") != backend.seed_password_for("vendas")
