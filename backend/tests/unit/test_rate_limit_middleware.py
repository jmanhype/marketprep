"""Unit tests for rate limiting middleware.

Tests Redis-backed rate limiting with sliding window:
- Per-IP rate limiting (anonymous: 100/min)
- Per-vendor rate limiting (authenticated: 1000/min)
- Redis sliding window algorithm
- Rate limit headers (X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset)
- Graceful degradation (fail-open when Redis unavailable)
- 429 Too Many Requests responses
- Client IP extraction
"""
import logging
import pytest
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from redis import Redis

from src.middleware.rate_limit import RateLimitMiddleware, RateLimitConfig, rate_limit


class TestRateLimitMiddlewareInitialization:
    """Test RateLimitMiddleware initialization."""

    def test_initialization_with_redis_available(self):
        """Test middleware initializes successfully when Redis is available."""
        with patch('src.middleware.rate_limit.Redis') as mock_redis_class:
            mock_redis = MagicMock()
            mock_redis.ping.return_value = True
            mock_redis_class.from_url.return_value = mock_redis

            middleware = RateLimitMiddleware(app=MagicMock())

            assert middleware.redis_client == mock_redis
            assert middleware.degraded_mode is False
            mock_redis.ping.assert_called_once()

    def test_initialization_with_redis_unavailable(self, caplog):
        """Test middleware handles Redis unavailability gracefully."""
        with patch('src.middleware.rate_limit.Redis') as mock_redis_class:
            mock_redis_class.from_url.side_effect = Exception("Connection refused")

            with caplog.at_level(logging.WARNING):
                middleware = RateLimitMiddleware(app=MagicMock())

                assert middleware.redis_client is None
                assert middleware.degraded_mode is True
                assert any("Redis unavailable" in record.message for record in caplog.records)

    def test_initialization_with_redis_ping_failure(self, caplog):
        """Test middleware handles Redis ping failure gracefully."""
        with patch('src.middleware.rate_limit.Redis') as mock_redis_class:
            mock_redis = MagicMock()
            mock_redis.ping.side_effect = Exception("Ping failed")
            mock_redis_class.from_url.return_value = mock_redis

            with caplog.at_level(logging.WARNING):
                middleware = RateLimitMiddleware(app=MagicMock())

                assert middleware.redis_client is None
                assert middleware.degraded_mode is True


class TestRateLimitMiddlewareBasic:
    """Test basic rate limiting functionality."""

    @pytest.fixture
    def mock_request_anonymous(self):
        """Mock anonymous request."""
        request = MagicMock(spec=Request)
        request.method = "GET"
        request.url.path = "/api/test"
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.100"
        request.state = SimpleNamespace()  # No vendor_id means anonymous
        return request

    @pytest.fixture
    def mock_request_authenticated(self):
        """Mock authenticated request."""
        request = MagicMock(spec=Request)
        request.method = "GET"
        request.url.path = "/api/test"
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.100"
        request.state = SimpleNamespace(vendor_id="vendor-123")
        return request

    @pytest.mark.asyncio
    async def test_skips_rate_limiting_when_redis_unavailable(self, mock_request_anonymous, caplog):
        """Test rate limiting is skipped when Redis is unavailable."""
        with patch('src.middleware.rate_limit.Redis') as mock_redis_class:
            mock_redis_class.from_url.side_effect = Exception("Connection refused")

            middleware = RateLimitMiddleware(app=MagicMock())

            expected_response = JSONResponse(content={"success": True}, status_code=200)
            call_next = AsyncMock(return_value=expected_response)

            with caplog.at_level(logging.WARNING):
                result = await middleware.dispatch(mock_request_anonymous, call_next)

                assert result == expected_response
                assert any("Rate limiting disabled" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_allows_request_under_limit(self, mock_request_anonymous):
        """Test request is allowed when under rate limit."""
        with patch('src.middleware.rate_limit.Redis') as mock_redis_class:
            mock_redis = MagicMock()
            mock_redis.ping.return_value = True
            mock_redis_class.from_url.return_value = mock_redis

            # Mock pipeline
            mock_pipeline = MagicMock()
            mock_pipeline.execute.return_value = [None, 50, None, None]  # 50 requests in window
            mock_redis.pipeline.return_value = mock_pipeline

            middleware = RateLimitMiddleware(app=MagicMock())

            expected_response = JSONResponse(content={"success": True}, status_code=200)
            call_next = AsyncMock(return_value=expected_response)

            result = await middleware.dispatch(mock_request_anonymous, call_next)

            assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_blocks_request_over_limit(self, mock_request_anonymous, caplog):
        """Test request is blocked when rate limit exceeded."""
        with patch('src.middleware.rate_limit.Redis') as mock_redis_class:
            mock_redis = MagicMock()
            mock_redis.ping.return_value = True
            mock_redis_class.from_url.return_value = mock_redis

            # Mock pipeline - 100 requests already in window (at limit)
            mock_pipeline = MagicMock()
            mock_pipeline.execute.return_value = [None, 100, None, None]
            mock_redis.pipeline.return_value = mock_pipeline

            middleware = RateLimitMiddleware(app=MagicMock())

            call_next = AsyncMock()

            with caplog.at_level(logging.WARNING):
                result = await middleware.dispatch(mock_request_anonymous, call_next)

                assert result.status_code == status.HTTP_429_TOO_MANY_REQUESTS
                assert not call_next.called  # Request not processed
                assert any("Rate limit exceeded" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_rate_limit_response_content(self, mock_request_anonymous):
        """Test 429 response includes rate limit information."""
        with patch('src.middleware.rate_limit.Redis') as mock_redis_class:
            mock_redis = MagicMock()
            mock_redis.ping.return_value = True
            mock_redis_class.from_url.return_value = mock_redis

            # Mock pipeline - exceed limit
            mock_pipeline = MagicMock()
            mock_pipeline.execute.return_value = [None, 100, None, None]
            mock_redis.pipeline.return_value = mock_pipeline

            middleware = RateLimitMiddleware(app=MagicMock())

            result = await middleware.dispatch(mock_request_anonymous, AsyncMock())

            import json
            content = json.loads(result.body)

            assert content['message'] == 'Rate limit exceeded'
            assert content['limit'] == 100  # Anonymous limit
            assert content['window_seconds'] == 60
            assert 'retry_after' in content

    @pytest.mark.asyncio
    async def test_adds_rate_limit_headers_to_successful_response(self, mock_request_anonymous):
        """Test rate limit headers are added to successful responses."""
        with patch('src.middleware.rate_limit.Redis') as mock_redis_class:
            mock_redis = MagicMock()
            mock_redis.ping.return_value = True
            mock_redis_class.from_url.return_value = mock_redis

            # Mock pipeline - 50 requests in window
            mock_pipeline = MagicMock()
            mock_pipeline.execute.return_value = [None, 50, None, None]
            mock_redis.pipeline.return_value = mock_pipeline

            middleware = RateLimitMiddleware(app=MagicMock())

            expected_response = JSONResponse(content={"success": True}, status_code=200)
            call_next = AsyncMock(return_value=expected_response)

            result = await middleware.dispatch(mock_request_anonymous, call_next)

            assert 'X-RateLimit-Limit' in result.headers
            assert result.headers['X-RateLimit-Limit'] == '100'  # Anonymous limit
            assert 'X-RateLimit-Remaining' in result.headers
            assert 'X-RateLimit-Reset' in result.headers

    @pytest.mark.asyncio
    async def test_adds_rate_limit_headers_to_429_response(self, mock_request_anonymous):
        """Test rate limit headers are added to 429 responses."""
        with patch('src.middleware.rate_limit.Redis') as mock_redis_class:
            mock_redis = MagicMock()
            mock_redis.ping.return_value = True
            mock_redis_class.from_url.return_value = mock_redis

            # Mock pipeline - exceed limit
            mock_pipeline = MagicMock()
            mock_pipeline.execute.return_value = [None, 100, None, None]
            mock_redis.pipeline.return_value = mock_pipeline

            middleware = RateLimitMiddleware(app=MagicMock())

            result = await middleware.dispatch(mock_request_anonymous, AsyncMock())

            assert result.headers['X-RateLimit-Limit'] == '100'
            assert result.headers['X-RateLimit-Remaining'] == '0'
            assert 'X-RateLimit-Reset' in result.headers
            assert 'Retry-After' in result.headers


class TestAnonymousVsAuthenticated:
    """Test different rate limits for anonymous vs authenticated requests."""

    @pytest.fixture
    def setup_middleware(self):
        """Setup middleware with mocked Redis."""
        with patch('src.middleware.rate_limit.Redis') as mock_redis_class:
            mock_redis = MagicMock()
            mock_redis.ping.return_value = True
            mock_redis_class.from_url.return_value = mock_redis

            # Mock pipeline
            mock_pipeline = MagicMock()
            mock_pipeline.execute.return_value = [None, 50, None, None]
            mock_redis.pipeline.return_value = mock_pipeline

            middleware = RateLimitMiddleware(app=MagicMock())
            return middleware, mock_redis

    @pytest.mark.asyncio
    async def test_anonymous_request_uses_ip_and_lower_limit(self, setup_middleware):
        """Test anonymous requests use IP-based limiting with 100/min limit."""
        middleware, mock_redis = setup_middleware

        request = MagicMock(spec=Request)
        request.url.path = "/api/test"
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.100"
        request.state = SimpleNamespace()  # No vendor_id

        expected_response = JSONResponse(content={"success": True}, status_code=200)
        call_next = AsyncMock(return_value=expected_response)

        result = await middleware.dispatch(request, call_next)

        # Check limit in response headers
        assert result.headers['X-RateLimit-Limit'] == '100'

    @pytest.mark.asyncio
    async def test_authenticated_request_uses_vendor_and_higher_limit(self, setup_middleware):
        """Test authenticated requests use vendor-based limiting with 1000/min limit."""
        middleware, mock_redis = setup_middleware

        request = MagicMock(spec=Request)
        request.url.path = "/api/test"
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.100"
        request.state = SimpleNamespace(vendor_id="vendor-123")

        expected_response = JSONResponse(content={"success": True}, status_code=200)
        call_next = AsyncMock(return_value=expected_response)

        result = await middleware.dispatch(request, call_next)

        # Check limit in response headers
        assert result.headers['X-RateLimit-Limit'] == '1000'


class TestClientIPExtraction:
    """Test client IP extraction logic."""

    @pytest.fixture
    def setup_middleware(self):
        """Setup middleware with mocked Redis."""
        with patch('src.middleware.rate_limit.Redis') as mock_redis_class:
            mock_redis = MagicMock()
            mock_redis.ping.return_value = True
            mock_redis_class.from_url.return_value = mock_redis

            mock_pipeline = MagicMock()
            mock_pipeline.execute.return_value = [None, 50, None, None]
            mock_redis.pipeline.return_value = mock_pipeline

            middleware = RateLimitMiddleware(app=MagicMock())
            return middleware

    @pytest.mark.asyncio
    async def test_extracts_ip_from_x_forwarded_for(self, setup_middleware):
        """Test IP is extracted from X-Forwarded-For header."""
        middleware = setup_middleware

        request = MagicMock(spec=Request)
        request.url.path = "/api/test"
        request.headers = {"X-Forwarded-For": "203.0.113.1, 198.51.100.1"}
        request.client = MagicMock()
        request.client.host = "192.168.1.1"
        request.state = SimpleNamespace()

        identifier, limit = middleware._get_identifier_and_limit(request)

        assert identifier == "ip:203.0.113.1"  # First IP in chain

    @pytest.mark.asyncio
    async def test_falls_back_to_client_host(self, setup_middleware):
        """Test falls back to client.host when no X-Forwarded-For."""
        middleware = setup_middleware

        request = MagicMock(spec=Request)
        request.url.path = "/api/test"
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.50"
        request.state = SimpleNamespace()

        identifier, limit = middleware._get_identifier_and_limit(request)

        assert identifier == "ip:192.168.1.50"


class TestGracefulDegradation:
    """Test graceful degradation on Redis failures."""

    @pytest.mark.asyncio
    async def test_fails_open_on_redis_error_during_check(self, caplog):
        """Test middleware allows request if Redis fails during check."""
        with patch('src.middleware.rate_limit.Redis') as mock_redis_class:
            mock_redis = MagicMock()
            mock_redis.ping.return_value = True
            mock_redis_class.from_url.return_value = mock_redis

            # Mock pipeline to raise error
            mock_pipeline = MagicMock()
            mock_pipeline.execute.side_effect = Exception("Redis connection lost")
            mock_redis.pipeline.return_value = mock_pipeline

            middleware = RateLimitMiddleware(app=MagicMock())

            request = MagicMock(spec=Request)
            request.url.path = "/api/test"
            request.headers = {}
            request.client = MagicMock()
            request.client.host = "192.168.1.100"
            request.state = SimpleNamespace()

            expected_response = JSONResponse(content={"success": True}, status_code=200)
            call_next = AsyncMock(return_value=expected_response)

            with caplog.at_level(logging.ERROR):
                result = await middleware.dispatch(request, call_next)

                # Should allow request (fail-open)
                assert result.status_code == 200
                assert any("Rate limit check failed" in record.message for record in caplog.records)


class TestRateLimitConfig:
    """Test RateLimitConfig for custom rate limits."""

    @pytest.mark.asyncio
    async def test_rate_limit_config_allows_request_under_limit(self):
        """Test custom rate limit allows requests under limit."""
        with patch('src.middleware.rate_limit.Redis') as mock_redis_class:
            mock_redis = MagicMock()
            mock_pipeline = MagicMock()
            mock_pipeline.execute.return_value = [None, 5, None, None]  # 5 requests
            mock_redis.pipeline.return_value = mock_pipeline
            mock_redis_class.from_url.return_value = mock_redis

            config = RateLimitConfig(limit=10, window_seconds=60, redis_client=mock_redis)

            request = MagicMock(spec=Request)
            request.url.path = "/api/expensive"
            request.client = MagicMock()
            request.client.host = "192.168.1.100"
            request.state = SimpleNamespace()

            # Should not raise exception
            await config(request)

    @pytest.mark.asyncio
    async def test_rate_limit_config_blocks_request_over_limit(self):
        """Test custom rate limit blocks requests over limit."""
        with patch('src.middleware.rate_limit.Redis') as mock_redis_class:
            mock_redis = MagicMock()
            mock_pipeline = MagicMock()
            mock_pipeline.execute.return_value = [None, 10, None, None]  # At limit
            mock_redis.pipeline.return_value = mock_pipeline
            mock_redis_class.from_url.return_value = mock_redis

            config = RateLimitConfig(limit=10, window_seconds=60, redis_client=mock_redis)

            request = MagicMock(spec=Request)
            request.url.path = "/api/expensive"
            request.client = MagicMock()
            request.client.host = "192.168.1.100"
            request.state = SimpleNamespace()

            with pytest.raises(HTTPException) as exc_info:
                await config(request)

            assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    @pytest.mark.asyncio
    async def test_rate_limit_config_fails_open_on_redis_error(self, caplog):
        """Test custom rate limit fails open on Redis errors."""
        with patch('src.middleware.rate_limit.Redis') as mock_redis_class:
            mock_redis_class.from_url.side_effect = Exception("Connection refused")

            config = RateLimitConfig(limit=10, window_seconds=60)

            request = MagicMock(spec=Request)
            request.url.path = "/api/expensive"
            request.client = MagicMock()
            request.client.host = "192.168.1.100"
            request.state = SimpleNamespace()

            with caplog.at_level(logging.WARNING):
                # Should not raise exception (fail-open)
                await config(request)

                assert any("Redis unavailable" in record.message for record in caplog.records)

    def test_rate_limit_helper_function(self):
        """Test rate_limit() helper creates RateLimitConfig."""
        config = rate_limit(limit=5, window_seconds=3600)

        assert isinstance(config, RateLimitConfig)
        assert config.limit == 5
        assert config.window_seconds == 3600
