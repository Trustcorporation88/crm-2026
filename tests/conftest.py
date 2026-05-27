"""
Pytest configuration and fixtures
"""

import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# Use test database
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://crm_admin:test123@localhost/crm_test"
)

@pytest.fixture(scope="session")
def engine():
    """Create test database engine"""
    from sqlalchemy import text
    
    # Connect to default postgres DB to create test DB
    default_engine = create_engine("postgresql://crm_admin:test123@localhost/postgres")
    
    with default_engine.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS crm_test"))
        conn.execute(text("CREATE DATABASE crm_test"))
        conn.commit()
    
    default_engine.dispose()
    
    # Create tables in test database
    engine = create_engine(TEST_DATABASE_URL)
    
    # Create all tables (from crm_backend schema)
    # This would import and call _create_schema from crm_backend
    
    yield engine
    
    # Cleanup
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
