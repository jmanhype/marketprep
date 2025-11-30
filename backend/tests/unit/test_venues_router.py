"""Unit tests for venues router.

Tests venues API endpoints (full CRUD):
- GET /venues - List venues with filtering
- POST /venues - Create new venue
- GET /venues/{id} - Get venue details
- PATCH /venues/{id} - Update venue
- DELETE /venues/{id} - Delete venue
"""
import pytest
from datetime import datetime
from decimal import Decimal
from uuid import uuid4, UUID
from unittest.mock import MagicMock, patch

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.routers.venues import (
    list_venues,
    create_venue,
    get_venue,
    update_venue,
    delete_venue,
)
from src.schemas.venue import VenueCreate, VenueUpdate, VenueResponse
from src.models.venue import Venue


class TestListVenues:
    """Test list_venues endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    @pytest.fixture
    def sample_venues(self, vendor_id):
        """Sample venue data."""
        venue1 = MagicMock(spec=Venue)
        venue1.id = uuid4()
        venue1.vendor_id = vendor_id
        venue1.name = "Downtown Farmers Market"
        venue1.location = "123 Main St"
        venue1.latitude = Decimal("40.7128")
        venue1.longitude = Decimal("-74.0060")
        venue1.typical_attendance = 500
        venue1.notes = "Busy on weekends"
        venue1.is_active = True
        venue1.created_at = datetime(2025, 1, 1, 10, 0, 0)
        venue1.updated_at = datetime(2025, 1, 15, 14, 30, 0)

        venue2 = MagicMock(spec=Venue)
        venue2.id = uuid4()
        venue2.vendor_id = vendor_id
        venue2.name = "City Park Market"
        venue2.location = "456 Park Ave"
        venue2.latitude = None
        venue2.longitude = None
        venue2.typical_attendance = None
        venue2.notes = None
        venue2.is_active = True
        venue2.created_at = datetime(2025, 1, 5, 9, 0, 0)
        venue2.updated_at = datetime(2025, 1, 5, 9, 0, 0)

        venue3 = MagicMock(spec=Venue)
        venue3.id = uuid4()
        venue3.vendor_id = vendor_id
        venue3.name = "Old Market (Inactive)"
        venue3.location = "789 Old St"
        venue3.latitude = Decimal("40.7000")
        venue3.longitude = Decimal("-74.0000")
        venue3.typical_attendance = 200
        venue3.notes = "Closed down"
        venue3.is_active = False
        venue3.created_at = datetime(2024, 12, 1, 10, 0, 0)
        venue3.updated_at = datetime(2025, 1, 1, 10, 0, 0)

        return [venue1, venue2, venue3]

    def test_list_all_venues(self, mock_db, vendor_id, sample_venues):
        """Test listing all venues."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = sample_venues

        mock_db.query.return_value = mock_query

        results = list_venues(vendor_id=vendor_id, db=mock_db, is_active=None)

        assert len(results) == 3
        mock_db.query.assert_called_once_with(Venue)

    def test_list_active_venues_only(self, mock_db, vendor_id, sample_venues):
        """Test filtering for active venues only."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = sample_venues[:2]  # Only active venues

        mock_db.query.return_value = mock_query

        results = list_venues(vendor_id=vendor_id, db=mock_db, is_active=True)

        assert len(results) == 2
        # Verify filter was called twice (vendor_id and is_active)
        assert mock_query.filter.call_count == 2

    def test_list_inactive_venues_only(self, mock_db, vendor_id, sample_venues):
        """Test filtering for inactive venues only."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [sample_venues[2]]  # Only inactive venue

        mock_db.query.return_value = mock_query

        results = list_venues(vendor_id=vendor_id, db=mock_db, is_active=False)

        assert len(results) == 1

    def test_list_venues_empty(self, mock_db, vendor_id):
        """Test listing when no venues exist."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []

        mock_db.query.return_value = mock_query

        results = list_venues(vendor_id=vendor_id, db=mock_db, is_active=None)

        assert results == []


class TestCreateVenue:
    """Test create_venue endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        db = MagicMock(spec=Session)
        # Mock refresh to set id and timestamps on the venue
        def mock_refresh(venue):
            venue.id = uuid4()
            venue.created_at = datetime(2025, 1, 20, 10, 0, 0)
            venue.updated_at = datetime(2025, 1, 20, 10, 0, 0)
        db.refresh = mock_refresh
        return db

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    def test_create_venue_with_all_fields(self, mock_db, vendor_id):
        """Test creating venue with all fields."""
        venue_data = VenueCreate(
            name="New Market",
            location="999 New St",
            latitude=Decimal("40.7500"),
            longitude=Decimal("-73.9900"),
            typical_attendance=300,
            notes="Great location",
            is_active=True,
        )

        result = create_venue(venue=venue_data, vendor_id=vendor_id, db=mock_db)

        # Verify db operations
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

        # Verify venue was created with correct data
        added_venue = mock_db.add.call_args[0][0]
        assert isinstance(added_venue, Venue)
        assert added_venue.vendor_id == vendor_id
        assert added_venue.name == "New Market"
        assert added_venue.location == "999 New St"
        assert added_venue.latitude == Decimal("40.7500")
        assert added_venue.typical_attendance == 300

    def test_create_venue_minimal_fields(self, mock_db, vendor_id):
        """Test creating venue with only required fields."""
        venue_data = VenueCreate(
            name="Minimal Market",
            location="100 Simple St",
            is_active=True,
        )

        result = create_venue(venue=venue_data, vendor_id=vendor_id, db=mock_db)

        mock_db.add.assert_called_once()
        added_venue = mock_db.add.call_args[0][0]
        assert added_venue.name == "Minimal Market"
        assert added_venue.latitude is None
        assert added_venue.longitude is None
        assert added_venue.typical_attendance is None
        assert added_venue.notes is None

    def test_create_venue_inactive(self, mock_db, vendor_id):
        """Test creating inactive venue."""
        venue_data = VenueCreate(
            name="Future Market",
            location="200 Future St",
            is_active=False,
        )

        result = create_venue(venue=venue_data, vendor_id=vendor_id, db=mock_db)

        added_venue = mock_db.add.call_args[0][0]
        assert added_venue.is_active is False


class TestGetVenue:
    """Test get_venue endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    @pytest.fixture
    def venue_id(self):
        """Test venue ID."""
        return uuid4()

    @pytest.fixture
    def sample_venue(self, venue_id, vendor_id):
        """Sample venue."""
        venue = MagicMock(spec=Venue)
        venue.id = venue_id
        venue.vendor_id = vendor_id
        venue.name = "Test Market"
        venue.location = "123 Test St"
        venue.latitude = Decimal("40.7128")
        venue.longitude = Decimal("-74.0060")
        venue.typical_attendance = 400
        venue.notes = "Test notes"
        venue.is_active = True
        venue.created_at = datetime(2025, 1, 1, 10, 0, 0)
        venue.updated_at = datetime(2025, 1, 10, 14, 0, 0)
        return venue

    def test_get_venue_success(self, mock_db, vendor_id, venue_id, sample_venue):
        """Test getting venue by ID."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = sample_venue

        mock_db.query.return_value = mock_query

        result = get_venue(venue_id=venue_id, vendor_id=vendor_id, db=mock_db)

        assert result == sample_venue
        mock_db.query.assert_called_once_with(Venue)

    def test_get_venue_not_found(self, mock_db, vendor_id, venue_id):
        """Test getting non-existent venue."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            get_venue(venue_id=venue_id, vendor_id=vendor_id, db=mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert exc_info.value.detail == "Venue not found"

    def test_get_venue_wrong_vendor(self, mock_db, venue_id):
        """Test accessing venue from wrong vendor."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None  # No match due to vendor filter

        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            get_venue(venue_id=venue_id, vendor_id=uuid4(), db=mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


class TestUpdateVenue:
    """Test update_venue endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        db = MagicMock(spec=Session)
        db.refresh = MagicMock()  # Mock refresh to do nothing
        return db

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    @pytest.fixture
    def venue_id(self):
        """Test venue ID."""
        return uuid4()

    @pytest.fixture
    def existing_venue(self, venue_id, vendor_id):
        """Existing venue to update."""
        venue = MagicMock(spec=Venue)
        venue.id = venue_id
        venue.vendor_id = vendor_id
        venue.name = "Old Name"
        venue.location = "Old Location"
        venue.latitude = Decimal("40.0000")
        venue.longitude = Decimal("-74.0000")
        venue.typical_attendance = 100
        venue.notes = "Old notes"
        venue.is_active = True
        return venue

    def test_update_venue_single_field(self, mock_db, vendor_id, venue_id, existing_venue):
        """Test updating single field."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = existing_venue

        mock_db.query.return_value = mock_query

        update_data = VenueUpdate(name="New Name")

        result = update_venue(
            venue_id=venue_id,
            venue_update=update_data,
            vendor_id=vendor_id,
            db=mock_db,
        )

        assert existing_venue.name == "New Name"
        # Other fields unchanged
        assert existing_venue.location == "Old Location"
        mock_db.commit.assert_called_once()

    def test_update_venue_multiple_fields(self, mock_db, vendor_id, venue_id, existing_venue):
        """Test updating multiple fields."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = existing_venue

        mock_db.query.return_value = mock_query

        update_data = VenueUpdate(
            name="Updated Market",
            location="Updated Location",
            typical_attendance=500,
        )

        result = update_venue(
            venue_id=venue_id,
            venue_update=update_data,
            vendor_id=vendor_id,
            db=mock_db,
        )

        assert existing_venue.name == "Updated Market"
        assert existing_venue.location == "Updated Location"
        assert existing_venue.typical_attendance == 500
        # Unchanged fields
        assert existing_venue.notes == "Old notes"

    def test_update_venue_deactivate(self, mock_db, vendor_id, venue_id, existing_venue):
        """Test deactivating venue."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = existing_venue

        mock_db.query.return_value = mock_query

        update_data = VenueUpdate(is_active=False)

        result = update_venue(
            venue_id=venue_id,
            venue_update=update_data,
            vendor_id=vendor_id,
            db=mock_db,
        )

        assert existing_venue.is_active is False

    def test_update_venue_not_found(self, mock_db, vendor_id, venue_id):
        """Test updating non-existent venue."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        mock_db.query.return_value = mock_query

        update_data = VenueUpdate(name="New Name")

        with pytest.raises(HTTPException) as exc_info:
            update_venue(
                venue_id=venue_id,
                venue_update=update_data,
                vendor_id=vendor_id,
                db=mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    def test_update_venue_no_fields(self, mock_db, vendor_id, venue_id, existing_venue):
        """Test update with no fields provided."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = existing_venue

        mock_db.query.return_value = mock_query

        update_data = VenueUpdate()  # No fields set

        result = update_venue(
            venue_id=venue_id,
            venue_update=update_data,
            vendor_id=vendor_id,
            db=mock_db,
        )

        # All fields should remain unchanged
        assert existing_venue.name == "Old Name"
        assert existing_venue.location == "Old Location"
        mock_db.commit.assert_called_once()


class TestDeleteVenue:
    """Test delete_venue endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    @pytest.fixture
    def venue_id(self):
        """Test venue ID."""
        return uuid4()

    @pytest.fixture
    def existing_venue(self, venue_id, vendor_id):
        """Existing venue to delete."""
        venue = MagicMock(spec=Venue)
        venue.id = venue_id
        venue.vendor_id = vendor_id
        venue.name = "Market to Delete"
        return venue

    def test_delete_venue_success(self, mock_db, vendor_id, venue_id, existing_venue):
        """Test successful venue deletion."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = existing_venue

        mock_db.query.return_value = mock_query

        result = delete_venue(venue_id=venue_id, vendor_id=vendor_id, db=mock_db)

        mock_db.delete.assert_called_once_with(existing_venue)
        mock_db.commit.assert_called_once()
        assert result is None

    def test_delete_venue_not_found(self, mock_db, vendor_id, venue_id):
        """Test deleting non-existent venue."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            delete_venue(venue_id=venue_id, vendor_id=vendor_id, db=mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        mock_db.delete.assert_not_called()

    def test_delete_venue_wrong_vendor(self, mock_db, venue_id):
        """Test deleting venue from wrong vendor."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            delete_venue(venue_id=venue_id, vendor_id=uuid4(), db=mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        mock_db.delete.assert_not_called()
