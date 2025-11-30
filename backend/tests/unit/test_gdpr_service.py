"""
Unit tests for GDPR compliance service

Tests GDPR compliance functionality:
- Consent management (Article 7)
- Data subject access requests (DSAR)
- Data export (Article 15 - Right to access)
- Data deletion (Article 17 - Right to erasure)
- Data anonymization
- Legal holds
- Retention policies
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import hashlib

from src.services.gdpr_service import GDPRService
from src.models.gdpr_compliance import (
    UserConsent,
    DataSubjectRequest,
    DSARStatus,
    LegalHold,
    DataRetentionPolicy,
    DataDeletionLog,
)


class TestConsentManagement:
    """Test GDPR Article 7 - Consent management"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        return db

    @pytest.fixture
    def gdpr_service(self, mock_db):
        """Create GDPR service"""
        return GDPRService(db=mock_db)

    def test_record_consent_given(self, gdpr_service, mock_db):
        """Test recording user consent"""
        consent = gdpr_service.record_consent(
            vendor_id="vendor-123",
            user_id="user-456",
            user_email="user@example.com",
            consent_type="marketing",
            consent_given=True,
            consent_text="I consent to marketing emails",
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
        )

        # Verify consent object
        assert consent.vendor_id == "vendor-123"
        assert consent.consent_type == "marketing"
        assert consent.consent_given is True
        assert consent.given_at is not None
        assert consent.withdrawn_at is None
        assert consent.ip_address == "192.168.1.1"

        # Verify database operations
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_record_consent_withdrawn(self, gdpr_service, mock_db):
        """Test recording consent withdrawal"""
        consent = gdpr_service.record_consent(
            vendor_id="vendor-123",
            user_id="user-456",
            user_email="user@example.com",
            consent_type="marketing",
            consent_given=False,
            consent_text="I withdraw consent",
            ip_address="192.168.1.1",
        )

        assert consent.consent_given is False
        assert consent.given_at is None
        assert consent.withdrawn_at is not None

    def test_withdraw_consent(self, gdpr_service, mock_db):
        """Test withdrawing previously given consent"""
        # Mock existing consent
        existing_consent = MagicMock(spec=UserConsent)
        existing_consent.consent_given = True
        existing_consent.withdrawn_at = None

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = existing_consent

        # Withdraw consent
        result = gdpr_service.withdraw_consent(
            user_id="user-456",
            consent_type="marketing",
        )

        # Verify consent was updated
        assert result.consent_given is False
        assert result.withdrawn_at is not None
        mock_db.commit.assert_called_once()

    def test_withdraw_consent_not_found(self, gdpr_service, mock_db):
        """Test withdrawing consent that doesn't exist"""
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        result = gdpr_service.withdraw_consent(
            user_id="user-456",
            consent_type="marketing",
        )

        assert result is None


class TestDSARCreation:
    """Test Data Subject Access Requests"""

    @pytest.fixture
    def mock_db(self):
        """Mock database"""
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        return db

    @pytest.fixture
    def gdpr_service(self, mock_db):
        """Create GDPR service"""
        return GDPRService(db=mock_db)

    def test_create_dsar(self, gdpr_service, mock_db):
        """Test creating a data subject access request"""
        dsar = gdpr_service.create_dsar(
            vendor_id="vendor-123",
            user_id="user-456",
            user_email="user@example.com",
            request_type="access",
            description="Request my personal data",
        )

        # Verify DSAR object
        assert dsar.vendor_id == "vendor-123"
        assert dsar.user_id == "user-456"
        assert dsar.request_type == "access"
        assert dsar.status == DSARStatus.PENDING
        assert dsar.requested_at is not None
        assert dsar.deadline is not None

        # Deadline should be 30 days from now
        expected_deadline = datetime.utcnow() + timedelta(days=30)
        assert abs((dsar.deadline - expected_deadline).total_seconds()) < 5

        # Verify database operations
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()


class TestDataExport:
    """Test GDPR Article 15 - Right to access"""

    @pytest.fixture
    def mock_db(self):
        """Mock database"""
        return MagicMock()

    @pytest.fixture
    def gdpr_service(self, mock_db):
        """Create GDPR service"""
        return GDPRService(db=mock_db)

    def test_export_user_data(self, gdpr_service, mock_db):
        """Test exporting complete user data package"""
        user_id = "user-123"

        # Mock vendor
        mock_vendor = MagicMock()
        mock_vendor.email = "user@example.com"
        mock_vendor.business_name = "Test Business"
        mock_vendor.created_at = datetime(2025, 1, 1)

        # Mock products
        mock_product = MagicMock()
        mock_product.id = "prod-1"
        mock_product.name = "Product 1"
        mock_product.category = "food"
        mock_product.price = 10.0
        mock_product.created_at = datetime(2025, 1, 2)

        # Mock sales
        mock_sale = MagicMock()
        mock_sale.id = "sale-1"
        mock_sale.product_id = "prod-1"
        mock_sale.quantity = 5
        mock_sale.total_amount = 50.0
        mock_sale.sale_date = datetime(2025, 1, 3)

        # Mock recommendations
        mock_rec = MagicMock()
        mock_rec.id = "rec-1"
        mock_rec.product_id = "prod-1"
        mock_rec.market_date = datetime(2025, 1, 4)
        mock_rec.recommended_quantity = 8
        mock_rec.confidence_score = 0.85

        # Mock feedback
        mock_feedback = MagicMock()
        mock_feedback.id = "fb-1"
        mock_feedback.recommendation_id = "rec-1"
        mock_feedback.actual_quantity_sold = 7
        mock_feedback.rating = 5
        mock_feedback.was_accurate = True

        # Mock consents
        mock_consent = MagicMock()
        mock_consent.consent_type = "marketing"
        mock_consent.consent_given = True
        mock_consent.given_at = datetime(2025, 1, 5)
        mock_consent.withdrawn_at = None

        # Setup query mocks
        call_count = [0]

        def mock_query_side_effect(model):
            result = MagicMock()
            result.filter.return_value = result
            result.first.return_value = None
            result.all.return_value = []

            call_count[0] += 1

            # Vendor query
            if call_count[0] == 1:
                result.first.return_value = mock_vendor
            # Products query
            elif call_count[0] == 2:
                result.all.return_value = [mock_product]
            # Sales query
            elif call_count[0] == 3:
                result.all.return_value = [mock_sale]
            # Recommendations query
            elif call_count[0] == 4:
                result.all.return_value = [mock_rec]
            # Feedback query
            elif call_count[0] == 5:
                result.all.return_value = [mock_feedback]
            # Consents query
            elif call_count[0] == 6:
                result.all.return_value = [mock_consent]

            return result

        mock_db.query.side_effect = mock_query_side_effect

        # Export data
        data_package = gdpr_service.export_user_data(user_id)

        # Verify structure
        assert "export_date" in data_package
        assert "user_id" in data_package
        assert data_package["user_id"] == user_id

        # Verify personal information
        assert data_package["personal_information"]["email"] == "user@example.com"
        assert data_package["personal_information"]["name"] == "Test Business"

        # Verify products
        assert len(data_package["products"]) == 1
        assert data_package["products"][0]["name"] == "Product 1"

        # Verify sales
        assert len(data_package["sales"]) == 1
        assert data_package["sales"][0]["quantity"] == 5

        # Verify recommendations
        assert len(data_package["recommendations"]) == 1

        # Verify feedback
        assert len(data_package["feedback"]) == 1

        # Verify consents
        assert len(data_package["consents"]) == 1


class TestDataDeletion:
    """Test GDPR Article 17 - Right to erasure"""

    @pytest.fixture
    def mock_db(self):
        """Mock database"""
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        db.delete = MagicMock()
        return db

    @pytest.fixture
    def gdpr_service(self, mock_db):
        """Create GDPR service"""
        return GDPRService(db=mock_db)

    def test_delete_user_data_checks_legal_holds(self, gdpr_service, mock_db):
        """Test that deletion checks for legal holds"""
        user_id = "user-123"

        # Mock active legal hold
        mock_hold = MagicMock()
        mock_hold.is_active = True

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [mock_hold]

        # Attempt deletion
        with pytest.raises(ValueError, match="Cannot delete data.*legal hold"):
            gdpr_service.delete_user_data(user_id)

    def test_delete_user_data_success(self, gdpr_service, mock_db):
        """Test successful data deletion"""
        user_id = "user-123"

        # Mock products, sales, recommendations
        mock_product = MagicMock()
        mock_product.id = "prod-1"
        mock_product.name = "Product 1"

        mock_sale = MagicMock()
        mock_sale.id = "sale-1"
        mock_sale.quantity = 5

        mock_rec = MagicMock()
        mock_rec.id = "rec-1"

        # Setup query chain for products, sales, recommendations
        call_count = [0]

        def mock_query_side_effect(model):
            result = MagicMock()
            result.filter.return_value = result

            call_count[0] += 1

            # Legal holds check
            if call_count[0] == 1:
                result.all.return_value = []
            # Products
            elif call_count[0] in [2, 5]:  # Query and delete
                result.all.return_value = [mock_product]
                result.delete.return_value = None
            # Sales
            elif call_count[0] in [3, 6]:
                result.all.return_value = [mock_sale]
                result.delete.return_value = None
            # Recommendations
            elif call_count[0] in [4, 7]:
                result.all.return_value = [mock_rec]
                result.delete.return_value = None

            return result

        mock_db.query.side_effect = mock_query_side_effect

        # Delete data
        counts = gdpr_service.delete_user_data(user_id, anonymize=False)

        # Verify counts exist (actual values depend on mock behavior)
        assert isinstance(counts, dict)
        assert mock_db.commit.called

    def test_anonymize_user_data(self, gdpr_service, mock_db):
        """Test data anonymization instead of deletion"""
        user_id = "user-123"

        # Mock no legal holds
        call_count = [0]

        def mock_query_side_effect(model):
            result = MagicMock()
            result.filter.return_value = result

            call_count[0] += 1

            if call_count[0] == 1:
                # Legal holds check
                result.all.return_value = []
            elif call_count[0] == 2:
                # Vendor query
                mock_vendor = MagicMock()
                mock_vendor.id = user_id
                mock_vendor.email = "user@example.com"
                mock_vendor.business_name = "Test Business"
                result.first.return_value = mock_vendor

            return result

        mock_db.query.side_effect = mock_query_side_effect

        # Anonymize data
        counts = gdpr_service.delete_user_data(user_id, anonymize=True)

        # Verify counts
        assert "vendor" in counts
        assert counts["vendor"] == 1


class TestRetentionPolicies:
    """Test automated data retention policies"""

    @pytest.fixture
    def mock_db(self):
        """Mock database"""
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        db.delete = MagicMock()
        return db

    @pytest.fixture
    def gdpr_service(self, mock_db):
        """Create GDPR service"""
        return GDPRService(db=mock_db)

    def test_apply_retention_policies(self, gdpr_service, mock_db):
        """Test applying automated retention policies"""
        # Mock active retention policy
        mock_policy = MagicMock()
        mock_policy.is_active = True
        mock_policy.auto_delete_enabled = True
        mock_policy.data_type = "sales"
        mock_policy.retention_days = 90
        mock_policy.anonymize_instead = False

        # Mock old sale
        cutoff = datetime.utcnow() - timedelta(days=90)
        mock_sale = MagicMock()
        mock_sale.id = "sale-1"
        mock_sale.vendor_id = "vendor-123"
        mock_sale.sale_date = cutoff - timedelta(days=10)  # Older than retention

        call_count = [0]

        def mock_query_side_effect(model):
            result = MagicMock()
            result.filter.return_value = result

            call_count[0] += 1

            if call_count[0] == 1:
                # Policies query
                result.all.return_value = [mock_policy]
            elif call_count[0] == 2:
                # Legal holds check
                result.first.return_value = None  # No active holds
            elif call_count[0] == 3:
                # Old sales query
                result.all.return_value = [mock_sale]

            return result

        mock_db.query.side_effect = mock_query_side_effect

        # Apply policies
        deletion_counts = gdpr_service.apply_retention_policies()

        # Verify
        assert "sales" in deletion_counts
        assert deletion_counts["sales"] == 1
        mock_db.commit.assert_called()

    def test_apply_retention_policies_skips_legal_holds(self, gdpr_service, mock_db):
        """Test that retention policies respect legal holds"""
        # Mock active retention policy
        mock_policy = MagicMock()
        mock_policy.is_active = True
        mock_policy.auto_delete_enabled = True
        mock_policy.data_type = "sales"
        mock_policy.retention_days = 90

        # Mock active legal hold
        mock_hold = MagicMock()
        mock_hold.is_active = True
        mock_hold.data_types = ["sales"]

        call_count = [0]

        def mock_query_side_effect(model):
            result = MagicMock()
            result.filter.return_value = result

            call_count[0] += 1

            if call_count[0] == 1:
                # Policies query
                result.all.return_value = [mock_policy]
            elif call_count[0] == 2:
                # Legal holds check - returns active hold
                result.first.return_value = mock_hold

            return result

        mock_db.query.side_effect = mock_query_side_effect

        # Apply policies
        deletion_counts = gdpr_service.apply_retention_policies()

        # Should have no deletions due to legal hold
        assert deletion_counts == {}

    def test_apply_retention_policies_anonymize_instead(self, gdpr_service, mock_db):
        """Test anonymization retention policy"""
        # Mock policy with anonymize flag
        mock_policy = MagicMock()
        mock_policy.is_active = True
        mock_policy.auto_delete_enabled = True
        mock_policy.data_type = "sales"
        mock_policy.retention_days = 90
        mock_policy.anonymize_instead = True

        # Mock old sale
        cutoff = datetime.utcnow() - timedelta(days=90)
        mock_sale = MagicMock()
        mock_sale.id = "sale-1"
        mock_sale.vendor_id = "vendor-123"
        mock_sale.sale_date = cutoff - timedelta(days=10)

        call_count = [0]

        def mock_query_side_effect(model):
            result = MagicMock()
            result.filter.return_value = result

            call_count[0] += 1

            if call_count[0] == 1:
                result.all.return_value = [mock_policy]
            elif call_count[0] == 2:
                result.first.return_value = None  # No legal holds
            elif call_count[0] == 3:
                result.all.return_value = [mock_sale]

            return result

        mock_db.query.side_effect = mock_query_side_effect

        # Apply policies
        deletion_counts = gdpr_service.apply_retention_policies()

        # Verify anonymization
        assert deletion_counts["sales"] == 1
        assert mock_sale.vendor_id == "anonymized"
