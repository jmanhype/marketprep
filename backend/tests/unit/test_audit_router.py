"""Unit tests for audit router.

Tests audit API endpoints:
- GET /audit/verify - Verify hash chain integrity
- GET /audit/logs - List audit logs
- GET /audit/access-logs - List data access logs
"""
import pytest
from datetime import datetime
from uuid import uuid4
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from src.routers.audit import (
    verify_hash_chain,
    list_audit_logs,
    list_data_access_logs,
    HashChainVerificationResponse,
    AuditLogResponse,
    DataAccessLogResponse,
)
from src.models.audit_log import AuditLog, DataAccessLog


class TestVerifyHashChain:
    """Test verify_hash_chain endpoint."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        return uuid4()

    def test_verify_no_logs(self, mock_db, vendor_id):
        """Test verification with no logs."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        result = verify_hash_chain(vendor_id=vendor_id, db=mock_db, days_back=90)

        assert result.is_valid is True
        assert result.total_logs_checked == 0
        assert "No audit logs" in result.message

    def test_verify_valid_chain(self, mock_db, vendor_id):
        """Test verification of valid hash chain."""
        # Create mock logs with valid chain
        log1 = MagicMock(spec=AuditLog)
        log1.id = uuid4()
        log1.timestamp = datetime(2025, 1, 1, 10, 0, 0)
        log1.previous_hash = None
        log1.hash_value = "hash1"
        log1.verify_hash = MagicMock(return_value=True)

        log2 = MagicMock(spec=AuditLog)
        log2.id = uuid4()
        log2.timestamp = datetime(2025, 1, 1, 11, 0, 0)
        log2.previous_hash = "hash1"
        log2.hash_value = "hash2"
        log2.verify_hash = MagicMock(return_value=True)

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [log1, log2]
        mock_db.query.return_value = mock_query

        result = verify_hash_chain(vendor_id=vendor_id, db=mock_db, days_back=90)

        assert result.is_valid is True
        assert result.total_logs_checked == 2
        assert result.broken_chain_at is None
        assert "valid" in result.message.lower()

    def test_verify_broken_chain(self, mock_db, vendor_id):
        """Test verification with broken hash chain."""
        log1 = MagicMock(spec=AuditLog)
        log1.id = uuid4()
        log1.timestamp = datetime(2025, 1, 1, 10, 0, 0)
        log1.previous_hash = None
        log1.hash_value = "hash1"

        log2 = MagicMock(spec=AuditLog)
        log2.id = uuid4()
        log2.timestamp = datetime(2025, 1, 1, 11, 0, 0)
        log2.previous_hash = "wrong_hash"  # Broken chain!
        log2.hash_value = "hash2"

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [log1, log2]
        mock_db.query.return_value = mock_query

        result = verify_hash_chain(vendor_id=vendor_id, db=mock_db, days_back=90)

        assert result.is_valid is False
        assert result.broken_log_id == log2.id
        assert "INVALID" in result.message


class TestListAuditLogs:
    """Test list_audit_logs endpoint."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        return uuid4()

    @pytest.fixture
    def sample_logs(self, vendor_id):
        log = MagicMock(spec=AuditLog)
        log.id = uuid4()
        log.vendor_id = str(vendor_id)
        log.user_email = "user@test.com"
        log.action = "UPDATE"
        log.resource_type = "Product"
        log.resource_id = str(uuid4())
        log.changes_summary = "Updated price"
        log.ip_address = "192.168.1.1"
        log.request_method = "PATCH"
        log.request_path = "/api/products/123"
        log.timestamp = datetime(2025, 1, 15, 12, 0, 0)
        log.is_sensitive = False
        return [log]

    def test_list_logs(self, mock_db, vendor_id, sample_logs):
        """Test listing audit logs."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.all.return_value = sample_logs
        mock_db.query.return_value = mock_query

        results = list_audit_logs(
            vendor_id=vendor_id,
            db=mock_db,
            limit=100,
            offset=0,
            days_back=30,
            action=None,
            resource_type=None,
        )

        assert len(results) == 1
        assert isinstance(results[0], AuditLogResponse)
        assert results[0].action == "UPDATE"


class TestListDataAccessLogs:
    """Test list_data_access_logs endpoint."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        return uuid4()

    @pytest.fixture
    def sample_access_logs(self, vendor_id):
        log = MagicMock(spec=DataAccessLog)
        log.id = uuid4()
        log.vendor_id = str(vendor_id)
        log.accessor_email = "admin@test.com"
        log.accessor_role = "admin"
        log.data_subject_email = "user@test.com"
        log.data_type = "PersonalData"
        log.access_method = "API"
        log.access_purpose = "Customer Support"
        log.legal_basis = "Legitimate Interest"
        log.records_accessed = 1
        log.accessed_at = datetime(2025, 1, 15, 12, 0, 0)
        return [log]

    def test_list_access_logs(self, mock_db, vendor_id, sample_access_logs):
        """Test listing data access logs."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.all.return_value = sample_access_logs
        mock_db.query.return_value = mock_query

        results = list_data_access_logs(
            vendor_id=vendor_id,
            db=mock_db,
            limit=100,
            offset=0,
            days_back=30,
        )

        assert len(results) == 1
        assert isinstance(results[0], DataAccessLogResponse)
        assert results[0].accessor_email == "admin@test.com"
