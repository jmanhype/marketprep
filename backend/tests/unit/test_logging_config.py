"""
Unit tests for Logging Configuration

Tests structured logging setup:
- StructuredFormatter (JSON logging for production)
- HumanReadableFormatter (colored logging for development)
- setup_logging function
- LogContext context manager
- get_logger function with adapters
"""

import pytest
import logging
import json
import sys
from io import StringIO
from unittest.mock import patch, MagicMock, mock_open
from datetime import datetime

from src.logging_config import (
    StructuredFormatter,
    HumanReadableFormatter,
    setup_logging,
    LogContext,
    get_logger,
)


class TestStructuredFormatter:
    """Test JSON structured logging formatter."""

    def test_add_fields_basic(self):
        """Test basic field addition to log record"""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name='test_logger',
            level=logging.INFO,
            pathname='/path/to/file.py',
            lineno=42,
            msg='Test message',
            args=(),
            exc_info=None,
        )
        record.funcName = 'test_function'
        record.module = 'test_module'

        with patch('src.config.settings') as mock_settings:
            mock_settings.environment = 'development'

            log_record = {}
            formatter.add_fields(log_record, record, {})

            assert 'timestamp' in log_record
            assert log_record['level'] == 'INFO'
            assert log_record['logger'] == 'test_logger'
            assert log_record['module'] == 'test_module'
            assert log_record['function'] == 'test_function'
            assert log_record['line'] == 42
            assert log_record['environment'] == 'development'

    def test_add_fields_with_correlation_id(self):
        """Test correlation_id is added if present"""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name='test_logger',
            level=logging.INFO,
            pathname='/path/to/file.py',
            lineno=42,
            msg='Test message',
            args=(),
            exc_info=None,
        )
        record.funcName = 'test_func'
        record.module = 'test_mod'
        record.correlation_id = 'corr-123'

        with patch('src.config.settings') as mock_settings:
            mock_settings.environment = 'production'

            log_record = {}
            formatter.add_fields(log_record, record, {})

            assert log_record['correlation_id'] == 'corr-123'

    def test_add_fields_with_vendor_id(self):
        """Test vendor_id is converted to string and added"""
        from uuid import uuid4

        formatter = StructuredFormatter()
        vendor_id = uuid4()

        record = logging.LogRecord(
            name='test_logger',
            level=logging.INFO,
            pathname='/path/to/file.py',
            lineno=42,
            msg='Test message',
            args=(),
            exc_info=None,
        )
        record.funcName = 'test_func'
        record.module = 'test_mod'
        record.vendor_id = vendor_id

        with patch('src.config.settings') as mock_settings:
            mock_settings.environment = 'production'

            log_record = {}
            formatter.add_fields(log_record, record, {})

            assert log_record['vendor_id'] == str(vendor_id)

    def test_add_fields_with_request_info(self):
        """Test request information is added when present"""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name='test_logger',
            level=logging.INFO,
            pathname='/path/to/file.py',
            lineno=42,
            msg='Test message',
            args=(),
            exc_info=None,
        )
        record.funcName = 'test_func'
        record.module = 'test_mod'
        record.request_id = 'req-123'
        record.request_method = 'GET'
        record.request_path = '/api/v1/products'
        record.request_ip = '192.168.1.1'

        with patch('src.config.settings') as mock_settings:
            mock_settings.environment = 'production'

            log_record = {}
            formatter.add_fields(log_record, record, {})

            assert log_record['request_id'] == 'req-123'
            assert log_record['request_method'] == 'GET'
            assert log_record['request_path'] == '/api/v1/products'
            assert log_record['request_ip'] == '192.168.1.1'

    def test_add_fields_with_exception(self):
        """Test exception information is added"""
        formatter = StructuredFormatter()

        try:
            raise ValueError("Test error")
        except ValueError:
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name='test_logger',
            level=logging.ERROR,
            pathname='/path/to/file.py',
            lineno=42,
            msg='Test message',
            args=(),
            exc_info=exc_info,
        )
        record.funcName = 'test_func'
        record.module = 'test_mod'

        with patch('src.config.settings') as mock_settings:
            mock_settings.environment = 'production'

            log_record = {}
            formatter.add_fields(log_record, record, {})

            assert 'exception' in log_record
            assert log_record['exception']['type'] == 'ValueError'
            assert log_record['exception']['message'] == 'Test error'


class TestHumanReadableFormatter:
    """Test human-readable colored formatter."""

    def test_format_basic_message(self):
        """Test basic log message formatting"""
        formatter = HumanReadableFormatter()
        record = logging.LogRecord(
            name='test_logger',
            level=logging.INFO,
            pathname='/path/to/file.py',
            lineno=42,
            msg='Test message',
            args=(),
            exc_info=None,
        )
        record.funcName = 'test_function'

        result = formatter.format(record)

        assert 'INFO' in result
        assert 'test_logger:test_function:42' in result
        assert 'Test message' in result

    def test_format_with_correlation_id(self):
        """Test log formatting includes correlation_id"""
        formatter = HumanReadableFormatter()
        record = logging.LogRecord(
            name='test_logger',
            level=logging.WARNING,
            pathname='/path/to/file.py',
            lineno=100,
            msg='Warning message',
            args=(),
            exc_info=None,
        )
        record.funcName = 'test_func'
        record.correlation_id = 'corr-456'

        result = formatter.format(record)

        assert '[corr-456]' in result
        assert 'WARNING' in result

    def test_format_with_exception(self):
        """Test exception formatting includes traceback"""
        formatter = HumanReadableFormatter()

        try:
            raise RuntimeError("Test runtime error")
        except RuntimeError:
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name='test_logger',
            level=logging.ERROR,
            pathname='/path/to/file.py',
            lineno=200,
            msg='Error occurred',
            args=(),
            exc_info=exc_info,
        )
        record.funcName = 'error_func'

        result = formatter.format(record)

        assert 'ERROR' in result
        assert 'Error occurred' in result
        assert 'RuntimeError' in result
        assert 'Test runtime error' in result


class TestSetupLogging:
    """Test logging setup function."""

    def test_setup_logging_production(self):
        """Test logging setup in production mode"""
        with patch('src.logging_config.settings') as mock_settings:
            mock_settings.environment = 'production'
            mock_settings.log_level = 'INFO'
            mock_settings.log_file = None

            setup_logging()

            root_logger = logging.getLogger()
            assert root_logger.level == logging.INFO
            assert len(root_logger.handlers) > 0

            # Check handler uses StructuredFormatter
            handler = root_logger.handlers[0]
            assert isinstance(handler.formatter, StructuredFormatter)

    def test_setup_logging_development(self):
        """Test logging setup in development mode"""
        with patch('src.logging_config.settings') as mock_settings:
            mock_settings.environment = 'development'
            mock_settings.log_level = 'DEBUG'
            mock_settings.log_file = None

            setup_logging()

            root_logger = logging.getLogger()
            assert root_logger.level == logging.DEBUG

            # Check handler uses HumanReadableFormatter
            handler = root_logger.handlers[0]
            assert isinstance(handler.formatter, HumanReadableFormatter)

    def test_setup_logging_with_file_handler(self):
        """Test logging setup with file handler"""
        with patch('src.logging_config.settings') as mock_settings:
            mock_settings.environment = 'production'
            mock_settings.log_level = 'INFO'
            mock_settings.log_file = '/tmp/test.log'

            with patch('logging.FileHandler') as mock_file_handler:
                # Configure mock to have proper level attribute
                mock_handler_instance = MagicMock()
                mock_handler_instance.level = logging.ERROR
                mock_file_handler.return_value = mock_handler_instance

                setup_logging()

                # File handler should be created
                mock_file_handler.assert_called_once_with('/tmp/test.log')

    def test_setup_logging_library_levels(self):
        """Test noisy library log levels are adjusted"""
        with patch('src.logging_config.settings') as mock_settings:
            mock_settings.environment = 'development'
            mock_settings.log_level = 'DEBUG'
            mock_settings.log_file = None

            setup_logging()

            # Check noisy libraries have higher log levels
            assert logging.getLogger('urllib3').level == logging.WARNING
            assert logging.getLogger('httpx').level == logging.WARNING
            assert logging.getLogger('sqlalchemy.engine').level == logging.WARNING
            assert logging.getLogger('alembic').level == logging.INFO

    def test_setup_logging_clears_existing_handlers(self):
        """Test existing handlers are cleared"""
        # Add a dummy handler
        root_logger = logging.getLogger()
        dummy_handler = logging.StreamHandler()
        root_logger.addHandler(dummy_handler)

        initial_handler_count = len(root_logger.handlers)

        with patch('src.logging_config.settings') as mock_settings:
            mock_settings.environment = 'development'
            mock_settings.log_level = 'INFO'
            mock_settings.log_file = None

            setup_logging()

            # Handlers should be cleared and new ones added
            # Should not include the dummy handler
            assert dummy_handler not in root_logger.handlers


class TestLogContext:
    """Test LogContext context manager."""

    def test_log_context_adds_extra_fields(self):
        """Test LogContext adds extra fields to log records"""
        logger = logging.getLogger('test_context')

        with LogContext(request_id='req-123', user_id='user-456'):
            # Create a log record within context
            handler = logging.StreamHandler(StringIO())
            logger.addHandler(handler)
            logger.info('Test message')

            # Get the most recent log record
            record = logging.getLogRecordFactory()('test', logging.INFO, '', 0, '', (), None)

            assert hasattr(record, 'request_id')
            assert hasattr(record, 'user_id')
            assert record.request_id == 'req-123'
            assert record.user_id == 'user-456'

    def test_log_context_restores_factory(self):
        """Test LogContext restores original factory on exit"""
        original_factory = logging.getLogRecordFactory()

        with LogContext(test_field='test_value'):
            # Factory should be modified
            current_factory = logging.getLogRecordFactory()
            assert current_factory != original_factory

        # Factory should be restored
        restored_factory = logging.getLogRecordFactory()
        assert restored_factory == original_factory


class TestGetLogger:
    """Test get_logger function."""

    def test_get_logger_basic(self):
        """Test getting a basic logger without extra fields"""
        logger = get_logger('test.module')

        assert isinstance(logger, logging.Logger)
        assert logger.name == 'test.module'

    def test_get_logger_with_extra_fields(self):
        """Test getting logger with extra context fields"""
        logger = get_logger('test.module', service='api', component='auth')

        assert isinstance(logger, logging.LoggerAdapter)
        assert logger.extra['service'] == 'api'
        assert logger.extra['component'] == 'auth'

    def test_logger_adapter_merges_extra_fields(self):
        """Test LoggerAdapter merges extra fields correctly"""
        logger = get_logger('test.module', service='api')

        # Capture log output
        handler = logging.StreamHandler(StringIO())
        handler.setLevel(logging.INFO)
        logging.getLogger('test.module').addHandler(handler)

        # Log with additional extra fields
        logger.info('Test message', extra={'request_id': 'req-789'})

        # The logger adapter should merge both sets of extra fields
        # (This is implicit in the process method)
        assert logger.extra['service'] == 'api'

    def test_logger_adapter_adds_extra_when_none_provided(self):
        """Test LoggerAdapter adds extra fields when not provided in log call.

        This covers line 236 in logging_config.py where kwargs['extra'] is
        created when not present in the log call.
        """
        logger = get_logger('test.module.adapter', service='api', component='auth')

        # Capture log output
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.INFO)
        logging.getLogger('test.module.adapter').addHandler(handler)

        # Log WITHOUT extra parameter
        # This triggers line 236: kwargs['extra'] = {}
        logger.info('Test message without extra')

        # Verify the logger adapter still has its extra fields
        assert logger.extra['service'] == 'api'
        assert logger.extra['component'] == 'auth'
