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
