"""Unit tests for events router.

Tests events API endpoints:
- POST /events - Create manual event
- GET /events - List events
- DELETE /events/{id} - Delete event
- POST /events/fetch - Fetch from Eventbrite
"""
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4, UUID
from unittest.mock import MagicMock, AsyncMock, patch

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.routers.events import (
    create_event,
    list_events,
    delete_event,
    fetch_eventbrite_events,
    EventCreateRequest,
    EventResponse,
    FetchEventsRequest,
)
from src.models.event_data import EventData


class TestCreateEvent:
    """Test create_event endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    def test_create_event_with_all_fields(self, mock_db, vendor_id):
        """Test creating event with all fields."""
        # Setup mock to simulate refresh with values
        event_id = uuid4()
        created_at = datetime(2025, 1, 15, 12, 0, 0)

        def mock_refresh(event):
            event.id = event_id
            event.created_at = created_at

        mock_db.refresh.side_effect = mock_refresh

        request_data = EventCreateRequest(
            name="Farmers Market",
            event_date="2025-06-15T10:00:00",
            location="Main Street Park",
            latitude=40.7128,
            longitude=-74.0060,
            expected_attendance=500,
            is_special=True,
            description="Annual summer farmers market",
        )

        result = create_event(
            request=request_data,
            vendor_id=vendor_id,
            db=mock_db,
        )

        # Verify database operations
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

        # Verify event was created correctly
        added_event = mock_db.add.call_args[0][0]
        assert isinstance(added_event, EventData)
        assert added_event.vendor_id == vendor_id
        assert added_event.name == "Farmers Market"
        assert added_event.event_date == datetime(2025, 6, 15, 10, 0, 0)
        assert added_event.location == "Main Street Park"
        assert added_event.latitude == 40.7128
        assert added_event.longitude == -74.0060
        assert added_event.expected_attendance == 500
        assert added_event.is_special is True
        assert added_event.description == "Annual summer farmers market"
        assert added_event.source == "manual"

    def test_create_event_minimal_fields(self, mock_db, vendor_id):
        """Test creating event with minimal required fields."""
        # Setup mock to simulate refresh with values
        event_id = uuid4()
        created_at = datetime(2025, 1, 15, 12, 0, 0)

        def mock_refresh(event):
            event.id = event_id
            event.created_at = created_at

        mock_db.refresh.side_effect = mock_refresh

        request_data = EventCreateRequest(
            name="Simple Event",
            event_date="2025-07-01T14:00:00",
        )

        result = create_event(
            request=request_data,
            vendor_id=vendor_id,
            db=mock_db,
        )

        added_event = mock_db.add.call_args[0][0]
        assert added_event.name == "Simple Event"
        assert added_event.location is None
        assert added_event.latitude is None
        assert added_event.longitude is None
        assert added_event.expected_attendance == 100  # Default value
        assert added_event.is_special is False  # Default value
        assert added_event.description is None

    def test_create_event_invalid_date_format(self, mock_db, vendor_id):
        """Test creating event with invalid date format."""
        request_data = EventCreateRequest(
            name="Bad Date Event",
            event_date="not-a-valid-date",
        )

        with pytest.raises(HTTPException) as exc_info:
            create_event(
                request=request_data,
                vendor_id=vendor_id,
                db=mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid event_date format" in exc_info.value.detail
        assert "ISO format" in exc_info.value.detail

    def test_create_event_response_format(self, mock_db, vendor_id):
        """Test response format matches EventResponse schema."""
        # Setup mock to simulate refresh with values
        event_id = uuid4()
        created_at = datetime(2025, 1, 15, 12, 0, 0)

        def mock_refresh(event):
            event.id = event_id
            event.created_at = created_at

        mock_db.refresh.side_effect = mock_refresh

        request_data = EventCreateRequest(
            name="Test Event",
            event_date="2025-06-15T10:00:00",
            location="Test Location",
            latitude=40.7128,
            longitude=-74.0060,
            expected_attendance=300,
            is_special=True,
            description="Test description",
        )

        result = create_event(
            request=request_data,
            vendor_id=vendor_id,
            db=mock_db,
        )

        assert isinstance(result, EventResponse)
        assert result.id == event_id
        assert result.name == "Test Event"
        assert result.event_date == "2025-06-15T10:00:00"
        assert result.location == "Test Location"
        assert result.latitude == 40.7128
        assert result.longitude == -74.0060
        assert result.expected_attendance == 300
        assert result.is_special is True
        assert result.source == "manual"
        assert result.description == "Test description"
        assert result.created_at == "2025-01-15T12:00:00"

    def test_create_event_handles_null_coordinates(self, mock_db, vendor_id):
        """Test creating event with null latitude/longitude."""
        event_id = uuid4()
        created_at = datetime(2025, 1, 15, 12, 0, 0)

        def mock_refresh(event):
            event.id = event_id
            event.created_at = created_at

        mock_db.refresh.side_effect = mock_refresh

        request_data = EventCreateRequest(
            name="No Coords Event",
            event_date="2025-06-15T10:00:00",
        )

        result = create_event(
            request=request_data,
            vendor_id=vendor_id,
            db=mock_db,
        )

        assert result.latitude is None
        assert result.longitude is None


class TestListEvents:
    """Test list_events endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    @pytest.fixture
    def sample_events(self, vendor_id):
        """Sample events data."""
        event1 = MagicMock(spec=EventData)
        event1.id = uuid4()
        event1.vendor_id = vendor_id
        event1.name = "Event 1"
        event1.event_date = datetime(2025, 6, 15, 10, 0, 0)
        event1.location = "Location 1"
        event1.latitude = Decimal("40.7128")
        event1.longitude = Decimal("-74.0060")
        event1.expected_attendance = 500
        event1.is_special = True
        event1.source = "manual"
        event1.description = "Description 1"
        event1.created_at = datetime(2025, 1, 1, 12, 0, 0)

        event2 = MagicMock(spec=EventData)
        event2.id = uuid4()
        event2.vendor_id = vendor_id
        event2.name = "Event 2"
        event2.event_date = datetime(2025, 6, 20, 14, 0, 0)
        event2.location = None
        event2.latitude = None
        event2.longitude = None
        event2.expected_attendance = 200
        event2.is_special = False
        event2.source = "eventbrite"
        event2.description = None
        event2.created_at = datetime(2025, 1, 2, 12, 0, 0)

        return [event1, event2]

    def test_list_events_default_period(self, mock_db, vendor_id, sample_events):
        """Test listing events with default 30-day period."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = sample_events

        mock_db.query.return_value = mock_query

        with patch('src.routers.events.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value = datetime(2025, 6, 1, 12, 0, 0)

            results = list_events(
                vendor_id=vendor_id,
                db=mock_db,
                days_ahead=30,
            )

            assert len(results) == 2
            assert results[0].name == "Event 1"
            assert results[1].name == "Event 2"

    def test_list_events_custom_period(self, mock_db, vendor_id, sample_events):
        """Test listing events with custom period."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [sample_events[0]]

        mock_db.query.return_value = mock_query

        results = list_events(
            vendor_id=vendor_id,
            db=mock_db,
            days_ahead=7,
        )

        assert len(results) == 1

    def test_list_events_empty_result(self, mock_db, vendor_id):
        """Test listing events when none exist."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []

        mock_db.query.return_value = mock_query

        results = list_events(
            vendor_id=vendor_id,
            db=mock_db,
            days_ahead=30,
        )

        assert results == []

    def test_list_events_response_format(self, mock_db, vendor_id, sample_events):
        """Test response format matches EventResponse schema."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [sample_events[0]]

        mock_db.query.return_value = mock_query

        results = list_events(
            vendor_id=vendor_id,
            db=mock_db,
            days_ahead=30,
        )

        assert isinstance(results[0], EventResponse)
        assert isinstance(results[0].id, UUID)
        assert results[0].name == "Event 1"
        assert results[0].event_date == "2025-06-15T10:00:00"
        assert results[0].latitude == 40.7128
        assert results[0].longitude == -74.0060
        assert results[0].expected_attendance == 500
        assert results[0].is_special is True
        assert results[0].source == "manual"

    def test_list_events_handles_null_fields(self, mock_db, vendor_id, sample_events):
        """Test null optional fields are handled correctly."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [sample_events[1]]

        mock_db.query.return_value = mock_query

        results = list_events(
            vendor_id=vendor_id,
            db=mock_db,
            days_ahead=30,
        )

        assert results[0].location is None
        assert results[0].latitude is None
        assert results[0].longitude is None
        assert results[0].description is None


class TestDeleteEvent:
    """Test delete_event endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    @pytest.fixture
    def event_id(self):
        """Test event ID."""
        return uuid4()

    @pytest.fixture
    def existing_event(self, event_id, vendor_id):
        """Existing event."""
        event = MagicMock(spec=EventData)
        event.id = event_id
        event.vendor_id = vendor_id
        event.name = "Event to Delete"
        return event

    def test_delete_event_success(self, mock_db, vendor_id, event_id, existing_event):
        """Test successful event deletion."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = existing_event

        mock_db.query.return_value = mock_query

        result = delete_event(
            event_id=event_id,
            vendor_id=vendor_id,
            db=mock_db,
        )

        mock_db.delete.assert_called_once_with(existing_event)
        mock_db.commit.assert_called_once()
        assert result == {"message": "Event deleted successfully"}

    def test_delete_event_not_found(self, mock_db, vendor_id, event_id):
        """Test deleting non-existent event."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            delete_event(
                event_id=event_id,
                vendor_id=vendor_id,
                db=mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert exc_info.value.detail == "Event not found"

    def test_delete_event_wrong_vendor(self, mock_db, event_id):
        """Test deleting event from wrong vendor."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None  # Filter excludes wrong vendor

        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            delete_event(
                event_id=event_id,
                vendor_id=uuid4(),  # Different vendor
                db=mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


class TestFetchEventbriteEvents:
    """Test fetch_eventbrite_events endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    @pytest.mark.asyncio
    async def test_fetch_eventbrite_success(self, mock_db, vendor_id):
        """Test successful Eventbrite fetch."""
        with patch('src.routers.events.EnhancedEventsService') as mock_service_class:
            mock_service = MagicMock()
            mock_service.fetch_eventbrite_events = AsyncMock(return_value={
                "new": 5,
                "updated": 2,
                "skipped": 1,
                "total": 8,
                "degraded": False,
            })
            mock_service_class.return_value = mock_service

            request_data = FetchEventsRequest(
                latitude=40.7128,
                longitude=-74.0060,
                radius_miles=10.0,
                days_ahead=30,
            )

            result = await fetch_eventbrite_events(
                request=request_data,
                vendor_id=vendor_id,
                db=mock_db,
            )

            assert "Successfully fetched 5 new events" in result["message"]
            assert result["new"] == 5
            assert result["updated"] == 2
            assert result["skipped"] == 1
            assert result["total"] == 8
            assert result["degraded"] is False

            # Verify service was initialized correctly
            mock_service_class.assert_called_once_with(vendor_id=vendor_id, db=mock_db)

    @pytest.mark.asyncio
    async def test_fetch_eventbrite_degraded_mode(self, mock_db, vendor_id):
        """Test Eventbrite fetch with API unavailable (degraded mode)."""
        with patch('src.routers.events.EnhancedEventsService') as mock_service_class:
            mock_service = MagicMock()
            mock_service.fetch_eventbrite_events = AsyncMock(return_value={
                "new": 0,
                "updated": 0,
                "skipped": 0,
                "total": 0,
                "degraded": True,
            })
            mock_service_class.return_value = mock_service

            request_data = FetchEventsRequest(
                latitude=40.7128,
                longitude=-74.0060,
            )

            result = await fetch_eventbrite_events(
                request=request_data,
                vendor_id=vendor_id,
                db=mock_db,
            )

            assert "Eventbrite API unavailable" in result["message"]
            assert "continuing with database and hardcoded events" in result["message"]
            assert result["degraded"] is True

    @pytest.mark.asyncio
    async def test_fetch_eventbrite_custom_parameters(self, mock_db, vendor_id):
        """Test fetch with custom parameters."""
        with patch('src.routers.events.EnhancedEventsService') as mock_service_class:
            mock_service = MagicMock()
            mock_service.fetch_eventbrite_events = AsyncMock(return_value={
                "new": 3,
                "updated": 0,
                "skipped": 0,
                "total": 3,
                "degraded": False,
            })
            mock_service_class.return_value = mock_service

            request_data = FetchEventsRequest(
                latitude=34.0522,
                longitude=-118.2437,
                radius_miles=25.0,
                days_ahead=60,
            )

            with patch('src.routers.events.datetime') as mock_datetime:
                mock_now = datetime(2025, 6, 1, 12, 0, 0)
                mock_datetime.utcnow.return_value = mock_now

                await fetch_eventbrite_events(
                    request=request_data,
                    vendor_id=vendor_id,
                    db=mock_db,
                )

                # Verify service was called with correct parameters
                call_kwargs = mock_service.fetch_eventbrite_events.call_args[1]
                assert call_kwargs['lat'] == 34.0522
                assert call_kwargs['lon'] == -118.2437
                assert call_kwargs['radius_miles'] == 25.0
                assert call_kwargs['start_date'] == mock_now
                assert call_kwargs['end_date'] == mock_now + timedelta(days=60)
