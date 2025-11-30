"""Unit tests for request logging middleware.

Tests request/response logging with correlation ID tracking:
- Correlation ID generation and propagation
- Request started logging
- Response completed logging with duration
- Error logging with exception details
- Client IP extraction from various headers
"""
import logging
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch, call
from fastapi import Request, Response
from starlette.datastructures import Headers

from src.middleware.request_logging import RequestLoggingMiddleware


class TestRequestLoggingBasic:
    """Test basic request logging functionality."""

    @pytest.fixture
    def mock_app(self):
        """Mock ASGI app."""
        return MagicMock()

    @pytest.fixture
    def mock_request(self):
        """Mock request."""
        request = MagicMock(spec=Request)
        request.method = "GET"
        request.url.path = "/api/test"
        request.query_params = {"foo": "bar", "baz": "qux"}
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.100"
        request.state = MagicMock()
        return request

    @pytest.fixture
    def mock_response(self):
        """Mock response."""
        response = Response(content="test response", status_code=200)
        return response

    @pytest.mark.asyncio
    async def test_generates_correlation_id(self, mock_app, mock_request, mock_response):
        """Test correlation ID is generated for each request."""
        middleware = RequestLoggingMiddleware(app=mock_app)
        call_next = AsyncMock(return_value=mock_response)

        with patch('src.middleware.request_logging.uuid.uuid4') as mock_uuid:
            mock_uuid.return_value.hex = 'test-correlation-id'
            mock_uuid.return_value.__str__ = MagicMock(return_value='test-correlation-id')

            await middleware.dispatch(mock_request, call_next)

            # Check correlation ID was set on request state
            assert mock_request.state.correlation_id == 'test-correlation-id'

    @pytest.mark.asyncio
    async def test_adds_correlation_id_to_response_headers(self, mock_app, mock_request, mock_response):
        """Test correlation ID is added to response headers."""
        middleware = RequestLoggingMiddleware(app=mock_app)
        call_next = AsyncMock(return_value=mock_response)

        with patch('src.middleware.request_logging.uuid.uuid4') as mock_uuid:
            mock_uuid.return_value.__str__ = MagicMock(return_value='test-correlation-id')

            result = await middleware.dispatch(mock_request, call_next)

            assert result.headers.get('X-Correlation-ID') == 'test-correlation-id'

    @pytest.mark.asyncio
    async def test_logs_request_started(self, mock_app, mock_request, mock_response, caplog):
        """Test request started is logged."""
        middleware = RequestLoggingMiddleware(app=mock_app)
        call_next = AsyncMock(return_value=mock_response)

        with caplog.at_level(logging.INFO):
            await middleware.dispatch(mock_request, call_next)

            # Check log message
            assert any('Request started: GET /api/test' in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_logs_query_params(self, mock_app, mock_request, mock_response, caplog):
        """Test query parameters are logged."""
        middleware = RequestLoggingMiddleware(app=mock_app)
        call_next = AsyncMock(return_value=mock_response)

        with caplog.at_level(logging.INFO):
            with patch('src.middleware.request_logging.logger.info') as mock_log:
                await middleware.dispatch(mock_request, call_next)

                # Find the request_started log call
                request_started_call = None
                for c in mock_log.call_args_list:
                    if 'Request started' in c[0][0]:
                        request_started_call = c
                        break

                assert request_started_call is not None
                assert 'extra' in request_started_call[1]
                assert request_started_call[1]['extra']['query_params'] == {"foo": "bar", "baz": "qux"}

    @pytest.mark.asyncio
    async def test_logs_request_completed(self, mock_app, mock_request, mock_response, caplog):
        """Test request completed is logged with status code."""
        middleware = RequestLoggingMiddleware(app=mock_app)
        call_next = AsyncMock(return_value=mock_response)

        with caplog.at_level(logging.INFO):
            await middleware.dispatch(mock_request, call_next)

            # Check log message includes status code
            assert any('[200]' in record.message for record in caplog.records)
            assert any('Request completed' in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_logs_duration(self, mock_app, mock_request, mock_response):
        """Test request duration is logged."""
        middleware = RequestLoggingMiddleware(app=mock_app)

        # Mock call_next to take some time
        async def slow_call_next(request):
            await AsyncMock(return_value=None)()  # Simulate async work
            return mock_response

        with patch('src.middleware.request_logging.logger.info') as mock_log:
            await middleware.dispatch(mock_request, slow_call_next)

            # Find the request_completed log call
            completed_call = None
            for c in mock_log.call_args_list:
                if 'Request completed' in c[0][0]:
                    completed_call = c
                    break

            assert completed_call is not None
            assert 'extra' in completed_call[1]
            assert 'duration_ms' in completed_call[1]['extra']
            # Duration should be a positive number
            assert completed_call[1]['extra']['duration_ms'] >= 0

    @pytest.mark.asyncio
    async def test_uses_log_context(self, mock_app, mock_request, mock_response):
        """Test LogContext is used with correct fields."""
        middleware = RequestLoggingMiddleware(app=mock_app)
        call_next = AsyncMock(return_value=mock_response)

        with patch('src.middleware.request_logging.LogContext') as mock_log_context:
            mock_context = MagicMock()
            mock_log_context.return_value.__enter__ = MagicMock(return_value=mock_context)
            mock_log_context.return_value.__exit__ = MagicMock(return_value=None)

            await middleware.dispatch(mock_request, call_next)

            # Check LogContext was called with correct fields
            assert mock_log_context.called
            call_kwargs = mock_log_context.call_args[1]
            assert 'correlation_id' in call_kwargs
            assert call_kwargs['request_method'] == 'GET'
            assert call_kwargs['request_path'] == '/api/test'
            assert call_kwargs['request_ip'] == '192.168.1.100'


class TestErrorLogging:
    """Test error logging functionality."""

    @pytest.fixture
    def mock_app(self):
        """Mock ASGI app."""
        return MagicMock()

    @pytest.fixture
    def mock_request(self):
        """Mock request."""
        request = MagicMock(spec=Request)
        request.method = "POST"
        request.url.path = "/api/error"
        request.query_params = {}
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.100"
        request.state = MagicMock()
        return request

    @pytest.mark.asyncio
    async def test_logs_error_on_exception(self, mock_app, mock_request, caplog):
        """Test errors are logged when exceptions occur."""
        middleware = RequestLoggingMiddleware(app=mock_app)

        # Mock call_next to raise an exception
        async def error_call_next(request):
            raise ValueError("Test error")

        with caplog.at_level(logging.ERROR):
            with pytest.raises(ValueError, match="Test error"):
                await middleware.dispatch(mock_request, error_call_next)

            # Check error was logged
            assert any('Request failed' in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_logs_error_details(self, mock_app, mock_request):
        """Test error details are included in log."""
        middleware = RequestLoggingMiddleware(app=mock_app)

        async def error_call_next(request):
            raise RuntimeError("Database connection failed")

        with patch('src.middleware.request_logging.logger.error') as mock_log:
            with pytest.raises(RuntimeError):
                await middleware.dispatch(mock_request, error_call_next)

            # Check error details in log
            assert mock_log.called
            call_kwargs = mock_log.call_args[1]
            assert call_kwargs['exc_info'] is True
            assert 'extra' in call_kwargs
            assert call_kwargs['extra']['error_type'] == 'RuntimeError'
            assert call_kwargs['extra']['error_message'] == 'Database connection failed'

    @pytest.mark.asyncio
    async def test_re_raises_exception(self, mock_app, mock_request):
        """Test exceptions are re-raised after logging."""
        middleware = RequestLoggingMiddleware(app=mock_app)

        async def error_call_next(request):
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            await middleware.dispatch(mock_request, error_call_next)

    @pytest.mark.asyncio
    async def test_logs_duration_on_error(self, mock_app, mock_request):
        """Test duration is still logged when error occurs."""
        middleware = RequestLoggingMiddleware(app=mock_app)

        async def error_call_next(request):
            raise ValueError("Test error")

        with patch('src.middleware.request_logging.logger.error') as mock_log:
            with pytest.raises(ValueError):
                await middleware.dispatch(mock_request, error_call_next)

            # Check duration was logged
            call_kwargs = mock_log.call_args[1]
            assert 'extra' in call_kwargs
            assert 'duration_ms' in call_kwargs['extra']
            assert call_kwargs['extra']['duration_ms'] >= 0


class TestClientIPExtraction:
    """Test client IP address extraction."""

    @pytest.fixture
    def mock_app(self):
        """Mock ASGI app."""
        return MagicMock()

    @pytest.fixture
    def mock_response(self):
        """Mock response."""
        return Response(content="test", status_code=200)

    @pytest.mark.asyncio
    async def test_extracts_ip_from_x_forwarded_for(self, mock_app, mock_response):
        """Test IP is extracted from X-Forwarded-For header."""
        request = MagicMock(spec=Request)
        request.method = "GET"
        request.url.path = "/api/test"
        request.query_params = {}
        request.headers = {"X-Forwarded-For": "203.0.113.1, 198.51.100.1"}
        request.client = MagicMock()
        request.client.host = "192.168.1.1"
        request.state = MagicMock()

        middleware = RequestLoggingMiddleware(app=mock_app)
        call_next = AsyncMock(return_value=mock_response)

        with patch('src.middleware.request_logging.LogContext') as mock_log_context:
            await middleware.dispatch(request, call_next)

            # Check IP from X-Forwarded-For was used (first in chain)
            call_kwargs = mock_log_context.call_args[1]
            assert call_kwargs['request_ip'] == '203.0.113.1'

    @pytest.mark.asyncio
    async def test_extracts_ip_from_x_real_ip(self, mock_app, mock_response):
        """Test IP is extracted from X-Real-IP header."""
        request = MagicMock(spec=Request)
        request.method = "GET"
        request.url.path = "/api/test"
        request.query_params = {}
        request.headers = {"X-Real-IP": "203.0.113.5"}
        request.client = MagicMock()
        request.client.host = "192.168.1.1"
        request.state = MagicMock()

        middleware = RequestLoggingMiddleware(app=mock_app)
        call_next = AsyncMock(return_value=mock_response)

        with patch('src.middleware.request_logging.LogContext') as mock_log_context:
            await middleware.dispatch(request, call_next)

            # Check IP from X-Real-IP was used
            call_kwargs = mock_log_context.call_args[1]
            assert call_kwargs['request_ip'] == '203.0.113.5'

    @pytest.mark.asyncio
    async def test_x_forwarded_for_takes_precedence(self, mock_app, mock_response):
        """Test X-Forwarded-For takes precedence over X-Real-IP."""
        request = MagicMock(spec=Request)
        request.method = "GET"
        request.url.path = "/api/test"
        request.query_params = {}
        request.headers = {
            "X-Forwarded-For": "203.0.113.1",
            "X-Real-IP": "203.0.113.5"
        }
        request.client = MagicMock()
        request.client.host = "192.168.1.1"
        request.state = MagicMock()

        middleware = RequestLoggingMiddleware(app=mock_app)
        call_next = AsyncMock(return_value=mock_response)

        with patch('src.middleware.request_logging.LogContext') as mock_log_context:
            await middleware.dispatch(request, call_next)

            # Check X-Forwarded-For was used, not X-Real-IP
            call_kwargs = mock_log_context.call_args[1]
            assert call_kwargs['request_ip'] == '203.0.113.1'

    @pytest.mark.asyncio
    async def test_falls_back_to_client_host(self, mock_app, mock_response):
        """Test falls back to direct client IP when headers not present."""
        request = MagicMock(spec=Request)
        request.method = "GET"
        request.url.path = "/api/test"
        request.query_params = {}
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.50"
        request.state = MagicMock()

        middleware = RequestLoggingMiddleware(app=mock_app)
        call_next = AsyncMock(return_value=mock_response)

        with patch('src.middleware.request_logging.LogContext') as mock_log_context:
            await middleware.dispatch(request, call_next)

            # Check client.host was used
            call_kwargs = mock_log_context.call_args[1]
            assert call_kwargs['request_ip'] == '192.168.1.50'

    @pytest.mark.asyncio
    async def test_handles_missing_client(self, mock_app, mock_response):
        """Test handles case where client is None."""
        request = MagicMock(spec=Request)
        request.method = "GET"
        request.url.path = "/api/test"
        request.query_params = {}
        request.headers = {}
        request.client = None
        request.state = MagicMock()

        middleware = RequestLoggingMiddleware(app=mock_app)
        call_next = AsyncMock(return_value=mock_response)

        with patch('src.middleware.request_logging.LogContext') as mock_log_context:
            await middleware.dispatch(request, call_next)

            # Check "unknown" was used
            call_kwargs = mock_log_context.call_args[1]
            assert call_kwargs['request_ip'] == 'unknown'

    @pytest.mark.asyncio
    async def test_handles_whitespace_in_forwarded_for(self, mock_app, mock_response):
        """Test whitespace is stripped from X-Forwarded-For."""
        request = MagicMock(spec=Request)
        request.method = "GET"
        request.url.path = "/api/test"
        request.query_params = {}
        request.headers = {"X-Forwarded-For": "  203.0.113.1  , 198.51.100.1"}
        request.client = None
        request.state = MagicMock()

        middleware = RequestLoggingMiddleware(app=mock_app)
        call_next = AsyncMock(return_value=mock_response)

        with patch('src.middleware.request_logging.LogContext') as mock_log_context:
            await middleware.dispatch(request, call_next)

            # Check IP was stripped of whitespace
            call_kwargs = mock_log_context.call_args[1]
            assert call_kwargs['request_ip'] == '203.0.113.1'
