"""WhatsApp webhook receiver for Mr.Holmes CRM."""

from __future__ import annotations

import base64
import json

from fastapi import FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel

from crm_backend import (
    clear_auth_throttle,
    consume_auth_attempt,
    create_access_token,
    create_refresh_token,
    get_auth_throttle_page,
    get_auth_throttle_metrics,
    get_auth_throttle_snapshot,
    get_user_by_username,
    get_rbac_matrix,
    get_webhook_hmac_secret,
    get_webhook_verify_token,
    has_permission,
    init_database,
    process_whatsapp_webhook,
    revoke_refresh_token,
    revoke_all_refresh_tokens_for_user,
    rotate_refresh_token,
    unlock_auth_throttle,
    register_auth_failure,
    register_auth_success,
    delete_entity,
    update_entity,
    verify_access_token,
    verify_webhook_hmac,
    start_aci_connection,
    complete_aci_connection,
    list_aci_tools,
    execute_aci_tool_call,
    get_aci_tool_calls,
)


init_database()
app = FastAPI(title="Mr.Holmes CRM WhatsApp Webhook", version="1.0.0")


class UpdatePayload(BaseModel):
    updates: dict


class RefreshPayload(BaseModel):
    refresh_token: str


class AuthThrottleClearPayload(BaseModel):
    subject: str | None = None
    endpoint: str | None = None


class AuthThrottleUnlockPayload(BaseModel):
    subject_prefix: str
    endpoint: str | None = None


class AciConnectStartPayload(BaseModel):
    provider: str
    tenant_id: str = "default"
    redirect_uri: str


class AciConnectCallbackPayload(BaseModel):
    connection_id: str
    code: str
    state: str


class AciToolCallPayload(BaseModel):
    tenant_id: str = "default"
    provider: str
    tool_name: str
    action_name: str
    input: dict
    idempotency_key: str | None = None


def _require_client_fingerprint(value: str | None) -> str:
    if not value or not value.strip():
        raise HTTPException(status_code=400, detail="Missing X-Client-Fingerprint header")
    return value.strip()


def _auth_subject(actor_username: str | None) -> str:
    value = (actor_username or "").strip()
    if value:
        return value
    return "anonymous"


def _client_ip(request: Request, x_forwarded_for: str | None) -> str:
    if x_forwarded_for:
        return x_forwarded_for.split(",", 1)[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _auth_subject_with_ip(actor_username: str | None, request: Request, x_forwarded_for: str | None) -> str:
    base = _auth_subject(actor_username)
    ip = _client_ip(request, x_forwarded_for)
    return f"{base}|{ip}"


def _consume_auth_or_429(subject: str, endpoint: str) -> None:
    try:
        consume_auth_attempt(subject, endpoint)
    except ValueError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


def _encode_throttle_cursor(row: dict) -> str:
    payload = {
        "updated_at": row["updated_at"],
        "subject": row["subject"],
        "endpoint": row["endpoint"],
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8")


def _decode_throttle_cursor(cursor: str | None) -> tuple[str | None, str | None, str | None]:
    if not cursor:
        return None, None, None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid cursor") from exc
    updated_at = data.get("updated_at")
    subject = data.get("subject")
    endpoint = data.get("endpoint")
    if not updated_at or subject is None or endpoint is None:
        raise HTTPException(status_code=400, detail="Invalid cursor payload")
    return str(updated_at), str(subject), str(endpoint)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/webhook/whatsapp/hmac-info")
def hmac_info() -> dict[str, str]:
    return {
        "algorithm": "HMAC-SHA256",
        "header": "X-Hub-Signature-256",
        "secret_preview": f"{get_webhook_hmac_secret()[:8]}...",
    }


@app.get("/webhook/whatsapp")
def verify_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> dict[str, str]:
    if hub_mode == "subscribe" and hub_verify_token == get_webhook_verify_token() and hub_challenge:
        return {"challenge": hub_challenge}
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@app.post("/webhook/whatsapp")
async def ingest_whatsapp(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
) -> dict[str, str]:
    raw_body = await request.body()
    if not verify_webhook_hmac(raw_body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    payload = await request.json()
    result = process_whatsapp_webhook(payload)
    return {
        "status": result["status"],
        "customer_id": result["customer_id"],
        "ticket_id": result["ticket_id"],
    }


def _actor_from_header(actor_username: str | None) -> dict[str, str]:
    if not actor_username:
        raise HTTPException(status_code=400, detail="Missing X-Actor-Username header")
    actor = get_user_by_username(actor_username)
    if actor is None:
        raise HTTPException(status_code=404, detail="Actor user not found or inactive")
    return actor


def _bearer_token_from_header(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    value = authorization.strip()
    if not value.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization scheme")
    token = value[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return token


def _authorize_actor(
    actor_username: str | None,
    authorization: str | None,
    required_action: str | None = None,
) -> dict[str, str]:
    actor = _actor_from_header(actor_username)
    token = _bearer_token_from_header(authorization)
    try:
        claims = verify_access_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    if claims.get("sub") != actor["username"]:
        raise HTTPException(status_code=403, detail="Token subject does not match actor header")
    if required_action:
        token_scopes = set(claims.get("scopes", []))
        if required_action not in token_scopes:
            raise HTTPException(status_code=403, detail=f"Token missing scope {required_action}")
        if not has_permission(actor["role"], required_action):
            raise HTTPException(status_code=403, detail=f"Actor has no permission for {required_action}")
    return actor


def _required_action(entity_type: str, operation: str) -> str:
    return f"{entity_type}.{operation}"


@app.post("/api/auth/token")
def create_token(
    request: Request,
    x_actor_username: str | None = Header(default=None),
    x_client_fingerprint: str | None = Header(default=None),
    x_forwarded_for: str | None = Header(default=None),
) -> dict[str, str]:
    endpoint = "/api/auth/token"
    subject = _auth_subject_with_ip(x_actor_username, request, x_forwarded_for)
    _consume_auth_or_429(subject, endpoint)
    try:
        actor = _actor_from_header(x_actor_username)
        client_fingerprint = _require_client_fingerprint(x_client_fingerprint)
        access_token = create_access_token(actor)
        refresh_token = create_refresh_token(actor, client_fingerprint=client_fingerprint)
    except HTTPException:
        register_auth_failure(subject, endpoint)
        raise
    register_auth_success(subject, endpoint)
    return {
        "token_type": "Bearer",
        "access_token": access_token,
        "refresh_token": refresh_token,
    }


@app.post("/api/auth/refresh")
def refresh_token(
    request: Request,
    payload: RefreshPayload,
    x_actor_username: str | None = Header(default=None),
    x_client_fingerprint: str | None = Header(default=None),
    x_forwarded_for: str | None = Header(default=None),
) -> dict[str, str]:
    endpoint = "/api/auth/refresh"
    subject = _auth_subject_with_ip(x_actor_username, request, x_forwarded_for)
    _consume_auth_or_429(subject, endpoint)
    try:
        actor = _actor_from_header(x_actor_username)
        client_fingerprint = _require_client_fingerprint(x_client_fingerprint)
        rotated = rotate_refresh_token(
            payload.refresh_token,
            expected_username=actor["username"],
            client_fingerprint=client_fingerprint,
        )
    except ValueError as exc:
        register_auth_failure(subject, endpoint)
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except HTTPException:
        register_auth_failure(subject, endpoint)
        raise
    access_token = create_access_token(rotated["actor"])
    register_auth_success(subject, endpoint)
    return {
        "token_type": "Bearer",
        "access_token": access_token,
        "refresh_token": rotated["refresh_token"],
    }


@app.post("/api/auth/logout")
def logout(
    request: Request,
    payload: RefreshPayload,
    x_actor_username: str | None = Header(default=None),
    x_client_fingerprint: str | None = Header(default=None),
    x_forwarded_for: str | None = Header(default=None),
) -> dict[str, str]:
    endpoint = "/api/auth/logout"
    subject = _auth_subject_with_ip(x_actor_username, request, x_forwarded_for)
    _consume_auth_or_429(subject, endpoint)
    try:
        actor = _actor_from_header(x_actor_username)
        client_fingerprint = _require_client_fingerprint(x_client_fingerprint)
        revoked = revoke_refresh_token(
            payload.refresh_token,
            actor=actor,
            client_fingerprint=client_fingerprint,
        )
    except HTTPException:
        register_auth_failure(subject, endpoint)
        raise
    if not revoked:
        register_auth_failure(subject, endpoint)
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    register_auth_success(subject, endpoint)
    return {"status": "revoked"}


@app.post("/api/auth/logout-all")
def logout_all(
    x_actor_username: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, str | int]:
    actor = _authorize_actor(x_actor_username, authorization)
    revoked_count = revoke_all_refresh_tokens_for_user(actor["username"], actor=actor)
    return {
        "status": "revoked_all",
        "username": actor["username"],
        "revoked_count": revoked_count,
    }


@app.put("/api/{entity_type}/{entity_id}")
def api_update_entity(
    entity_type: str,
    entity_id: str,
    payload: UpdatePayload,
    x_actor_username: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    actor = _authorize_actor(x_actor_username, authorization, required_action=_required_action(entity_type, "update"))
    try:
        updated = update_entity(
            entity_type=entity_type,
            entity_id=entity_id,
            updates=payload.updates,
            actor=actor,
            source="api-update",
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "updated", "entity_type": entity_type, "entity_id": entity_id, "after": updated}


@app.delete("/api/{entity_type}/{entity_id}")
def api_delete_entity(
    entity_type: str,
    entity_id: str,
    x_actor_username: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    actor = _authorize_actor(x_actor_username, authorization, required_action=_required_action(entity_type, "delete"))
    try:
        before = delete_entity(
            entity_type=entity_type,
            entity_id=entity_id,
            actor=actor,
            source="api-delete",
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "deleted", "entity_type": entity_type, "entity_id": entity_id, "before": before}


@app.get("/api/admin/rbac-matrix")
def api_rbac_matrix(
    x_actor_username: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    actor = _authorize_actor(x_actor_username, authorization, required_action="admin.view")
    matrix = get_rbac_matrix()
    return {
        "status": "ok",
        "requested_by": actor["username"],
        "roles": [{"role": role, "actions": actions} for role, actions in matrix.items()],
    }


@app.get("/api/admin/auth-throttle")
def api_auth_throttle(
    x_actor_username: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
    limit: int = Query(default=200),
    cursor: str | None = Query(default=None),
    subject_prefix: str | None = Query(default=None),
    endpoint: str | None = Query(default=None),
    sort_by: str = Query(default="updated_at"),
    sort_order: str = Query(default="desc"),
) -> dict:
    actor = _authorize_actor(x_actor_username, authorization, required_action="admin.view")
    sort_by_value = (sort_by or "updated_at").strip().lower()
    sort_order_value = (sort_order or "desc").strip().lower()
    if sort_by_value not in {"updated_at", "fail_count", "request_count"}:
        raise HTTPException(status_code=400, detail="Invalid sort_by")
    if sort_order_value not in {"asc", "desc"}:
        raise HTTPException(status_code=400, detail="Invalid sort_order")
    if cursor and not (sort_by_value == "updated_at" and sort_order_value == "desc"):
        raise HTTPException(status_code=400, detail="Cursor is supported only for sort_by=updated_at and sort_order=desc")

    cursor_updated_at, cursor_subject, cursor_endpoint = _decode_throttle_cursor(cursor)
    rows = get_auth_throttle_page(
        limit=limit,
        cursor_updated_at=cursor_updated_at,
        cursor_subject=cursor_subject,
        cursor_endpoint=cursor_endpoint,
        subject_prefix=subject_prefix,
        endpoint_filter=endpoint,
        sort_by=sort_by_value,
        sort_order=sort_order_value,
    )
    metrics = get_auth_throttle_metrics(subject_prefix=subject_prefix, endpoint_filter=endpoint)
    next_cursor = _encode_throttle_cursor(rows[-1]) if rows else None
    return {
        "status": "ok",
        "requested_by": actor["username"],
        "count": len(rows),
        "metrics": metrics,
        "next_cursor": next_cursor,
        "rows": rows,
    }


@app.post("/api/admin/auth-throttle/clear")
def api_auth_throttle_clear(
    payload: AuthThrottleClearPayload,
    x_actor_username: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    actor = _authorize_actor(x_actor_username, authorization, required_action="admin.view")
    deleted = clear_auth_throttle(subject=payload.subject, endpoint=payload.endpoint)
    return {
        "status": "ok",
        "requested_by": actor["username"],
        "deleted": deleted,
    }


@app.post("/api/admin/auth-throttle/unlock")
def api_auth_throttle_unlock(
    payload: AuthThrottleUnlockPayload,
    x_actor_username: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    actor = _authorize_actor(x_actor_username, authorization, required_action="admin.view")
    unlocked = unlock_auth_throttle(subject_prefix=payload.subject_prefix, endpoint=payload.endpoint)
    return {
        "status": "ok",
        "requested_by": actor["username"],
        "unlocked": unlocked,
    }


@app.post("/api/aci/connect/start")
def api_aci_connect_start(
    payload: AciConnectStartPayload,
    x_actor_username: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    actor = _authorize_actor(x_actor_username, authorization, required_action="aci.connect")
    try:
        result = start_aci_connection(
            provider=payload.provider,
            tenant_id=payload.tenant_id,
            redirect_uri=payload.redirect_uri,
            actor=actor,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", **result}


@app.post("/api/aci/connect/callback")
def api_aci_connect_callback(
    payload: AciConnectCallbackPayload,
    x_actor_username: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    actor = _authorize_actor(x_actor_username, authorization, required_action="aci.connect")
    try:
        result = complete_aci_connection(
            connection_id=payload.connection_id,
            code=payload.code,
            state=payload.state,
            actor=actor,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", **result}


@app.get("/api/aci/tools")
def api_aci_tools(
    provider: str | None = Query(default=None),
    x_actor_username: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    actor = _authorize_actor(x_actor_username, authorization, required_action="aci.tools.read")
    rows = list_aci_tools(provider=provider, actor=actor)
    return {
        "status": "ok",
        "requested_by": actor["username"],
        "tools": rows,
    }


@app.post("/api/aci/tool-call")
def api_aci_tool_call(
    payload: AciToolCallPayload,
    x_actor_username: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    actor = _authorize_actor(x_actor_username, authorization, required_action="aci.tools.execute")
    try:
        result = execute_aci_tool_call(
            tenant_id=payload.tenant_id,
            provider=payload.provider,
            tool_name=payload.tool_name,
            action_name=payload.action_name,
            input_payload=payload.input,
            actor=actor,
            idempotency_key=payload.idempotency_key,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@app.get("/api/aci/tool-calls")
def api_aci_tool_calls(
    limit: int = Query(default=50),
    cursor: str | None = Query(default=None),
    status: str | None = Query(default=None),
    tool_name: str | None = Query(default=None),
    x_actor_username: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    actor = _authorize_actor(x_actor_username, authorization, required_action="aci.calls.read")
    result = get_aci_tool_calls(
        actor=actor,
        limit=limit,
        cursor=cursor,
        status_filter=status,
        tool_name=tool_name,
    )
    return {
        "status": "ok",
        "requested_by": actor["username"],
        **result,
    }
