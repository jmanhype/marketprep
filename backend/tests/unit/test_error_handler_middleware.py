"""Unit tests for error handling middleware.

Tests global error handling with standardized responses:
- ErrorResponse class
- GlobalErrorHandler middleware
- Database error handling (SQLAlchemyError)
- Validation error handling (ValueError)
- Generic exception handling
- Error ID correlation
- Debug vs production error details
"""
import logging
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from src.middleware.error_handler import (
    ErrorResponse,
    GlobalErrorHandler,
)


class TestErrorResponse:
    """Test ErrorResponse class."""

    def test_error_response_basic(self):
        """Test basic error response construction."""
        error = ErrorResponse(
            error_id="test-123",
            message="Test error",
            status_code=400,
        )

        assert error.error_id == "test-123"
        assert error.message == "Test error"
        assert error.status_code == 400

    def test_error_response_to_dict_without_details(self):
        """Test to_dict without details."""
        error = ErrorResponse(
            error_id="test-123",
            message="Test error",
        )

        result = error.to_dict()

        assert result == {
            "error_id": "test-123",
            "message": "Test error",
        }

    def test_error_response_includes_details_in_debug(self):
        """Test details are included when debug is enabled."""
        with patch('src.middleware.error_handler.settings') as mock_settings:
            mock_settings.debug = True

            error = ErrorResponse(
                error_id="test-123",
                message="Test error",
                details="Detailed error information",
            )

            result = error.to_dict()

            assert result == {
                "error_id": "test-123",
                "message": "Test error",
                "details": "Detailed error information",
            }

    def test_error_response_hides_details_in_production(self):
        """Test details are hidden when debug is disabled."""
        with patch('src.middleware.error_handler.settings') as mock_settings:
            mock_settings.debug = False

            error = ErrorResponse(
                error_id="test-123",
                message="Test error",
                details="Detailed error information",
            )

            assert error.details is None

            result = error.to_dict()

            assert result == {
                "error_id": "test-123",
                "message": "Test error",
            }


class TestGlobalErrorHandlerBasic:
    """Test basic GlobalErrorHandler functionality."""

    @pytest.fixture
    def mock_request(self):
        """Mock request."""
        request = MagicMock(spec=Request)
        request.method = "GET"
        request.url.path = "/api/test"
        request.state = MagicMock()
        return request

    @pytest.mark.asyncio
    async def test_sets_error_id_on_request_state(self, mock_request):
        """Test error ID is set on request state."""
        middleware = GlobalErrorHandler(app=MagicMock())

        async def call_next(request):
            return JSONResponse(content={"success": True}, status_code=200)

        with patch('src.middleware.error_handler.uuid4') as mock_uuid:
            mock_uuid.return_value.__str__ = MagicMock(return_value='test-error-id')

            await middleware.dispatch(mock_request, call_next)

            assert mock_request.state.error_id == 'test-error-id'

    @pytest.mark.asyncio
    async def test_passes_through_successful_response(self, mock_request):
        """Test successful responses are passed through unchanged."""
        middleware = GlobalErrorHandler(app=MagicMock())

        expected_response = JSONResponse(content={"success": True}, status_code=200)

        async def call_next(request):
            return expected_response

        result = await middleware.dispatch(mock_request, call_next)

        assert result == expected_response


class TestDatabaseErrorHandling:
    """Test database error handling."""

    @pytest.fixture
    def mock_request(self):
        """Mock request."""
        request = MagicMock(spec=Request)
        request.method = "POST"
        request.url.path = "/api/database"
        request.state = MagicMock()
        return request

    @pytest.mark.asyncio
    async def test_handles_sqlalchemy_error(self, mock_request):
        """Test SQLAlchemy errors are caught and handled."""
        middleware = GlobalErrorHandler(app=MagicMock())

        async def call_next(request):
            raise SQLAlchemyError("Database connection failed")

        with patch('src.middleware.error_handler.uuid4') as mock_uuid:
            mock_uuid.return_value.__str__ = MagicMock(return_value='db-error-123')

            result = await middleware.dispatch(mock_request, call_next)

            assert isinstance(result, JSONResponse)
            assert result.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    @pytest.mark.asyncio
    async def test_database_error_response_content(self, mock_request):
        """Test database error response content."""
        middleware = GlobalErrorHandler(app=MagicMock())

        async def call_next(request):
            raise SQLAlchemyError("Connection timeout")

        with patch('src.middleware.error_handler.uuid4') as mock_uuid:
            mock_uuid.return_value.__str__ = MagicMock(return_value='db-error-123')
            with patch('src.middleware.error_handler.settings') as mock_settings:
                mock_settings.debug = False

                result = await middleware.dispatch(mock_request, call_next)

                # Parse JSON response
                import json
                content = json.loads(result.body)

                assert content['error_id'] == 'db-error-123'
                assert content['message'] == 'Database error occurred'
                assert 'details' not in content  # Hidden in production

    @pytest.mark.asyncio
    async def test_database_error_includes_details_in_debug(self, mock_request):
        """Test database error includes details in debug mode."""
        middleware = GlobalErrorHandler(app=MagicMock())

        async def call_next(request):
            raise SQLAlchemyError("Connection timeout")

        with patch('src.middleware.error_handler.uuid4') as mock_uuid:
            mock_uuid.return_value.__str__ = MagicMock(return_value='db-error-123')
            with patch('src.middleware.error_handler.settings') as mock_settings:
                mock_settings.debug = True

                result = await middleware.dispatch(mock_request, call_next)

                import json
                content = json.loads(result.body)

                assert 'details' in content
                assert 'Connection timeout' in content['details']

    @pytest.mark.asyncio
    async def test_database_error_logging(self, mock_request, caplog):
        """Test database errors are logged."""
        middleware = GlobalErrorHandler(app=MagicMock())

        async def call_next(request):
            raise SQLAlchemyError("Connection timeout")

        with caplog.at_level(logging.ERROR):
            with patch('src.middleware.error_handler.uuid4') as mock_uuid:
                mock_uuid.return_value.__str__ = MagicMock(return_value='db-error-123')

                await middleware.dispatch(mock_request, call_next)

                # Check error was logged
                assert any('Database error' in record.message for record in caplog.records)
                assert any('db-error-123' in record.message for record in caplog.records)


class TestValidationErrorHandling:
    """Test validation error handling."""

    @pytest.fixture
    def mock_request(self):
        """Mock request."""
        request = MagicMock(spec=Request)
        request.method = "POST"
        request.url.path = "/api/validate"
        request.state = MagicMock()
        return request

    @pytest.mark.asyncio
    async def test_handles_value_error(self, mock_request):
        """Test ValueError is caught and handled."""
        middleware = GlobalErrorHandler(app=MagicMock())

        async def call_next(request):
            raise ValueError("Invalid input: age must be positive")

        with patch('src.middleware.error_handler.uuid4') as mock_uuid:
            mock_uuid.return_value.__str__ = MagicMock(return_value='val-error-456')

            result = await middleware.dispatch(mock_request, call_next)

            assert isinstance(result, JSONResponse)
            assert result.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_validation_error_response_content(self, mock_request):
        """Test validation error response content."""
        middleware = GlobalErrorHandler(app=MagicMock())

        async def call_next(request):
            raise ValueError("Invalid email format")

        with patch('src.middleware.error_handler.uuid4') as mock_uuid:
            mock_uuid.return_value.__str__ = MagicMock(return_value='val-error-456')
            with patch('src.middleware.error_handler.settings') as mock_settings:
                mock_settings.debug = True

                result = await middleware.dispatch(mock_request, call_next)

                import json
                content = json.loads(result.body)

                assert content['error_id'] == 'val-error-456'
                assert content['message'] == 'Validation error'
                assert content['details'] == 'Invalid email format'

    @pytest.mark.asyncio
    async def test_validation_error_logging(self, mock_request, caplog):
        """Test validation errors are logged as warnings."""
        middleware = GlobalErrorHandler(app=MagicMock())

        async def call_next(request):
            raise ValueError("Invalid input")

        with caplog.at_level(logging.WARNING):
            with patch('src.middleware.error_handler.uuid4') as mock_uuid:
                mock_uuid.return_value.__str__ = MagicMock(return_value='val-error-456')

                await middleware.dispatch(mock_request, call_next)

                # Check warning was logged
                assert any('Validation error' in record.message for record in caplog.records)
                assert any(record.levelname == 'WARNING' for record in caplog.records)


class TestGenericErrorHandling:
    """Test generic exception handling."""

    @pytest.fixture
    def mock_request(self):
        """Mock request."""
        request = MagicMock(spec=Request)
        request.method = "GET"
        request.url.path = "/api/generic"
        request.state = MagicMock()
        return request

    @pytest.mark.asyncio
    async def test_handles_generic_exception(self, mock_request):
        """Test generic exceptions are caught and handled."""
        middleware = GlobalErrorHandler(app=MagicMock())

        async def call_next(request):
            raise RuntimeError("Unexpected error")

        with patch('src.middleware.error_handler.uuid4') as mock_uuid:
            mock_uuid.return_value.__str__ = MagicMock(return_value='gen-error-789')

            result = await middleware.dispatch(mock_request, call_next)

            assert isinstance(result, JSONResponse)
            assert result.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    @pytest.mark.asyncio
    async def test_generic_error_response_content_production(self, mock_request):
        """Test generic error hides details in production."""
        middleware = GlobalErrorHandler(app=MagicMock())

        async def call_next(request):
            raise RuntimeError("Internal failure")

        with patch('src.middleware.error_handler.uuid4') as mock_uuid:
            mock_uuid.return_value.__str__ = MagicMock(return_value='gen-error-789')
            with patch('src.middleware.error_handler.settings') as mock_settings:
                mock_settings.debug = False

                result = await middleware.dispatch(mock_request, call_next)

                import json
                content = json.loads(result.body)

                assert content['error_id'] == 'gen-error-789'
                assert content['message'] == 'Internal server error'
                assert 'details' not in content  # Hidden in production

    @pytest.mark.asyncio
    async def test_generic_error_includes_details_in_debug(self, mock_request):
        """Test generic error includes exception type and message in debug."""
        middleware = GlobalErrorHandler(app=MagicMock())

        async def call_next(request):
            raise RuntimeError("Internal failure")

        with patch('src.middleware.error_handler.uuid4') as mock_uuid:
            mock_uuid.return_value.__str__ = MagicMock(return_value='gen-error-789')
            with patch('src.middleware.error_handler.settings') as mock_settings:
                mock_settings.debug = True

                result = await middleware.dispatch(mock_request, call_next)

                import json
                content = json.loads(result.body)

                assert 'details' in content
                assert 'RuntimeError' in content['details']
                assert 'Internal failure' in content['details']

    @pytest.mark.asyncio
    async def test_generic_error_logging_includes_traceback(self, mock_request):
        """Test generic errors are logged with traceback."""
        middleware = GlobalErrorHandler(app=MagicMock())

        async def call_next(request):
            raise RuntimeError("Internal failure")

        with patch('src.middleware.error_handler.logger.error') as mock_log:
            with patch('src.middleware.error_handler.uuid4') as mock_uuid:
                mock_uuid.return_value.__str__ = MagicMock(return_value='gen-error-789')

                await middleware.dispatch(mock_request, call_next)

                # Check error was logged with traceback
                assert mock_log.called
                call_kwargs = mock_log.call_args[1]
                assert call_kwargs['exc_info'] is True
                assert 'extra' in call_kwargs
                assert 'traceback' in call_kwargs['extra']


class TestErrorHandlerEdgeCases:
    """Test edge cases and special scenarios."""

    @pytest.fixture
    def mock_request(self):
        """Mock request."""
        request = MagicMock(spec=Request)
        request.method = "DELETE"
        request.url.path = "/api/edge-case"
        request.state = MagicMock()
        return request

    @pytest.mark.asyncio
    async def test_handles_exception_with_empty_message(self, mock_request):
        """Test exceptions with empty messages are handled."""
        middleware = GlobalErrorHandler(app=MagicMock())

        async def call_next(request):
            raise ValueError("")

        with patch('src.middleware.error_handler.uuid4') as mock_uuid:
            mock_uuid.return_value.__str__ = MagicMock(return_value='empty-msg-error')

            result = await middleware.dispatch(mock_request, call_next)

            assert isinstance(result, JSONResponse)
            assert result.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_different_exception_types_get_different_handlers(self, mock_request):
        """Test different exception types route to appropriate handlers."""
        middleware = GlobalErrorHandler(app=MagicMock())

        # ValueError → 422
        async def value_error_call_next(request):
            raise ValueError("validation")

        with patch('src.middleware.error_handler.uuid4') as mock_uuid:
            mock_uuid.return_value.__str__ = MagicMock(return_value='test-id')
            result = await middleware.dispatch(mock_request, value_error_call_next)
            assert result.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        # SQLAlchemyError → 500
        async def db_error_call_next(request):
            raise SQLAlchemyError("database")

        with patch('src.middleware.error_handler.uuid4') as mock_uuid:
            mock_uuid.return_value.__str__ = MagicMock(return_value='test-id')
            result = await middleware.dispatch(mock_request, db_error_call_next)
            assert result.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

        # Generic Exception → 500
        async def generic_error_call_next(request):
            raise Exception("generic")

        with patch('src.middleware.error_handler.uuid4') as mock_uuid:
            mock_uuid.return_value.__str__ = MagicMock(return_value='test-id')
            result = await middleware.dispatch(mock_request, generic_error_call_next)
            assert result.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
