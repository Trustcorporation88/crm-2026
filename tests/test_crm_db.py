"""Testes da camada de compatibilidade SQLite ↔ PostgreSQL.

A tradução de SQL é o ponto onde uma migração corrompe dados em silêncio:
um literal transformado em placeholder, um upsert que vira insert simples.
Estes testes fixam cada caso.
"""

import pytest

from crm_db import (
    backend_name,
    is_postgres,
    split_script,
    translate_ddl,
    translate_placeholders,
    translate_statement,
)


class TestSelecaoDeBackend:
    def test_sem_variavel_usa_sqlite(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        assert is_postgres() is False
        assert backend_name() == "sqlite"

    @pytest.mark.parametrize(
        "url",
        [
            "postgres://u:p@host:5432/db",
            "postgresql://u:p@host:5432/db",
            "postgresql+psycopg2://u:p@host/db",
        ],
    )
    def test_url_postgres_ativa_o_backend(self, monkeypatch, url):
        monkeypatch.setenv("DATABASE_URL", url)
        assert is_postgres() is True
        assert backend_name() == "postgres"

    def test_url_sqlite_nao_ativa_postgres(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "sqlite:///Data/crm.sqlite3")
        assert is_postgres() is False


class TestPlaceholders:
    def test_posicional(self):
        traduzido = translate_placeholders(
            "SELECT * FROM users WHERE username = ? AND is_active = ?"
        )
        assert traduzido == "SELECT * FROM users WHERE username = %s AND is_active = %s"

    def test_nomeado(self):
        traduzido = translate_placeholders(
            "INSERT INTO users (username, role) VALUES (:username, :role)"
        )
        assert ":username" not in traduzido
        assert "%(username)s" in traduzido and "%(role)s" in traduzido

    def test_literal_com_dois_pontos_nao_vira_parametro(self):
        # A máscara de hora é o caso clássico que um regex ingênuo destrói.
        sql = "SELECT strftime('%Y-%m-%d %H:%M:%S', created_at) FROM tickets WHERE id = ?"
        traduzido = translate_placeholders(sql)

        assert "'%Y-%m-%d %H:%M:%S'" in traduzido, "o literal de data foi corrompido"
        assert traduzido.endswith("id = %s")

    def test_interrogacao_dentro_de_literal_e_preservada(self):
        sql = "SELECT * FROM tickets WHERE subject = 'Tudo certo?' AND owner = ?"
        traduzido = translate_placeholders(sql)

        assert "'Tudo certo?'" in traduzido, "a interrogação do literal virou placeholder"
        assert traduzido.count("%s") == 1

    def test_aspas_duplicadas_escapadas(self):
        sql = "SELECT * FROM t WHERE nome = 'O''Brien?' AND id = ?"
        traduzido = translate_placeholders(sql)
        assert "'O''Brien?'" in traduzido
        assert traduzido.count("%s") == 1

    def test_cast_com_dois_pontos_duplos_nao_e_tocado(self):
        sql = "SELECT valor::text FROM deals WHERE id = ?"
        traduzido = translate_placeholders(sql)
        assert "valor::text" in traduzido


class TestDDL:
    def test_autoincrement_vira_serial(self):
        ddl = "CREATE TABLE interactions (id INTEGER PRIMARY KEY AUTOINCREMENT, corpo TEXT)"
        assert "SERIAL PRIMARY KEY" in translate_ddl(ddl)
        assert "AUTOINCREMENT" not in translate_ddl(ddl)

    def test_real_vira_precisao_dupla(self):
        assert "DOUBLE PRECISION" in translate_ddl("CREATE TABLE d (valor REAL)")

    def test_texto_dentro_de_literal_nao_e_reescrito(self):
        ddl = "INSERT INTO logs (msg) VALUES ('campo REAL do formulário')"
        assert "'campo REAL do formulário'" in translate_ddl(ddl)


class TestUpsert:
    def test_insert_or_ignore_vira_do_nothing(self):
        sql = "INSERT OR IGNORE INTO role_permissions (role, action) VALUES (?, ?)"
        traduzido = translate_statement(sql)

        assert "INSERT INTO role_permissions" in traduzido
        assert "ON CONFLICT (role, action) DO NOTHING" in traduzido
        assert "OR IGNORE" not in traduzido

    def test_insert_or_replace_vira_do_update(self):
        sql = (
            "INSERT OR REPLACE INTO campaigns "
            "(campaign, channel, leads, qualified, conversion_rate, revenue) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )
        traduzido = translate_statement(sql)

        assert "ON CONFLICT (campaign) DO UPDATE SET" in traduzido
        # A chave de conflito não pode entrar no SET.
        assert "campaign = EXCLUDED.campaign" not in traduzido
        assert "channel = EXCLUDED.channel" in traduzido
        assert "revenue = EXCLUDED.revenue" in traduzido

    def test_tabela_sem_chave_declarada_falha_alto(self):
        # Preferir erro explícito a gerar um upsert silenciosamente errado.
        with pytest.raises(ValueError, match="conflito"):
            translate_statement("INSERT OR IGNORE INTO tabela_desconhecida (a) VALUES (?)")


class TestPragma:
    def test_pragma_table_info_vira_consulta_ao_catalogo(self):
        traduzido = translate_statement("PRAGMA table_info(customers)")

        assert "information_schema.columns" in traduzido
        assert "table_name = 'customers'" in traduzido
        # O backend lê row["name"]; o alias precisa existir.
        assert "column_name AS name" in traduzido


class TestDivisaoDeScript:
    def test_divide_por_ponto_e_virgula(self):
        script = "CREATE TABLE a (x TEXT); CREATE TABLE b (y TEXT);"
        assert len(split_script(script)) == 2

    def test_ponto_e_virgula_dentro_de_literal_nao_divide(self):
        script = "INSERT INTO t (msg) VALUES ('primeiro; segundo'); CREATE TABLE b (y TEXT);"
        comandos = split_script(script)

        assert len(comandos) == 2
        assert "'primeiro; segundo'" in comandos[0]

    def test_ignora_trecho_vazio(self):
        assert split_script("CREATE TABLE a (x TEXT);;  ;") == ["CREATE TABLE a (x TEXT)"]

    def test_script_vazio(self):
        assert split_script("   ") == []
