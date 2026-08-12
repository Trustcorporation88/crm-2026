"""
Pytest configuration and fixtures
"""

import itertools
import os
import pathlib
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# Test environment bootstrap.
#
# Precisa rodar antes de qualquer módulo de teste importar o backend: as
# variáveis DATABASE_URL / REDIS_URL / JWT_SECRET_KEY são lidas na importação.
# O conftest é carregado primeiro pelo pytest, então este é o ponto de gancho.
# Antes, a suíte exigia Postgres e Redis de verdade rodando.
# ---------------------------------------------------------------------------
_TMP_DIR = pathlib.Path(tempfile.mkdtemp(prefix="crm-tests-"))

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    f"sqlite:///{_TMP_DIR / 'crm_test.db'}",
)

os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)
os.environ.setdefault("JWT_SECRET_KEY", "change-me-in-production")
os.environ.setdefault("CRM_DB_PATH", str(_TMP_DIR / "crm.sqlite3"))

# O duplo de Redis em memória (fakeredis) foi removido junto com o crm_api.py.
# Ele existia porque aquele serviço abria conexão com o Redis na importação do
# módulo, o que fazia a suíte exigir um Redis de verdade. Nenhum módulo do
# sistema usa Redis hoje, então não há mais o que substituir.


@pytest.fixture(scope="session")
def engine():
    """Create test database engine"""
    engine = create_engine(TEST_DATABASE_URL)

    yield engine

    engine.dispose()


# ---------------------------------------------------------------------------
# Isolamento por teste quando a suíte roda contra Postgres.
#
# Com SQLite cada teste recebe um arquivo próprio via CRM_DB_PATH. No Postgres
# esse caminho é ignorado e todos os testes compartilhariam a mesma base —
# estado de um teste vazaria para o seguinte (contadores de throttle, por
# exemplo). Aqui cada teste ganha um schema próprio, descartado ao fim.
# ---------------------------------------------------------------------------
_PG_SCHEMA_COUNTER = itertools.count()


def _running_against_postgres() -> bool:
    return os.getenv("DATABASE_URL", "").startswith(("postgres://", "postgresql://"))


@pytest.fixture(autouse=True)
def isolated_pg_schema(request):
    """Dá a cada teste um schema Postgres limpo."""
    if not _running_against_postgres():
        yield
        return

    schema = f"t{next(_PG_SCHEMA_COUNTER)}_{os.getpid()}"
    previous = os.environ.get("CRM_PG_SCHEMA")
    os.environ["CRM_PG_SCHEMA"] = schema

    yield

    if previous is None:
        os.environ.pop("CRM_PG_SCHEMA", None)
    else:
        os.environ["CRM_PG_SCHEMA"] = previous

    try:
        import psycopg2

        with psycopg2.connect(os.environ["DATABASE_URL"]) as conn:
            with conn.cursor() as cur:
                cur.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            conn.commit()
    except Exception:  # pragma: no cover - limpeza é best-effort
        pass

@pytest.fixture(scope="session")
def db_session(engine):
    """Create test database session"""
    connection = engine.connect()
    transaction = connection.begin()
    session_factory = sessionmaker(bind=connection)
    session = session_factory()

    yield session

    session.close()
    transaction.rollback()
    connection.close()

# A fixture `client` foi removida junto com o crm_api.py. O serviço oficial
# (crm_whatsapp_webhook.py) monta seu próprio TestClient nos testes que o usam.

@pytest.fixture
def test_user():
    """Test user credentials"""
    return {
        "username": "test_user",
        "password": "test_password123",
        "role": "admin"
    }


# ---------------------------------------------------------------------------
# Assinatura de webhook para os testes.
#
# As rotas /webhooks/* passaram a exigir HMAC-SHA256 sobre o corpo bruto, do
# mesmo modo que o serviço crm_whatsapp_webhook.py sempre exigiu. Os testes
# precisam assinar o payload exatamente como um emissor legítimo faria — daí
# enviarem `content=` (bytes crus) em vez de `json=`: o HMAC é calculado sobre
# os bytes que trafegam, e deixar o cliente reserializar mudaria o corpo.
# ---------------------------------------------------------------------------
def _assinar_webhook(corpo: bytes) -> dict[str, str]:
    """Cabeçalho de assinatura válido para o corpo informado."""
    import hashlib
    import hmac as _hmac

    import crm_backend

    assinatura = _hmac.new(
        key=crm_backend.get_webhook_hmac_secret().encode("utf-8"),
        msg=corpo,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return {
        "X-Hub-Signature-256": f"sha256={assinatura}",
        "Content-Type": "application/json",
    }


@pytest.fixture
def assinar_webhook():
    """Exposto como fixture para ficar disponível sem importar o conftest."""
    return _assinar_webhook
