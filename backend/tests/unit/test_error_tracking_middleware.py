"""
Unit tests for Error Tracking Middleware

Tests error handling, categorization, logging, and metrics.
"""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from fastapi import Request, HTTPException, status
from pydantic import ValidationError, BaseModel
from starlette.responses import JSONResponse

from src.middleware.error_tracking import (
    ErrorTrackingMiddleware,
    ErrorMetrics,
    error_metrics,
)


class SampleModel(BaseModel):
    """Sample Pydantic model for validation error testing"""
    name: str
    age: int


@pytest.fixture
def middleware():
    """Create ErrorTrackingMiddleware instance"""
    return ErrorTrackingMiddleware(app=MagicMock(), enable_error_details=False)


@pytest.fixture
def middleware_with_details():
    """Create ErrorTrackingMiddleware with error details enabled"""
    return ErrorTrackingMiddleware(app=MagicMock(), enable_error_details=True)


class TestErrorTrackingMiddlewareDispatch:
    """Test error tracking middleware dispatch"""

    @pytest.mark.asyncio
    async def test_successful_request_passes_through(self, middleware):
        """Test successful request passes through without error handling"""
        request = Mock(spec=Request)
        request.method = "GET"
        request.url.path = "/api/test"

        response = JSONResponse({"data": "success"})

        async def mock_call_next(req):
            return response

        result = await middleware.dispatch(request, mock_call_next)

        assert result == response

    @pytest.mark.asyncio
    async def test_http_exception_client_error_handled(self, middleware, caplog):
        """Test HTTPException with 4xx status is logged as client error"""
        request = Mock(spec=Request)
        request.method = "POST"
        request.url.path = "/api/test"
        request.url = Mock()
        request.url.__str__ = Mock(return_value="http://test.com/api/test")
        request.query_params = {}
        request.headers = {}
        request.state = Mock()
        request.state.correlation_id = "test-corr-123"
        request.state.vendor_id = "vendor-456"

        async def mock_call_next(req):
            raise HTTPException(status_code=404, detail="Not found")

        import logging
        with patch('src.middleware.error_tracking.LogContext'):
            with caplog.at_level(logging.WARNING):
                result = await middleware.dispatch(request, mock_call_next)

                # Verify response
                assert result.status_code == 404
                assert "X-Correlation-ID" in result.headers
                assert result.headers["X-Correlation-ID"] == "test-corr-123"

                # Verify logging
                assert any("Client error" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_http_exception_server_error_handled(self, middleware, caplog):
        """Test HTTPException with 5xx status is logged as server error"""
        request = Mock(spec=Request)
        request.method = "GET"
        request.url.path = "/api/error"
        request.url = Mock()
        request.url.__str__ = Mock(return_value="http://test.com/api/error")
        request.query_params = {}
        request.headers = {}
        request.state = Mock()
        request.state.correlation_id = "error-corr-789"

        async def mock_call_next(req):
            raise HTTPException(status_code=503, detail="Service unavailable")

        import logging
        with patch('src.middleware.error_tracking.LogContext'):
            with caplog.at_level(logging.ERROR):
                result = await middleware.dispatch(request, mock_call_next)

                # Verify response
                assert result.status_code == 503

                # Verify error logging
                assert any("Server error" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_validation_error_handled(self, middleware, caplog):
        """Test Pydantic ValidationError is handled as client error"""
        request = Mock(spec=Request)
        request.method = "POST"
        request.url.path = "/api/validate"
        request.url = Mock()
        request.url.__str__ = Mock(return_value="http://test.com/api/validate")
        request.query_params = {}
        request.headers = {}
        request.state = Mock()
        request.state.correlation_id = "val-corr-123"

        async def mock_call_next(req):
            # Trigger Pydantic validation error
            try:
                SampleModel(name="test", age="invalid")
            except ValidationError as e:
                raise e

        import logging
        with patch('src.middleware.error_tracking.LogContext'):
            with caplog.at_level(logging.WARNING):
                result = await middleware.dispatch(request, mock_call_next)

                # Verify response
                assert result.status_code == 422  # Unprocessable Entity

                # Verify client error logging
                assert any("Client error" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_generic_exception_handled(self, middleware, caplog):
        """Test generic exception is handled as server error"""
        request = Mock(spec=Request)
        request.method = "DELETE"
        request.url.path = "/api/crash"
        request.url = Mock()
        request.url.__str__ = Mock(return_value="http://test.com/api/crash")
        request.query_params = {}
        request.headers = {}
        request.state = Mock()
        request.state.correlation_id = "crash-corr-999"

        async def mock_call_next(req):
            raise RuntimeError("Something went wrong")

        import logging
        with patch('src.middleware.error_tracking.LogContext'):
            with caplog.at_level(logging.ERROR):
                result = await middleware.dispatch(request, mock_call_next)

                # Verify response
                assert result.status_code == 500

                # Verify server error logging with stack trace
                assert any("Server error" in record.message for record in caplog.records)
                assert any("RuntimeError" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_error_without_correlation_id_uses_unknown(self, middleware):
        """Test error handling when correlation_id is missing"""
        request = Mock(spec=Request)
        request.method = "GET"
        request.url.path = "/api/test"
        request.url = Mock()
        request.url.__str__ = Mock(return_value="http://test.com/api/test")
        request.query_params = {}
        request.headers = {}
        request.state = Mock(spec=[])  # No correlation_id attribute

        async def mock_call_next(req):
            raise ValueError("Test error")

        with patch('src.middleware.error_tracking.LogContext'):
            result = await middleware.dispatch(request, mock_call_next)

            # Should use 'unknown' correlation ID
            assert result.headers["X-Correlation-ID"] == "unknown"


class TestCategorizeError:
    """Test error categorization"""

    def test_categorize_http_exception_4xx_as_client_error(self, middleware):
        """Test 4xx HTTPException categorized as client error"""
        exception = HTTPException(status_code=400, detail="Bad request")

        category = middleware._categorize_error(exception)

        assert category == "client_error"

    def test_categorize_http_exception_5xx_as_server_error(self, middleware):
        """Test 5xx HTTPException categorized as server error"""
        exception = HTTPException(status_code=500, detail="Internal error")

        category = middleware._categorize_error(exception)

        assert category == "server_error"

    def test_categorize_validation_error_as_client_error(self, middleware):
        """Test ValidationError categorized as client error"""
        try:
            SampleModel(name="test", age="invalid")
        except ValidationError as e:
            category = middleware._categorize_error(e)
            assert category == "client_error"

    def test_categorize_generic_exception_as_server_error(self, middleware):
        """Test generic exception categorized as server error"""
        exception = RuntimeError("Generic error")

        category = middleware._categorize_error(exception)

        assert category == "server_error"


class TestGetStatusCode:
    """Test status code extraction"""

    def test_get_status_code_from_http_exception(self, middleware):
        """Test status code extracted from HTTPException"""
        exception = HTTPException(status_code=404, detail="Not found")

        status_code = middleware._get_status_code(exception)

        assert status_code == 404

    def test_get_status_code_from_validation_error(self, middleware):
        """Test ValidationError returns 422"""
        try:
            SampleModel(name="test", age="invalid")
        except ValidationError as e:
            status_code = middleware._get_status_code(e)
            assert status_code == 422

    def test_get_status_code_from_generic_exception(self, middleware):
        """Test generic exception returns 500"""
        exception = ValueError("Generic error")

        status_code = middleware._get_status_code(exception)

        assert status_code == 500


class TestBuildErrorContext:
    """Test error context building"""

    def test_build_error_context_with_vendor_id(self, middleware):
        """Test error context includes vendor_id when authenticated"""
        request = Mock(spec=Request)
        request.url = Mock()
        request.url.__str__ = Mock(return_value="http://test.com/api/test?foo=bar")
        request.url.path = "/api/test"
        request.method = "POST"
        request.query_params = {"foo": "bar"}
        request.headers = {"Authorization": "Bearer token"}

        exception = ValueError("Test error")
        vendor_id = "vendor-123"

        context = middleware._build_error_context(
            request=request,
            exception=exception,
            correlation_id="corr-456",
            vendor_id=vendor_id
        )

        assert context["correlation_id"] == "corr-456"
        assert context["vendor_id"] == "vendor-123"
        assert context["method"] == "POST"
        assert context["path"] == "/api/test"
        assert "Test error" in context["error_message"]

    def test_build_error_context_without_vendor_id(self, middleware):
        """Test error context without vendor_id for unauthenticated requests"""
        request = Mock(spec=Request)
        request.url = Mock()
        request.url.__str__ = Mock(return_value="http://test.com/api/public")
        request.url.path = "/api/public"
        request.method = "GET"
        request.query_params = {}
        request.headers = {}

        exception = ValueError("Public error")

        context = middleware._build_error_context(
            request=request,
            exception=exception,
            correlation_id="corr-789",
            vendor_id=None
        )

        assert "vendor_id" not in context
        assert context["correlation_id"] == "corr-789"

    def test_build_error_context_includes_stack_trace_for_server_errors(self, middleware):
        """Test error context includes stack trace for server errors"""
        request = Mock(spec=Request)
        request.url = Mock()
        request.url.__str__ = Mock(return_value="http://test.com/api/error")
        request.url.path = "/api/error"
        request.method = "GET"
        request.query_params = {}
        request.headers = {}

        exception = RuntimeError("Server error")  # Server error

        context = middleware._build_error_context(
            request=request,
            exception=exception,
            correlation_id="corr-999",
            vendor_id=None
        )

        # Server errors should include stack trace
        assert "stack_trace" in context


class TestBuildErrorResponse:
    """Test error response building"""

    def test_build_error_response_for_http_exception(self, middleware):
        """Test error response for HTTPException"""
        exception = HTTPException(status_code=404, detail="Resource not found")

        response = middleware._build_error_response(
            exception=exception,
            status_code=404,
            correlation_id="corr-123"
        )

        assert response["error"] is True
        assert response["correlation_id"] == "corr-123"
        assert response["message"] == "Resource not found"
        assert response["type"] == "http_error"

    def test_build_error_response_for_validation_error(self, middleware):
        """Test error response for ValidationError"""
        try:
            SampleModel(name="test", age="invalid")
        except ValidationError as e:
            response = middleware._build_error_response(
                exception=e,
                status_code=422,
                correlation_id="corr-456"
            )

            assert response["error"] is True
            assert response["message"] == "Validation error"
            assert response["type"] == "validation_error"
            # Details should NOT be included when enable_error_details=False
            assert "details" not in response

    def test_build_error_response_for_validation_error_with_details(self, middleware_with_details):
        """Test error response includes validation details when enabled"""
        try:
            SampleModel(name="test", age="invalid")
        except ValidationError as e:
            response = middleware_with_details._build_error_response(
                exception=e,
                status_code=422,
                correlation_id="corr-789"
            )

            # Details SHOULD be included when enable_error_details=True
            assert "details" in response
            assert len(response["details"]) > 0

    def test_build_error_response_for_generic_exception(self, middleware):
        """Test error response for generic exception"""
        exception = RuntimeError("Something broke")

        response = middleware._build_error_response(
            exception=exception,
            status_code=500,
            correlation_id="corr-999"
        )

        assert response["error"] is True
        assert response["message"] == "Internal server error"
        assert response["type"] == "server_error"
        # Exception details should NOT be included in production
        assert "exception" not in response

    def test_build_error_response_includes_exception_details_when_enabled(self, middleware_with_details):
        """Test error response includes exception details in development"""
        exception = ValueError("Development error")

        response = middleware_with_details._build_error_response(
            exception=exception,
            status_code=500,
            correlation_id="corr-dev"
        )

        # Exception details SHOULD be included when enable_error_details=True
        assert "exception" in response
        assert response["exception"]["type"] == "ValueError"
        assert "Development error" in response["exception"]["message"]


class TestErrorMetrics:
    """Test ErrorMetrics class"""

    def test_error_metrics_init(self):
        """Test ErrorMetrics initialization"""
        metrics = ErrorMetrics()

        assert metrics.error_counts == {}

    def test_record_error(self):
        """Test recording error increments count"""
        metrics = ErrorMetrics()

        metrics.record_error(
            error_type="ValueError",
            error_category="server_error",
            endpoint="/api/test"
        )

        key = "server_error:ValueError:/api/test"
        assert metrics.error_counts[key] == 1

    def test_record_error_increments_existing_count(self):
        """Test recording same error multiple times"""
        metrics = ErrorMetrics()

        metrics.record_error("TypeError", "server_error", "/api/endpoint")
        metrics.record_error("TypeError", "server_error", "/api/endpoint")
        metrics.record_error("TypeError", "server_error", "/api/endpoint")

        key = "server_error:TypeError:/api/endpoint"
        assert metrics.error_counts[key] == 3

    def test_get_metrics_returns_copy(self):
        """Test get_metrics returns copy of error counts"""
        metrics = ErrorMetrics()
        metrics.record_error("ValueError", "client_error", "/api/test")

        counts = metrics.get_metrics()

        # Modifying returned dict should not affect internal state
        counts["new_key"] = 999
        assert "new_key" not in metrics.error_counts

    def test_reset_metrics_clears_counts(self):
        """Test reset_metrics clears all error counts"""
        metrics = ErrorMetrics()
        metrics.record_error("ValueError", "server_error", "/api/test")
        metrics.record_error("TypeError", "client_error", "/api/other")

        assert len(metrics.error_counts) == 2

        metrics.reset_metrics()

        assert len(metrics.error_counts) == 0

    def test_global_error_metrics_instance_exists(self):
        """Test global error_metrics instance is initialized"""
        from src.middleware.error_tracking import error_metrics

        assert error_metrics is not None
        assert isinstance(error_metrics, ErrorMetrics)
