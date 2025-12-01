"""
Unit tests for WORM Storage Adapter

Tests AWS S3 Object Lock integration for immutable audit log storage.
"""

import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
from botocore.exceptions import ClientError

from src.adapters.worm_storage_adapter import (
    WORMStorageAdapter,
    get_worm_storage,
    store_audit_to_worm,
)


class TestWORMStorageAdapterInit:
    """Test WORMStorageAdapter initialization"""

    def test_init_with_bucket_name(self):
        """Test initialization with explicit bucket name"""
        with patch('src.adapters.worm_storage_adapter.boto3') as mock_boto3:
            mock_s3 = MagicMock()
            mock_boto3.client.return_value = mock_s3

            # Mock Object Lock configuration check
            mock_s3.get_object_lock_configuration.return_value = {
                "ObjectLockConfiguration": {"ObjectLockEnabled": "Enabled"}
            }

            adapter = WORMStorageAdapter(bucket_name="test-worm-bucket")

            assert adapter.bucket_name == "test-worm-bucket"
            assert adapter.enabled is True
            assert adapter.retention_days == 2555  # Default 7 years

    def test_init_without_bucket_name_disables_storage(self):
        """Test initialization without bucket name disables WORM storage"""
        with patch('src.adapters.worm_storage_adapter.settings') as mock_settings:
            mock_settings.worm_bucket = None

            adapter = WORMStorageAdapter()

            assert adapter.enabled is False
            assert adapter.bucket_name is None

    def test_init_with_custom_retention_days(self):
        """Test initialization with custom retention period"""
        with patch('src.adapters.worm_storage_adapter.boto3') as mock_boto3:
            mock_s3 = MagicMock()
            mock_boto3.client.return_value = mock_s3
            mock_s3.get_object_lock_configuration.return_value = {
                "ObjectLockConfiguration": {"ObjectLockEnabled": "Enabled"}
            }

            adapter = WORMStorageAdapter(bucket_name="test-bucket", retention_days=365)

            assert adapter.retention_days == 365

    def test_init_verifies_object_lock_enabled(self):
        """Test initialization verifies Object Lock is enabled"""
        with patch('src.adapters.worm_storage_adapter.boto3') as mock_boto3:
            mock_s3 = MagicMock()
            mock_boto3.client.return_value = mock_s3

            # Object Lock is NOT enabled
            mock_s3.get_object_lock_configuration.return_value = {
                "ObjectLockConfiguration": {"ObjectLockEnabled": "Disabled"}
            }

            with pytest.raises(ValueError, match="does not have Object Lock enabled"):
                WORMStorageAdapter(bucket_name="test-bucket")

    def test_init_handles_object_lock_check_failure(self, caplog):
        """Test initialization handles Object Lock check failure gracefully"""
        with patch('src.adapters.worm_storage_adapter.boto3') as mock_boto3:
            mock_s3 = MagicMock()
            mock_boto3.client.return_value = mock_s3

            # Simulate AWS error
            mock_s3.get_object_lock_configuration.side_effect = ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
                "GetObjectLockConfiguration"
            )

            adapter = WORMStorageAdapter(bucket_name="test-bucket")

            # Should disable storage instead of crashing
            assert adapter.enabled is False


class TestStoreAuditLog:
    """Test store_audit_log method"""

    @pytest.fixture
    def adapter(self):
        """Create enabled WORMStorageAdapter"""
        with patch('src.adapters.worm_storage_adapter.boto3') as mock_boto3:
            mock_s3 = MagicMock()
            mock_boto3.client.return_value = mock_s3
            mock_s3.get_object_lock_configuration.return_value = {
                "ObjectLockConfiguration": {"ObjectLockEnabled": "Enabled"}
            }

            adapter = WORMStorageAdapter(bucket_name="test-bucket")
            adapter.s3_client = mock_s3
            return adapter

    def test_store_audit_log_success(self, adapter):
        """Test successful audit log storage"""
        audit_data = {
            "action": "DELETE",
            "resource": "product",
            "timestamp": "2024-01-15T10:30:00",
        }

        key = adapter.store_audit_log(
            audit_log_id="test-id-123",
            audit_data=audit_data,
            vendor_id="vendor-456"
        )

        # Verify S3 put_object was called
        assert adapter.s3_client.put_object.called
        call_kwargs = adapter.s3_client.put_object.call_args.kwargs

        assert call_kwargs["Bucket"] == "test-bucket"
        assert "audit_logs/vendor-456/2024/01/15/test-id-123.json" in call_kwargs["Key"]
        assert call_kwargs["ObjectLockMode"] == "COMPLIANCE"
        assert call_kwargs["ServerSideEncryption"] == "AES256"
        assert "ObjectLockRetainUntilDate" in call_kwargs

        # Verify key format
        assert key.startswith("audit_logs/vendor-456/")
        assert key.endswith("test-id-123.json")

    def test_store_audit_log_when_disabled_returns_none(self):
        """Test store_audit_log returns None when WORM storage is disabled"""
        adapter = WORMStorageAdapter()  # No bucket = disabled

        key = adapter.store_audit_log(
            audit_log_id="test-id",
            audit_data={"action": "DELETE"},
            vendor_id="vendor-1"
        )

        assert key is None

    def test_store_audit_log_handles_exception(self, adapter, caplog):
        """Test store_audit_log handles S3 exceptions gracefully"""
        adapter.s3_client.put_object.side_effect = Exception("S3 error")

        key = adapter.store_audit_log(
            audit_log_id="test-id",
            audit_data={"action": "DELETE"},
            vendor_id="vendor-1"
        )

        assert key is None
        assert "Failed to store audit log" in caplog.text


class TestStoreDeletionRecord:
    """Test store_deletion_record method"""

    @pytest.fixture
    def adapter(self):
        """Create enabled WORMStorageAdapter"""
        with patch('src.adapters.worm_storage_adapter.boto3') as mock_boto3:
            mock_s3 = MagicMock()
            mock_boto3.client.return_value = mock_s3
            mock_s3.get_object_lock_configuration.return_value = {
                "ObjectLockConfiguration": {"ObjectLockEnabled": "Enabled"}
            }

            adapter = WORMStorageAdapter(bucket_name="test-bucket")
            adapter.s3_client = mock_s3
            return adapter

    def test_store_deletion_record_success(self, adapter):
        """Test successful deletion record storage"""
        deletion_data = {
            "vendor_id": "vendor-123",
            "deleted_at": "2024-01-15T10:30:00",
            "reason": "GDPR request"
        }

        key = adapter.store_deletion_record(
            deletion_id="del-456",
            deletion_data=deletion_data,
            vendor_id="vendor-123"
        )

        # Verify S3 put_object was called
        assert adapter.s3_client.put_object.called
        call_kwargs = adapter.s3_client.put_object.call_args.kwargs

        assert call_kwargs["Bucket"] == "test-bucket"
        assert "deletion_records/vendor-123/" in call_kwargs["Key"]
        assert call_kwargs["Key"].endswith("del-456.json")
        assert call_kwargs["ObjectLockMode"] == "COMPLIANCE"

        assert key is not None

    def test_store_deletion_record_when_disabled_returns_none(self):
        """Test store_deletion_record returns None when disabled"""
        adapter = WORMStorageAdapter()  # Disabled

        key = adapter.store_deletion_record(
            deletion_id="del-1",
            deletion_data={},
            vendor_id="vendor-1"
        )

        assert key is None

    def test_store_deletion_record_handles_exception(self, adapter, caplog):
        """Test store_deletion_record handles exceptions"""
        adapter.s3_client.put_object.side_effect = Exception("S3 error")

        key = adapter.store_deletion_record(
            deletion_id="del-1",
            deletion_data={},
            vendor_id="vendor-1"
        )

        assert key is None
        assert "Failed to store deletion record" in caplog.text


class TestRetrieveAuditLog:
    """Test retrieve_audit_log method"""

    @pytest.fixture
    def adapter(self):
        """Create enabled WORMStorageAdapter"""
        with patch('src.adapters.worm_storage_adapter.boto3') as mock_boto3:
            mock_s3 = MagicMock()
            mock_boto3.client.return_value = mock_s3
            mock_s3.get_object_lock_configuration.return_value = {
                "ObjectLockConfiguration": {"ObjectLockEnabled": "Enabled"}
            }

            adapter = WORMStorageAdapter(bucket_name="test-bucket")
            adapter.s3_client = mock_s3
            return adapter

    def test_retrieve_audit_log_success(self, adapter):
        """Test successful audit log retrieval"""
        audit_data = {"action": "DELETE", "resource": "product"}
        data_hash = adapter._calculate_hash(audit_data)

        # Mock S3 response
        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps(audit_data).encode()

        adapter.s3_client.get_object.return_value = {
            "Body": mock_body,
            "Metadata": {"hash": data_hash}
        }

        result = adapter.retrieve_audit_log("audit_logs/vendor-1/2024/01/15/test.json")

        assert result == audit_data
        assert "_hash_mismatch" not in result

    def test_retrieve_audit_log_when_disabled_returns_none(self):
        """Test retrieve returns None when disabled"""
        adapter = WORMStorageAdapter()

        result = adapter.retrieve_audit_log("some-key")

        assert result is None

    def test_retrieve_audit_log_detects_hash_mismatch(self, adapter, caplog):
        """Test retrieve detects hash mismatch (tampering)"""
        audit_data = {"action": "DELETE"}

        mock_body = MagicMock()
        mock_body.read.return_value = json.dumps(audit_data).encode()

        adapter.s3_client.get_object.return_value = {
            "Body": mock_body,
            "Metadata": {"hash": "wrong-hash-value"}
        }

        result = adapter.retrieve_audit_log("test-key")

        # Should still return data but flag the mismatch
        assert result is not None
        assert result["_hash_mismatch"] is True
        assert "Hash mismatch" in caplog.text

    def test_retrieve_audit_log_handles_not_found(self, adapter, caplog):
        """Test retrieve handles NoSuchKey error"""
        adapter.s3_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Not found"}},
            "GetObject"
        )

        result = adapter.retrieve_audit_log("missing-key")

        assert result is None
        assert "not found" in caplog.text.lower()

    def test_retrieve_audit_log_handles_other_errors(self, adapter, caplog):
        """Test retrieve handles other AWS errors"""
        adapter.s3_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
            "GetObject"
        )

        result = adapter.retrieve_audit_log("test-key")

        assert result is None
        assert "Failed to retrieve" in caplog.text


class TestListAuditLogs:
    """Test list_audit_logs method"""

    @pytest.fixture
    def adapter(self):
        """Create enabled WORMStorageAdapter"""
        with patch('src.adapters.worm_storage_adapter.boto3') as mock_boto3:
            mock_s3 = MagicMock()
            mock_boto3.client.return_value = mock_s3
            mock_s3.get_object_lock_configuration.return_value = {
                "ObjectLockConfiguration": {"ObjectLockEnabled": "Enabled"}
            }

            adapter = WORMStorageAdapter(bucket_name="test-bucket")
            adapter.s3_client = mock_s3
            return adapter

    def test_list_audit_logs_success(self, adapter):
        """Test successful audit log listing"""
        adapter.s3_client.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "audit_logs/vendor-1/2024/01/15/log1.json"},
                {"Key": "audit_logs/vendor-1/2024/01/15/log2.json"},
            ]
        }

        keys = adapter.list_audit_logs(vendor_id="vendor-1")

        assert len(keys) == 2
        assert "log1.json" in keys[0]
        assert "log2.json" in keys[1]

    def test_list_audit_logs_when_disabled_returns_empty(self):
        """Test list returns empty list when disabled"""
        adapter = WORMStorageAdapter()

        keys = adapter.list_audit_logs(vendor_id="vendor-1")

        assert keys == []

    def test_list_audit_logs_with_start_date(self, adapter):
        """Test listing with start date builds correct prefix"""
        adapter.s3_client.list_objects_v2.return_value = {"Contents": []}

        start_date = datetime(2024, 1, 15)
        adapter.list_audit_logs(vendor_id="vendor-1", start_date=start_date)

        call_kwargs = adapter.s3_client.list_objects_v2.call_args.kwargs
        assert call_kwargs["Prefix"] == "audit_logs/vendor-1/2024/01/"

    def test_list_audit_logs_without_start_date(self, adapter):
        """Test listing without start date uses vendor prefix"""
        adapter.s3_client.list_objects_v2.return_value = {"Contents": []}

        adapter.list_audit_logs(vendor_id="vendor-1")

        call_kwargs = adapter.s3_client.list_objects_v2.call_args.kwargs
        assert call_kwargs["Prefix"] == "audit_logs/vendor-1/"

    def test_list_audit_logs_filters_by_end_date(self, adapter):
        """Test listing filters results by end date"""
        adapter.s3_client.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "audit_logs/vendor-1/2024/01/10/log1.json"},
                {"Key": "audit_logs/vendor-1/2024/01/20/log2.json"},
            ]
        }

        end_date = datetime(2024, 1, 15)
        keys = adapter.list_audit_logs(vendor_id="vendor-1", end_date=end_date)

        # Should only include log1 (Jan 10 <= Jan 15)
        assert len(keys) == 1
        assert "01/10" in keys[0]

    def test_list_audit_logs_when_no_contents(self, adapter):
        """Test listing when bucket has no matching objects"""
        adapter.s3_client.list_objects_v2.return_value = {}  # No Contents key

        keys = adapter.list_audit_logs(vendor_id="vendor-1")

        assert keys == []

    def test_list_audit_logs_handles_exception(self, adapter, caplog):
        """Test listing handles exceptions"""
        adapter.s3_client.list_objects_v2.side_effect = Exception("S3 error")

        keys = adapter.list_audit_logs(vendor_id="vendor-1")

        assert keys == []
        assert "Failed to list audit logs" in caplog.text


class TestVerifyImmutability:
    """Test verify_immutability method"""

    @pytest.fixture
    def adapter(self):
        """Create enabled WORMStorageAdapter"""
        with patch('src.adapters.worm_storage_adapter.boto3') as mock_boto3:
            mock_s3 = MagicMock()
            mock_boto3.client.return_value = mock_s3
            mock_s3.get_object_lock_configuration.return_value = {
                "ObjectLockConfiguration": {"ObjectLockEnabled": "Enabled"}
            }

            adapter = WORMStorageAdapter(bucket_name="test-bucket")
            adapter.s3_client = mock_s3
            return adapter

    def test_verify_immutability_returns_true_for_locked_object(self, adapter):
        """Test verify returns True for object with COMPLIANCE lock"""
        from datetime import timezone

        future_date = datetime.now(timezone.utc) + timedelta(days=365)

        adapter.s3_client.get_object_retention.return_value = {
            "Retention": {
                "Mode": "COMPLIANCE",
                "RetainUntilDate": future_date
            }
        }

        result = adapter.verify_immutability("test-key")

        assert result is True

    def test_verify_immutability_when_disabled_returns_false(self):
        """Test verify returns False when storage is disabled"""
        adapter = WORMStorageAdapter()

        result = adapter.verify_immutability("test-key")

        assert result is False

    def test_verify_immutability_returns_false_for_governance_mode(self, adapter):
        """Test verify returns False for GOVERNANCE mode (not COMPLIANCE)"""
        from datetime import timezone

        future_date = datetime.now(timezone.utc) + timedelta(days=365)

        adapter.s3_client.get_object_retention.return_value = {
            "Retention": {
                "Mode": "GOVERNANCE",  # Not COMPLIANCE
                "RetainUntilDate": future_date
            }
        }

        result = adapter.verify_immutability("test-key")

        assert result is False

    def test_verify_immutability_returns_false_for_expired_retention(self, adapter):
        """Test verify returns False for expired retention date"""
        from datetime import timezone

        past_date = datetime.now(timezone.utc) - timedelta(days=1)

        adapter.s3_client.get_object_retention.return_value = {
            "Retention": {
                "Mode": "COMPLIANCE",
                "RetainUntilDate": past_date
            }
        }

        result = adapter.verify_immutability("test-key")

        assert result is False

    def test_verify_immutability_handles_no_lock_configuration(self, adapter, caplog):
        """Test verify handles NoSuchObjectLockConfiguration error"""
        adapter.s3_client.get_object_retention.side_effect = ClientError(
            {"Error": {"Code": "NoSuchObjectLockConfiguration", "Message": "No lock"}},
            "GetObjectRetention"
        )

        result = adapter.verify_immutability("test-key")

        assert result is False
        assert "does not have Object Lock enabled" in caplog.text

    def test_verify_immutability_handles_other_errors(self, adapter, caplog):
        """Test verify handles other AWS errors"""
        adapter.s3_client.get_object_retention.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
            "GetObjectRetention"
        )

        result = adapter.verify_immutability("test-key")

        assert result is False
        assert "Failed to verify immutability" in caplog.text


class TestHelperMethods:
    """Test helper methods"""

    def test_calculate_hash_deterministic(self):
        """Test hash calculation is deterministic"""
        with patch('src.adapters.worm_storage_adapter.boto3') as mock_boto3:
            mock_s3 = MagicMock()
            mock_boto3.client.return_value = mock_s3
            mock_s3.get_object_lock_configuration.return_value = {
                "ObjectLockConfiguration": {"ObjectLockEnabled": "Enabled"}
            }

            adapter = WORMStorageAdapter(bucket_name="test")

            data = {"action": "DELETE", "id": 123}

            hash1 = adapter._calculate_hash(data)
            hash2 = adapter._calculate_hash(data)

            assert hash1 == hash2
            assert len(hash1) == 64  # SHA-256 hex digest

    def test_calculate_hash_different_for_different_data(self):
        """Test hash changes when data changes"""
        with patch('src.adapters.worm_storage_adapter.boto3') as mock_boto3:
            mock_s3 = MagicMock()
            mock_boto3.client.return_value = mock_s3
            mock_s3.get_object_lock_configuration.return_value = {
                "ObjectLockConfiguration": {"ObjectLockEnabled": "Enabled"}
            }

            adapter = WORMStorageAdapter(bucket_name="test")

            data1 = {"action": "DELETE"}
            data2 = {"action": "UPDATE"}

            hash1 = adapter._calculate_hash(data1)
            hash2 = adapter._calculate_hash(data2)

            assert hash1 != hash2

    def test_extract_date_from_key(self):
        """Test date extraction from S3 key"""
        with patch('src.adapters.worm_storage_adapter.boto3') as mock_boto3:
            mock_s3 = MagicMock()
            mock_boto3.client.return_value = mock_s3
            mock_s3.get_object_lock_configuration.return_value = {
                "ObjectLockConfiguration": {"ObjectLockEnabled": "Enabled"}
            }

            adapter = WORMStorageAdapter(bucket_name="test")

            key = "audit_logs/vendor-1/2024/01/15/log-id.json"
            date = adapter._extract_date_from_key(key)

            assert date.year == 2024
            assert date.month == 1
            assert date.day == 15

    def test_extract_date_from_invalid_key(self):
        """Test date extraction from invalid key returns datetime.min"""
        with patch('src.adapters.worm_storage_adapter.boto3') as mock_boto3:
            mock_s3 = MagicMock()
            mock_boto3.client.return_value = mock_s3
            mock_s3.get_object_lock_configuration.return_value = {
                "ObjectLockConfiguration": {"ObjectLockEnabled": "Enabled"}
            }

            adapter = WORMStorageAdapter(bucket_name="test")

            key = "invalid/key"
            date = adapter._extract_date_from_key(key)

            assert date == datetime.min


class TestGlobalFunctions:
    """Test module-level functions"""

    def test_get_worm_storage_returns_singleton(self):
        """Test get_worm_storage returns same instance"""
        with patch('src.adapters.worm_storage_adapter.boto3'):
            # Reset global
            import src.adapters.worm_storage_adapter
            src.adapters.worm_storage_adapter._worm_storage = None

            storage1 = get_worm_storage()
            storage2 = get_worm_storage()

            assert storage1 is storage2

    def test_store_audit_to_worm_convenience_function(self):
        """Test store_audit_to_worm convenience function"""
        with patch('src.adapters.worm_storage_adapter.get_worm_storage') as mock_get_storage:
            mock_storage = MagicMock()
            mock_get_storage.return_value = mock_storage

            store_audit_to_worm(
                audit_log_id="test-id",
                audit_data={"action": "DELETE"},
                vendor_id="vendor-1"
            )

            # Verify it called the adapter
            mock_storage.store_audit_log.assert_called_once_with(
                "test-id",
                {"action": "DELETE"},
                "vendor-1"
            )

    def test_store_audit_to_worm_handles_exception(self, caplog):
        """Test store_audit_to_worm handles exceptions gracefully"""
        with patch('src.adapters.worm_storage_adapter.get_worm_storage') as mock_get_storage:
            mock_storage = MagicMock()
            mock_storage.store_audit_log.side_effect = Exception("Storage error")
            mock_get_storage.return_value = mock_storage

            # Should not raise
            store_audit_to_worm(
                audit_log_id="test-id",
                audit_data={},
                vendor_id="vendor-1"
            )

            assert "Failed to store audit log" in caplog.text
