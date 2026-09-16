"""Testes do agente de pesquisa de lead (lead_research.py).

O que importa validar: o agente nunca inventa fato (só aceita o que a IA
citou com fonte válida), grava toda rodada (mesmo sem achar nada), e o
webhook do Instagram cria lead + dispara pesquisa em segundo plano.
"""

from __future__ import annotations

import importlib
import os
import sys

import pytest


def _load(tmp_path, monkeypatch):
    monkeypatch.setenv("CRM_SEED_PASSWORD_ADMIN", "Senha-De-Deploy-2026")
    os.environ["CRM_DATA_DIR"] = str(tmp_path / "data")
    os.environ["CRM_DB_PATH"] = str(tmp_path / "crm.sqlite3")
    monkeypatch.setenv("SERPER_API_KEY", "chave-de-teste-serper")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "chave-de-teste-deepseek")
    for mod in ("crm_backend", "lead_research", "deepseek_assistant"):
        if mod in sys.modules:
            del sys.modules[mod]
    backend = importlib.import_module("crm_backend")
    backend.init_database()
    lead_research = importlib.import_module("lead_research")
    return backend, lead_research


def _seed_customer(backend, cid="C-LEAD-1", name="Cyntia Rinaldi"):
    with backend._connect() as c:
        c.execute(
            """INSERT INTO customers (customer_id, name, segment, city, country, owner, status,
               health_score, lifetime_value, last_purchase, channel, next_action, source)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (cid, name, "Doces", "Bauru", "Brasil", "Amanda Souza", "Novo", 70, 0, "2026-01-01",
             "Instagram", "", "instagram-webhook"),
        )
        c.commit()
    return cid


SEARCH_RESULTS = [
    {"title": "Cyntia Rinaldi Doces - Instagram", "link": "https://instagram.com/cyntiarinaldidoces", "snippet": "Doces artesanais em Bauru/SP."},
    {"title": "Página aleatória", "link": "https://example.com/x", "snippet": "Nada relacionado."},
]


def test_research_lead_grava_fatos_confirmados(tmp_path, monkeypatch):
    backend, lead_research = _load(tmp_path, monkeypatch)
    cid = _seed_customer(backend)

    monkeypatch.setattr(lead_research, "serper_search", lambda query, num=8: (SEARCH_RESULTS, None))
    monkeypatch.setattr(
        lead_research,
        "chat_completion",
        lambda *a, **k: (
            '{"facts": [{"fact": "Vende doces artesanais em Bauru/SP", "source_index": 1}]}',
            None,
        ),
    )

    resultado = lead_research.research_lead(cid, name="Cyntia Rinaldi")

    assert resultado["status"] == "com_fatos"
    assert len(resultado["facts"]) == 1
    assert resultado["facts"][0]["source_url"] == "https://instagram.com/cyntiarinaldidoces"

    historico = backend.get_lead_research_history(cid)
    assert len(historico) == 1
    assert historico[0]["status"] == "com_fatos"
    assert historico[0]["facts_count"] == 1


def test_research_lead_ignora_fato_sem_indice_de_fonte_valido(tmp_path, monkeypatch):
    """A IA citando um source_index fora do intervalo não pode virar fato gravado — proteção contra alucinação de fonte."""
    backend, lead_research = _load(tmp_path, monkeypatch)
    cid = _seed_customer(backend)

    monkeypatch.setattr(lead_research, "serper_search", lambda query, num=8: (SEARCH_RESULTS, None))
    monkeypatch.setattr(
        lead_research,
        "chat_completion",
        lambda *a, **k: (
            '{"facts": [{"fact": "Fato com fonte inventada", "source_index": 99}]}',
            None,
        ),
    )

    resultado = lead_research.research_lead(cid, name="Cyntia Rinaldi")

    assert resultado["status"] == "sem_fatos"
    assert resultado["facts"] == []


def test_research_lead_sem_resultados_de_busca_nao_inventa_nada(tmp_path, monkeypatch):
    backend, lead_research = _load(tmp_path, monkeypatch)
    cid = _seed_customer(backend)

    monkeypatch.setattr(lead_research, "serper_search", lambda query, num=8: ([], None))

    resultado = lead_research.research_lead(cid, name="Alguém Sem Rastro Público")

    assert resultado["status"] == "sem_fatos"
    assert resultado["facts"] == []
    historico = backend.get_lead_research_history(cid)
    assert historico[0]["status"] == "sem_fatos"


def test_research_lead_sem_serper_configurada_registra_erro(tmp_path, monkeypatch):
    backend, lead_research = _load(tmp_path, monkeypatch)
    cid = _seed_customer(backend)
    monkeypatch.delenv("SERPER_API_KEY", raising=False)

    resultado = lead_research.research_lead(cid, name="Cyntia Rinaldi")

    assert resultado["status"] == "erro"
    assert "SERPER_API_KEY" in resultado["error"]


def test_research_lead_json_invalido_da_ia_registra_erro_sem_gravar_fato(tmp_path, monkeypatch):
    backend, lead_research = _load(tmp_path, monkeypatch)
    cid = _seed_customer(backend)

    monkeypatch.setattr(lead_research, "serper_search", lambda query, num=8: (SEARCH_RESULTS, None))
    monkeypatch.setattr(lead_research, "chat_completion", lambda *a, **k: ("isto não é json", None))

    resultado = lead_research.research_lead(cid, name="Cyntia Rinaldi")

    assert resultado["status"] == "erro"
    assert resultado["facts"] == []


def test_process_instagram_webhook_cria_lead_a_partir_de_dm(tmp_path, monkeypatch):
    backend, _lead_research = _load(tmp_path, monkeypatch)

    payload = {
        "entry": [
            {
                "messaging": [
                    {
                        "sender": {"id": "1234567890"},
                        "timestamp": 1735689600,
                        "message": {"mid": "mid.abc", "text": "Oi, quero saber sobre os doces!"},
                    }
                ]
            }
        ]
    }

    resultado = backend.process_instagram_webhook(payload)

    assert resultado["status"] == "processed"
    assert len(resultado["processed"]) == 1
    customer_id = resultado["processed"][0]["customer_id"]

    with backend._connect() as c:
        row = c.execute(
            "SELECT name, channel FROM customers WHERE customer_id = ?", (customer_id,)
        ).fetchone()
    assert row["channel"] == "Instagram"


def test_process_instagram_webhook_cria_lead_a_partir_de_comentario(tmp_path, monkeypatch):
    backend, _lead_research = _load(tmp_path, monkeypatch)

    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": "comment-1",
                            "text": "Quanto custa a caixa de brigadeiro?",
                            "from": {"id": "999", "username": "cliente_interessada"},
                        },
                    }
                ]
            }
        ]
    }

    resultado = backend.process_instagram_webhook(payload)

    assert resultado["status"] == "processed"
    assert resultado["processed"][0]["handle"] == "cliente_interessada"


def test_process_instagram_webhook_ignora_eco_da_propria_conta(tmp_path, monkeypatch):
    backend, _lead_research = _load(tmp_path, monkeypatch)

    payload = {
        "entry": [
            {
                "messaging": [
                    {
                        "sender": {"id": "self"},
                        "message": {"mid": "mid.echo", "text": "Resposta enviada por nós", "is_echo": True},
                    }
                ]
            }
        ]
    }

    resultado = backend.process_instagram_webhook(payload)

    assert resultado["status"] == "ignored"
    assert resultado["processed"] == []


def test_process_instagram_webhook_payload_sem_eventos(tmp_path, monkeypatch):
    backend, _lead_research = _load(tmp_path, monkeypatch)
    resultado = backend.process_instagram_webhook({"entry": []})
    assert resultado["status"] == "ignored"


def test_verify_instagram_webhook_hmac(tmp_path, monkeypatch):
    import hashlib
    import hmac as hmac_module

    backend, _lead_research = _load(tmp_path, monkeypatch)
    monkeypatch.setenv("CRM_INSTAGRAM_APP_SECRET", "segredo-de-teste")

    body = b'{"entry": []}'
    assinatura = "sha256=" + hmac_module.new(b"segredo-de-teste", body, hashlib.sha256).hexdigest()

    assert backend.verify_instagram_webhook_hmac(body, assinatura) is True
    assert backend.verify_instagram_webhook_hmac(body, "sha256=assinatura-errada") is False
    assert backend.verify_instagram_webhook_hmac(body, None) is False


def test_schema_sem_comando_vazio():
    """Nenhum comando do schema pode virar 'query vazia' no Postgres.

    split_script() quebra o script em todo ponto e vírgula e não entende
    comentário SQL. Um ponto e vírgula dentro de um comentário gera um
    "comando" que é só comentário: o SQLite ignora, mas o psycopg2 recusa
    com "can't execute an empty query" e derruba init_database() inteiro.

    Este teste roda sem Postgres e cobre o schema todo, não só as tabelas
    do agente de pesquisa.
    """
    import inspect
    import re

    import crm_backend
    import crm_db

    fonte = inspect.getsource(crm_backend._create_schema)
    bloco = re.search(r'executescript\(\s*"""(.*?)"""', fonte, re.S)
    assert bloco, "nao encontrei o script DDL em _create_schema"

    vazios = []
    for comando in crm_db.split_script(bloco.group(1)):
        sql = "\n".join(
            linha
            for linha in comando.split("\n")
            if not linha.strip().startswith("--")
        ).strip()
        if not sql:
            vazios.append(comando.strip()[:120])

    assert not vazios, (
        "comando(s) do schema sem SQL, so comentario. Provavel ponto e virgula "
        f"dentro de comentario: {vazios}"
    )
