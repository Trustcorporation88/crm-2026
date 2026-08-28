"""Testes da preferência de relatório configurável da Visão Executiva."""

from __future__ import annotations

import importlib
import os
import sys


def _load_backend(tmp_path):
    os.environ["CRM_DATA_DIR"] = str(tmp_path / "data")
    os.environ["CRM_DB_PATH"] = str(tmp_path / "crm.sqlite3")
    if "crm_backend" in sys.modules:
        del sys.modules["crm_backend"]
    return importlib.import_module("crm_backend")


def test_default_config_when_nothing_saved(tmp_path, monkeypatch):
    monkeypatch.setenv("CRM_SEED_PASSWORD_ADMIN", "Senha-De-Deploy-2026")
    backend = _load_backend(tmp_path)
    backend.init_database()

    config = backend.get_exec_report_config("admin")
    assert config["kpis"] == backend.EXEC_REPORT_DEFAULT_KPIS
    assert config["group_by"] == backend.EXEC_REPORT_DEFAULT_GROUP_BY


def test_set_and_get_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("CRM_SEED_PASSWORD_ADMIN", "Senha-De-Deploy-2026")
    backend = _load_backend(tmp_path)
    backend.init_database()
    actor = {"username": "admin", "role": "admin"}

    backend.set_exec_report_config(actor, ["csat_medio", "sla_risco", "receita_ganha"], "channel")
    config = backend.get_exec_report_config("admin")
    assert config["kpis"] == ["csat_medio", "sla_risco", "receita_ganha"]
    assert config["group_by"] == "channel"


def test_get_falls_back_to_default_on_corrupt_json(tmp_path, monkeypatch):
    monkeypatch.setenv("CRM_SEED_PASSWORD_ADMIN", "Senha-De-Deploy-2026")
    backend = _load_backend(tmp_path)
    backend.init_database()

    with backend._connect() as connection:
        connection.execute(
            "UPDATE users SET exec_report_config = ? WHERE username = ?",
            ("{isso nao e json valido", "admin"),
        )
        connection.commit()

    config = backend.get_exec_report_config("admin")
    assert config["kpis"] == backend.EXEC_REPORT_DEFAULT_KPIS
    assert config["group_by"] == backend.EXEC_REPORT_DEFAULT_GROUP_BY


def test_get_falls_back_to_default_when_kpis_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("CRM_SEED_PASSWORD_ADMIN", "Senha-De-Deploy-2026")
    backend = _load_backend(tmp_path)
    backend.init_database()
    actor = {"username": "admin", "role": "admin"}

    # Uma preferência salva sem nenhum KPI escolhido não deve deixar o painel
    # vazio — cai de volta no recorte padrão.
    backend.set_exec_report_config(actor, [], "owner")
    config = backend.get_exec_report_config("admin")
    assert config["kpis"] == backend.EXEC_REPORT_DEFAULT_KPIS


def test_set_requires_username(tmp_path, monkeypatch):
    monkeypatch.setenv("CRM_SEED_PASSWORD_ADMIN", "Senha-De-Deploy-2026")
    backend = _load_backend(tmp_path)
    backend.init_database()

    try:
        backend.set_exec_report_config({"username": ""}, ["clientes"], "owner")
        raised = False
    except ValueError:
        raised = True
    assert raised
