"""
Smoke tests for API health and basic functionality.

These tests verify that the API is up and running with basic functionality.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.smoke
class TestAPIHealth:
    """Smoke tests for API health endpoints."""

    def test_root_endpoint_returns_200(self):
        """Root endpoint should return 200 and app info."""
        from src.main import app

        client = TestClient(app)
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert "app" in data
        assert data["app"] == "MarketPrep API"
        assert "status" in data
        assert data["status"] == "running"

    def test_health_endpoint_returns_200(self):
        """Health endpoint should return 200."""
        from src.main import app

        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_metrics_endpoint_exists(self):
        """Metrics endpoint should be accessible."""
        from src.main import app

        client = TestClient(app)
        response = client.get("/metrics")

        # Should return 200 with Prometheus metrics
        assert response.status_code == 200
        assert "http_requests_total" in response.text


@pytest.mark.smoke
class TestDatabaseConnection:
    """Smoke tests for database connectivity."""

    def test_database_connection_works(self, db_session):
        """Database connection should work."""
        from sqlalchemy import text

        result = db_session.execute(text("SELECT 1 as test"))
        row = result.fetchone()
        assert row[0] == 1

    def test_can_query_vendors_table(self, db_session):
        """Should be able to query vendors table."""
        from sqlalchemy import text

        # This will fail if table doesn't exist or connection is broken
        result = db_session.execute(text("SELECT COUNT(*) FROM vendors"))
        count = result.scalar()
        assert count is not None
        assert count >= 0


@pytest.mark.smoke
class TestAuthenticationFlow:
    """Smoke tests for authentication."""

    def test_can_register_and_login(self, test_client):
        """Full authentication flow should work."""
        from uuid import uuid4

        # Register a new vendor
        unique_email = f"smoke-test-{uuid4()}@example.com"
        register_data = {
            "email": unique_email,
            "password": "SecurePassword123!",
            "business_name": "Smoke Test Farm",
        }

        register_response = test_client.post("/api/v1/auth/register", json=register_data)
        assert register_response.status_code == 201

        # Login with the new vendor
        login_data = {
            "email": unique_email,
            "password": "SecurePassword123!",
        }

        login_response = test_client.post("/api/v1/auth/login", json=login_data)
        assert login_response.status_code == 200
        assert "access_token" in login_response.json()
        assert "refresh_token" in login_response.json()
