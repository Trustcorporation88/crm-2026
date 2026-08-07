"""
Regression tests for defects found in the v2.0 API layer.

Each test here maps to a specific bug that shipped in crm_api.py and its
supporting modules. They exist to keep those failures from silently returning.
"""

import logging
import uuid

import jwt
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from crm_api import app, get_redis
from structured_logging import StructuredLogger


client = TestClient(app)

JWT_SECRET = "change-me-in-production"


def _token(**overrides) -> str:
    payload = {
        "username": "test_user",
        "user_id": "u-1",
        "role": "admin",
        # Unique per call: tests that revoke a token must not invalidate the
        # token another test is still using.
        "jti": str(uuid.uuid4()),
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    payload.update(overrides)
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


class TestRequestBodySurvivesMiddleware:
    """
    The Prometheus middleware used to read the request body and then swap in a
    receive() returning http.disconnect, leaving the endpoint with an empty
    body. Every POST/PUT/PATCH route was effectively broken.
    """

    def test_post_body_reaches_endpoint(self):
        response = client.post(
            "/webhooks/whatsapp",
            json={
                "event_type": "message_received",
                "channel": "whatsapp",
                "source_id": "customer_42",
                "payload": {"message": "body must survive the middleware"},
            },
        )
        assert response.status_code == 200
        # A truncated body would have produced a 422 from model validation.
        assert response.json()["event_type"] == "message_received"


class TestTokenRevocation:
    """
    /auth/logout wrote the token to a Redis blacklist that nothing ever read,
    so logging out did not actually invalidate the session.
    """

    def test_logout_actually_revokes_the_token(self):
        token = _token()
        headers = {"Authorization": f"Bearer {token}"}

        # Token works before logout.
        assert client.get("/api/integrations", headers=headers).status_code == 200

        assert client.post("/auth/logout", headers=headers).status_code == 200

        # ...and is rejected afterwards.
        after = client.get("/api/integrations", headers=headers)
        assert after.status_code == 401

    def test_revoked_token_cannot_be_refreshed(self):
        token = _token()
        headers = {"Authorization": f"Bearer {token}"}

        client.post("/auth/logout", headers=headers)

        refreshed = client.post("/auth/refresh", headers=headers)
        assert refreshed.status_code == 401


class TestAuthorizationStatusCodes:
    """
    Role checks raised ValidationError(status_code=...), which that class does
    not accept, and the surrounding `except Exception` re-wrapped the result as
    a generic error. Permission denials surfaced as 500s.
    """

    def test_non_admin_gets_403_not_500(self):
        headers = {"Authorization": f"Bearer {_token(role='vendas')}"}
        response = client.get("/api/admin/users", headers=headers)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "AUTHORIZATION_ERROR"

    def test_admin_still_allowed(self):
        headers = {"Authorization": f"Bearer {_token(role='admin')}"}
        assert client.get("/api/admin/users", headers=headers).status_code == 200


class TestErrorHandlerLogging:
    """
    The CRMException handler logged with extra={"message": ...}, colliding with
    a reserved LogRecord attribute and raising KeyError from inside the error
    handler itself.
    """

    def test_domain_error_is_rendered_not_crashed(self):
        headers = {"Authorization": f"Bearer {_token(role='vendas')}"}
        response = client.get("/api/admin/logs", headers=headers)
        assert response.status_code == 403
        body = response.json()
        assert body["error"]["message"] == "Admin access required"

    def test_reserved_log_keys_do_not_raise(self, caplog):
        logger = StructuredLogger("regression_probe")
        with caplog.at_level(logging.INFO):
            # Each of these collides with a reserved LogRecord attribute and
            # used to raise KeyError from inside the logging call.
            logger.info("probe", name="n", module="mod", args="a", lineno=1)
        assert "probe" in caplog.text


class TestMetricsEndpoint:
    """
    /metrics returned raw bytes through the JSON encoder, so Prometheus could
    not scrape it.
    """

    def test_metrics_served_as_prometheus_text(self):
        response = client.get("/metrics")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert "http_requests_total" in response.text


class TestHealthEndpoint:
    def test_health_reports_components(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["components"] == {"database": "up", "redis": "up"}


class TestCacheInvalidation:
    """
    redis.delete("customers:*") does not expand globs, so the customer list
    cache was never invalidated after a write.
    """

    def test_create_customer_clears_list_cache(self):
        headers = {"Authorization": f"Bearer {_token()}"}
        redis_client = get_redis()

        # Populate the cache via the list endpoint.
        assert client.get("/api/customers", headers=headers).status_code == 200
        assert redis_client.keys("customers:*")

        payload = {
            "customer_id": "C-REG",
            "name": "Regression Co",
            "segment": "Tech",
            "city": "São Paulo",
            "country": "Brasil",
            "owner": "Test User",
            "status": "Active",
            "health_score": 80,
            "lifetime_value": 1000,
            "last_purchase": "2026-05-25",
            "channel": "Email",
            "next_action": "Follow up",
            "source": "Inbound",
        }
        assert client.post("/api/customers", json=payload, headers=headers).status_code == 200

        assert redis_client.keys("customers:*") == []
