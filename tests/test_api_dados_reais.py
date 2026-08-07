"""Testes dos endpoints da API contra dados reais.

Antes desta rodada, todos os endpoints de customers/tickets/deals devolviam
listas vazias — a API parecia existir mas não era integrável. Estes testes
provam que ela agora serve e grava dados de verdade.
"""

import uuid

import jwt
import pytest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from crm_api import app

client = TestClient(app)
JWT_SECRET = "change-me-in-production"


def _token(role="admin"):
    return jwt.encode(
        {
            "username": "api_test",
            "role": role,
            "jti": str(uuid.uuid4()),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        JWT_SECRET,
        algorithm="HS256",
    )


def _headers(role="admin"):
    return {"Authorization": f"Bearer {_token(role)}"}


class TestListagens:
    def test_customers_devolve_os_dados_semeados(self):
        resp = client.get("/api/customers", headers=_headers())
        assert resp.status_code == 200

        body = resp.json()
        assert body["pagination"]["total"] >= 1, "a API voltou a devolver lista vazia"
        primeiro = body["data"][0]
        assert "customer_id" in primeiro and "name" in primeiro

    def test_paginacao_respeita_o_limite(self):
        resp = client.get("/api/customers?skip=0&limit=2", headers=_headers())
        body = resp.json()
        assert len(body["data"]) <= 2
        assert body["pagination"]["limit"] == 2

    def test_tickets_filtra_por_status(self):
        todos = client.get("/api/tickets", headers=_headers()).json()
        abertos = client.get("/api/tickets?status_filter=Aberto", headers=_headers()).json()

        assert todos["pagination"]["total"] >= abertos["pagination"]["total"]
        for item in abertos["data"]:
            assert item["status"] == "Aberto"

    def test_deals_filtra_por_etapa(self):
        resp = client.get("/api/deals?stage=Proposta", headers=_headers())
        for item in resp.json()["data"]:
            assert item["stage"] == "Proposta"


class TestGetPorId:
    def test_cliente_existente(self):
        listado = client.get("/api/customers", headers=_headers()).json()["data"][0]
        resp = client.get(f"/api/customers/{listado['customer_id']}", headers=_headers())

        assert resp.status_code == 200
        assert resp.json()["name"] == listado["name"]

    def test_cliente_inexistente_da_404(self):
        resp = client.get("/api/customers/C-NAO-EXISTE", headers=_headers())
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    def test_negociacao_inexistente_da_404(self):
        resp = client.get("/api/deals/D-NAO-EXISTE", headers=_headers())
        assert resp.status_code == 404


class TestCriacao:
    def test_criar_cliente_persiste_e_aparece_na_listagem(self):
        payload = {
            "customer_id": "ignorado",  # o backend gera o id real
            "name": f"Cliente API {uuid.uuid4().hex[:6]}",
            "segment": "Tecnologia", "city": "Curitiba", "country": "Brasil",
            "owner": "Camila Costa", "status": "Novo", "health_score": 70,
            "lifetime_value": 0, "last_purchase": "2026-08-01",
            "channel": "Email", "next_action": "Qualificar", "source": "API",
        }
        criado = client.post("/api/customers", json=payload, headers=_headers())
        assert criado.status_code == 200
        novo_id = criado.json()["customer_id"]
        assert novo_id.startswith("C"), f"id gerado pelo backend esperado, veio {novo_id!r}"

        buscado = client.get(f"/api/customers/{novo_id}", headers=_headers())
        assert buscado.status_code == 200
        assert buscado.json()["name"] == payload["name"]


class TestDashboard:
    def test_numeros_saem_do_banco_e_nao_de_constantes(self):
        resp = client.get("/api/reports/dashboard", headers=_headers())
        assert resp.status_code == 200

        body = resp.json()
        listagem = client.get("/api/customers?limit=100", headers=_headers()).json()
        assert body["customers_total"] == listagem["pagination"]["total"], (
            "o total do dashboard deve refletir o banco, não um número fixo"
        )


class TestAdminUsers:
    def test_admin_lista_usuarios_sem_hash_de_senha(self):
        resp = client.get("/api/admin/users", headers=_headers("admin"))
        assert resp.status_code == 200

        users = resp.json()["users"]
        assert len(users) >= 1
        for u in users:
            assert "password_hash" not in u, "hash de senha nunca pode sair pela API"

    def test_nao_admin_recebe_403(self):
        resp = client.get("/api/admin/users", headers=_headers("vendas"))
        assert resp.status_code == 403
