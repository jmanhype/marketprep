"""
Unit tests for Metrics Middleware

Tests HTTP request tracking and Prometheus metrics collection.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from starlette.datastructures import Headers

from src.middleware.metrics_middleware import MetricsMiddleware


@pytest.fixture
def middleware():
    """Create MetricsMiddleware instance with mocked app"""
    return MetricsMiddleware(app=MagicMock())


class TestMetricsMiddlewareDispatch:
    """Test metrics collection during request dispatch"""

    @pytest.mark.asyncio
    async def test_successful_request_records_metrics(self, middleware):
        """Test successful request records all metrics"""

        # Mock request
        request = Mock(spec=Request)
        request.url.path = "/api/products"
        request.method = "GET"

        # Mock response
        response = JSONResponse({"products": []})
        response.body = b'{"products":[]}'

        # Mock call_next
        async def mock_call_next(req):
            return response

        # Mock Prometheus metrics
        with patch('src.middleware.metrics_middleware.http_requests_in_progress') as mock_in_progress, \
             patch('src.middleware.metrics_middleware.http_requests_total') as mock_total, \
             patch('src.middleware.metrics_middleware.http_request_duration_seconds') as mock_duration, \
             patch('src.middleware.metrics_middleware.http_response_size_bytes') as mock_size:

            # Configure mocks
            mock_in_progress_gauge = MagicMock()
            mock_in_progress.labels.return_value = mock_in_progress_gauge

            mock_total_counter = MagicMock()
            mock_total.labels.return_value = mock_total_counter

            mock_duration_histogram = MagicMock()
            mock_duration.labels.return_value = mock_duration_histogram

            mock_size_histogram = MagicMock()
            mock_size.labels.return_value = mock_size_histogram

            # Process request
            result = await middleware.dispatch(request, mock_call_next)

            # Verify metrics were recorded
            mock_in_progress.labels.assert_called_with(method="GET", endpoint="/api/products")
            mock_in_progress_gauge.inc.assert_called_once()
            mock_in_progress_gauge.dec.assert_called_once()

            mock_total.labels.assert_called_with(method="GET", endpoint="/api/products", status_code=200)
            mock_total_counter.inc.assert_called_once()

            mock_duration.labels.assert_called_with(method="GET", endpoint="/api/products")
            mock_duration_histogram.observe.assert_called_once()

            mock_size.labels.assert_called_with(method="GET", endpoint="/api/products")
            mock_size_histogram.observe.assert_called_once()

            assert result == response

    @pytest.mark.asyncio
    async def test_request_exception_records_error_metrics(self, middleware):
        """Test exception during request records error metrics"""

        # Mock request
        request = Mock(spec=Request)
        request.url.path = "/api/error"
        request.method = "POST"

        # Mock call_next that raises exception
        async def mock_call_next(req):
            raise ValueError("Simulated error")

        # Mock Prometheus metrics
        with patch('src.middleware.metrics_middleware.http_requests_in_progress') as mock_in_progress, \
             patch('src.middleware.metrics_middleware.http_requests_total') as mock_total, \
             patch('src.middleware.metrics_middleware.http_request_duration_seconds') as mock_duration:

            # Configure mocks
            mock_in_progress_gauge = MagicMock()
            mock_in_progress.labels.return_value = mock_in_progress_gauge

            mock_total_counter = MagicMock()
            mock_total.labels.return_value = mock_total_counter

            mock_duration_histogram = MagicMock()
            mock_duration.labels.return_value = mock_duration_histogram

            # Process request (should raise)
            with pytest.raises(ValueError, match="Simulated error"):
                await middleware.dispatch(request, mock_call_next)

            # Verify error metrics were recorded
            mock_total.labels.assert_called_with(method="POST", endpoint="/api/error", status_code=500)
            mock_total_counter.inc.assert_called_once()

            mock_duration.labels.assert_called_with(method="POST", endpoint="/api/error")
            mock_duration_histogram.observe.assert_called_once()

            # Verify in-progress counter was decremented (in finally block)
            mock_in_progress_gauge.dec.assert_called_once()

    @pytest.mark.asyncio
    async def test_response_without_body_skips_size_metric(self, middleware):
        """Test response without body attribute skips size metric"""

        # Mock request
        request = Mock(spec=Request)
        request.url.path = "/api/test"
        request.method = "GET"

        # Mock response without body
        response = Mock(spec=Response)
        response.status_code = 204  # No Content
        # Don't set body attribute

        async def mock_call_next(req):
            return response

        # Mock Prometheus metrics
        with patch('src.middleware.metrics_middleware.http_requests_in_progress') as mock_in_progress, \
             patch('src.middleware.metrics_middleware.http_requests_total') as mock_total, \
             patch('src.middleware.metrics_middleware.http_request_duration_seconds') as mock_duration, \
             patch('src.middleware.metrics_middleware.http_response_size_bytes') as mock_size:

            # Configure mocks
            mock_in_progress.labels.return_value = MagicMock()
            mock_total.labels.return_value = MagicMock()
            mock_duration.labels.return_value = MagicMock()

            # Process request
            await middleware.dispatch(request, mock_call_next)

            # Verify size metric was NOT called
            mock_size.labels.assert_not_called()


class TestMetricsMiddlewareNormalization:
    """Test endpoint path normalization"""

    def test_normalize_metrics_endpoint(self, middleware):
        """Test /metrics endpoint is not normalized"""
        result = middleware._normalize_endpoint("/metrics")
        assert result == "/metrics"

    def test_normalize_health_endpoints(self, middleware):
        """Test health endpoints are not normalized"""
        assert middleware._normalize_endpoint("/health") == "/health"
        assert middleware._normalize_endpoint("/health/live") == "/health/live"
        assert middleware._normalize_endpoint("/health/ready") == "/health/ready"

    def test_normalize_uuid_in_path(self, middleware):
        """Test UUID is normalized to {id}"""
        # UUID with dashes
        result = middleware._normalize_endpoint("/api/products/123e4567-e89b-12d3-a456-426614174000")
        assert result == "/api/products/{id}"

        # UUID without dashes (hex format)
        result = middleware._normalize_endpoint("/api/products/123e4567e89b12d3a456426614174000")
        assert result == "/api/products/{id}"

    def test_normalize_numeric_id_in_path(self, middleware):
        """Test numeric ID is normalized to {id}"""
        result = middleware._normalize_endpoint("/api/products/12345")
        assert result == "/api/products/{id}"

    def test_normalize_date_in_path(self, middleware):
        """Test date is normalized to {date}"""
        result = middleware._normalize_endpoint("/api/sales/2025-01-15")
        assert result == "/api/sales/{date}"

    def test_normalize_complex_path(self, middleware):
        """Test complex path with multiple IDs"""
        result = middleware._normalize_endpoint("/api/vendors/123e4567-e89b-12d3-a456-426614174000/products/456")
        assert result == "/api/vendors/{id}/products/{id}"

    def test_normalize_static_path(self, middleware):
        """Test static path without IDs"""
        result = middleware._normalize_endpoint("/api/v1/recommendations")
        assert result == "/api/v1/recommendations"

    def test_normalize_empty_segments(self, middleware):
        """Test paths with empty segments (leading/trailing slashes)"""
        result = middleware._normalize_endpoint("/api/products/")
        assert result == "/api/products"


class TestIsUUID:
    """Test UUID detection"""

    def test_is_uuid_with_dashes(self):
        """Test UUID with standard format"""
        assert MetricsMiddleware._is_uuid("123e4567-e89b-12d3-a456-426614174000") is True

    def test_is_uuid_hex_format(self):
        """Test UUID in hex format (32 chars, no dashes)"""
        assert MetricsMiddleware._is_uuid("123e4567e89b12d3a456426614174000") is True
        assert MetricsMiddleware._is_uuid("ABCDEF0123456789ABCDEF0123456789") is True

    def test_is_uuid_invalid_formats(self):
        """Test non-UUID strings"""
        assert MetricsMiddleware._is_uuid("not-a-uuid") is False
        assert MetricsMiddleware._is_uuid("123") is False
        assert MetricsMiddleware._is_uuid("123e4567-e89b-12d3-a456") is False  # Too short
        assert MetricsMiddleware._is_uuid("zzz456789abcdef0123456789abcdef") is False  # Invalid hex


class TestIsDate:
    """Test date detection"""

    def test_is_date_valid_formats(self):
        """Test valid date formats"""
        assert MetricsMiddleware._is_date("2025-01-15") is True
        assert MetricsMiddleware._is_date("2025-12-31") is True
        assert MetricsMiddleware._is_date("2024-02-29") is True  # Leap year

    def test_is_date_invalid_month(self):
        """Test invalid month values"""
        assert MetricsMiddleware._is_date("2025-13-01") is False  # Month > 12
        assert MetricsMiddleware._is_date("2025-00-01") is False  # Month < 1

    def test_is_date_invalid_day(self):
        """Test invalid day values"""
        assert MetricsMiddleware._is_date("2025-01-32") is False  # Day > 31
        assert MetricsMiddleware._is_date("2025-01-00") is False  # Day < 1

    def test_is_date_wrong_format(self):
        """Test non-date strings"""
        assert MetricsMiddleware._is_date("not-a-date") is False
        assert MetricsMiddleware._is_date("2025/01/15") is False  # Wrong separator
        assert MetricsMiddleware._is_date("2025-1-5") is False  # Wrong length
        assert MetricsMiddleware._is_date("25-01-15") is False  # Wrong year length
