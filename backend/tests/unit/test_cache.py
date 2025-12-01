"""
Unit tests for Redis Cache Management

Tests Redis connection and session management:
- Redis client creation and connection
- Connection reuse (singleton pattern)
- Graceful degradation when Redis unavailable
- FastAPI dependency injection
- Connection cleanup on shutdown
- Error handling for all operations
"""

import pytest
from unittest.mock import MagicMock, patch
from redis import Redis

from src.cache import get_redis_client, get_redis, close_redis


class TestGetRedisClient:
    """Test get_redis_client function"""

    def teardown_method(self):
        """Reset global Redis client after each test"""
        import src.cache
        src.cache._redis_client = None

    @patch('src.cache.Redis.from_url')
    @patch('src.cache.settings')
    def test_get_redis_client_success(self, mock_settings, mock_redis_from_url):
        """Test successful Redis client creation"""
        mock_settings.redis_url = "redis://localhost:6379/0"

        mock_client = MagicMock(spec=Redis)
        mock_client.ping.return_value = True
        mock_redis_from_url.return_value = mock_client

        client = get_redis_client()

        assert client is not None
        assert client == mock_client
        mock_redis_from_url.assert_called_once_with(
            "redis://localhost:6379/0",
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        mock_client.ping.assert_called_once()

    @patch('src.cache.Redis.from_url')
    @patch('src.cache.settings')
    def test_get_redis_client_returns_existing_client(self, mock_settings, mock_redis_from_url):
        """Test client reuse (singleton pattern)"""
        mock_settings.redis_url = "redis://localhost:6379/0"

        mock_client = MagicMock(spec=Redis)
        mock_client.ping.return_value = True
        mock_redis_from_url.return_value = mock_client

        # First call creates client
        client1 = get_redis_client()
        assert client1 is not None

        # Second call returns same client without creating new one
        client2 = get_redis_client()
        assert client2 == client1
        mock_redis_from_url.assert_called_once()  # Only called once

    @patch('src.cache.Redis.from_url')
    @patch('src.cache.settings')
    def test_get_redis_client_connection_failure(self, mock_settings, mock_redis_from_url):
        """Test graceful degradation when Redis unavailable"""
        mock_settings.redis_url = "redis://localhost:6379/0"
        mock_redis_from_url.side_effect = Exception("Connection refused")

        client = get_redis_client()

        assert client is None  # Returns None instead of raising

    @patch('src.cache.Redis.from_url')
    @patch('src.cache.settings')
    def test_get_redis_client_ping_failure(self, mock_settings, mock_redis_from_url):
        """Test graceful degradation when ping fails"""
        mock_settings.redis_url = "redis://localhost:6379/0"

        mock_client = MagicMock(spec=Redis)
        mock_client.ping.side_effect = Exception("Ping timeout")
        mock_redis_from_url.return_value = mock_client

        client = get_redis_client()

        assert client is None  # Returns None instead of raising


class TestGetRedis:
    """Test get_redis dependency"""

    def teardown_method(self):
        """Reset global Redis client after each test"""
        import src.cache
        src.cache._redis_client = None

    @patch('src.cache.get_redis_client')
    def test_get_redis_yields_client(self, mock_get_client):
        """Test dependency yields Redis client"""
        mock_client = MagicMock(spec=Redis)
        mock_get_client.return_value = mock_client

        # Use generator
        gen = get_redis()
        client = next(gen)

        assert client == mock_client

        # Close generator
        try:
            next(gen)
        except StopIteration:
            pass  # Expected

    @patch('src.cache.get_redis_client')
    def test_get_redis_yields_none_when_unavailable(self, mock_get_client):
        """Test dependency yields None when Redis unavailable"""
        mock_get_client.return_value = None

        # Use generator
        gen = get_redis()
        client = next(gen)

        assert client is None

        # Close generator
        try:
            next(gen)
        except StopIteration:
            pass  # Expected

    @patch('src.cache.get_redis_client')
    def test_get_redis_cleanup_runs(self, mock_get_client):
        """Test dependency finally block runs (even though it's a pass)"""
        mock_client = MagicMock(spec=Redis)
        mock_get_client.return_value = mock_client

        # Use context manager to ensure cleanup
        gen = get_redis()
        try:
            client = next(gen)
            assert client == mock_client
        finally:
            try:
                next(gen)
            except StopIteration:
                pass  # Expected - cleanup ran


class TestCloseRedis:
    """Test close_redis function"""

    def teardown_method(self):
        """Reset global Redis client after each test"""
        import src.cache
        src.cache._redis_client = None

    def test_close_redis_success(self):
        """Test successful Redis connection close"""
        import src.cache

        # Set up mock client
        mock_client = MagicMock(spec=Redis)
        src.cache._redis_client = mock_client

        close_redis()

        # Client should be closed and set to None
        mock_client.close.assert_called_once()
        assert src.cache._redis_client is None

    def test_close_redis_with_exception(self):
        """Test Redis close handles exception gracefully"""
        import src.cache

        # Set up mock client that raises on close
        mock_client = MagicMock(spec=Redis)
        mock_client.close.side_effect = Exception("Close failed")
        src.cache._redis_client = mock_client

        # Should not raise exception
        close_redis()

        # Client should still be set to None
        assert src.cache._redis_client is None

    def test_close_redis_no_client(self):
        """Test Redis close when no client exists"""
        import src.cache

        # Ensure no client
        src.cache._redis_client = None

        # Should not raise exception
        close_redis()

        # Client should still be None
        assert src.cache._redis_client is None


class TestCacheIntegration:
    """Test cache module integration"""

    def teardown_method(self):
        """Reset global Redis client after each test"""
        import src.cache
        src.cache._redis_client = None

    @patch('src.cache.Redis.from_url')
    @patch('src.cache.settings')
    def test_full_lifecycle(self, mock_settings, mock_redis_from_url):
        """Test full cache lifecycle: connect -> use -> close"""
        mock_settings.redis_url = "redis://localhost:6379/0"

        mock_client = MagicMock(spec=Redis)
        mock_client.ping.return_value = True
        mock_redis_from_url.return_value = mock_client

        # Connect
        client = get_redis_client()
        assert client is not None

        # Use via dependency
        gen = get_redis()
        dep_client = next(gen)
        assert dep_client == client

        # Close generator
        try:
            next(gen)
        except StopIteration:
            pass

        # Close connection
        close_redis()
        mock_client.close.assert_called_once()

        import src.cache
        assert src.cache._redis_client is None
