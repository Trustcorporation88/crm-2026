"""Pool de conexões do Postgres (crm_db).

Roda só com Postgres de verdade (TEST_PG_URL), como os testes de migração.
"""

from __future__ import annotations

import os

import pytest

import crm_db

PG_URL = os.getenv("TEST_PG_URL", "")
requer_postgres = pytest.mark.skipif(not PG_URL, reason="TEST_PG_URL não definida")


@pytest.fixture
def pg(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", PG_URL)
    monkeypatch.delenv("CRM_PG_POOL", raising=False)
    crm_db.close_pools()
    yield
    crm_db.close_pools()


def _pid(conn) -> int:
    return conn.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]


@requer_postgres
class TestPool:
    def test_reaproveita_a_conexao_entre_usos(self, pg):
        with crm_db.connect() as c1:
            primeiro = _pid(c1)
        with crm_db.connect() as c2:
            segundo = _pid(c2)
        assert primeiro == segundo, "cada uso abriu uma conexão nova"

    def test_usos_simultaneos_recebem_conexoes_diferentes(self, pg):
        with crm_db.connect() as c1, crm_db.connect() as c2:
            assert _pid(c1) != _pid(c2)

    def test_transacao_esquecida_nao_vaza_para_o_proximo_uso(self, pg, monkeypatch):
        monkeypatch.setenv("CRM_PG_SCHEMA", "pool_vazamento")
        with crm_db.connect() as c:
            c.execute("CREATE TABLE IF NOT EXISTS t_pool (v INT)")
            c.execute("DELETE FROM t_pool")

        c = crm_db.connect()
        c.execute("INSERT INTO t_pool VALUES (1)")  # sem commit
        c.close()

        with crm_db.connect() as c:
            total = c.execute("SELECT COUNT(*) AS n FROM t_pool").fetchone()["n"]
            c.execute('DROP SCHEMA "pool_vazamento" CASCADE')
        assert total == 0, "insert não confirmado apareceu para o próximo usuário do pool"

    def test_erro_dentro_do_with_desfaz_e_conexao_continua_util(self, pg):
        with pytest.raises(Exception):
            with crm_db.connect() as c:
                c.execute("SELECT * FROM tabela_que_nao_existe")
        with crm_db.connect() as c:
            assert c.execute("SELECT 1 AS um").fetchone()["um"] == 1

    def test_conexao_derrubada_e_descartada(self, pg):
        with crm_db.connect() as c:
            vitima = _pid(c)  # volta para o pool
        # Derruba a conexão ociosa por fora, como faria o servidor ou o pooler.
        algoz = crm_db._open_postgres(PG_URL)
        with algoz.cursor() as cur:
            cur.execute("SELECT pg_terminate_backend(%s)", (vitima,))
        algoz.commit()
        algoz.close()
        # Força o ping na próxima retirada.
        for pool in crm_db._POOLS.values():
            pool._idle = [(raw, 0.0) for raw, _ in pool._idle]
        with crm_db.connect() as c:
            assert c.execute("SELECT 1 AS um").fetchone()["um"] == 1
            assert _pid(c) != vitima

    def test_troca_de_schema_entre_usos(self, pg, monkeypatch):
        monkeypatch.setenv("CRM_PG_SCHEMA", "pool_a")
        with crm_db.connect() as c:
            a = c.execute("SELECT current_schema() AS s").fetchone()["s"]
        monkeypatch.setenv("CRM_PG_SCHEMA", "pool_b")
        with crm_db.connect() as c:
            b = c.execute("SELECT current_schema() AS s").fetchone()["s"]
        monkeypatch.delenv("CRM_PG_SCHEMA")
        with crm_db.connect() as c:
            padrao = c.execute("SELECT current_schema() AS s").fetchone()["s"]
            c.execute('DROP SCHEMA IF EXISTS "pool_a" CASCADE')
            c.execute('DROP SCHEMA IF EXISTS "pool_b" CASCADE')
        assert (a, b, padrao) == ("pool_a", "pool_b", "public")

    def test_pool_pode_ser_desligado(self, pg, monkeypatch):
        monkeypatch.setenv("CRM_PG_POOL", "0")
        with crm_db.connect() as c1:
            primeiro = _pid(c1)
        with crm_db.connect() as c2:
            segundo = _pid(c2)
        assert primeiro != segundo
