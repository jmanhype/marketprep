"""Unit tests for events service."""
import pytest
from datetime import datetime
from uuid import uuid4
from unittest.mock import MagicMock, AsyncMock, patch

from src.services.events import EventsService, EnhancedEventsService


class TestEventsService:
    """Test basic EventsService."""

    def test_get_special_event(self):
        """Test getting a special event date."""
        service = EventsService()
        result = service.get_event_for_date(datetime(2025, 12, 25))
        
        assert result["is_special"] is True
        assert "Christmas" in result["name"]
        assert result["expected_attendance"] > 200

    def test_get_weekend_event(self):
        """Test weekend market detection."""
        service = EventsService()
        # 2025-01-04 is a Saturday
        result = service.get_event_for_date(datetime(2025, 1, 4))
        
        assert result["is_special"] is False
        assert "Weekend" in result["name"]
        assert result["expected_attendance"] == 150

    def test_get_weekday_event(self):
        """Test weekday market detection."""
        service = EventsService()
        # 2025-01-06 is a Monday
        result = service.get_event_for_date(datetime(2025, 1, 6))
        
        assert result["is_special"] is False
        assert "Weekday" in result["name"]
        assert result["expected_attendance"] == 100


class TestEnhancedEventsService:
    """Test EnhancedEventsService."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.fixture
    def vendor_id(self):
        return uuid4()

    def test_calculate_attendance_impact_special_large(self):
        """Test attendance impact calculation for large special event."""
        service = EnhancedEventsService(uuid4(), MagicMock())
        
        result = service.calculate_attendance_impact({
            "expected_attendance": 5000,
            "is_special": True
        })
        
        assert result == 3.0  # 1.5 * 2.0

    def test_calculate_attendance_impact_normal_small(self):
        """Test attendance impact for small normal event."""
        service = EnhancedEventsService(uuid4(), MagicMock())
        
        result = service.calculate_attendance_impact({
            "expected_attendance": 100,
            "is_special": False
        })
        
        assert result == 1.1

    def test_calculate_distance(self):
        """Test Haversine distance calculation."""
        service = EnhancedEventsService(uuid4(), MagicMock())
        
        # NYC to Philadelphia (~80 miles)
        distance = service._calculate_distance(40.7128, -74.0060, 39.9526, -75.1652)
        
        assert 75 < distance < 85  # Approximately 80 miles

    def test_calculate_attendance_impact_medium_special(self):
        """Test attendance impact for medium (1000-2000) special event - line 200."""
        service = EnhancedEventsService(uuid4(), MagicMock())

        result = service.calculate_attendance_impact({
            "expected_attendance": 1500,
            "is_special": True
        })

        # 1.5 (special) * 1.3 (medium attendance) = 1.95
        assert result == pytest.approx(1.95)

    def test_calculate_attendance_impact_small_medium_special(self):
        """Test attendance impact for 500-1000 special event - line 202."""
        service = EnhancedEventsService(uuid4(), MagicMock())

        result = service.calculate_attendance_impact({
            "expected_attendance": 750,
            "is_special": True
        })

        # 1.5 (special) * 1.2 (small-medium attendance) = 1.8
        assert result == pytest.approx(1.8)

    def test_find_events_near_location_default_radius(self, mock_db, vendor_id):
        """Test finding events with default radius - line 134."""
        service = EnhancedEventsService(vendor_id, mock_db)

        # Mock event data
        mock_event = MagicMock()
        mock_event.name = "Local Festival"
        mock_event.expected_attendance = 500
        mock_event.is_special = True
        mock_event.location = "Downtown"
        mock_event.latitude = 40.7200
        mock_event.longitude = -74.0100

        # Mock query
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [mock_event]

        # Call without specifying radius (should use DEFAULT_RADIUS_MILES) - covers line 134
        result = service.find_events_near_location(
            lat=40.7128,
            lon=-74.0060,
            target_date=datetime(2025, 6, 15),
            # radius_miles not specified - triggers line 134
        )

        assert result is not None
        assert result["name"] == "Local Festival"
        assert result["expected_attendance"] == 500

    @pytest.mark.asyncio
    async def test_fetch_eventbrite_no_events(self, mock_db, vendor_id):
        """Test Eventbrite fetch with no events returned."""
        service = EnhancedEventsService(vendor_id, mock_db)

        with patch.object(service.eventbrite, 'search_events', new_callable=AsyncMock) as mock_search:
            mock_search.return_value = []

            result = await service.fetch_eventbrite_events(
                40.7128, -74.0060,
                datetime(2025, 6, 1),
                datetime(2025, 6, 30)
            )

            assert result["degraded"] is True
            assert result["api_available"] is False
            assert result["fetched"] == 0

    @pytest.mark.asyncio
    async def test_fetch_eventbrite_with_new_events(self, mock_db, vendor_id):
        """Test Eventbrite fetch with new events to store - lines 257-303."""
        service = EnhancedEventsService(vendor_id, mock_db)

        # Mock event data from Eventbrite
        mock_events = [
            {
                "eventbrite_id": "evt-123",
                "name": "Summer Festival",
                "event_date": datetime(2025, 7, 15),
                "expected_attendance": 2000,
                "is_special": True,
                "location": "City Park",
                "latitude": 40.7500,
                "longitude": -73.9900,
            },
            {
                "eventbrite_id": "evt-456",
                "name": "Food Truck Rally",
                "event_date": datetime(2025, 7, 20),
                "expected_attendance": 1000,
                "is_special": False,
                "location": "Main Street",
                "latitude": 40.7300,
                "longitude": -74.0200,
            }
        ]

        # Mock query to return None (no existing events)
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None  # No duplicates

        # Mock add and commit
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()

        with patch.object(service.eventbrite, 'search_events', new_callable=AsyncMock) as mock_search:
            mock_search.return_value = mock_events

            result = await service.fetch_eventbrite_events(
                40.7128, -74.0060,
                datetime(2025, 7, 1),
                datetime(2025, 7, 31)
            )

            # Verify results (covers lines 257-287)
            assert result["api_available"] is True
            assert result["degraded"] is False
            assert result["fetched"] == 2
            assert result["new"] == 2
            assert result["duplicates"] == 0

            # Verify database operations
            assert mock_db.add.call_count == 2
            mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_eventbrite_with_duplicates(self, mock_db, vendor_id):
        """Test Eventbrite fetch with duplicate events - lines 257-303."""
        service = EnhancedEventsService(vendor_id, mock_db)

        # Mock event data
        mock_events = [
            {
                "eventbrite_id": "evt-789",
                "name": "Existing Event",
                "event_date": datetime(2025, 8, 1),
                "expected_attendance": 500,
                "is_special": False,
                "location": "Park",
                "latitude": 40.7400,
                "longitude": -74.0100,
            }
        ]

        # Mock query to return existing event (duplicate)
        mock_existing_event = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_existing_event  # Duplicate found

        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()

        with patch.object(service.eventbrite, 'search_events', new_callable=AsyncMock) as mock_search:
            mock_search.return_value = mock_events

            result = await service.fetch_eventbrite_events(
                40.7128, -74.0060,
                datetime(2025, 8, 1),
                datetime(2025, 8, 31)
            )

            # Verify duplicate was skipped (covers lines 272-280)
            assert result["fetched"] == 1
            assert result["new"] == 0
            assert result["duplicates"] == 1

            # Should not add duplicate
            mock_db.add.assert_not_called()
            mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_eventbrite_storage_error(self, mock_db, vendor_id):
        """Test Eventbrite fetch with individual event storage error - lines 282-284."""
        service = EnhancedEventsService(vendor_id, mock_db)

        # Mock event data
        mock_events = [
            {
                "eventbrite_id": "evt-error",
                "name": "Problematic Event",
                "event_date": datetime(2025, 9, 1),
                "expected_attendance": 300,
                "is_special": False,
                "location": "Unknown",
                "latitude": 40.7500,
                "longitude": -74.0300,
            },
            {
                "eventbrite_id": "evt-good",
                "name": "Good Event",
                "event_date": datetime(2025, 9, 5),
                "expected_attendance": 400,
                "is_special": False,
                "location": "Plaza",
                "latitude": 40.7600,
                "longitude": -74.0400,
            }
        ]

        # Mock query - first event errors, second succeeds
        call_count = [0]
        def query_side_effect(*args):
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            if call_count[0] == 0:
                # First event - raise error
                mock_q.first.side_effect = Exception("Database error")
            else:
                # Second event - no duplicate
                mock_q.first.return_value = None
            call_count[0] += 1
            return mock_q

        mock_db.query.side_effect = query_side_effect
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()

        with patch.object(service.eventbrite, 'search_events', new_callable=AsyncMock) as mock_search:
            mock_search.return_value = mock_events

            result = await service.fetch_eventbrite_events(
                40.7128, -74.0060,
                datetime(2025, 9, 1),
                datetime(2025, 9, 30)
            )

            # First event should error and continue, second should succeed
            # Covers lines 282-284 (exception handling in storage loop)
            assert result["fetched"] == 2
            assert result["new"] == 1  # Only second event stored
            mock_db.add.assert_called_once()  # Only good event added

    @pytest.mark.asyncio
    async def test_fetch_eventbrite_unexpected_error(self, mock_db, vendor_id):
        """Test Eventbrite fetch with unexpected error - lines 297-310."""
        service = EnhancedEventsService(vendor_id, mock_db)

        # Make search_events raise an unexpected exception
        with patch.object(service.eventbrite, 'search_events', new_callable=AsyncMock) as mock_search:
            mock_search.side_effect = RuntimeError("Network timeout")

            result = await service.fetch_eventbrite_events(
                40.7128, -74.0060,
                datetime(2025, 10, 1),
                datetime(2025, 10, 31)
            )

            # Should handle gracefully and return degraded state (covers lines 297-310)
            assert result["degraded"] is True
            assert result["api_available"] is False
            assert result["fetched"] == 0
            assert "error" in result
            assert "Network timeout" in result["error"]

    def test_calculate_attendance_impact_large_special(self):
        """Test attendance impact for 2000-4999 special event - line 198."""
        service = EnhancedEventsService(uuid4(), MagicMock())

        result = service.calculate_attendance_impact({
            "expected_attendance": 3000,
            "is_special": True
        })

        # 1.5 (special) * 1.5 (large attendance 2000-4999) = 2.25
        assert result == pytest.approx(2.25)

    def test_get_event_for_date_with_database_event(self, mock_db, vendor_id):
        """Test get_event_for_date with database event - lines 108-110, 321-341."""
        service = EnhancedEventsService(vendor_id, mock_db)

        # Mock database event
        mock_event = MagicMock()
        mock_event.name = "Database Event"
        mock_event.expected_attendance = 800
        mock_event.is_special = True
        mock_event.location = "Convention Center"

        # Mock query to return event
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [mock_event]

        result = service.get_event_for_date(datetime(2025, 6, 15))

        # Verify it returned the database event (covers lines 108-110, 321-341)
        assert result is not None
        assert result["name"] == "Database Event"
        assert result["expected_attendance"] == 800
        assert result["is_special"] is True

    def test_get_event_for_date_fallback_to_hardcoded(self, mock_db, vendor_id):
        """Test get_event_for_date falling back to hardcoded dates - lines 112-113."""
        service = EnhancedEventsService(vendor_id, mock_db)

        # Mock query to return no events
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        # Query for Christmas (hardcoded special date)
        result = service.get_event_for_date(datetime(2025, 12, 25))

        # Should fall back to fallback_service (covers lines 112-113)
        assert result is not None
        assert result["is_special"] is True
        assert "Christmas" in result["name"]

    def test_find_events_near_location_no_nearby_events(self, mock_db, vendor_id):
        """Test find_events_near_location with no nearby events - line 164."""
        service = EnhancedEventsService(vendor_id, mock_db)

        # Mock event data that's too far away (>10 miles)
        mock_event = MagicMock()
        mock_event.latitude = 41.0  # Far from search location
        mock_event.longitude = -75.0

        # Mock query
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [mock_event]

        # Call with NYC coordinates
        result = service.find_events_near_location(
            lat=40.7128,
            lon=-74.0060,
            target_date=datetime(2025, 6, 15),
        )

        # Should return None when no events within radius (covers line 164)
        assert result is None
