"""Regressões da Fase 1 do endurecimento.

Cada teste aqui corresponde a um defeito que estava em produção e que passava
despercebido justamente por não ter cobertura. O objetivo não é aumentar
contagem de testes: é impedir que estes comportamentos específicos voltem.

Defeitos cobertos:

1. `PUT /api/customers/{id}` respondia 200 sem gravar nada no banco.
2. `DELETE /api/customers/{id}` respondia 200 sem remover nada.
3. Endpoints sem implementação (`backup`, `export`, `connect`) respondiam 200
   com corpo sintético, levando o cliente a acreditar que a operação ocorreu.
4. `GET /api/admin/logs` devolvia lista vazia fixa, ignorando o audit_log.
5. `render.yaml` versionava um token de exportação da base inteira.
"""

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from fastapi.testclient import TestClient

from crm_api import app

client = TestClient(app)
JWT_SECRET = "change-me-in-production"

REPO_RAIZ = Path(__file__).resolve().parent.parent


def _headers(role="admin"):
    token = jwt.encode(
        {
            "username": "api_test",
            "role": role,
            "jti": str(uuid.uuid4()),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        JWT_SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def _novo_cliente() -> dict:
    return {
        "customer_id": f"TESTE-{uuid.uuid4().hex[:8]}",
        "name": "Cliente de Regressão",
        "segment": "Enterprise",
        "city": "São Paulo",
        "country": "Brasil",
        "owner": "api_test",
        "status": "Ativo",
        "health_score": 70,
        "lifetime_value": 1000.0,
        "last_purchase": "2026-01-01",
        "channel": "Direto",
        "next_action": "Follow-up",
        "source": "teste",
    }


class TestEscritaRealDeClientes:
    """PUT e DELETE precisam tocar o banco, não só responder 200."""

    def test_put_persiste_a_alteracao(self):
        payload = _novo_cliente()
        criado = client.post("/api/customers", json=payload, headers=_headers())
        assert criado.status_code == 200, criado.text
        customer_id = criado.json()["customer_id"]

        alterado = dict(payload, customer_id=customer_id, name="Nome Depois do PUT")
        resp = client.put(
            f"/api/customers/{customer_id}", json=alterado, headers=_headers()
        )
        assert resp.status_code == 200, resp.text

        # O ponto do teste: reler do banco e conferir que mudou de verdade.
        lido = client.get(f"/api/customers/{customer_id}", headers=_headers())
        assert lido.status_code == 200
        assert lido.json()["name"] == "Nome Depois do PUT"

    def test_put_em_cliente_inexistente_devolve_404(self):
        payload = _novo_cliente()
        resp = client.put(
            "/api/customers/NAO-EXISTE-999", json=payload, headers=_headers()
        )
        assert resp.status_code == 404

    def test_delete_remove_de_verdade(self):
        payload = _novo_cliente()
        criado = client.post("/api/customers", json=payload, headers=_headers())
        customer_id = criado.json()["customer_id"]

        resp = client.delete(f"/api/customers/{customer_id}", headers=_headers())
        assert resp.status_code == 200, resp.text

        lido = client.get(f"/api/customers/{customer_id}", headers=_headers())
        assert lido.status_code == 404, "o cliente continuou no banco após o DELETE"

    def test_delete_exige_admin(self):
        payload = _novo_cliente()
        criado = client.post("/api/customers", json=payload, headers=_headers())
        customer_id = criado.json()["customer_id"]

        resp = client.delete(f"/api/customers/{customer_id}", headers=_headers("vendas"))
        assert resp.status_code == 403


class TestEndpointsSemImplementacao:
    """Melhor 501 explícito do que 200 mentiroso."""

    def test_backup_responde_501(self):
        resp = client.post("/api/admin/backup", headers=_headers())
        assert resp.status_code == 501
        assert "não foi implementado" in resp.text

    def test_export_responde_501(self):
        resp = client.get("/api/reports/export/vendas", headers=_headers())
        assert resp.status_code == 501

    def test_connect_integration_responde_501(self):
        resp = client.post(
            "/api/integrations/slack/connect", json={"token": "x"}, headers=_headers()
        )
        assert resp.status_code == 501


class TestLogsDeAuditoria:
    def test_logs_retornam_eventos_reais(self):
        # Gera pelo menos um evento auditável.
        client.post("/api/customers", json=_novo_cliente(), headers=_headers())

        resp = client.get("/api/admin/logs?limit=5", headers=_headers())
        assert resp.status_code == 200

        body = resp.json()
        assert body["total"] > 0, "audit_log voltou a ser uma lista vazia fixa"
        assert len(body["logs"]) <= 5
        assert "action" in body["logs"][0]

    def test_logs_exigem_admin(self):
        resp = client.get("/api/admin/logs", headers=_headers("vendas"))
        assert resp.status_code == 403


class TestSegredosNaoVersionados:
    """O token de exportação não pode voltar para o repositório."""

    def test_render_yaml_nao_contem_token_de_migracao(self):
        conteudo = (REPO_RAIZ / "render.yaml").read_text(encoding="utf-8")

        assert "crm-migrate-20260705-temp" not in conteudo
        # Em modo export o contêiner sobe o servidor de exportação da base
        # inteira no lugar do CRM. Isso nunca deve estar fixo no blueprint.
        assert "value: export" not in conteudo
