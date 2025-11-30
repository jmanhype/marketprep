"""Unit tests for security headers middleware.

Tests OWASP security headers implementation:
- X-Frame-Options
- X-Content-Type-Options
- X-XSS-Protection
- Strict-Transport-Security (HSTS)
- Content-Security-Policy (CSP)
- Referrer-Policy
- Permissions-Policy
- Information disclosure headers removal
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import Request, Response
from starlette.datastructures import Headers

from src.middleware.security_headers import SecurityHeadersMiddleware


class TestSecurityHeadersBasic:
    """Test basic security headers functionality."""

    @pytest.fixture
    def mock_app(self):
        """Mock ASGI app."""
        return MagicMock()

    @pytest.fixture
    def mock_request(self):
        """Mock request."""
        request = MagicMock(spec=Request)
        request.url.path = "/api/test"
        request.method = "GET"
        return request

    @pytest.fixture
    def mock_response(self):
        """Mock response."""
        response = Response(content="test response", status_code=200)
        return response

    @pytest.mark.asyncio
    async def test_adds_x_frame_options(self, mock_app, mock_request, mock_response):
        """Test X-Frame-Options header is added."""
        middleware = SecurityHeadersMiddleware(app=mock_app)

        call_next = AsyncMock(return_value=mock_response)

        result = await middleware.dispatch(mock_request, call_next)

        assert result.headers.get('X-Frame-Options') == 'DENY'

    @pytest.mark.asyncio
    async def test_adds_x_content_type_options(self, mock_app, mock_request, mock_response):
        """Test X-Content-Type-Options header is added."""
        middleware = SecurityHeadersMiddleware(app=mock_app)

        call_next = AsyncMock(return_value=mock_response)

        result = await middleware.dispatch(mock_request, call_next)

        assert result.headers.get('X-Content-Type-Options') == 'nosniff'

    @pytest.mark.asyncio
    async def test_adds_x_xss_protection(self, mock_app, mock_request, mock_response):
        """Test X-XSS-Protection header is added."""
        middleware = SecurityHeadersMiddleware(app=mock_app)

        call_next = AsyncMock(return_value=mock_response)

        result = await middleware.dispatch(mock_request, call_next)

        assert result.headers.get('X-XSS-Protection') == '1; mode=block'

    @pytest.mark.asyncio
    async def test_adds_referrer_policy(self, mock_app, mock_request, mock_response):
        """Test Referrer-Policy header is added."""
        middleware = SecurityHeadersMiddleware(app=mock_app)

        call_next = AsyncMock(return_value=mock_response)

        result = await middleware.dispatch(mock_request, call_next)

        assert result.headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'

    @pytest.mark.asyncio
    async def test_adds_permissions_policy(self, mock_app, mock_request, mock_response):
        """Test Permissions-Policy header is added."""
        middleware = SecurityHeadersMiddleware(app=mock_app)

        call_next = AsyncMock(return_value=mock_response)

        result = await middleware.dispatch(mock_request, call_next)

        permissions_policy = result.headers.get('Permissions-Policy')
        assert 'geolocation=()' in permissions_policy
        assert 'microphone=()' in permissions_policy
        assert 'camera=()' in permissions_policy
        assert 'payment=()' in permissions_policy

    @pytest.mark.asyncio
    async def test_adds_x_permitted_cross_domain_policies(self, mock_app, mock_request, mock_response):
        """Test X-Permitted-Cross-Domain-Policies header is added."""
        middleware = SecurityHeadersMiddleware(app=mock_app)

        call_next = AsyncMock(return_value=mock_response)

        result = await middleware.dispatch(mock_request, call_next)

        assert result.headers.get('X-Permitted-Cross-Domain-Policies') == 'none'

    @pytest.mark.asyncio
    async def test_adds_x_download_options(self, mock_app, mock_request, mock_response):
        """Test X-Download-Options header is added."""
        middleware = SecurityHeadersMiddleware(app=mock_app)

        call_next = AsyncMock(return_value=mock_response)

        result = await middleware.dispatch(mock_request, call_next)

        assert result.headers.get('X-Download-Options') == 'noopen'


class TestContentSecurityPolicy:
    """Test Content-Security-Policy configurations."""

    @pytest.fixture
    def mock_app(self):
        """Mock ASGI app."""
        return MagicMock()

    @pytest.fixture
    def mock_request(self):
        """Mock request."""
        request = MagicMock(spec=Request)
        request.url.path = "/api/test"
        return request

    @pytest.fixture
    def mock_response(self):
        """Mock response."""
        return Response(content="test", status_code=200)

    @pytest.mark.asyncio
    async def test_moderate_csp_by_default(self, mock_app, mock_request, mock_response):
        """Test moderate CSP is used by default."""
        middleware = SecurityHeadersMiddleware(app=mock_app, enable_strict_csp=False)

        call_next = AsyncMock(return_value=mock_response)

        result = await middleware.dispatch(mock_request, call_next)

        csp = result.headers.get('Content-Security-Policy')
        assert "'unsafe-inline'" in csp
        assert "'unsafe-eval'" in csp
        assert "frame-ancestors 'none'" in csp

    @pytest.mark.asyncio
    async def test_strict_csp_when_enabled(self, mock_app, mock_request, mock_response):
        """Test strict CSP when explicitly enabled."""
        middleware = SecurityHeadersMiddleware(app=mock_app, enable_strict_csp=True)

        call_next = AsyncMock(return_value=mock_response)

        result = await middleware.dispatch(mock_request, call_next)

        csp = result.headers.get('Content-Security-Policy')
        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp
        assert "style-src 'self'" in csp
        assert "'unsafe-inline'" not in csp
        assert "'unsafe-eval'" not in csp
        assert "frame-ancestors 'none'" in csp
        assert "base-uri 'self'" in csp
        assert "form-action 'self'" in csp


class TestHSTSHeader:
    """Test Strict-Transport-Security header."""

    @pytest.fixture
    def mock_app(self):
        """Mock ASGI app."""
        return MagicMock()

    @pytest.fixture
    def mock_request(self):
        """Mock request."""
        request = MagicMock(spec=Request)
        request.url.path = "/api/test"
        return request

    @pytest.fixture
    def mock_response(self):
        """Mock response."""
        return Response(content="test", status_code=200)

    @pytest.mark.asyncio
    async def test_hsts_added_in_production(self, mock_app, mock_request, mock_response):
        """Test HSTS header is added in production."""
        with patch('src.middleware.security_headers.settings') as mock_settings:
            mock_settings.environment = 'production'

            middleware = SecurityHeadersMiddleware(app=mock_app)

            call_next = AsyncMock(return_value=mock_response)

            result = await middleware.dispatch(mock_request, call_next)

            hsts = result.headers.get('Strict-Transport-Security')
            assert hsts == 'max-age=31536000; includeSubDomains; preload'

    @pytest.mark.asyncio
    async def test_hsts_not_added_in_development(self, mock_app, mock_request, mock_response):
        """Test HSTS header is not added in development."""
        with patch('src.middleware.security_headers.settings') as mock_settings:
            mock_settings.environment = 'development'

            middleware = SecurityHeadersMiddleware(app=mock_app)

            call_next = AsyncMock(return_value=mock_response)

            result = await middleware.dispatch(mock_request, call_next)

            assert 'Strict-Transport-Security' not in result.headers


class TestInformationDisclosure:
    """Test removal of information disclosure headers."""

    @pytest.fixture
    def mock_app(self):
        """Mock ASGI app."""
        return MagicMock()

    @pytest.fixture
    def mock_request(self):
        """Mock request."""
        request = MagicMock(spec=Request)
        request.url.path = "/api/test"
        return request

    @pytest.mark.asyncio
    async def test_removes_server_header(self, mock_app, mock_request):
        """Test Server header is removed."""
        response = Response(content="test", status_code=200)
        response.headers['Server'] = 'uvicorn'

        middleware = SecurityHeadersMiddleware(app=mock_app)
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(mock_request, call_next)

        assert 'Server' not in result.headers

    @pytest.mark.asyncio
    async def test_removes_x_powered_by_header(self, mock_app, mock_request):
        """Test X-Powered-By header is removed."""
        response = Response(content="test", status_code=200)
        response.headers['X-Powered-By'] = 'FastAPI'

        middleware = SecurityHeadersMiddleware(app=mock_app)
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(mock_request, call_next)

        assert 'X-Powered-By' not in result.headers

    @pytest.mark.asyncio
    async def test_handles_response_without_disclosure_headers(self, mock_app, mock_request):
        """Test handles response that doesn't have disclosure headers."""
        response = Response(content="test", status_code=200)
        # No Server or X-Powered-By headers

        middleware = SecurityHeadersMiddleware(app=mock_app)
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(mock_request, call_next)

        # Should not error, just skip deletion
        assert 'Server' not in result.headers
        assert 'X-Powered-By' not in result.headers


class TestCompleteHeaderSet:
    """Test that all security headers are applied together."""

    @pytest.fixture
    def mock_app(self):
        """Mock ASGI app."""
        return MagicMock()

    @pytest.fixture
    def mock_request(self):
        """Mock request."""
        request = MagicMock(spec=Request)
        request.url.path = "/api/test"
        return request

    @pytest.mark.asyncio
    async def test_all_security_headers_present(self, mock_app, mock_request):
        """Test all security headers are present in response."""
        response = Response(content="test", status_code=200)
        response.headers['Server'] = 'test-server'
        response.headers['X-Powered-By'] = 'test-framework'

        middleware = SecurityHeadersMiddleware(app=mock_app, enable_strict_csp=False)
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(mock_request, call_next)

        # Check all expected headers are present
        expected_headers = [
            'X-Frame-Options',
            'X-Content-Type-Options',
            'X-XSS-Protection',
            'Content-Security-Policy',
            'Referrer-Policy',
            'Permissions-Policy',
            'X-Permitted-Cross-Domain-Policies',
            'X-Download-Options',
        ]

        for header in expected_headers:
            assert header in result.headers, f"Missing security header: {header}"

        # Check disclosure headers are removed
        assert 'Server' not in result.headers
        assert 'X-Powered-By' not in result.headers

    @pytest.mark.asyncio
    async def test_headers_do_not_affect_response_body(self, mock_app, mock_request):
        """Test security headers don't modify response body."""
        original_body = b"Test response body with special chars: <script>alert('xss')</script>"
        response = Response(content=original_body, status_code=200)

        middleware = SecurityHeadersMiddleware(app=mock_app)
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(mock_request, call_next)

        assert result.body == original_body

    @pytest.mark.asyncio
    async def test_headers_do_not_affect_status_code(self, mock_app, mock_request):
        """Test security headers don't modify status code."""
        response = Response(content="Not Found", status_code=404)

        middleware = SecurityHeadersMiddleware(app=mock_app)
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(mock_request, call_next)

        assert result.status_code == 404

    @pytest.mark.asyncio
    async def test_headers_applied_to_error_responses(self, mock_app, mock_request):
        """Test security headers are applied to error responses."""
        error_response = Response(content="Internal Server Error", status_code=500)

        middleware = SecurityHeadersMiddleware(app=mock_app)
        call_next = AsyncMock(return_value=error_response)

        result = await middleware.dispatch(mock_request, call_next)

        # Security headers should still be present on error responses
        assert result.headers.get('X-Frame-Options') == 'DENY'
        assert result.headers.get('X-Content-Type-Options') == 'nosniff'
        assert result.headers.get('Content-Security-Policy') is not None
