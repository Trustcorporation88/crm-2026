"""
Basic tests for Mr.Holmes CRM API
"""

import pytest
from fastapi.testclient import TestClient
from crm_api import app

client = TestClient(app)

@pytest.fixture
def valid_token():
    """Generate a valid JWT token for testing"""
    import jwt
    from datetime import datetime, timedelta, timezone
    
    payload = {
        "username": "test_user",
        "role": "admin",
        "exp": datetime.now(timezone.utc) + timedelta(hours=24)
    }
    return jwt.encode(payload, "change-me-in-production", algorithm="HS256")

class TestHealth:
    """Health check tests"""
    
    def test_health_check(self):
        """Test API health endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

class TestAuth:
    """Authentication tests"""
    
    def test_login_placeholder(self):
        """Test login endpoint returns placeholder"""
        response = client.post(
            "/auth/login",
            json={"username": "admin", "password": "admin123"}
        )
        assert response.status_code in [401, 500]
    
    def test_logout_requires_auth(self):
        """Test logout requires valid token"""
        response = client.post("/auth/logout")
        assert response.status_code == 403

class TestCustomers:
    """Customer endpoint tests"""
    
    def test_list_customers_requires_auth(self):
        """Test customers endpoint requires authentication"""
        response = client.get("/api/customers")
        assert response.status_code == 403
    
    def test_create_customer_requires_auth(self):
        """Test creating customer requires authentication"""
        response = client.post(
            "/api/customers",
            json={
                "customer_id": "C-TEST",
                "name": "Test Company",
                "segment": "Tech",
                "city": "São Paulo",
                "country": "Brasil",
                "owner": "Test User",
                "status": "Active",
                "health_score": 85,
                "lifetime_value": 100000,
                "last_purchase": "2026-05-25",
                "channel": "Email",
                "next_action": "Follow up",
                "source": "Inbound"
            }
        )
        assert response.status_code == 403

class TestTickets:
    """Ticket endpoint tests"""
    
    def test_list_tickets_requires_auth(self):
        """Test tickets endpoint requires authentication"""
        response = client.get("/api/tickets")
        assert response.status_code == 403

class TestDeals:
    """Deal endpoint tests"""
    
    def test_list_deals_requires_auth(self):
        """Test deals endpoint requires authentication"""
        response = client.get("/api/deals")
        assert response.status_code == 403

class TestWebhooks:
    """Webhook endpoint tests"""
    
    def test_whatsapp_webhook(self):
        """Test WhatsApp webhook receives messages"""
        response = client.post(
            "/webhooks/whatsapp",
            json={
                "event_type": "message_received",
                "channel": "whatsapp",
                "source_id": "customer_123",
                "payload": {"message": "Test message"}
            }
        )
        assert response.status_code == 200
    
    def test_email_webhook(self):
        """Test Email webhook receives messages"""
        response = client.post(
            "/webhooks/email",
            json={
                "event_type": "email_received",
                "channel": "email",
                "source_id": "customer_123",
                "payload": {"subject": "Test", "body": "Test email"}
            }
        )
        assert response.status_code == 200

class TestIntegrations:
    """Integration endpoint tests"""
    
    def test_list_integrations_requires_auth(self):
        """Test integrations list requires authentication"""
        response = client.get("/api/integrations")
        assert response.status_code == 403

class TestReports:
    """Report endpoint tests"""
    
    def test_dashboard_report_requires_auth(self):
        """Test dashboard report requires authentication"""
        response = client.get("/api/reports/dashboard")
        assert response.status_code == 403

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
