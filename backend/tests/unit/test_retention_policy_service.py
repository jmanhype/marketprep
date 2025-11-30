"""
Unit tests for retention policy service

Tests data retention policy management:
- Policy CRUD operations
- Policy enforcement with legal holds
- Sales data retention (deletion and anonymization)
- Recommendations retention
- Audit logs retention
- Deletion history tracking
- Retention status reporting
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock
from sqlalchemy import and_

from src.services.retention_policy_service import RetentionPolicyService
from src.models.gdpr_compliance import DataRetentionPolicy, LegalHold, DataDeletionLog


class TestPolicyManagement:
    """Test retention policy CRUD operations"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        return db

    @pytest.fixture
    def service(self, mock_db):
        """Create retention policy service"""
        return RetentionPolicyService(db=mock_db)

    def test_create_policy(self, service, mock_db):
        """Test creating a retention policy"""
        policy = service.create_policy(
            vendor_id="vendor-123",
            data_type="sales",
            retention_days=365,
            legal_basis="Business records retention",
            description="Keep sales data for 1 year",
            auto_delete_enabled=True,
            anonymize_instead=False,
        )

        # Verify policy attributes
        assert policy.vendor_id == "vendor-123"
        assert policy.data_type == "sales"
        assert policy.retention_days == 365
        assert policy.is_active is True
        assert policy.auto_delete_enabled is True
        assert policy.anonymize_instead is False

        # Verify database operations
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_get_policy(self, service, mock_db):
        """Test retrieving an active policy"""
        # Mock policy
        mock_policy = MagicMock(spec=DataRetentionPolicy)
        mock_policy.vendor_id = "vendor-123"
        mock_policy.data_type = "sales"
        mock_policy.is_active = True

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_policy

        # Get policy
        result = service.get_policy("vendor-123", "sales")

        assert result == mock_policy
        mock_db.query.assert_called_once()

    def test_list_policies_active_only(self, service, mock_db):
        """Test listing active policies"""
        # Mock policies
        mock_policies = [MagicMock(), MagicMock()]

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = mock_policies

        # List policies
        result = service.list_policies("vendor-123", active_only=True)

        assert len(result) == 2
        assert result == mock_policies

    def test_list_policies_all(self, service, mock_db):
        """Test listing all policies including inactive"""
        mock_policies = [MagicMock(), MagicMock(), MagicMock()]

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = mock_policies

        result = service.list_policies("vendor-123", active_only=False)

        assert len(result) == 3

    def test_update_policy(self, service, mock_db):
        """Test updating a retention policy"""
        # Mock existing policy
        mock_policy = MagicMock(spec=DataRetentionPolicy)
        mock_policy.retention_days = 180
        mock_policy.auto_delete_enabled = False

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_policy

        # Update policy
        result = service.update_policy(
            policy_id="policy-1",
            retention_days=365,
            auto_delete_enabled=True,
        )

        # Verify updates
        assert result.retention_days == 365
        assert result.auto_delete_enabled is True
        mock_db.commit.assert_called_once()

    def test_update_policy_not_found(self, service, mock_db):
        """Test updating non-existent policy raises error"""
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        with pytest.raises(ValueError, match="Policy not found"):
            service.update_policy("nonexistent", retention_days=100)

    def test_delete_policy(self, service, mock_db):
        """Test deactivating a policy (soft delete)"""
        # Mock policy
        mock_policy = MagicMock(spec=DataRetentionPolicy)
        mock_policy.is_active = True

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_policy

        # Delete policy
        service.delete_policy("policy-1")

        # Verify deactivation
        assert mock_policy.is_active is False
        mock_db.commit.assert_called_once()


class TestPolicyEnforcement:
    """Test retention policy enforcement"""

    @pytest.fixture
    def mock_db(self):
        """Mock database"""
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        db.delete = MagicMock()
        return db

    @pytest.fixture
    def service(self, mock_db):
        """Create service"""
        return RetentionPolicyService(db=mock_db)

    def test_enforce_policy_with_legal_hold(self, service, mock_db):
        """Test that enforcement skips policies with legal holds"""
        # Mock policy
        mock_policy = MagicMock(spec=DataRetentionPolicy)
        mock_policy.id = "policy-1"
        mock_policy.vendor_id = "vendor-123"
        mock_policy.data_type = "sales"

        # Mock legal hold
        mock_hold = MagicMock(spec=LegalHold)
        mock_hold.is_active = True
        mock_hold.data_types = ["sales", "recommendations"]

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [mock_hold]

        # Enforce policy
        result = service.enforce_policy(mock_policy, dry_run=False)

        # Should be skipped
        assert "skipped" in result
        assert result["reason"] == "legal_hold"

    def test_enforce_sales_policy_dry_run(self, service, mock_db):
        """Test sales policy enforcement in dry run mode"""
        mock_policy = MagicMock(spec=DataRetentionPolicy)
        mock_policy.vendor_id = "vendor-123"
        mock_policy.data_type = "sales"
        mock_policy.retention_days = 365
        mock_policy.anonymize_instead = False

        # Mock old sales
        mock_sales = [MagicMock(), MagicMock(), MagicMock()]

        call_count = [0]

        def mock_query_side_effect(model):
            result = MagicMock()
            result.filter.return_value = result

            call_count[0] += 1

            if call_count[0] == 1:
                # Legal holds check
                result.all.return_value = []
            elif call_count[0] == 2:
                # Old sales query
                result.all.return_value = mock_sales

            return result

        mock_db.query.side_effect = mock_query_side_effect

        # Enforce in dry run
        result = service.enforce_policy(mock_policy, dry_run=True)

        # Verify dry run result
        assert result["sales"] == 3
        assert result["dry_run"] is True
        # Should not delete in dry run
        mock_db.delete.assert_not_called()

    def test_enforce_sales_policy_deletion(self, service, mock_db):
        """Test actual sales data deletion"""
        mock_policy = MagicMock(spec=DataRetentionPolicy)
        mock_policy.vendor_id = "vendor-123"
        mock_policy.data_type = "sales"
        mock_policy.retention_days = 365
        mock_policy.anonymize_instead = False

        # Mock old sales
        mock_sale = MagicMock()
        mock_sale.id = "sale-1"
        mock_sale.quantity = 10
        mock_sale.total_amount = 100.0

        call_count = [0]

        def mock_query_side_effect(model):
            result = MagicMock()
            result.filter.return_value = result

            call_count[0] += 1

            if call_count[0] == 1:
                result.all.return_value = []  # No legal holds
            elif call_count[0] == 2:
                result.all.return_value = [mock_sale]

            return result

        mock_db.query.side_effect = mock_query_side_effect

        # Enforce policy
        result = service.enforce_policy(mock_policy, dry_run=False)

        # Verify deletion
        assert result["sales"] == 1
        assert result["anonymized"] is False
        mock_db.delete.assert_called()
        mock_db.commit.assert_called()

    def test_enforce_sales_policy_anonymization(self, service, mock_db):
        """Test sales data anonymization instead of deletion"""
        mock_policy = MagicMock(spec=DataRetentionPolicy)
        mock_policy.vendor_id = "vendor-123"
        mock_policy.data_type = "sales"
        mock_policy.retention_days = 365
        mock_policy.anonymize_instead = True

        # Mock old sale
        mock_sale = MagicMock()
        mock_sale.id = "sale-1"
        mock_sale.vendor_id = "vendor-123"
        mock_sale.quantity = 10

        call_count = [0]

        def mock_query_side_effect(model):
            result = MagicMock()
            result.filter.return_value = result

            call_count[0] += 1

            if call_count[0] == 1:
                result.all.return_value = []
            elif call_count[0] == 2:
                result.all.return_value = [mock_sale]

            return result

        mock_db.query.side_effect = mock_query_side_effect

        # Enforce policy
        result = service.enforce_policy(mock_policy, dry_run=False)

        # Verify anonymization
        assert result["sales"] == 1
        assert result["anonymized"] is True
        assert mock_sale.vendor_id == "anonymized"
        mock_db.delete.assert_not_called()  # Should not delete when anonymizing
        mock_db.commit.assert_called()

    def test_enforce_recommendations_policy(self, service, mock_db):
        """Test recommendations retention enforcement"""
        mock_policy = MagicMock(spec=DataRetentionPolicy)
        mock_policy.vendor_id = "vendor-123"
        mock_policy.data_type = "recommendations"
        mock_policy.retention_days = 180

        # Mock old recommendations
        mock_recs = [MagicMock(), MagicMock()]
        for rec in mock_recs:
            rec.id = "rec-1"
            rec.product_id = "prod-1"

        call_count = [0]

        def mock_query_side_effect(model):
            result = MagicMock()
            result.filter.return_value = result

            call_count[0] += 1

            if call_count[0] == 1:
                result.all.return_value = []  # No legal holds
            elif call_count[0] == 2:
                result.all.return_value = mock_recs

            return result

        mock_db.query.side_effect = mock_query_side_effect

        # Enforce policy
        result = service.enforce_policy(mock_policy, dry_run=False)

        # Verify deletion
        assert result["recommendations"] == 2
        assert mock_db.delete.call_count == 2

    def test_enforce_audit_logs_policy(self, service, mock_db):
        """Test audit logs retention enforcement"""
        mock_policy = MagicMock(spec=DataRetentionPolicy)
        mock_policy.vendor_id = "vendor-123"
        mock_policy.data_type = "audit_logs"
        mock_policy.retention_days = 90

        # Mock old logs (non-sensitive, no retention required)
        mock_logs = [MagicMock()]

        call_count = [0]

        def mock_query_side_effect(model):
            result = MagicMock()
            result.filter.return_value = result

            call_count[0] += 1

            if call_count[0] == 1:
                result.all.return_value = []  # No legal holds
            elif call_count[0] == 2:
                result.all.return_value = mock_logs

            return result

        mock_db.query.side_effect = mock_query_side_effect

        # Enforce policy
        result = service.enforce_policy(mock_policy, dry_run=False)

        # Verify deletion
        assert result["audit_logs"] == 1
        mock_db.delete.assert_called_once()

    def test_enforce_unknown_data_type(self, service, mock_db):
        """Test enforcement with unknown data type"""
        mock_policy = MagicMock(spec=DataRetentionPolicy)
        mock_policy.vendor_id = "vendor-123"  # Required for legal hold check
        mock_policy.data_type = "unknown_type"
        mock_policy.retention_days = 365  # Required for cutoff_date calculation

        # Mock no legal holds
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        # Enforce policy
        result = service.enforce_policy(mock_policy, dry_run=False)

        # Should return error
        assert "error" in result
        assert result["error"] == "unknown_data_type"


class TestEnforceAllPolicies:
    """Test bulk policy enforcement"""

    @pytest.fixture
    def mock_db(self):
        """Mock database"""
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        return db

    @pytest.fixture
    def service(self, mock_db):
        """Create service"""
        return RetentionPolicyService(db=mock_db)

    def test_enforce_all_policies_for_vendor(self, service, mock_db):
        """Test enforcing all policies for a specific vendor"""
        # Mock policies
        mock_policy1 = MagicMock(spec=DataRetentionPolicy)
        mock_policy1.id = "policy-1"
        mock_policy1.vendor_id = "vendor-123"
        mock_policy1.data_type = "sales"
        mock_policy1.retention_days = 365

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [mock_policy1]

        # Mock enforce_policy to return success
        with MagicMock() as mock_enforce:
            service.enforce_policy = MagicMock(return_value={"sales": 5})

            # Enforce all
            result = service.enforce_all_policies(vendor_id="vendor-123", dry_run=False)

            # Verify result
            assert result["total_policies"] == 1
            assert result["dry_run"] is False
            assert len(result["policies"]) == 1


class TestHelperMethods:
    """Test helper methods"""

    @pytest.fixture
    def mock_db(self):
        """Mock database"""
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        return db

    @pytest.fixture
    def service(self, mock_db):
        """Create service"""
        return RetentionPolicyService(db=mock_db)

    def test_get_deletion_history(self, service, mock_db):
        """Test retrieving deletion history"""
        # Mock deletion logs
        mock_logs = [MagicMock(), MagicMock()]

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = mock_logs

        # Get history
        result = service.get_deletion_history("vendor-123", days=90)

        # Verify
        assert len(result) == 2
        assert result == mock_logs

    def test_get_retention_status_sales(self, service, mock_db):
        """Test getting retention status for sales policy"""
        # Mock policy
        mock_policy = MagicMock(spec=DataRetentionPolicy)
        mock_policy.data_type = "sales"
        mock_policy.retention_days = 365
        mock_policy.auto_delete_enabled = True
        mock_policy.anonymize_instead = False

        call_count = [0]

        def mock_query_side_effect(model):
            result = MagicMock()
            result.filter.return_value = result

            call_count[0] += 1

            if call_count[0] == 1:
                # list_policies query
                result.all.return_value = [mock_policy]
            elif call_count[0] == 2:
                # Count affected sales
                result.count.return_value = 10

            return result

        mock_db.query.side_effect = mock_query_side_effect

        # Get status
        result = service.get_retention_status("vendor-123")

        # Verify
        assert result["vendor_id"] == "vendor-123"
        assert result["total_policies"] == 1
        assert len(result["policies"]) == 1
        assert result["policies"][0]["data_type"] == "sales"
        assert result["policies"][0]["affected_records"] == 10

    def test_get_retention_status_recommendations(self, service, mock_db):
        """Test retention status for recommendations policy"""
        # Mock policy
        mock_policy = MagicMock(spec=DataRetentionPolicy)
        mock_policy.data_type = "recommendations"
        mock_policy.retention_days = 180
        mock_policy.auto_delete_enabled = True
        mock_policy.anonymize_instead = False

        call_count = [0]

        def mock_query_side_effect(model):
            result = MagicMock()
            result.filter.return_value = result

            call_count[0] += 1

            if call_count[0] == 1:
                result.all.return_value = [mock_policy]
            elif call_count[0] == 2:
                result.count.return_value = 5

            return result

        mock_db.query.side_effect = mock_query_side_effect

        # Get status
        result = service.get_retention_status("vendor-123")

        # Verify
        assert result["policies"][0]["data_type"] == "recommendations"
        assert result["policies"][0]["affected_records"] == 5

    def test_get_retention_status_unknown_type(self, service, mock_db):
        """Test retention status with unknown data type"""
        # Mock policy with unknown type
        mock_policy = MagicMock(spec=DataRetentionPolicy)
        mock_policy.data_type = "unknown"
        mock_policy.retention_days = 90
        mock_policy.auto_delete_enabled = False
        mock_policy.anonymize_instead = False

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [mock_policy]

        # Get status
        result = service.get_retention_status("vendor-123")

        # Unknown types should have 0 affected records
        assert result["policies"][0]["affected_records"] == 0
