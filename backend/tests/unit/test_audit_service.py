"""
Unit tests for audit log service

Tests audit logging functionality:
- Log action recording
- Data access logging
- Hash chain generation
- Audit trail queries
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from unittest.mock import MagicMock, patch

from src.services.audit_service import AuditService
from src.models.audit_log import AuditLog, DataAccessLog, AuditAction


class TestAuditLogCreation:
    """Test audit log creation"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        db.query = MagicMock()
        return db

    @pytest.fixture
    def audit_service(self, mock_db):
        """Create audit service with mocked db"""
        return AuditService(db=mock_db)

    def test_log_action(self, audit_service, mock_db):
        """Test basic action logging"""
        log = audit_service.log_action(
            vendor_id="vendor-123",
            action=AuditAction.CREATE,
            user_email="user@example.com",
            resource_type="product",
            resource_id="prod-123",
            changes_summary="Created new product"
        )

        # Verify database operations
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

        # Verify log properties
        assert log.vendor_id == "vendor-123"
        assert log.action == AuditAction.CREATE
        assert log.resource_type == "product"
        assert log.resource_id == "prod-123"
        assert log.user_email == "user@example.com"
        assert log.changes_summary == "Created new product"

    def test_log_action_with_old_new_values(self, audit_service, mock_db):
        """Test logging with before/after values"""
        old_values = {"name": "Old Name", "price": 10.0}
        new_values = {"name": "New Name", "price": 12.0}

        log = audit_service.log_action(
            vendor_id="vendor-123",
            action=AuditAction.UPDATE,
            resource_type="product",
            resource_id="prod-123",
            old_values=old_values,
            new_values=new_values
        )

        assert log.old_values == old_values
        assert log.new_values == new_values
        mock_db.commit.assert_called_once()

    def test_log_action_with_request_context(self, audit_service, mock_db):
        """Test logging with FastAPI request context (lines 65-69)"""
        # Create mock request
        mock_request = MagicMock()
        mock_request.client.host = "192.168.1.1"
        mock_request.headers.get.return_value = "Mozilla/5.0"
        mock_request.method = "POST"
        mock_request.url.path = "/api/products"
        mock_request.state.correlation_id = "corr-123"

        log = audit_service.log_action(
            vendor_id="vendor-123",
            action=AuditAction.CREATE,
            user_email="user@example.com",
            resource_type="product",
            resource_id="prod-123",
            request=mock_request
        )

        # Verify request context was captured (covers lines 65-69)
        assert log.ip_address == "192.168.1.1"
        assert log.user_agent == "Mozilla/5.0"
        assert log.request_method == "POST"
        assert log.request_path == "/api/products"
        assert log.correlation_id == "corr-123"

    def test_log_action_without_request(self, audit_service, mock_db):
        """Test logging without request (lines stay None)"""
        log = audit_service.log_action(
            vendor_id="vendor-123",
            action=AuditAction.DELETE,
            user_email="user@example.com",
            resource_type="product",
            resource_id="prod-123"
        )

        # Without request, these should be None
        assert log.ip_address is None
        assert log.user_agent is None
        assert log.request_method is None
        assert log.request_path is None
        assert log.correlation_id is None

    def test_log_action_sensitive_flag(self, audit_service, mock_db):
        """Test logging with sensitive data flag"""
        log = audit_service.log_action(
            vendor_id="vendor-123",
            action=AuditAction.UPDATE,
            user_email="user@example.com",
            resource_type="customer",
            resource_id="cust-123",
            is_sensitive=True
        )

        assert log.is_sensitive is True


class TestDataAccessLogging:
    """Test GDPR data access logging"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        return db

    @pytest.fixture
    def audit_service(self, mock_db):
        """Create audit service with mocked db"""
        return AuditService(db=mock_db)

    def test_log_data_access(self, audit_service, mock_db):
        """Test data access logging"""
        access_log = audit_service.log_data_access(
            vendor_id="vendor-123",
            accessor_id="admin-1",
            accessor_email="admin@example.com",
            accessor_role="admin",
            data_subject_id="vendor-123",
            data_subject_email="vendor@example.com",
            data_type="sales_data",
            access_method="export",
            access_purpose="GDPR data export request",
            legal_basis="consent"
        )

        # Verify database operations
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

        # Verify access log properties
        assert access_log.vendor_id == "vendor-123"
        assert access_log.accessor_id == "admin-1"
        assert access_log.accessor_email == "admin@example.com"
        assert access_log.accessor_role == "admin"
        assert access_log.data_subject_id == "vendor-123"
        assert access_log.data_subject_email == "vendor@example.com"
        assert access_log.data_type == "sales_data"
        assert access_log.access_method == "export"
        assert access_log.access_purpose == "GDPR data export request"
        assert access_log.legal_basis == "consent"
        assert access_log.records_accessed == 1  # Default
        assert access_log.ip_address == "unknown"  # Default without request

    def test_log_data_access_with_request(self, audit_service, mock_db):
        """Test data access logging with request context (lines 144-145)"""
        # Create mock request
        mock_request = MagicMock()
        mock_request.client.host = "10.0.0.1"
        mock_request.state.correlation_id = "corr-456"

        access_log = audit_service.log_data_access(
            vendor_id="vendor-123",
            accessor_id="admin-1",
            accessor_email="admin@example.com",
            accessor_role="admin",
            data_subject_id="vendor-123",
            data_subject_email="vendor@example.com",
            data_type="profile_data",
            access_method="view",
            access_purpose="Customer support",
            records_accessed=5,
            request=mock_request
        )

        # Verify request context was captured (covers lines 144-145)
        assert access_log.ip_address == "10.0.0.1"
        assert access_log.correlation_id == "corr-456"
        assert access_log.records_accessed == 5

    def test_log_data_access_without_request(self, audit_service, mock_db):
        """Test data access logging defaults without request"""
        access_log = audit_service.log_data_access(
            vendor_id="vendor-123",
            accessor_id="admin-1",
            accessor_email="admin@example.com",
            accessor_role="admin",
            data_subject_id="vendor-123",
            data_subject_email="vendor@example.com",
            data_type="analytics_data",
            access_method="api",
            access_purpose="Automated reporting"
        )

        # Without request, should use defaults
        assert access_log.ip_address == "unknown"
        assert access_log.correlation_id is None


class TestAuditTrailRetrieval:
    """Test audit trail and access history queries"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return MagicMock()

    @pytest.fixture
    def audit_service(self, mock_db):
        """Create audit service with mocked db"""
        return AuditService(db=mock_db)

    def test_get_user_audit_trail(self, audit_service, mock_db):
        """Test getting user audit trail (lines 184-191)"""
        user_id = "user-123"

        # Mock audit logs
        mock_logs = [
            MagicMock(id=1, user_id=user_id, action=AuditAction.CREATE),
            MagicMock(id=2, user_id=user_id, action=AuditAction.UPDATE),
        ]

        # Mock query chain
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = mock_logs

        # Call method
        logs = audit_service.get_user_audit_trail(user_id=user_id, days=90)

        # Verify query was called correctly
        mock_db.query.assert_called_once_with(AuditLog)
        mock_query.filter.assert_called_once()
        mock_query.order_by.assert_called_once()
        assert len(logs) == 2

    def test_get_user_audit_trail_custom_days(self, audit_service, mock_db):
        """Test getting user audit trail with custom date range"""
        user_id = "user-456"

        # Mock empty results
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []

        logs = audit_service.get_user_audit_trail(user_id=user_id, days=30)

        assert len(logs) == 0
        mock_db.query.assert_called_once()

    def test_get_data_access_history(self, audit_service, mock_db):
        """Test getting data access history (lines 199-206)"""
        data_subject_id = "subject-789"

        # Mock access logs
        mock_access_logs = [
            MagicMock(id=1, data_subject_id=data_subject_id, data_type="sales"),
            MagicMock(id=2, data_subject_id=data_subject_id, data_type="profile"),
        ]

        # Mock query chain
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = mock_access_logs

        # Call method
        logs = audit_service.get_data_access_history(data_subject_id=data_subject_id, days=90)

        # Verify query was called correctly
        mock_db.query.assert_called_once_with(DataAccessLog)
        mock_query.filter.assert_called_once()
        mock_query.order_by.assert_called_once()
        assert len(logs) == 2

    def test_get_data_access_history_custom_days(self, audit_service, mock_db):
        """Test getting data access history with custom date range"""
        data_subject_id = "subject-999"

        # Mock empty results
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []

        logs = audit_service.get_data_access_history(data_subject_id=data_subject_id, days=7)

        assert len(logs) == 0
        mock_db.query.assert_called_once()
