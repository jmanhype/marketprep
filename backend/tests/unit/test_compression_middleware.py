"""
Unit tests for Compression Middleware

Tests response compression middleware:
- Middleware initialization with default parameters
- Middleware initialization with custom parameters
- Inheritance from Starlette's GZipMiddleware
"""

import pytest
from unittest.mock import MagicMock
from starlette.middleware.gzip import GZipMiddleware

from src.middleware.compression import CompressionMiddleware


class TestCompressionMiddleware:
    """Test CompressionMiddleware initialization"""

    def test_middleware_inherits_from_gzip(self):
        """Test CompressionMiddleware inherits from GZipMiddleware"""
        assert issubclass(CompressionMiddleware, GZipMiddleware)

    def test_middleware_init_with_defaults(self):
        """Test middleware initialization with default parameters"""
        app = MagicMock()

        middleware = CompressionMiddleware(app)

        # Verify it was initialized (check parent class attributes)
        assert middleware.minimum_size == 500
        assert hasattr(middleware, 'app')

    def test_middleware_init_with_custom_params(self):
        """Test middleware initialization with custom parameters"""
        app = MagicMock()

        middleware = CompressionMiddleware(
            app,
            minimum_size=1000,
            compresslevel=9
        )

        # Verify custom parameters were passed
        assert middleware.minimum_size == 1000
        assert hasattr(middleware, 'app')

    def test_middleware_init_with_minimum_size_only(self):
        """Test middleware initialization with just minimum_size"""
        app = MagicMock()

        middleware = CompressionMiddleware(app, minimum_size=250)

        assert middleware.minimum_size == 250

    def test_middleware_init_with_compresslevel_only(self):
        """Test middleware initialization with just compresslevel"""
        app = MagicMock()

        middleware = CompressionMiddleware(app, compresslevel=3)

        # Default minimum_size should be used
        assert middleware.minimum_size == 500
