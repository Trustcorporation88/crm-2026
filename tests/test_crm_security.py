import hashlib
import hmac
import importlib
import json
import os
import sys

from fastapi.testclient import TestClient


def _reset_modules() -> None:
    for module_name in ["crm_whatsapp_webhook", "crm_backend"]:
        if module_name in sys.modules:
            del sys.modules[module_name]


def _load_app(tmp_path, env_overrides=None):
    os.environ["CRM_DATA_DIR"] = str(tmp_path / "data")
    os.environ["CRM_DB_PATH"] = str(tmp_path / "crm.sqlite3")
    os.environ["CRM_WHATSAPP_HMAC_SECRET"] = "test-hmac-secret-32-bytes-minimum-key"
    os.environ["CRM_API_JWT_SECRET"] = "test-jwt-secret-32-bytes-minimum-key"
    os.environ["CRM_AUTH_RATE_LIMIT_WINDOW_SECONDS"] = "60"
    os.environ["CRM_AUTH_RATE_LIMIT_MAX_ATTEMPTS"] = "10"
    os.environ["CRM_AUTH_LOCK_THRESHOLD"] = "5"
    os.environ["CRM_AUTH_LOCK_SECONDS"] = "300"
    if env_overrides:
        for key, value in env_overrides.items():
            os.environ[key] = str(value)

    _reset_modules()
    crm_backend = importlib.import_module("crm_backend")
    crm_backend.init_database()
    crm_webhook = importlib.import_module("crm_whatsapp_webhook")
    client = TestClient(crm_webhook.app)
    return crm_backend, client


def _sign_payload(raw_body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_webhook_requires_valid_hmac(tmp_path):
    _, client = _load_app(tmp_path)

    payload = {
        "message": {
            "id": "msg-hmac-1",
            "from": "+5511999999999",
            "name": "Cliente HMAC",
            "text": "Preciso de ajuda",
        }
    }
    raw = json.dumps(payload).encode("utf-8")

    ok = client.post(
        "/webhook/whatsapp",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": _sign_payload(raw, "test-hmac-secret-32-bytes-minimum-key"),
        },
    )
    bad = client.post(
        "/webhook/whatsapp",
        content=raw,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=invalid",
        },
    )

    assert ok.status_code == 200
    assert bad.status_code == 401


def test_update_delete_require_jwt_and_audit_before_after(tmp_path):
    crm_backend, client = _load_app(tmp_path)

    admin = crm_backend.get_user_by_username("admin")
    assert admin is not None
    admin_token = crm_backend.create_access_token(admin)
    admin_claims = crm_backend.verify_access_token(admin_token)
    assert "campaign.update" in admin_claims["scopes"]

    crm_backend.add_campaign(
        {
            "campaign": "TEMP-AUDIT-API",
            "channel": "Email",
            "leads": 10,
            "qualified": 2,
            "conversion_rate": 20,
            "revenue": 1000,
        },
        actor=admin,
        source="test-seed",
    )

    missing_auth = client.put(
        "/api/campaign/TEMP-AUDIT-API",
        json={"updates": {"revenue": 2500}},
        headers={"X-Actor-Username": "admin"},
    )
    assert missing_auth.status_code == 401

    atendimento = crm_backend.get_user_by_username("atendimento")
    assert atendimento is not None
    atendimento_token = crm_backend.create_access_token(atendimento)

    forbidden_scope = client.put(
        "/api/campaign/TEMP-AUDIT-API",
        json={"updates": {"revenue": 2500}},
        headers={
            "X-Actor-Username": "atendimento",
            "Authorization": f"Bearer {atendimento_token}",
        },
    )
    assert forbidden_scope.status_code == 403
    assert "Token missing scope campaign.update" in forbidden_scope.text

    mismatch_actor = client.put(
        "/api/campaign/TEMP-AUDIT-API",
        json={"updates": {"revenue": 2500}},
        headers={
            "X-Actor-Username": "admin",
            "Authorization": f"Bearer {atendimento_token}",
        },
    )
    assert mismatch_actor.status_code == 403

    updated = client.put(
        "/api/campaign/TEMP-AUDIT-API",
        json={"updates": {"revenue": 2500}},
        headers={
            "X-Actor-Username": "admin",
            "Authorization": f"Bearer {admin_token}",
        },
    )
    assert updated.status_code == 200
    assert float(updated.json()["after"]["revenue"]) == 2500.0

    deleted = client.delete(
        "/api/campaign/TEMP-AUDIT-API",
        headers={
            "X-Actor-Username": "admin",
            "Authorization": f"Bearer {admin_token}",
        },
    )
    assert deleted.status_code == 200
    assert deleted.json()["before"]["campaign"] == "TEMP-AUDIT-API"

    audit_df = crm_backend.get_data()["audit_log"]
    api_rows = audit_df[audit_df["source"].isin(["api-update", "api-delete"])]
    actions = set(api_rows["action"].tolist())
    assert "campaign.update" in actions
    assert "campaign.delete" in actions

    update_payload_raw = api_rows[api_rows["action"] == "campaign.update"].iloc[0]["payload_json"]
    delete_payload_raw = api_rows[api_rows["action"] == "campaign.delete"].iloc[0]["payload_json"]
    update_payload = json.loads(update_payload_raw)
    delete_payload = json.loads(delete_payload_raw)

    assert update_payload["before"]["revenue"] == 1000.0
    assert update_payload["after"]["revenue"] == 2500.0
    assert delete_payload["before"]["campaign"] == "TEMP-AUDIT-API"
    assert delete_payload["after"] is None


def test_rbac_admin_endpoint_and_rbac_audit(tmp_path):
    crm_backend, client = _load_app(tmp_path)

    admin = crm_backend.get_user_by_username("admin")
    atendimento = crm_backend.get_user_by_username("atendimento")
    assert admin is not None
    assert atendimento is not None

    admin_token = crm_backend.create_access_token(admin)
    atendimento_token = crm_backend.create_access_token(atendimento)

    admin_read = client.get(
        "/api/admin/rbac-matrix",
        headers={
            "X-Actor-Username": "admin",
            "Authorization": f"Bearer {admin_token}",
        },
    )
    assert admin_read.status_code == 200
    roles = admin_read.json()["roles"]
    admin_row = [row for row in roles if row["role"] == "admin"]
    assert admin_row
    assert "rbac.manage" in admin_row[0]["actions"]

    non_admin_read = client.get(
        "/api/admin/rbac-matrix",
        headers={
            "X-Actor-Username": "atendimento",
            "Authorization": f"Bearer {atendimento_token}",
        },
    )
    assert non_admin_read.status_code == 403

    crm_backend.update_role_permissions(
        "marketing",
        ["campaign.create", "campaign.update", "campaign.delete"],
        actor=admin,
        source="test-rbac-update",
    )

    audit_df = crm_backend.get_data()["audit_log"]
    row = audit_df[audit_df["source"] == "test-rbac-update"].iloc[0]
    payload = json.loads(row["payload_json"])

    assert row["action"] == "rbac.manage"
    assert "before" in payload
    assert "after" in payload
    assert "campaign.delete" in payload["after"]


def test_refresh_token_rotation_and_revocation(tmp_path):
    _, client = _load_app(tmp_path)
    fingerprint = "device-admin-01"
    wrong_fingerprint = "device-admin-02"

    issue = client.post(
        "/api/auth/token",
        headers={
            "X-Actor-Username": "admin",
            "X-Client-Fingerprint": fingerprint,
        },
    )
    assert issue.status_code == 200
    issue_payload = issue.json()
    refresh_1 = issue_payload["refresh_token"]
    assert refresh_1

    refreshed = client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_1},
        headers={
            "X-Actor-Username": "admin",
            "X-Client-Fingerprint": fingerprint,
        },
    )
    assert refreshed.status_code == 200
    refresh_2 = refreshed.json()["refresh_token"]
    assert refresh_2
    assert refresh_2 != refresh_1

    wrong_device = client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_2},
        headers={
            "X-Actor-Username": "admin",
            "X-Client-Fingerprint": wrong_fingerprint,
        },
    )
    assert wrong_device.status_code == 401

    reuse_old = client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_1},
        headers={
            "X-Actor-Username": "admin",
            "X-Client-Fingerprint": fingerprint,
        },
    )
    assert reuse_old.status_code == 401

    logout = client.post(
        "/api/auth/logout",
        json={"refresh_token": refresh_2},
        headers={
            "X-Actor-Username": "admin",
            "X-Client-Fingerprint": fingerprint,
        },
    )
    assert logout.status_code == 200

    after_logout = client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_2},
        headers={
            "X-Actor-Username": "admin",
            "X-Client-Fingerprint": fingerprint,
        },
    )
    assert after_logout.status_code == 401


def test_auth_endpoints_require_client_fingerprint(tmp_path):
    _, client = _load_app(tmp_path)

    missing_fp = client.post(
        "/api/auth/token",
        headers={"X-Actor-Username": "admin"},
    )
    assert missing_fp.status_code == 400


def test_logout_all_revokes_all_active_refresh_sessions(tmp_path):
    _, client = _load_app(tmp_path)

    issue_a = client.post(
        "/api/auth/token",
        headers={
            "X-Actor-Username": "admin",
            "X-Client-Fingerprint": "device-a",
        },
    )
    issue_b = client.post(
        "/api/auth/token",
        headers={
            "X-Actor-Username": "admin",
            "X-Client-Fingerprint": "device-b",
        },
    )
    assert issue_a.status_code == 200
    assert issue_b.status_code == 200

    access_token = issue_a.json()["access_token"]
    refresh_a = issue_a.json()["refresh_token"]
    refresh_b = issue_b.json()["refresh_token"]

    logout_all = client.post(
        "/api/auth/logout-all",
        headers={
            "X-Actor-Username": "admin",
            "Authorization": f"Bearer {access_token}",
        },
    )
    assert logout_all.status_code == 200
    assert logout_all.json()["revoked_count"] >= 2

    refresh_after_logout_a = client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_a},
        headers={
            "X-Actor-Username": "admin",
            "X-Client-Fingerprint": "device-a",
        },
    )
    refresh_after_logout_b = client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_b},
        headers={
            "X-Actor-Username": "admin",
            "X-Client-Fingerprint": "device-b",
        },
    )
    assert refresh_after_logout_a.status_code == 401
    assert refresh_after_logout_b.status_code == 401


def test_auth_rate_limit_blocks_excessive_token_requests(tmp_path):
    _, client = _load_app(
        tmp_path,
        env_overrides={
            "CRM_AUTH_RATE_LIMIT_MAX_ATTEMPTS": "2",
            "CRM_AUTH_RATE_LIMIT_WINDOW_SECONDS": "300",
        },
    )

    headers = {
        "X-Actor-Username": "admin",
        "X-Client-Fingerprint": "device-limit",
    }
    r1 = client.post("/api/auth/token", headers=headers)
    r2 = client.post("/api/auth/token", headers=headers)
    r3 = client.post("/api/auth/token", headers=headers)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429


def test_auth_progressive_lock_after_invalid_refresh_attempts(tmp_path):
    _, client = _load_app(
        tmp_path,
        env_overrides={
            "CRM_AUTH_RATE_LIMIT_MAX_ATTEMPTS": "20",
            "CRM_AUTH_RATE_LIMIT_WINDOW_SECONDS": "300",
            "CRM_AUTH_LOCK_THRESHOLD": "2",
            "CRM_AUTH_LOCK_SECONDS": "300",
        },
    )

    issue = client.post(
        "/api/auth/token",
        headers={
            "X-Actor-Username": "admin",
            "X-Client-Fingerprint": "device-lock",
        },
    )
    assert issue.status_code == 200
    valid_refresh = issue.json()["refresh_token"]

    bad1 = client.post(
        "/api/auth/refresh",
        json={"refresh_token": "bad-token-1"},
        headers={
            "X-Actor-Username": "admin",
            "X-Client-Fingerprint": "device-lock",
        },
    )
    bad2 = client.post(
        "/api/auth/refresh",
        json={"refresh_token": "bad-token-2"},
        headers={
            "X-Actor-Username": "admin",
            "X-Client-Fingerprint": "device-lock",
        },
    )
    blocked = client.post(
        "/api/auth/refresh",
        json={"refresh_token": valid_refresh},
        headers={
            "X-Actor-Username": "admin",
            "X-Client-Fingerprint": "device-lock",
        },
    )

    assert bad1.status_code == 401
    assert bad2.status_code == 401
    assert blocked.status_code == 429


def test_auth_rate_limit_scoped_by_ip(tmp_path):
    _, client = _load_app(
        tmp_path,
        env_overrides={
            "CRM_AUTH_RATE_LIMIT_MAX_ATTEMPTS": "2",
            "CRM_AUTH_RATE_LIMIT_WINDOW_SECONDS": "300",
        },
    )

    headers_ip1 = {
        "X-Actor-Username": "admin",
        "X-Client-Fingerprint": "device-ip-1",
        "X-Forwarded-For": "198.51.100.10",
    }
    headers_ip2 = {
        "X-Actor-Username": "admin",
        "X-Client-Fingerprint": "device-ip-2",
        "X-Forwarded-For": "203.0.113.25",
    }

    ip1_a = client.post("/api/auth/token", headers=headers_ip1)
    ip1_b = client.post("/api/auth/token", headers=headers_ip1)
    ip1_c = client.post("/api/auth/token", headers=headers_ip1)
    ip2_a = client.post("/api/auth/token", headers=headers_ip2)

    assert ip1_a.status_code == 200
    assert ip1_b.status_code == 200
    assert ip1_c.status_code == 429
    assert ip2_a.status_code == 200


def test_admin_auth_throttle_endpoint_returns_rows(tmp_path):
    _, client = _load_app(tmp_path)

    issue = client.post(
        "/api/auth/token",
        headers={
            "X-Actor-Username": "admin",
            "X-Client-Fingerprint": "device-metrics",
        },
    )
    assert issue.status_code == 200
    access_token = issue.json()["access_token"]

    throttle = client.get(
        "/api/admin/auth-throttle",
        headers={
            "X-Actor-Username": "admin",
            "Authorization": f"Bearer {access_token}",
        },
    )
    assert throttle.status_code == 200
    payload = throttle.json()
    assert payload["status"] == "ok"
    assert payload["count"] >= 1
    assert "metrics" in payload
    assert payload["metrics"]["total_rows"] >= 1
    assert isinstance(payload["metrics"]["top_subjects"], list)
    assert isinstance(payload["rows"], list)


def test_admin_can_clear_auth_throttle_rows(tmp_path):
    _, client = _load_app(tmp_path)

    issue = client.post(
        "/api/auth/token",
        headers={
            "X-Actor-Username": "admin",
            "X-Client-Fingerprint": "device-clear-1",
        },
    )
    assert issue.status_code == 200
    access_token = issue.json()["access_token"]

    before = client.get(
        "/api/admin/auth-throttle",
        headers={
            "X-Actor-Username": "admin",
            "Authorization": f"Bearer {access_token}",
        },
    )
    assert before.status_code == 200
    assert before.json()["metrics"]["total_rows"] >= 1

    cleared = client.post(
        "/api/admin/auth-throttle/clear",
        json={"subject": "admin|testclient", "endpoint": "/api/auth/token"},
        headers={
            "X-Actor-Username": "admin",
            "Authorization": f"Bearer {access_token}",
        },
    )
    assert cleared.status_code == 200
    assert cleared.json()["deleted"] >= 1

    after = client.get(
        "/api/admin/auth-throttle",
        headers={
            "X-Actor-Username": "admin",
            "Authorization": f"Bearer {access_token}",
        },
    )
    assert after.status_code == 200
    assert after.json()["metrics"]["total_rows"] == 0


def test_admin_auth_throttle_cursor_pagination(tmp_path):
    _, client = _load_app(tmp_path)

    base_headers = {
        "X-Actor-Username": "admin",
    }
    for idx, ip in enumerate(["198.51.100.31", "198.51.100.32", "198.51.100.33"]):
        headers = {
            **base_headers,
            "X-Client-Fingerprint": f"device-page-{idx}",
            "X-Forwarded-For": ip,
        }
        issued = client.post("/api/auth/token", headers=headers)
        assert issued.status_code == 200

    admin_issue = client.post(
        "/api/auth/token",
        headers={
            "X-Actor-Username": "admin",
            "X-Client-Fingerprint": "device-page-admin",
        },
    )
    access_token = admin_issue.json()["access_token"]

    page1 = client.get(
        "/api/admin/auth-throttle?limit=2",
        headers={
            "X-Actor-Username": "admin",
            "Authorization": f"Bearer {access_token}",
        },
    )
    assert page1.status_code == 200
    payload1 = page1.json()
    assert payload1["count"] == 2
    assert payload1["next_cursor"]

    page2 = client.get(
        f"/api/admin/auth-throttle?limit=2&cursor={payload1['next_cursor']}",
        headers={
            "X-Actor-Username": "admin",
            "Authorization": f"Bearer {access_token}",
        },
    )
    assert page2.status_code == 200
    payload2 = page2.json()
    assert payload2["count"] >= 1


def test_admin_can_unlock_auth_throttle_by_subject_prefix(tmp_path):
    _, client = _load_app(
        tmp_path,
        env_overrides={
            "CRM_AUTH_RATE_LIMIT_MAX_ATTEMPTS": "20",
            "CRM_AUTH_RATE_LIMIT_WINDOW_SECONDS": "300",
            "CRM_AUTH_LOCK_THRESHOLD": "2",
            "CRM_AUTH_LOCK_SECONDS": "300",
        },
    )

    subject_ip = "198.51.100.77"
    issue = client.post(
        "/api/auth/token",
        headers={
            "X-Actor-Username": "admin",
            "X-Client-Fingerprint": "device-unlock",
            "X-Forwarded-For": subject_ip,
        },
    )
    assert issue.status_code == 200
    access_token = issue.json()["access_token"]
    refresh_token = issue.json()["refresh_token"]

    for bad in ["bad-unlock-1", "bad-unlock-2"]:
        resp = client.post(
            "/api/auth/refresh",
            json={"refresh_token": bad},
            headers={
                "X-Actor-Username": "admin",
                "X-Client-Fingerprint": "device-unlock",
                "X-Forwarded-For": subject_ip,
            },
        )
        assert resp.status_code == 401

    blocked = client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token},
        headers={
            "X-Actor-Username": "admin",
            "X-Client-Fingerprint": "device-unlock",
            "X-Forwarded-For": subject_ip,
        },
    )
    assert blocked.status_code == 429

    unlocked = client.post(
        "/api/admin/auth-throttle/unlock",
        json={"subject_prefix": f"admin|{subject_ip}", "endpoint": "/api/auth/refresh"},
        headers={
            "X-Actor-Username": "admin",
            "Authorization": f"Bearer {access_token}",
        },
    )
    assert unlocked.status_code == 200
    assert unlocked.json()["unlocked"] >= 1

    success_after_unlock = client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token},
        headers={
            "X-Actor-Username": "admin",
            "X-Client-Fingerprint": "device-unlock",
            "X-Forwarded-For": subject_ip,
        },
    )
    assert success_after_unlock.status_code == 200


def test_admin_auth_throttle_filters_by_endpoint_and_subject_prefix(tmp_path):
    _, client = _load_app(tmp_path)

    seed_issue = client.post(
        "/api/auth/token",
        headers={
            "X-Actor-Username": "admin",
            "X-Client-Fingerprint": "device-filter-seed",
            "X-Forwarded-For": "198.51.100.88",
        },
    )
    assert seed_issue.status_code == 200
    access_token = seed_issue.json()["access_token"]

    refresh_fail = client.post(
        "/api/auth/refresh",
        json={"refresh_token": "bad-filter-token"},
        headers={
            "X-Actor-Username": "admin",
            "X-Client-Fingerprint": "device-filter-seed",
            "X-Forwarded-For": "198.51.100.88",
        },
    )
    assert refresh_fail.status_code == 401

    filtered = client.get(
        "/api/admin/auth-throttle?endpoint=/api/auth/refresh&subject_prefix=admin|198.51.100.88",
        headers={
            "X-Actor-Username": "admin",
            "Authorization": f"Bearer {access_token}",
        },
    )
    assert filtered.status_code == 200
    payload = filtered.json()
    assert payload["count"] >= 1
    assert payload["metrics"]["total_rows"] >= 1
    for row in payload["rows"]:
        assert row["endpoint"] == "/api/auth/refresh"
        assert row["subject"].startswith("admin|198.51.100.88")


def test_admin_auth_throttle_supports_sorting(tmp_path):
    _, client = _load_app(
        tmp_path,
        env_overrides={
            "CRM_AUTH_RATE_LIMIT_MAX_ATTEMPTS": "20",
            "CRM_AUTH_RATE_LIMIT_WINDOW_SECONDS": "300",
            "CRM_AUTH_LOCK_THRESHOLD": "5",
            "CRM_AUTH_LOCK_SECONDS": "300",
        },
    )

    seed = client.post(
        "/api/auth/token",
        headers={
            "X-Actor-Username": "admin",
            "X-Client-Fingerprint": "device-sort-seed",
            "X-Forwarded-For": "198.51.100.121",
        },
    )
    assert seed.status_code == 200
    access_token = seed.json()["access_token"]

    for value in ["bad-sort-1", "bad-sort-2"]:
        bad = client.post(
            "/api/auth/refresh",
            json={"refresh_token": value},
            headers={
                "X-Actor-Username": "admin",
                "X-Client-Fingerprint": "device-sort-seed",
                "X-Forwarded-For": "198.51.100.121",
            },
        )
        assert bad.status_code == 401

    ordered = client.get(
        "/api/admin/auth-throttle?sort_by=fail_count&sort_order=desc",
        headers={
            "X-Actor-Username": "admin",
            "Authorization": f"Bearer {access_token}",
        },
    )
    assert ordered.status_code == 200
    rows = ordered.json()["rows"]
    assert rows
    assert int(rows[0]["fail_count"]) >= int(rows[-1]["fail_count"])


def test_admin_auth_throttle_rejects_cursor_for_non_default_sort(tmp_path):
    _, client = _load_app(tmp_path)

    seed = client.post(
        "/api/auth/token",
        headers={
            "X-Actor-Username": "admin",
            "X-Client-Fingerprint": "device-sort-cursor",
        },
    )
    assert seed.status_code == 200
    access_token = seed.json()["access_token"]

    first_page = client.get(
        "/api/admin/auth-throttle?limit=1",
        headers={
            "X-Actor-Username": "admin",
            "Authorization": f"Bearer {access_token}",
        },
    )
    assert first_page.status_code == 200
    cursor = first_page.json()["next_cursor"]
    assert cursor

    invalid_cursor_combo = client.get(
        f"/api/admin/auth-throttle?sort_by=fail_count&cursor={cursor}",
        headers={
            "X-Actor-Username": "admin",
            "Authorization": f"Bearer {access_token}",
        },
    )
    assert invalid_cursor_combo.status_code == 400
