"""
Pytest configuration and fixtures
"""

import os
import pathlib
import tempfile

import pytest
import redis
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Test environment bootstrap.
#
# This block MUST run before any test module imports crm_api: that module reads
# DATABASE_URL / REDIS_URL / JWT_SECRET_KEY at import time and calls
# redis.from_url() eagerly. conftest is imported first by pytest, so this is the
# hook point. Previously the suite required a live Postgres and Redis, which is
# why tests/test_api.py could never run.
# ---------------------------------------------------------------------------
_TMP_DIR = pathlib.Path(tempfile.mkdtemp(prefix="crm-tests-"))

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    f"sqlite:///{_TMP_DIR / 'crm_test.db'}",
)

os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
# Matches the token signed in tests/test_api.py::valid_token.
os.environ.setdefault("JWT_SECRET_KEY", "change-me-in-production")
os.environ.setdefault("CRM_DB_PATH", str(_TMP_DIR / "crm.sqlite3"))

# Swap the Redis driver for an in-memory double so the suite has no external
# service dependency. Patching the factory covers every module that calls
# redis.from_url(), including cache_utils at import time.
try:
    import fakeredis

    # A single shared server, so every module that calls from_url() sees the
    # same keyspace — as they would against one real Redis. Handing out
    # independent instances would hide cross-module cache bugs.
    _FAKE_SERVER = fakeredis.FakeServer()

    def _fake_from_url(url, *args, **kwargs):
        kwargs.pop("decode_responses", None)
        return fakeredis.FakeRedis(server=_FAKE_SERVER, decode_responses=True)

    redis.from_url = _fake_from_url
except ImportError:  # pragma: no cover - fakeredis is a test-only dependency
    pass


@pytest.fixture(scope="session")
def engine():
    """Create test database engine"""
    engine = create_engine(TEST_DATABASE_URL)

    yield engine

    engine.dispose()

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

@pytest.fixture
def client():
    """Create test client"""
    from crm_api import app
    return TestClient(app)

@pytest.fixture
def test_user():
    """Test user credentials"""
    return {
        "username": "test_user",
        "password": "test_password123",
        "role": "admin"
    }
