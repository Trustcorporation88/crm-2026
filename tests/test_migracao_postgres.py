"""Testes do script de migração SQLite → PostgreSQL.

Os testes de integração só rodam quando há um Postgres alcançável em
``TEST_PG_URL``; caso contrário são pulados, para que a suíte não dependa de
um banco externo. As funções puras (checksum, ordem de tabelas) rodam sempre.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from migrate_to_postgres import (
    CONFLICT_KEYS,
    TABLE_ORDER,
    checksum,
    open_sqlite,
    sqlite_tables,
    table_columns,
)

RAIZ = Path(__file__).resolve().parent.parent
PG_URL = os.getenv("TEST_PG_URL", "")
requer_postgres = pytest.mark.skipif(not PG_URL, reason="TEST_PG_URL não definida")


class TestChecksum:
    """Contagem igual não prova conteúdo igual — o checksum é quem prova."""

    def test_mesmo_conteudo_mesma_impressao(self):
        linhas = [(1, "a"), (2, "b")]
        assert checksum(linhas) == checksum(list(linhas))

    def test_ordem_das_linhas_nao_importa(self):
        # A ordem de leitura pode diferir entre os bancos; o conteúdo não.
        assert checksum([(1, "a"), (2, "b")]) == checksum([(2, "b"), (1, "a")])

    def test_valor_alterado_muda_a_impressao(self):
        assert checksum([(1, "a")]) != checksum([(1, "b")])

    def test_nulo_difere_de_string_vazia(self):
        assert checksum([(1, None)]) != checksum([(1, "")])

    def test_separador_evita_colisao_entre_colunas(self):
        # Sem separador, ("ab","c") e ("a","bc") teriam a mesma impressão.
        assert checksum([("ab", "c")]) != checksum([("a", "bc")])

    def test_conjunto_vazio(self):
        assert checksum([]) == checksum([])


class TestOrdemDasTabelas:
    def test_pais_vem_antes_dos_filhos(self):
        posicao = {t: i for i, t in enumerate(TABLE_ORDER)}

        # customers referencia users; interactions referencia customers.
        assert posicao["users"] < posicao["customers"]
        assert posicao["customers"] < posicao["interactions"]
        assert posicao["customers"] < posicao["tickets"]
        assert posicao["customers"] < posicao["deals"]
        # A ordem alfabética inverteria este par.
        assert posicao["cadences"] < posicao["cadence_steps"]

    def test_sem_tabela_repetida(self):
        assert len(TABLE_ORDER) == len(set(TABLE_ORDER))

    def test_chaves_de_conflito_sao_tabelas_conhecidas(self):
        for tabela in CONFLICT_KEYS:
            assert tabela in TABLE_ORDER, f"{tabela} não está na ordem de migração"


class TestLeituraDaOrigem:
    def test_abre_o_sqlite_somente_leitura(self, tmp_path):
        import sqlite3

        caminho = tmp_path / "origem.sqlite3"
        with sqlite3.connect(caminho) as conn:
            conn.execute("CREATE TABLE t (a TEXT)")
            conn.execute("INSERT INTO t VALUES ('x')")

        leitura = open_sqlite(str(caminho))
        assert [r["a"] for r in leitura.execute("SELECT a FROM t").fetchall()] == ["x"]

        # A origem nunca pode ser alterada pela migração.
        with pytest.raises(sqlite3.OperationalError):
            leitura.execute("INSERT INTO t VALUES ('y')")
        leitura.close()

    def test_lista_tabelas_ignorando_internas(self, tmp_path):
        import sqlite3

        caminho = tmp_path / "o.sqlite3"
        with sqlite3.connect(caminho) as conn:
            conn.execute("CREATE TABLE alfa (a TEXT)")
            conn.execute("CREATE TABLE beta (b INTEGER PRIMARY KEY AUTOINCREMENT)")

        leitura = open_sqlite(str(caminho))
        tabelas = sqlite_tables(leitura)
        leitura.close()

        assert "alfa" in tabelas and "beta" in tabelas
        assert not any(t.startswith("sqlite_") for t in tabelas)

    def test_le_as_colunas_na_ordem_do_schema(self, tmp_path):
        import sqlite3

        caminho = tmp_path / "o.sqlite3"
        with sqlite3.connect(caminho) as conn:
            conn.execute("CREATE TABLE t (primeiro TEXT, segundo TEXT)")

        leitura = open_sqlite(str(caminho))
        assert table_columns(leitura, "t") == ["primeiro", "segundo"]
        leitura.close()


@requer_postgres
class TestMigracaoPontaAPonta:
    """Migra um SQLite populado para um Postgres limpo e confere o resultado."""

    @pytest.fixture
    def origem(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        caminho = tmp_path / "origem.sqlite3"
        monkeypatch.setenv("CRM_DB_PATH", str(caminho))

        import importlib
        import crm_backend

        importlib.reload(crm_backend)
        crm_backend.init_database()
        crm_backend.add_customer(
            {
                "name": "Açaí & Cia",
                "document": "11222333000181",
                "segment": "Alimentação",
                "city": "São Paulo",
                "country": "Brasil",
                "owner": "Camila Costa",
            },
            actor={"username": "admin", "role": "admin"},
            source="teste",
        )
        return str(caminho)

    def _rodar(self, *args) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(RAIZ / "migrate_to_postgres.py"), *args],
            capture_output=True,
            text=True,
            cwd=str(RAIZ),
            timeout=300,
        )

    def test_ensaio_nao_escreve_nada(self, origem):
        resultado = self._rodar("--sqlite", origem, "--postgres", PG_URL, "--dry-run")
        assert resultado.returncode == 0
        assert "Nada foi escrito" in resultado.stdout

    def test_migracao_verifica_contagem_e_checksum(self, origem):
        resultado = self._rodar("--sqlite", origem, "--postgres", PG_URL, "--replace")

        assert resultado.returncode == 0, resultado.stdout + resultado.stderr
        assert "Migração verificada" in resultado.stdout
        assert "✗" not in resultado.stdout

    def test_destino_com_dados_exige_confirmacao(self, origem):
        self._rodar("--sqlite", origem, "--postgres", PG_URL, "--replace")

        # Segunda execução sem --replace precisa parar.
        resultado = self._rodar("--sqlite", origem, "--postgres", PG_URL)
        assert resultado.returncode == 1
        assert "--replace" in resultado.stdout
