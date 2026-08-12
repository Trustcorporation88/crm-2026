"""Regressões da Fase 2: desempenho, atomicidade e consistência de dados.

Defeitos cobertos:

1. O schema não declarava índice nenhum, e get_data() ordena todas as tabelas
   a cada rerun do Streamlit.
2. Escritas multi-tabela usavam três transações separadas: uma falha após a
   primeira deixava a entidade sem linha do tempo e sem auditoria.
3. Três formatos de timestamp conviviam na mesma coluna TEXT, embaralhando a
   ordenação lexicográfica.
4. Não havia como saber se os dados mudaram sem reler o banco inteiro.
"""

import importlib
import os
import sys

import pytest


@pytest.fixture
def backend(tmp_path):
    os.environ["CRM_DATA_DIR"] = str(tmp_path / "data")
    os.environ["CRM_DB_PATH"] = str(tmp_path / "crm.sqlite3")
    os.environ["CRM_SEED_PASSWORD_ADMIN"] = "senha-de-teste-2026"
    sys.modules.pop("crm_backend", None)
    module = importlib.import_module("crm_backend")
    module.init_database()
    return module


ADMIN = {"username": "admin", "role": "admin"}


class TestIndices:
    def test_schema_declara_indices(self, backend):
        with backend._connect() as connection:
            nomes = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
                ).fetchall()
            }

        # As colunas de junção e de ordenação são as que get_data() percorre.
        for esperado in (
            "idx_interactions_customer",
            "idx_interactions_event_at",
            "idx_audit_log_event_at",
            "idx_tickets_customer",
            "idx_deals_customer",
        ):
            assert esperado in nomes, f"índice ausente: {esperado}"

    def test_consulta_da_timeline_usa_indice(self, backend):
        """Confirma no plano de execução, não por suposição."""
        with backend._connect() as connection:
            plano = connection.execute(
                "EXPLAIN QUERY PLAN "
                "SELECT * FROM interactions WHERE customer_id = ? ORDER BY event_at DESC",
                ("C001",),
            ).fetchall()

        texto = " ".join(str(linha[-1]) for linha in plano)
        assert "idx_interactions" in texto, f"varredura completa: {texto}"


class TestAtomicidade:
    def test_criar_cliente_grava_entidade_timeline_e_auditoria(self, backend):
        customer_id = backend.add_customer(
            {
                "name": "Cliente Atômico",
                "segment": "Enterprise",
                "city": "Recife",
                "country": "Brasil",
                "owner": "admin",
            },
            actor=ADMIN,
        )

        with backend._connect() as connection:
            cliente = connection.execute(
                "SELECT 1 FROM customers WHERE customer_id = ?", (customer_id,)
            ).fetchone()
            interacoes = connection.execute(
                "SELECT COUNT(*) AS n FROM interactions WHERE customer_id = ?",
                (customer_id,),
            ).fetchone()
            auditoria = connection.execute(
                "SELECT COUNT(*) AS n FROM audit_log WHERE entity_id = ?",
                (customer_id,),
            ).fetchone()

        assert cliente is not None
        assert interacoes["n"] >= 1, "cliente gravado sem linha do tempo"
        assert auditoria["n"] >= 1, "cliente gravado sem rastro de auditoria"

    def test_falha_na_auditoria_desfaz_o_cliente(self, backend, monkeypatch):
        """O ponto central: ou grava tudo, ou não grava nada.

        Antes, o INSERT do cliente era confirmado antes da auditoria acontecer,
        então uma falha aqui deixava um cliente órfão, sem rastro nenhum.
        """
        def explodir(*args, **kwargs):
            raise RuntimeError("falha simulada na auditoria")

        monkeypatch.setattr(backend, "log_audit_event", explodir)

        with pytest.raises(RuntimeError):
            backend.add_customer(
                {
                    "name": "Nao Deve Sobrar",
                    "segment": "Enterprise",
                    "city": "Recife",
                    "country": "Brasil",
                    "owner": "admin",
                },
                actor=ADMIN,
            )

        with backend._connect() as connection:
            sobrou = connection.execute(
                "SELECT COUNT(*) AS n FROM customers WHERE name = ?", ("Nao Deve Sobrar",)
            ).fetchone()

        assert sobrou["n"] == 0, "o cliente foi confirmado apesar da falha posterior"


class TestTimestamps:
    def test_novos_registros_usam_utc_iso(self, backend):
        backend.add_customer(
            {
                "name": "Cliente Data",
                "segment": "SMB",
                "city": "Curitiba",
                "country": "Brasil",
                "owner": "admin",
            },
            actor=ADMIN,
        )

        with backend._connect() as connection:
            evento = connection.execute(
                "SELECT event_at FROM audit_log ORDER BY id DESC LIMIT 1"
            ).fetchone()

        valor = evento["event_at"]
        assert "T" in valor, f"timestamp fora do padrão ISO: {valor}"
        assert valor.endswith("+00:00"), f"timestamp sem fuso UTC: {valor}"

    @pytest.mark.parametrize(
        "entrada,esperado_prefixo",
        [
            ("2026-05-25 08:30", "2026-05-25T08:30:00+00:00"),
            ("2026-05-25 08:30:00", "2026-05-25T08:30:00+00:00"),
            ("2026-05-25T08:30:00+00:00", "2026-05-25T08:30:00+00:00"),
            ("2026-05-25", "2026-05-25T00:00:00+00:00"),
        ],
    )
    def test_normalizacao_dos_formatos_herdados(self, backend, entrada, esperado_prefixo):
        assert backend.normalize_timestamp(entrada) == esperado_prefixo

    def test_valor_irreconhecivel_e_preservado(self, backend):
        """Melhor devolver intacto do que destruir o dado."""
        assert backend.normalize_timestamp("ontem à tarde") == "ontem à tarde"
        assert backend.normalize_timestamp(None) is None


class TestVersaoDosDados:
    def test_versao_muda_a_cada_escrita(self, backend):
        antes = backend.data_version()
        backend.add_customer(
            {
                "name": "Cliente Versao",
                "segment": "SMB",
                "city": "Belém",
                "country": "Brasil",
                "owner": "admin",
            },
            actor=ADMIN,
        )
        depois = backend.data_version()

        assert antes != depois

    def test_versao_estavel_sem_escrita(self, backend):
        """Se oscilasse sozinha, o cache da interface nunca serviria."""
        assert backend.data_version() == backend.data_version()
