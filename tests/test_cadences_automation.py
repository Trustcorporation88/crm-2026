"""Testes de integração das jornadas automáticas contra o backend real.

nurture_rules.py é lógica pura (coberta em test_nurture_rules.py); aqui o
que importa é a ponte com o banco: get_active_enrollment_keys() reconhece
matrícula em andamento, e enroll_proposals() não duplica quem já está
inscrito, nem entre chamadas nem dentro do mesmo lote.
"""

from __future__ import annotations

import importlib
import os
import sys


def _load(tmp_path, monkeypatch):
    monkeypatch.setenv("CRM_SEED_PASSWORD_ADMIN", "Senha-De-Deploy-2026")
    os.environ["CRM_DATA_DIR"] = str(tmp_path / "data")
    os.environ["CRM_DB_PATH"] = str(tmp_path / "crm.sqlite3")
    for mod in ("crm_backend", "cadences", "nurture_rules"):
        if mod in sys.modules:
            del sys.modules[mod]
    backend = importlib.import_module("crm_backend")
    backend.init_database()
    cadences = importlib.import_module("cadences")
    cadences.init_cadences_schema()
    return backend, cadences


def _seed_customer(backend, cid="C-NEW-1", name="Cliente Teste"):
    with backend._connect() as c:
        c.execute(
            """INSERT INTO customers (customer_id, name, segment, city, country, owner, status,
               health_score, lifetime_value, last_purchase, channel, next_action, source)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (cid, name, "SaaS", "Sao Paulo", "Brasil", "Rafael", "Novo", 70, 10000, "2026-01-01",
             "WhatsApp", "", "manual"),
        )
        c.commit()


def test_get_active_enrollment_keys_vazio_no_inicio(tmp_path, monkeypatch):
    backend, cadences = _load(tmp_path, monkeypatch)
    assert cadences.get_active_enrollment_keys() == set()


def test_enroll_marca_como_ativo(tmp_path, monkeypatch):
    backend, cadences = _load(tmp_path, monkeypatch)
    _seed_customer(backend)
    cadences.enroll("new_lead_outbound", "C-NEW-1", "Rafael")
    assert ("C-NEW-1", "new_lead_outbound") in cadences.get_active_enrollment_keys()


def test_enroll_proposals_nao_duplica_quem_ja_esta_inscrito(tmp_path, monkeypatch):
    backend, cadences = _load(tmp_path, monkeypatch)
    _seed_customer(backend)
    cadences.enroll("new_lead_outbound", "C-NEW-1", "Rafael")

    from nurture_rules import ProposedEnrollment

    proposta = ProposedEnrollment(
        rule="lead_novo_sem_jornada", cadence_key="new_lead_outbound",
        cadence_title="Novo lead", customer_id="C-NEW-1", customer_name="Cliente Teste",
        deal_id=None, owner="Rafael", reason="teste",
    )
    resultado = cadences.enroll_proposals([proposta])
    assert resultado["created"] == []
    assert len(resultado["skipped"]) == 1


def test_enroll_proposals_nao_duplica_dentro_do_mesmo_lote(tmp_path, monkeypatch):
    backend, cadences = _load(tmp_path, monkeypatch)
    _seed_customer(backend)

    from nurture_rules import ProposedEnrollment

    proposta = ProposedEnrollment(
        rule="lead_novo_sem_jornada", cadence_key="new_lead_outbound",
        cadence_title="Novo lead", customer_id="C-NEW-1", customer_name="Cliente Teste",
        deal_id=None, owner="Rafael", reason="teste",
    )
    resultado = cadences.enroll_proposals([proposta, proposta])
    assert len(resultado["created"]) == 1
    assert len(resultado["skipped"]) == 1


def test_enroll_proposals_cria_quando_ninguem_esta_inscrito(tmp_path, monkeypatch):
    backend, cadences = _load(tmp_path, monkeypatch)
    _seed_customer(backend)

    from nurture_rules import ProposedEnrollment

    proposta = ProposedEnrollment(
        rule="lead_novo_sem_jornada", cadence_key="new_lead_outbound",
        cadence_title="Novo lead", customer_id="C-NEW-1", customer_name="Cliente Teste",
        deal_id=None, owner="Rafael", reason="teste",
    )
    resultado = cadences.enroll_proposals([proposta])
    assert len(resultado["created"]) == 1
    assert resultado["skipped"] == []


def test_get_cadence_titles_traz_titulos_das_cadencias_padrao(tmp_path, monkeypatch):
    backend, cadences = _load(tmp_path, monkeypatch)
    titles = cadences.get_cadence_titles()
    assert titles["new_lead_outbound"] == "Novo lead - 5 toques em 14d"
    assert titles["win_back"] == "Reativacao inativo"
