"""Throttle da tela de login do Streamlit.

O backend sempre teve throttle progressivo com bloqueio temporário, mas ele
estava ligado apenas no serviço de webhook (`/api/auth/token`). A tela de
login — o caminho realmente exposto ao público — chamava `verify_login()`
direto, sem contabilizar tentativa alguma. Dava para varrer senhas à vontade.

Estes testes exercitam o formulário de verdade, via AppTest, e falham se
alguém desfizer a ligação.
"""

import os
import pathlib
import tempfile

import pytest

_TMP = pathlib.Path(tempfile.mkdtemp(prefix="crm-login-throttle-"))
os.environ.setdefault("CRM_DATA_DIR", str(_TMP))
# Limiar baixo para o teste não precisar de dezenas de submissões.
os.environ["CRM_AUTH_LOCK_THRESHOLD"] = "3"
os.environ["CRM_AUTH_LOCK_SECONDS"] = "300"
os.environ["CRM_AUTH_RATE_LIMIT_MAX_ATTEMPTS"] = "50"

from streamlit.testing.v1 import AppTest  # noqa: E402

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "crm_app.py")

USUARIO = "admin"
SENHA_ERRADA = "senha-errada-de-proposito"


def _tentar_login(usuario: str, senha: str) -> AppTest:
    app = AppTest.from_file(APP_PATH, default_timeout=60)
    app.run()

    # O formulário tem um campo de usuário e um de senha, nesta ordem.
    campos = app.text_input
    campos[0].set_value(usuario)
    campos[1].set_value(senha)
    app.button[0].click()
    return app.run()


def _mensagens_de_erro(app: AppTest) -> str:
    return " | ".join(str(item.value) for item in app.error)


class TestThrottleDoLogin:
    def test_credencial_invalida_mostra_erro(self):
        app = _tentar_login(USUARIO, SENHA_ERRADA)
        assert "Credenciais inválidas." in _mensagens_de_erro(app)

    def test_tentativas_repetidas_acabam_bloqueadas(self):
        """Depois do limiar, a resposta muda de 'inválidas' para bloqueio."""
        import crm_backend

        # Assunto isolado para este teste, evitando interferência de outros.
        usuario = "usuario-bruteforce"
        crm_backend.init_database()

        bloqueou = False
        for _ in range(8):
            app = _tentar_login(usuario, SENHA_ERRADA)
            texto = _mensagens_de_erro(app)
            if "locked" in texto.lower() or "bloque" in texto.lower():
                bloqueou = True
                break

        assert bloqueou, (
            "o login aceitou repetidas tentativas sem nunca bloquear — "
            "o throttle do backend não está ligado na tela de login"
        )

    def test_registro_de_throttle_e_criado(self):
        """A tentativa precisa aparecer em auth_throttle, não só na tela."""
        import crm_backend

        usuario = "usuario-registrado"
        crm_backend.init_database()
        _tentar_login(usuario, SENHA_ERRADA)

        with crm_backend._connect() as connection:
            linhas = connection.execute(
                "SELECT subject, endpoint, fail_count FROM auth_throttle WHERE endpoint = ?",
                ("streamlit/login",),
            ).fetchall()

        assert linhas, "nenhuma tentativa foi contabilizada em auth_throttle"


class TestSubjectDoThrottle:
    """A função vive em crm_ux porque crm_app só importa sob o Streamlit."""

    def test_normaliza_usuario(self):
        import crm_ux

        assert crm_ux.login_throttle_subject("  Admin  ") == "user:admin"

    def test_campo_vazio_ainda_e_contabilizado(self):
        import crm_ux

        # Rajada de submissões em branco também precisa consumir tentativa,
        # senão vira um caminho livre de volume contra o banco.
        assert crm_ux.login_throttle_subject("") == "user:<vazio>"
        assert crm_ux.login_throttle_subject(None) == "user:<vazio>"
