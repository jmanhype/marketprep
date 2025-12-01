"""
Unit tests for Request Logging Middleware

Tests correlation IDs, structured logging, and request/response logging.
"""

import pytest
import logging
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from fastapi import Request
from starlette.responses import Response, JSONResponse

from src.middleware.logging import (
    RequestLoggingMiddleware,
    StructuredLogger,
    get_logger,
    configure_logging,
)


@pytest.fixture
def middleware():
    """Create RequestLoggingMiddleware instance"""
    return RequestLoggingMiddleware(app=MagicMock())


class TestRequestLoggingMiddlewareDispatch:
    """Test request logging middleware dispatch"""

    @pytest.mark.asyncio
    async def test_successful_request_logs_and_adds_correlation_id(self, middleware, caplog):
        """Test successful request logs and adds correlation ID to response"""
        # Mock request
        request = Mock(spec=Request)
        request.method = "GET"
        request.url.path = "/api/products"
        request.query_params = {}
        request.client = Mock()
        request.client.host = "192.168.1.100"
        request.headers = {"user-agent": "TestClient/1.0"}
        request.state = Mock()

        # Mock response
        response = JSONResponse({"data": "test"})

        async def mock_call_next(req):
            return response

        with caplog.at_level(logging.INFO):
            result = await middleware.dispatch(request, mock_call_next)

            # Verify response has correlation ID header
            assert "X-Correlation-ID" in result.headers
            correlation_id = result.headers["X-Correlation-ID"]
            assert correlation_id is not None

            # Verify request.state has correlation ID
            assert request.state.correlation_id == correlation_id

            # Verify logging
            assert any("Request started" in record.message for record in caplog.records)
            assert any("Request completed" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_request_with_existing_correlation_id_uses_it(self, middleware):
        """Test request with existing X-Correlation-ID header uses it"""
        existing_correlation_id = "test-correlation-123"

        request = Mock(spec=Request)
        request.method = "POST"
        request.url.path = "/api/sales"
        request.query_params = {}
        request.client = Mock()
        request.client.host = "10.0.0.1"
        request.headers = {
            "X-Correlation-ID": existing_correlation_id,
            "user-agent": "TestApp/2.0"
        }
        request.state = Mock()

        response = JSONResponse({"status": "ok"})

        async def mock_call_next(req):
            return response

        result = await middleware.dispatch(request, mock_call_next)

        # Verify existing correlation ID was used
        assert result.headers["X-Correlation-ID"] == existing_correlation_id
        assert request.state.correlation_id == existing_correlation_id

    @pytest.mark.asyncio
    async def test_request_without_client_logs_none_for_host(self, middleware, caplog):
        """Test request without client object logs None for client_host"""
        request = Mock(spec=Request)
        request.method = "GET"
        request.url.path = "/api/test"
        request.query_params = {}
        request.client = None  # No client
        request.headers = {}
        request.state = Mock()

        response = JSONResponse({})

        async def mock_call_next(req):
            return response

        with caplog.at_level(logging.INFO):
            result = await middleware.dispatch(request, mock_call_next)

            # Should log successfully even without client
            assert "Request started" in caplog.text
            assert "Request completed" in caplog.text

    @pytest.mark.asyncio
    async def test_request_exception_logs_error(self, middleware, caplog):
        """Test exception during request logs error with correlation ID"""
        request = Mock(spec=Request)
        request.method = "POST"
        request.url.path = "/api/error"
        request.query_params = {}
        request.client = Mock()
        request.client.host = "127.0.0.1"
        request.headers = {}
        request.state = Mock()

        # Mock call_next that raises exception
        async def mock_call_next(req):
            raise ValueError("Test error")

        with caplog.at_level(logging.ERROR):
            with pytest.raises(ValueError, match="Test error"):
                await middleware.dispatch(request, mock_call_next)

            # Verify error was logged
            assert any("Request failed" in record.message for record in caplog.records)
            assert any("ValueError" in record.message for record in caplog.records)


class TestGetOrCreateCorrelationId:
    """Test correlation ID generation"""

    def test_get_or_create_correlation_id_with_existing_header(self, middleware):
        """Test correlation ID extracted from header"""
        existing_id = "external-correlation-456"

        request = Mock(spec=Request)
        request.headers = {"X-Correlation-ID": existing_id}

        correlation_id = middleware._get_or_create_correlation_id(request)

        assert correlation_id == existing_id

    def test_get_or_create_correlation_id_generates_new_uuid(self, middleware):
        """Test new correlation ID is generated when header is missing"""
        request = Mock(spec=Request)
        request.headers = {}

        correlation_id = middleware._get_or_create_correlation_id(request)

        # Should be a valid UUID string
        assert isinstance(correlation_id, str)
        assert len(correlation_id) == 36  # UUID format with dashes
        assert correlation_id.count("-") == 4


class TestStructuredLogger:
    """Test StructuredLogger class"""

    def test_structured_logger_init_with_correlation_id(self):
        """Test StructuredLogger initializes with correlation ID from request"""
        request = Mock(spec=Request)
        request.state = Mock()
        request.state.correlation_id = "test-corr-123"

        logger = StructuredLogger(request)

        assert logger.correlation_id == "test-corr-123"

    def test_structured_logger_init_without_correlation_id(self):
        """Test StructuredLogger handles missing correlation ID gracefully"""
        request = Mock(spec=Request)
        request.state = Mock(spec=[])  # No correlation_id attribute

        logger = StructuredLogger(request)

        assert logger.correlation_id is None

    def test_structured_logger_info(self, caplog):
        """Test StructuredLogger.info logs with correlation ID"""
        request = Mock(spec=Request)
        request.state = Mock()
        request.state.correlation_id = "info-test-id"

        logger = StructuredLogger(request)

        with caplog.at_level(logging.INFO):
            logger.info("Test info message", user_id="user-123")

            assert "Test info message" in caplog.text

    def test_structured_logger_debug(self, caplog):
        """Test StructuredLogger.debug logs with DEBUG level"""
        request = Mock(spec=Request)
        request.state = Mock()
        request.state.correlation_id = "debug-test-id"

        logger = StructuredLogger(request)

        with caplog.at_level(logging.DEBUG):
            logger.debug("Debug message", action="testing")

            assert "Debug message" in caplog.text

    def test_structured_logger_warning(self, caplog):
        """Test StructuredLogger.warning logs with WARNING level"""
        request = Mock(spec=Request)
        request.state = Mock()
        request.state.correlation_id = "warn-test-id"

        logger = StructuredLogger(request)

        with caplog.at_level(logging.WARNING):
            logger.warning("Warning message", severity="medium")

            assert "Warning message" in caplog.text

    def test_structured_logger_error(self, caplog):
        """Test StructuredLogger.error logs with ERROR level"""
        request = Mock(spec=Request)
        request.state = Mock()
        request.state.correlation_id = "error-test-id"

        logger = StructuredLogger(request)

        with caplog.at_level(logging.ERROR):
            logger.error("Error message", error_code="E500")

            assert "Error message" in caplog.text


class TestGetLoggerDependency:
    """Test get_logger FastAPI dependency"""

    def test_get_logger_returns_structured_logger(self):
        """Test get_logger returns StructuredLogger instance"""
        request = Mock(spec=Request)
        request.state = Mock()
        request.state.correlation_id = "dep-test-id"

        logger = get_logger(request)

        assert isinstance(logger, StructuredLogger)
        assert logger.correlation_id == "dep-test-id"


class TestConfigureLogging:
    """Test configure_logging function"""

    @pytest.fixture(autouse=True)
    def cleanup_logging(self):
        """Save and restore root logger state for each test"""
        root_logger = logging.getLogger()
        original_level = root_logger.level
        original_handlers = root_logger.handlers.copy()

        yield

        # Restore original state
        root_logger.setLevel(original_level)
        root_logger.handlers.clear()
        for handler in original_handlers:
            root_logger.addHandler(handler)

    def test_configure_logging_production_json_format(self):
        """Test production environment uses JSON formatter"""
        with patch('src.config.settings') as mock_settings:
            mock_settings.environment = "production"
            mock_settings.log_level = "INFO"

            # Call configure_logging
            configure_logging()

            # Verify root logger configuration
            root_logger = logging.getLogger()
            assert root_logger.level == logging.INFO
            assert len(root_logger.handlers) == 1

            # Verify handler
            handler = root_logger.handlers[0]
            assert isinstance(handler, logging.StreamHandler)
            assert handler.level == logging.INFO

            # Verify formatter creates JSON output
            formatter = handler.formatter
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg="Test message",
                args=(),
                exc_info=None
            )
            formatted = formatter.format(record)

            # Should be valid JSON
            import json
            parsed = json.loads(formatted)
            assert parsed["level"] == "INFO"
            assert parsed["message"] == "Test message"

    def test_configure_logging_development_human_readable_format(self):
        """Test development environment uses human-readable formatter"""
        with patch('src.config.settings') as mock_settings:
            mock_settings.environment = "development"
            mock_settings.log_level = "DEBUG"

            # Call configure_logging
            configure_logging()

            # Verify root logger configuration
            root_logger = logging.getLogger()
            assert root_logger.level == logging.DEBUG
            assert len(root_logger.handlers) == 1

            # Verify handler
            handler = root_logger.handlers[0]
            assert isinstance(handler, logging.StreamHandler)
            assert handler.level == logging.DEBUG

    def test_configure_logging_json_formatter_with_correlation_id(self):
        """Test JSON formatter includes correlation_id from record"""
        with patch('src.config.settings') as mock_settings:
            mock_settings.environment = "production"
            mock_settings.log_level = "INFO"

            configure_logging()

            # Get formatter
            handler = logging.getLogger().handlers[0]
            formatter = handler.formatter

            # Create record with correlation_id
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg="Test message",
                args=(),
                exc_info=None
            )
            record.correlation_id = "test-corr-123"

            formatted = formatter.format(record)

            import json
            parsed = json.loads(formatted)
            assert parsed["correlation_id"] == "test-corr-123"

    def test_configure_logging_json_formatter_with_request_fields(self):
        """Test JSON formatter includes method, path, duration_ms"""
        with patch('src.config.settings') as mock_settings:
            mock_settings.environment = "production"
            mock_settings.log_level = "INFO"

            configure_logging()

            # Get formatter
            handler = logging.getLogger().handlers[0]
            formatter = handler.formatter

            # Create record with request fields
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg="Request completed",
                args=(),
                exc_info=None
            )
            record.method = "GET"
            record.path = "/api/test"
            record.duration_ms = 125.5

            formatted = formatter.format(record)

            import json
            parsed = json.loads(formatted)
            assert parsed["method"] == "GET"
            assert parsed["path"] == "/api/test"
            assert parsed["duration_ms"] == 125.5

    def test_configure_logging_json_formatter_with_exception(self):
        """Test JSON formatter includes exception info"""
        with patch('src.config.settings') as mock_settings:
            mock_settings.environment = "production"
            mock_settings.log_level = "INFO"

            configure_logging()

            # Get formatter
            handler = logging.getLogger().handlers[0]
            formatter = handler.formatter

            # Create record with exception
            try:
                raise ValueError("Test exception")
            except ValueError:
                import sys
                exc_info = sys.exc_info()

                record = logging.LogRecord(
                    name="test",
                    level=logging.ERROR,
                    pathname="",
                    lineno=0,
                    msg="Error occurred",
                    args=(),
                    exc_info=exc_info
                )

                formatted = formatter.format(record)

                import json
                parsed = json.loads(formatted)
                assert "exception" in parsed
                assert "ValueError" in parsed["exception"]
                assert "Test exception" in parsed["exception"]

    def test_configure_logging_clears_existing_handlers(self):
        """Test configure_logging clears existing handlers"""
        # Add a dummy handler
        root_logger = logging.getLogger()
        dummy_handler = logging.StreamHandler()
        root_logger.addHandler(dummy_handler)

        initial_handler_count = len(root_logger.handlers)
        assert initial_handler_count > 0

        with patch('src.config.settings') as mock_settings:
            mock_settings.environment = "development"
            mock_settings.log_level = "INFO"

            configure_logging()

            # Should have exactly 1 handler (old ones cleared)
            assert len(root_logger.handlers) == 1
            assert root_logger.handlers[0] != dummy_handler

    def test_configure_logging_reduces_third_party_noise(self):
        """Test third-party loggers are set to WARNING level"""
        with patch('src.config.settings') as mock_settings:
            mock_settings.environment = "development"
            mock_settings.log_level = "DEBUG"

            configure_logging()

            # Verify third-party loggers have WARNING level
            uvicorn_logger = logging.getLogger("uvicorn.access")
            sqlalchemy_logger = logging.getLogger("sqlalchemy.engine")

            assert uvicorn_logger.level == logging.WARNING
            assert sqlalchemy_logger.level == logging.WARNING
