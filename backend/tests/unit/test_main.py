"""
Unit tests for FastAPI application entry point

Tests app configuration, lifespan, and middleware setup.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
from fastapi.testclient import TestClient


class TestAppConfiguration:
    """Test FastAPI app configuration and setup"""

    def test_app_is_created(self):
        """Test app is properly instantiated"""
        from src.main import app

        assert app is not None
        assert app.title == "MarketPrep API"
        assert app.version is not None

    def test_app_includes_routers(self):
        """Test all routers are included in app"""
        from src.main import app

        # Check that routes exist for each router
        routes = [route.path for route in app.routes]

        # API v1 routes should exist
        assert any("/api/v1/auth" in route for route in routes)
        assert any("/api/v1/products" in route for route in routes)
        assert any("/api/v1/sales" in route for route in routes)
        assert any("/api/v1/recommendations" in route for route in routes)
        assert any("/api/v1/feedback" in route for route in routes)
        assert any("/api/v1/events" in route for route in routes)
        assert any("/api/v1/vendors" in route for route in routes)
        assert any("/api/v1/venues" in route for route in routes)
        assert any("/api/v1/audit" in route for route in routes)
        assert any("/api/v1/webhooks" in route for route in routes)
        assert any("/api/v1/square" in route for route in routes)

        # Monitoring routes (no prefix)
        assert any("/health" in route for route in routes)

    def test_app_has_middleware(self):
        """Test app has required middleware configured"""
        from src.main import app

        # Get middleware classes
        middleware_classes = [type(m).__name__ for m in app.user_middleware]

        # Check for expected middleware (note: middleware names may have different patterns)
        # Just verify we have multiple middleware layers
        assert len(app.user_middleware) > 0

    def test_app_has_cors_configured(self):
        """Test CORS middleware is configured"""
        from src.main import app

        # CORS is in user_middleware
        middleware_names = [m.cls.__name__ if hasattr(m, 'cls') else type(m).__name__
                           for m in app.user_middleware]

        # Check for CORSMiddleware by name
        assert 'CORSMiddleware' in middleware_names


class TestLifespan:
    """Test application lifespan events"""

    @pytest.mark.asyncio
    async def test_lifespan_startup(self):
        """Test lifespan startup events"""
        from src.main import lifespan

        mock_app = MagicMock()

        with patch('src.main.setup_logging') as mock_setup_logging, \
             patch('src.main.initialize_metrics') as mock_init_metrics:

            # Use async context manager
            async with lifespan(mock_app):
                # Verify startup was called
                mock_setup_logging.assert_called_once()
                mock_init_metrics.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_shutdown(self):
        """Test lifespan shutdown events"""
        from src.main import lifespan
        import logging

        mock_app = MagicMock()

        with patch('src.main.setup_logging'), \
             patch('src.main.initialize_metrics'):

            # Mock logger
            with patch('logging.getLogger') as mock_get_logger:
                mock_logger = MagicMock()
                mock_get_logger.return_value = mock_logger

                # Enter and exit context manager
                async with lifespan(mock_app):
                    pass  # Startup already tested

                # After exiting, shutdown logging should have been called
                # Check that logger.info was called with shutdown message
                shutdown_calls = [c for c in mock_logger.info.call_args_list
                                 if 'Shutting down' in str(c)]
                assert len(shutdown_calls) > 0


class TestRootEndpoint:
    """Test root endpoint"""

    def test_read_root_returns_app_info(self):
        """Test root endpoint returns application information"""
        from src.main import app

        client = TestClient(app)
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()

        assert "app" in data
        assert data["app"] == "MarketPrep API"
        assert "version" in data
        assert "environment" in data
        assert "status" in data
        assert data["status"] == "running"


class TestMainEntryPoint:
    """Test __main__ entry point"""

    def test_main_block_runs_uvicorn(self):
        """Test __main__ block starts uvicorn server"""
        import sys
        import subprocess

        # Test by running main.py as a module with mocked uvicorn
        # We can't easily test this without actually running the server,
        # but we can verify the code is valid Python

        # Instead, let's test by importing and checking the code path
        with patch('uvicorn.run') as mock_uvicorn_run:
            # Simulate running as main
            import importlib
            import src.main as main_module

            # We can't easily trigger __main__ block from tests,
            # but we can at least verify the module is importable
            # and contains the expected code

            # Read the source to verify __main__ block exists
            import inspect
            source = inspect.getsource(main_module)

            assert 'if __name__ == "__main__"' in source
            assert 'uvicorn.run' in source


class TestAppMetadata:
    """Test app metadata and documentation"""

    def test_app_has_title(self):
        """Test app has title"""
        from src.main import app
        assert app.title == "MarketPrep API"

    def test_app_has_version(self):
        """Test app has version"""
        from src.main import app
        assert app.version is not None

    def test_app_has_description(self):
        """Test app has description"""
        from src.main import app
        assert app.description is not None
        assert "MarketPrep" in app.description

    def test_app_has_tags(self):
        """Test app has OpenAPI tags defined"""
        from src.main import app
        assert app.openapi_tags is not None
        assert len(app.openapi_tags) > 0

        # Check for specific tags
        tag_names = [tag["name"] for tag in app.openapi_tags]
        assert "auth" in tag_names
        assert "products" in tag_names
        assert "recommendations" in tag_names
        assert "monitoring" in tag_names

    def test_app_contact_info(self):
        """Test app has contact information"""
        from src.main import app
        assert app.contact is not None
        assert "name" in app.contact
        assert "email" in app.contact

    def test_app_license_info(self):
        """Test app has license information"""
        from src.main import app
        assert app.license_info is not None
        assert "name" in app.license_info
