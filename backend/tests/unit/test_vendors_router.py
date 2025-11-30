"""Unit tests for vendors router.

Tests vendor API endpoints:
- GET /vendors/me - Get profile
- PATCH /vendors/me - Update profile
- GET /vendors/me/data-export - GDPR data export
- DELETE /vendors/me - Delete account
- GET /vendors/me/data-requests - Get DSARs
- GET /vendors/me/consents - Get consents
"""
import pytest
from datetime import datetime
from uuid import uuid4, UUID
from unittest.mock import MagicMock, patch

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.routers.vendors import (
    get_current_vendor_profile,
    update_vendor_profile,
    export_vendor_data,
    delete_vendor_account,
    get_vendor_data_requests,
    get_vendor_consents,
    VendorUpdateRequest,
    DeleteAccountRequest,
)
from src.models.vendor import Vendor


class TestGetCurrentVendorProfile:
    """Test get_current_vendor_profile endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    @pytest.fixture
    def existing_vendor(self, vendor_id):
        """Existing vendor."""
        vendor = MagicMock(spec=Vendor)
        vendor.id = vendor_id
        vendor.email = "vendor@example.com"
        vendor.business_name = "Test Market"
        vendor.phone = "555-1234"
        vendor.created_at = datetime(2025, 1, 1, 12, 0, 0)
        return vendor

    def test_get_profile_success(self, mock_db, vendor_id, existing_vendor):
        """Test getting vendor profile."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = existing_vendor
        mock_db.query.return_value = mock_query

        with patch('src.routers.vendors.VendorResponse') as mock_response:
            mock_response.model_validate.return_value = existing_vendor

            result = get_current_vendor_profile(vendor_id=vendor_id, db=mock_db)

            mock_response.model_validate.assert_called_once_with(existing_vendor)

    def test_get_profile_not_found(self, mock_db, vendor_id):
        """Test getting non-existent vendor profile."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            get_current_vendor_profile(vendor_id=vendor_id, db=mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


class TestUpdateVendorProfile:
    """Test update_vendor_profile endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    @pytest.fixture
    def existing_vendor(self, vendor_id):
        """Existing vendor."""
        vendor = MagicMock(spec=Vendor)
        vendor.id = vendor_id
        vendor.email = "old@example.com"
        vendor.business_name = "Old Name"
        vendor.phone = "555-0000"
        return vendor

    def test_update_profile_all_fields(self, mock_db, vendor_id, existing_vendor):
        """Test updating all profile fields."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = existing_vendor
        mock_db.query.return_value = mock_query

        update_data = VendorUpdateRequest(
            business_name="New Business",
            phone="555-9999",
            email="new@example.com",
        )

        with patch('src.routers.vendors.AuditService') as mock_audit:
            with patch('src.routers.vendors.VendorResponse') as mock_response:
                mock_response.model_validate.return_value = existing_vendor

                result = update_vendor_profile(
                    update_data=update_data,
                    vendor_id=vendor_id,
                    db=mock_db,
                )

                # Verify fields were updated
                assert existing_vendor.business_name == "New Business"
                assert existing_vendor.phone == "555-9999"
                assert existing_vendor.email == "new@example.com"

                # Verify database operations
                mock_db.commit.assert_called_once()
                mock_db.refresh.assert_called_once()

                # Verify audit log was created
                mock_audit.assert_called_once()

    def test_update_profile_partial(self, mock_db, vendor_id, existing_vendor):
        """Test updating only some fields."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = existing_vendor
        mock_db.query.return_value = mock_query

        update_data = VendorUpdateRequest(
            business_name="New Name",
        )

        with patch('src.routers.vendors.AuditService'):
            with patch('src.routers.vendors.VendorResponse') as mock_response:
                mock_response.model_validate.return_value = existing_vendor

                update_vendor_profile(
                    update_data=update_data,
                    vendor_id=vendor_id,
                    db=mock_db,
                )

                assert existing_vendor.business_name == "New Name"
                assert existing_vendor.phone == "555-0000"  # Unchanged

    def test_update_profile_not_found(self, mock_db, vendor_id):
        """Test updating non-existent vendor."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        update_data = VendorUpdateRequest(business_name="New Name")

        with pytest.raises(HTTPException) as exc_info:
            update_vendor_profile(
                update_data=update_data,
                vendor_id=vendor_id,
                db=mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


class TestExportVendorData:
    """Test export_vendor_data endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    @pytest.mark.asyncio
    async def test_export_data_success(self, mock_db, vendor_id):
        """Test successful data export."""
        with patch('src.routers.vendors.GDPRService') as mock_gdpr:
            with patch('src.routers.vendors.AuditService'):
                mock_gdpr_instance = MagicMock()
                mock_gdpr_instance.export_user_data.return_value = {
                    "vendor_id": str(vendor_id),
                    "email": "vendor@example.com",
                    "data": "exported data",
                }
                mock_gdpr.return_value = mock_gdpr_instance

                result = await export_vendor_data(vendor_id=vendor_id, db=mock_db)

                # Verify GDPR service was called
                mock_gdpr_instance.export_user_data.assert_called_once_with(str(vendor_id))

                # Verify response headers
                assert "Content-Disposition" in result.headers
                assert "attachment" in result.headers["Content-Disposition"]

    @pytest.mark.asyncio
    async def test_export_data_failure(self, mock_db, vendor_id):
        """Test data export with service error."""
        with patch('src.routers.vendors.GDPRService') as mock_gdpr:
            mock_gdpr_instance = MagicMock()
            mock_gdpr_instance.export_user_data.side_effect = Exception("Export failed")
            mock_gdpr.return_value = mock_gdpr_instance

            with pytest.raises(HTTPException) as exc_info:
                await export_vendor_data(vendor_id=vendor_id, db=mock_db)

            assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestDeleteVendorAccount:
    """Test delete_vendor_account endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    @pytest.fixture
    def existing_vendor(self, vendor_id):
        """Existing vendor."""
        vendor = MagicMock(spec=Vendor)
        vendor.id = vendor_id
        vendor.email = "vendor@example.com"
        return vendor

    @pytest.mark.asyncio
    async def test_delete_account_success(self, mock_db, vendor_id, existing_vendor):
        """Test successful account deletion."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = existing_vendor
        mock_db.query.return_value = mock_query

        delete_request = DeleteAccountRequest(
            confirm_email="vendor@example.com",
            reason="No longer needed",
        )

        with patch('src.routers.vendors.GDPRService') as mock_gdpr:
            mock_dsar = MagicMock()
            mock_dsar.id = uuid4()

            mock_gdpr_instance = MagicMock()
            mock_gdpr_instance.create_dsar.return_value = mock_dsar
            mock_gdpr_instance.delete_user_data.return_value = {"deleted": 5, "anonymized": 10}
            mock_gdpr.return_value = mock_gdpr_instance

            result = await delete_vendor_account(
                delete_request=delete_request,
                vendor_id=vendor_id,
                db=mock_db,
            )

            assert result["message"] == "Account deletion completed"
            assert result["anonymized"] is True
            assert "deletion_counts" in result

    @pytest.mark.asyncio
    async def test_delete_account_email_mismatch(self, mock_db, vendor_id, existing_vendor):
        """Test account deletion with wrong email confirmation."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = existing_vendor
        mock_db.query.return_value = mock_query

        delete_request = DeleteAccountRequest(
            confirm_email="wrong@example.com",
        )

        with pytest.raises(HTTPException) as exc_info:
            await delete_vendor_account(
                delete_request=delete_request,
                vendor_id=vendor_id,
                db=mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "does not match" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_delete_account_not_found(self, mock_db, vendor_id):
        """Test deleting non-existent account."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        delete_request = DeleteAccountRequest(confirm_email="vendor@example.com")

        with pytest.raises(HTTPException) as exc_info:
            await delete_vendor_account(
                delete_request=delete_request,
                vendor_id=vendor_id,
                db=mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_delete_account_legal_hold(self, mock_db, vendor_id, existing_vendor):
        """Test account deletion with legal hold."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = existing_vendor
        mock_db.query.return_value = mock_query

        delete_request = DeleteAccountRequest(confirm_email="vendor@example.com")

        with patch('src.routers.vendors.GDPRService') as mock_gdpr:
            mock_gdpr_instance = MagicMock()
            mock_gdpr_instance.create_dsar.return_value = MagicMock(id=uuid4())
            mock_gdpr_instance.delete_user_data.side_effect = ValueError("Legal hold active")
            mock_gdpr.return_value = mock_gdpr_instance

            with pytest.raises(HTTPException) as exc_info:
                await delete_vendor_account(
                    delete_request=delete_request,
                    vendor_id=vendor_id,
                    db=mock_db,
                )

            assert exc_info.value.status_code == status.HTTP_409_CONFLICT


class TestGetVendorDataRequests:
    """Test get_vendor_data_requests endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    def test_get_data_requests(self, mock_db, vendor_id):
        """Test getting vendor's data requests."""
        mock_dsar = MagicMock()
        mock_dsar.id = uuid4()
        mock_dsar.request_type = "ERASURE"
        mock_dsar.status = "COMPLETED"
        mock_dsar.requested_at = datetime(2025, 1, 15, 12, 0, 0)
        mock_dsar.deadline = datetime(2025, 2, 14, 12, 0, 0)
        mock_dsar.completed_at = datetime(2025, 1, 20, 12, 0, 0)
        mock_dsar.description = "Account deletion"

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [mock_dsar]
        mock_db.query.return_value = mock_query

        results = get_vendor_data_requests(vendor_id=vendor_id, db=mock_db)

        assert len(results) == 1
        assert results[0]["request_type"] == "ERASURE"
        assert results[0]["status"] == "COMPLETED"


class TestGetVendorConsents:
    """Test get_vendor_consents endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    def test_get_consents(self, mock_db, vendor_id):
        """Test getting vendor's consent history."""
        mock_consent = MagicMock()
        mock_consent.id = uuid4()
        mock_consent.consent_type = "MARKETING"
        mock_consent.consent_given = True
        mock_consent.given_at = datetime(2025, 1, 15, 12, 0, 0)
        mock_consent.withdrawn_at = None
        mock_consent.consent_version = "1.0"

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [mock_consent]
        mock_db.query.return_value = mock_query

        results = get_vendor_consents(vendor_id=vendor_id, db=mock_db)

        assert len(results) == 1
        assert results[0]["consent_type"] == "MARKETING"
        assert results[0]["consent_given"] is True
