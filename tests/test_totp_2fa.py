"""Testes da autenticação de dois fatores (TOTP), RFC 6238.

Cobrem: o algoritmo em si contra os vetores oficiais da RFC, o fluxo de
cadastro (segredo pendente -> confirmado), o login em duas etapas, os
códigos de backup de uso único e a exigência de senha para desativar.
"""

from __future__ import annotations

import base64
import importlib
import os
import sys


def _load_backend(tmp_path):
    os.environ["CRM_DATA_DIR"] = str(tmp_path / "data")
    os.environ["CRM_DB_PATH"] = str(tmp_path / "crm.sqlite3")
    if "crm_backend" in sys.modules:
        del sys.modules["crm_backend"]
    return importlib.import_module("crm_backend")


def test_totp_code_matches_rfc6238_vectors(tmp_path):
    """Vetores oficiais do Apêndice B da RFC 6238 (segredo SHA1 de 20 bytes).

    A RFC usa códigos de 8 dígitos; comparamos os 6 últimos porque a
    truncagem binária é idêntica, só muda o módulo final.
    """
    backend = _load_backend(tmp_path)
    secret_b32 = base64.b32encode(b"12345678901234567890").decode("ascii")

    assert backend._totp_code_at(secret_b32, 59) == "287082"
    assert backend._totp_code_at(secret_b32, 1111111109) == "081804"
    assert backend._totp_code_at(secret_b32, 1234567890) == "005924"


def test_verify_totp_rejects_wrong_code(tmp_path):
    backend = _load_backend(tmp_path)
    secret = backend._generate_totp_secret()
    assert backend._verify_totp(secret, "000000") is False
    assert backend._verify_totp(secret, "not-a-code") is False
    assert backend._verify_totp(secret, "") is False


def test_enrollment_flow_requires_valid_code(tmp_path, monkeypatch):
    monkeypatch.setenv("CRM_SEED_PASSWORD_ADMIN", "Senha-De-Deploy-2026")
    backend = _load_backend(tmp_path)
    backend.init_database()
    actor = {"username": "admin", "role": "admin"}

    assert backend.totp_is_enabled("admin") is False

    secret, uri = backend.start_totp_enrollment(actor)
    assert secret
    assert "otpauth://totp/" in uri
    assert secret in uri

    # Ativação pendente ainda não vale para login.
    assert backend.totp_is_enabled("admin") is False

    try:
        backend.confirm_totp_enrollment(actor, "000000")
        raised = False
    except ValueError:
        raised = True
    assert raised, "código errado não deveria confirmar a ativação"

    import time

    valid_code = backend._totp_code_at(secret, time.time())
    backup_codes = backend.confirm_totp_enrollment(actor, valid_code)

    assert len(backup_codes) == 8
    assert backend.totp_is_enabled("admin") is True


def test_login_two_step_with_totp_and_backup_codes(tmp_path, monkeypatch):
    monkeypatch.setenv("CRM_SEED_PASSWORD_ADMIN", "Senha-De-Deploy-2026")
    backend = _load_backend(tmp_path)
    backend.init_database()
    actor = {"username": "admin", "role": "admin"}

    import time

    secret, _ = backend.start_totp_enrollment(actor)
    code = backend._totp_code_at(secret, time.time())
    backup_codes = backend.confirm_totp_enrollment(actor, code)

    # Etapa 1: senha continua funcionando normalmente e não decide sozinha.
    user = backend.verify_login("admin", "Senha-De-Deploy-2026")
    assert user is not None
    assert backend.totp_is_enabled(user["username"]) is True

    # Etapa 2: código errado não entra.
    assert backend.verify_totp_login("admin", "000000") is False

    # Etapa 2: código certo entra.
    fresh_code = backend._totp_code_at(secret, time.time())
    assert backend.verify_totp_login("admin", fresh_code) is True

    # Código de backup funciona uma vez e depois é consumido.
    one_backup = backup_codes[0]
    assert backend.verify_totp_login("admin", one_backup) is True
    assert backend.verify_totp_login("admin", one_backup) is False


def test_disable_totp_requires_current_password(tmp_path, monkeypatch):
    monkeypatch.setenv("CRM_SEED_PASSWORD_ADMIN", "Senha-De-Deploy-2026")
    backend = _load_backend(tmp_path)
    backend.init_database()
    actor = {"username": "admin", "role": "admin"}

    import time

    secret, _ = backend.start_totp_enrollment(actor)
    code = backend._totp_code_at(secret, time.time())
    backend.confirm_totp_enrollment(actor, code)
    assert backend.totp_is_enabled("admin") is True

    try:
        backend.disable_totp(actor, "senha-errada")
        raised = False
    except ValueError:
        raised = True
    assert raised
    assert backend.totp_is_enabled("admin") is True

    backend.disable_totp(actor, "Senha-De-Deploy-2026")
    assert backend.totp_is_enabled("admin") is False
