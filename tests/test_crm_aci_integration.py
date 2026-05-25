import importlib
import os
import sys

from fastapi.testclient import TestClient


def _reset_modules() -> None:
    for module_name in ["crm_whatsapp_webhook", "crm_backend"]:
        if module_name in sys.modules:
            del sys.modules[module_name]


def _load_app(tmp_path):
    os.environ["CRM_DATA_DIR"] = str(tmp_path / "data")
    os.environ["CRM_DB_PATH"] = str(tmp_path / "crm.sqlite3")
    os.environ["CRM_WHATSAPP_HMAC_SECRET"] = "test-hmac-secret-32-bytes-minimum-key"
    os.environ["CRM_API_JWT_SECRET"] = "test-jwt-secret-32-bytes-minimum-key"

    _reset_modules()
    crm_backend = importlib.import_module("crm_backend")
    crm_backend.init_database()
    crm_webhook = importlib.import_module("crm_whatsapp_webhook")
    client = TestClient(crm_webhook.app)
    return crm_backend, client


def _auth_headers(crm_backend, username: str) -> dict[str, str]:
    actor = crm_backend.get_user_by_username(username)
    assert actor is not None
    token = crm_backend.create_access_token(actor)
    return {
        "X-Actor-Username": username,
        "Authorization": f"Bearer {token}",
    }


def test_admin_can_connect_list_tools_execute_and_list_calls(tmp_path):
    crm_backend, client = _load_app(tmp_path)

    admin_headers = _auth_headers(crm_backend, "admin")

    start = client.post(
        "/api/aci/connect/start",
        json={
            "provider": "google",
            "tenant_id": "default",
            "redirect_uri": "https://crm.local/aci/callback",
        },
        headers=admin_headers,
    )
    assert start.status_code == 200
    connection_id = start.json()["connection_id"]

    callback = client.post(
        "/api/aci/connect/callback",
        json={
            "connection_id": connection_id,
            "code": "oauth-code-123",
            "state": "invalid-state",
        },
        headers=admin_headers,
    )
    assert callback.status_code == 400

    # use the expected state from start URL
    auth_url = start.json()["authorization_url"]
    expected_state = auth_url.split("state=", 1)[1].split("&", 1)[0]

    callback_ok = client.post(
        "/api/aci/connect/callback",
        json={
            "connection_id": connection_id,
            "code": "oauth-code-123",
            "state": expected_state,
        },
        headers=admin_headers,
    )
    assert callback_ok.status_code == 200
    assert callback_ok.json()["status"] == "active"

    tools = client.get("/api/aci/tools?provider=google", headers=admin_headers)
    assert tools.status_code == 200
    assert any(tool["tool_name"] == "google_calendar" for tool in tools.json()["tools"])

    run_tool = client.post(
        "/api/aci/tool-call",
        json={
            "tenant_id": "default",
            "provider": "google",
            "tool_name": "google_calendar",
            "action_name": "create_event",
            "input": {"title": "Kickoff"},
            "idempotency_key": "ticket-101-google-kickoff",
        },
        headers=admin_headers,
    )
    assert run_tool.status_code == 200
    assert run_tool.json()["status"] == "success"
    first_call_id = run_tool.json()["call_id"]

    replay = client.post(
        "/api/aci/tool-call",
        json={
            "tenant_id": "default",
            "provider": "google",
            "tool_name": "google_calendar",
            "action_name": "create_event",
            "input": {"title": "Kickoff"},
            "idempotency_key": "ticket-101-google-kickoff",
        },
        headers=admin_headers,
    )
    assert replay.status_code == 200
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["call_id"] == first_call_id

    rows = client.get("/api/aci/tool-calls?limit=20", headers=admin_headers)
    assert rows.status_code == 200
    assert rows.json()["rows"]
    assert rows.json()["rows"][0]["call_id"] == first_call_id


def test_non_admin_cannot_start_connection(tmp_path):
    crm_backend, client = _load_app(tmp_path)
    atendimento_headers = _auth_headers(crm_backend, "atendimento")

    start = client.post(
        "/api/aci/connect/start",
        json={
            "provider": "google",
            "tenant_id": "default",
            "redirect_uri": "https://crm.local/aci/callback",
        },
        headers=atendimento_headers,
    )
    assert start.status_code == 403


def test_non_admin_can_execute_but_cannot_read_calls(tmp_path):
    crm_backend, client = _load_app(tmp_path)
    admin_headers = _auth_headers(crm_backend, "admin")
    atendimento_headers = _auth_headers(crm_backend, "atendimento")

    # admin prepares active connection for admin user only
    actor = crm_backend.get_user_by_username("admin")
    assert actor is not None
    start = crm_backend.start_aci_connection(
        provider="google",
        tenant_id="default",
        redirect_uri="https://crm.local/aci/callback",
        actor=actor,
        source="test-setup",
    )
    state = start["authorization_url"].split("state=", 1)[1].split("&", 1)[0]
    crm_backend.complete_aci_connection(
        connection_id=start["connection_id"],
        code="oauth-code-setup",
        state=state,
        actor=actor,
        source="test-setup",
    )

    run_tool = client.post(
        "/api/aci/tool-call",
        json={
            "tenant_id": "default",
            "provider": "google",
            "tool_name": "google_calendar",
            "action_name": "list_events",
            "input": {},
        },
        headers=atendimento_headers,
    )
    assert run_tool.status_code == 200
    assert run_tool.json()["status"] == "failed"
    assert run_tool.json()["error_code"] == "connection_not_active"

    list_calls = client.get("/api/aci/tool-calls", headers=atendimento_headers)
    assert list_calls.status_code == 403

    admin_list_calls = client.get("/api/aci/tool-calls", headers=admin_headers)
    assert admin_list_calls.status_code == 200
