"""
Unit tests for Audit Trail Middleware

Tests audit logging functionality:
- Request/response logging for compliance
- Skip conditions (health checks, static assets, OPTIONS)
- Action determination (CREATE, UPDATE, DELETE, LOGIN, etc.)
- Resource extraction from URLs
- Sensitive endpoint detection
- Audit trail error handling
- Manual audit logging helper
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from fastapi import Request, FastAPI
from starlette.responses import Response

from src.middleware.audit import (
    AuditTrailMiddleware,
    add_audit_log,
)
from src.models.audit_log import AuditAction


class TestAuditTrailMiddleware:
    """Test audit middleware functionality"""

    @pytest.fixture
    def app(self):
        """Create FastAPI app"""
        return FastAPI()

    @pytest.fixture
    def middleware(self, app):
        """Create middleware instance"""
        return AuditTrailMiddleware(app)

    @pytest.mark.asyncio
    async def test_middleware_skip_health_paths(self, middleware):
        """Test skip paths bypass audit logging"""
        skip_paths = ["/health", "/health/ready", "/docs", "/openapi.json", "/redoc", "/metrics"]

        for path in skip_paths:
            request = MagicMock(spec=Request)
            request.url.path = path
            call_next = AsyncMock(return_value=Response())

            response = await middleware.dispatch(request, call_next)

            call_next.assert_called_once_with(request)
            call_next.reset_mock()

    @pytest.mark.asyncio
    async def test_middleware_skip_static_assets(self, middleware):
        """Test static asset paths are skipped"""
        request = MagicMock(spec=Request)
        request.url.path = "/static/css/main.css"
        call_next = AsyncMock(return_value=Response())

        response = await middleware.dispatch(request, call_next)

        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_middleware_skip_options_requests(self, middleware):
        """Test OPTIONS requests (CORS preflight) are skipped"""
        request = MagicMock(spec=Request)
        request.url.path = "/api/items"
        request.method = "OPTIONS"
        call_next = AsyncMock(return_value=Response())

        response = await middleware.dispatch(request, call_next)

        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    @patch('src.middleware.audit.SessionLocal')
    @patch('src.middleware.audit.AuditService')
    async def test_middleware_logs_post_request(self, mock_audit_service, mock_session, middleware):
        """Test POST request is logged to audit trail"""
        request = MagicMock(spec=Request)
        request.url.path = "/api/products"
        request.method = "POST"
        request.state.vendor_id = "vendor123"
        request.state.user_email = "vendor@example.com"
        request.query_params = {}

        call_next = AsyncMock(return_value=Response(status_code=201))

        response = await middleware.dispatch(request, call_next)

        # Verify audit service was called
        mock_session.assert_called_once()
        mock_audit_service.assert_called_once()

    @pytest.mark.asyncio
    @patch('src.middleware.audit.SessionLocal')
    @patch('src.middleware.audit.logger')
    async def test_middleware_handles_logging_errors(self, mock_logger, mock_session, middleware):
        """Test middleware handles audit logging errors gracefully"""
        # Make SessionLocal raise an exception
        mock_session.side_effect = Exception("Database error")

        request = MagicMock(spec=Request)
        request.url.path = "/api/products"
        request.method = "POST"
        request.state.vendor_id = "vendor123"
        request.query_params = {}

        call_next = AsyncMock(return_value=Response())

        # Should not raise, but log error
        response = await middleware.dispatch(request, call_next)

        assert response is not None
        mock_logger.error.assert_called()

    def test_should_skip_audit_health_check(self, middleware):
        """Test _should_skip_audit returns True for health checks"""
        request = MagicMock(spec=Request)
        request.url.path = "/health"

        should_skip = middleware._should_skip_audit(request)

        assert should_skip is True

    def test_should_skip_audit_static(self, middleware):
        """Test _should_skip_audit returns True for static files"""
        request = MagicMock(spec=Request)
        request.url.path = "/static/image.png"

        should_skip = middleware._should_skip_audit(request)

        assert should_skip is True

    def test_should_skip_audit_options(self, middleware):
        """Test _should_skip_audit returns True for OPTIONS"""
        request = MagicMock(spec=Request)
        request.url.path = "/api/items"
        request.method = "OPTIONS"

        should_skip = middleware._should_skip_audit(request)

        assert should_skip is True

    def test_should_skip_audit_regular_request(self, middleware):
        """Test _should_skip_audit returns False for regular requests"""
        request = MagicMock(spec=Request)
        request.url.path = "/api/products"
        request.method = "GET"

        should_skip = middleware._should_skip_audit(request)

        assert should_skip is False


class TestDetermineAction:
    """Test action determination from requests"""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance"""
        app = FastAPI()
        return AuditTrailMiddleware(app)

    def test_determine_action_login(self, middleware):
        """Test login action detection"""
        request = MagicMock(spec=Request)
        request.method = "POST"
        request.url.path = "/auth/login"

        action = middleware._determine_action(request)

        assert action == AuditAction.LOGIN

    def test_determine_action_logout(self, middleware):
        """Test logout action detection"""
        request = MagicMock(spec=Request)
        request.method = "POST"
        request.url.path = "/auth/logout"

        action = middleware._determine_action(request)

        assert action == AuditAction.LOGOUT

    def test_determine_action_register(self, middleware):
        """Test registration action detection"""
        request = MagicMock(spec=Request)
        request.method = "POST"
        request.url.path = "/auth/register"

        action = middleware._determine_action(request)

        assert action == AuditAction.CREATE  # Account registration is a CREATE

    def test_determine_action_data_export(self, middleware):
        """Test data export action detection"""
        request = MagicMock(spec=Request)
        request.method = "GET"
        request.url.path = "/vendors/me/data-export"

        action = middleware._determine_action(request)

        assert action == AuditAction.DATA_EXPORT_REQUESTED

    def test_determine_action_account_deletion(self, middleware):
        """Test account deletion action detection"""
        request = MagicMock(spec=Request)
        request.method = "DELETE"
        request.url.path = "/vendors/me"

        action = middleware._determine_action(request)

        assert action == AuditAction.DATA_DELETION_REQUESTED

    def test_determine_action_create(self, middleware):
        """Test CREATE action for POST requests"""
        request = MagicMock(spec=Request)
        request.method = "POST"
        request.url.path = "/api/products"

        action = middleware._determine_action(request)

        assert action == AuditAction.CREATE

    def test_determine_action_update_put(self, middleware):
        """Test UPDATE action for PUT requests"""
        request = MagicMock(spec=Request)
        request.method = "PUT"
        request.url.path = "/api/products/123"

        action = middleware._determine_action(request)

        assert action == AuditAction.UPDATE

    def test_determine_action_update_patch(self, middleware):
        """Test UPDATE action for PATCH requests"""
        request = MagicMock(spec=Request)
        request.method = "PATCH"
        request.url.path = "/api/products/123"

        action = middleware._determine_action(request)

        assert action == AuditAction.UPDATE

    def test_determine_action_delete(self, middleware):
        """Test DELETE action"""
        request = MagicMock(spec=Request)
        request.method = "DELETE"
        request.url.path = "/api/products/123"

        action = middleware._determine_action(request)

        assert action == AuditAction.DELETE

    def test_determine_action_view(self, middleware):
        """Test VIEW action for GET with ID"""
        request = MagicMock(spec=Request)
        request.method = "GET"
        request.url.path = "/api/products/550e8400-e29b-41d4-a716-446655440000"

        action = middleware._determine_action(request)

        assert action == AuditAction.VIEW

    def test_determine_action_list(self, middleware):
        """Test SEARCH action for GET without ID"""
        request = MagicMock(spec=Request)
        request.method = "GET"
        request.url.path = "/api/products"

        action = middleware._determine_action(request)

        assert action == AuditAction.SEARCH  # List operations are logged as SEARCH


class TestExtractResourceInfo:
    """Test resource extraction from URLs"""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance"""
        app = FastAPI()
        return AuditTrailMiddleware(app)

    def test_extract_resource_simple_path(self, middleware):
        """Test resource extraction from simple path"""
        request = MagicMock(spec=Request)
        request.url.path = "/products"

        resource_type, resource_id = middleware._extract_resource_info(request)

        assert resource_type == "products"
        assert resource_id is None

    def test_extract_resource_with_uuid(self, middleware):
        """Test resource extraction with UUID"""
        uuid = "550e8400-e29b-41d4-a716-446655440000"
        request = MagicMock(spec=Request)
        request.url.path = f"/products/{uuid}"

        resource_type, resource_id = middleware._extract_resource_info(request)

        assert resource_type == "products"
        assert resource_id == uuid

    def test_extract_resource_with_api_prefix(self, middleware):
        """Test resource extraction with /api prefix"""
        request = MagicMock(spec=Request)
        request.url.path = "/api/products"

        resource_type, resource_id = middleware._extract_resource_info(request)

        assert resource_type == "products"

    def test_extract_resource_with_version(self, middleware):
        """Test resource extraction with version prefix"""
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/products"

        resource_type, resource_id = middleware._extract_resource_info(request)

        assert resource_type == "products"

    def test_extract_resource_nested_path(self, middleware):
        """Test resource extraction from nested path"""
        uuid = "550e8400-e29b-41d4-a716-446655440000"
        request = MagicMock(spec=Request)
        request.url.path = f"/vendors/{uuid}/products"

        resource_type, resource_id = middleware._extract_resource_info(request)

        assert resource_type == "vendors"
        assert resource_id == uuid  # Should find first UUID

    def test_extract_resource_empty_path(self, middleware):
        """Test resource extraction from empty/root path"""
        request = MagicMock(spec=Request)
        request.url.path = "/"

        resource_type, resource_id = middleware._extract_resource_info(request)

        assert resource_type is None or resource_type == ""
        assert resource_id is None


class TestGetRequestData:
    """Test request data extraction"""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance"""
        app = FastAPI()
        return AuditTrailMiddleware(app)

    def test_get_request_data_with_query_params(self, middleware):
        """Test extracting query parameters"""
        request = MagicMock(spec=Request)
        request.query_params = {"search": "test", "limit": "10"}

        data = middleware._get_request_data(request)

        assert data == {"search": "test", "limit": "10"}

    def test_get_request_data_no_params(self, middleware):
        """Test extraction with no query params"""
        request = MagicMock(spec=Request)
        request.query_params = {}

        data = middleware._get_request_data(request)

        assert data is None

    @patch('src.middleware.audit.logger')
    def test_get_request_data_exception_handling(self, mock_logger, middleware):
        """Test exception handling in data extraction"""
        request = MagicMock(spec=Request)
        request.query_params = MagicMock()
        request.query_params.__bool__ = MagicMock(side_effect=Exception("Error"))

        data = middleware._get_request_data(request)

        assert data is None
        mock_logger.warning.assert_called()


class TestIsSensitiveEndpoint:
    """Test sensitive endpoint detection"""

    @pytest.fixture
    def middleware(self):
        """Create middleware instance"""
        app = FastAPI()
        return AuditTrailMiddleware(app)

    def test_is_sensitive_auth(self, middleware):
        """Test auth endpoints are sensitive"""
        is_sensitive = middleware._is_sensitive_endpoint("/auth/login")

        assert is_sensitive is True

    def test_is_sensitive_vendor_me(self, middleware):
        """Test /vendors/me is sensitive"""
        is_sensitive = middleware._is_sensitive_endpoint("/vendors/me")

        assert is_sensitive is True

    def test_is_sensitive_square(self, middleware):
        """Test Square OAuth endpoints are sensitive"""
        is_sensitive = middleware._is_sensitive_endpoint("/square/callback")

        assert is_sensitive is True

    def test_is_sensitive_feedback(self, middleware):
        """Test feedback endpoints are sensitive"""
        is_sensitive = middleware._is_sensitive_endpoint("/feedback")

        assert is_sensitive is True

    def test_is_sensitive_data_export(self, middleware):
        """Test GDPR export is sensitive"""
        is_sensitive = middleware._is_sensitive_endpoint("/vendors/me/data-export")

        assert is_sensitive is True

    def test_is_not_sensitive_regular_endpoint(self, middleware):
        """Test regular endpoints are not sensitive"""
        is_sensitive = middleware._is_sensitive_endpoint("/api/products")

        assert is_sensitive is False


class TestAddAuditLog:
    """Test manual audit logging helper function"""

    @patch('src.middleware.audit.AuditService')
    def test_add_audit_log_success(self, mock_audit_service):
        """Test successful audit log addition"""
        mock_db = MagicMock()

        add_audit_log(
            db=mock_db,
            vendor_id="vendor123",
            action=AuditAction.UPDATE,
            user_email="vendor@example.com",
            resource_type="product",
            resource_id="product123",
            old_values={"name": "Old"},
            new_values={"name": "New"},
            changes_summary="Updated name",
        )

        mock_audit_service.assert_called_once_with(mock_db)
        mock_audit_service.return_value.log_action.assert_called_once()

    @patch('src.middleware.audit.AuditService')
    def test_add_audit_log_with_request(self, mock_audit_service):
        """Test audit log with request object"""
        mock_db = MagicMock()
        mock_request = MagicMock(spec=Request)

        add_audit_log(
            db=mock_db,
            vendor_id="vendor123",
            action=AuditAction.CREATE,
            request=mock_request,
        )

        mock_audit_service.return_value.log_action.assert_called_once()
        call_kwargs = mock_audit_service.return_value.log_action.call_args[1]
        assert call_kwargs["request"] == mock_request

    @patch('src.middleware.audit.AuditService')
    def test_add_audit_log_sensitive_data(self, mock_audit_service):
        """Test audit log with sensitive flag"""
        mock_db = MagicMock()

        add_audit_log(
            db=mock_db,
            vendor_id="vendor123",
            action=AuditAction.VIEW,
            is_sensitive=True,
        )

        call_kwargs = mock_audit_service.return_value.log_action.call_args[1]
        assert call_kwargs["is_sensitive"] is True

    @patch('src.middleware.audit.AuditService')
    @patch('src.middleware.audit.logger')
    def test_add_audit_log_handles_errors(self, mock_logger, mock_audit_service):
        """Test error handling in manual audit logging"""
        mock_db = MagicMock()
        mock_audit_service.side_effect = Exception("Database error")

        # Should not raise
        add_audit_log(
            db=mock_db,
            vendor_id="vendor123",
            action=AuditAction.CREATE,
        )

        mock_logger.error.assert_called()

    @patch('src.middleware.audit.AuditService')
    def test_add_audit_log_minimal_params(self, mock_audit_service):
        """Test audit log with only required parameters"""
        mock_db = MagicMock()

        add_audit_log(
            db=mock_db,
            vendor_id="vendor123",
            action=AuditAction.VIEW,  # Use valid enum value
        )

        mock_audit_service.assert_called_once_with(mock_db)
        call_kwargs = mock_audit_service.return_value.log_action.call_args[1]
        assert call_kwargs["vendor_id"] == "vendor123"
        assert call_kwargs["action"] == AuditAction.VIEW
