"""Regression tests for bcrypt password hashing (no passlib wrap-bug)."""

from __future__ import annotations

import importlib
import os
import sys


def _load_backend(tmp_path):
    os.environ["CRM_DATA_DIR"] = str(tmp_path / "data")
    os.environ["CRM_DB_PATH"] = str(tmp_path / "crm.sqlite3")
    if "crm_backend" in sys.modules:
        del sys.modules["crm_backend"]
    return importlib.import_module("crm_backend")


def test_hash_password_roundtrip(tmp_path):
    backend = _load_backend(tmp_path)
    hashed = backend.hash_password("admin123")
    assert hashed.startswith("$2")
    assert backend._password_matches(hashed, "admin123")
    assert not backend._password_matches(hashed, "wrong-password")


def test_seed_passwords_and_login(tmp_path):
    backend = _load_backend(tmp_path)
    backend.init_database()
    user = backend.verify_login("admin", "admin123")
    assert user is not None
    assert user["username"] == "admin"


def test_password_longer_than_72_bytes_rejected(tmp_path):
    backend = _load_backend(tmp_path)
    too_long = "a" * 73
    try:
        backend.hash_password(too_long)
        raised = False
    except ValueError as exc:
        raised = True
        assert "72 bytes" in str(exc)
    assert raised
