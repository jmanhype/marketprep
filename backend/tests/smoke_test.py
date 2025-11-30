"""Smoke tests for MarketPrep application.

Quick sanity checks to verify basic functionality.
"""
import pytest
from uuid import uuid4
from fastapi.testclient import TestClient


class TestApplicationSmoke:
    """Smoke tests for application startup and basic endpoints."""

    def test_app_imports_successfully(self) -> None:
        """Application should import without errors."""
        from src.main import app

        assert app is not None
        assert app.title == "MarketPrep API"

    def test_health_endpoint_accessible(self) -> None:
        """Health endpoint should be accessible without auth."""
        from src.main import app

        client = TestClient(app)
        response = client.get("/health")

        # Should return 200 or 503 (depending on services)
        assert response.status_code in [200, 503]

    def test_root_endpoint_returns_app_info(self) -> None:
        """Root endpoint should return app info."""
        from src.main import app

        client = TestClient(app)
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert "app" in data
        assert "version" in data
        assert data["app"] == "MarketPrep API"

    def test_openapi_docs_accessible(self) -> None:
        """OpenAPI docs should be accessible in debug mode."""
        from src.main import app

        client = TestClient(app)
        response = client.get("/api/docs")

        # Should be accessible (200) or redirect if debug=False
        assert response.status_code in [200, 404, 307]


class TestModelsSmoke:
    """Smoke tests for database models."""

    def test_vendor_model_imports(self) -> None:
        """Vendor model should import successfully."""
        from src.models.vendor import Vendor

        assert Vendor is not None

    def test_product_model_imports(self) -> None:
        """Product model should import successfully."""
        from src.models.product import Product

        assert Product is not None

    def test_recommendation_model_imports(self) -> None:
        """Recommendation model should import successfully."""
        from src.models.recommendation import Recommendation

        assert Recommendation is not None

    def test_venue_model_imports(self) -> None:
        """Venue model should import successfully."""
        from src.models.venue import Venue

        assert Venue is not None


class TestServicesSmoke:
    """Smoke tests for core services."""

    def test_auth_service_imports(self) -> None:
        """AuthService should import successfully."""
        from src.services.auth_service import AuthService

        service = AuthService()
        assert service is not None

    def test_auth_service_generates_tokens(self) -> None:
        """AuthService should generate valid tokens."""
        from src.services.auth_service import AuthService

        service = AuthService()
        vendor_id = uuid4()

        access_token = service.generate_access_token(
            vendor_id=vendor_id,
            email="test@example.com",
        )
        refresh_token = service.generate_refresh_token(vendor_id=vendor_id)

        assert isinstance(access_token, str)
        assert len(access_token) > 0
        assert access_token.count(".") == 2  # Valid JWT format

        assert isinstance(refresh_token, str)
        assert len(refresh_token) > 0
        assert refresh_token.count(".") == 2


class TestRoutersSmoke:
    """Smoke tests for routers."""

    def test_auth_router_imports(self) -> None:
        """Auth router should import successfully."""
        from src.routers import auth

        assert auth.router is not None

    def test_recommendations_router_imports(self) -> None:
        """Recommendations router should import successfully."""
        from src.routers import recommendations

        assert recommendations.router is not None

    def test_products_router_imports(self) -> None:
        """Products router should import successfully."""
        from src.routers import products

        assert products.router is not None

    def test_venues_router_imports(self) -> None:
        """Venues router should import successfully."""
        from src.routers import venues

        assert venues.router is not None

    def test_vendors_router_imports(self) -> None:
        """Vendors router should import successfully."""
        from src.routers import vendors

        assert vendors.router is not None

    def test_audit_router_imports(self) -> None:
        """Audit router should import successfully."""
        from src.routers import audit

        assert audit.router is not None

    def test_webhooks_router_imports(self) -> None:
        """Webhooks router should import successfully."""
        from src.routers import webhooks

        assert webhooks.router is not None


class TestConfigSmoke:
    """Smoke tests for configuration."""

    def test_settings_loads(self) -> None:
        """Settings should load from environment."""
        from src.config import settings

        assert settings is not None
        assert settings.app_name == "MarketPrep API"
        assert settings.app_version is not None

    def test_database_url_configured(self) -> None:
        """Database URL should be configured."""
        from src.config import settings

        assert settings.database_url is not None
        assert "postgresql" in str(settings.database_url)

    def test_redis_url_configured(self) -> None:
        """Redis URL should be configured."""
        from src.config import settings

        assert settings.redis_url is not None
        assert "redis" in str(settings.redis_url)


class TestMiddlewareSmoke:
    """Smoke tests for middleware."""

    def test_auth_middleware_imports(self) -> None:
        """Auth middleware should import successfully."""
        from src.middleware import auth

        assert auth is not None

    def test_rate_limit_middleware_imports(self) -> None:
        """Rate limit middleware should import successfully."""
        from src.middleware import rate_limit

        assert rate_limit is not None

    def test_security_headers_middleware_imports(self) -> None:
        """Security headers middleware should import successfully."""
        from src.middleware import security_headers

        assert security_headers is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
