"""
Unit tests for Eventbrite API adapter

Tests event searching, parsing, and graceful error handling.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import httpx

from src.adapters.eventbrite_adapter import (
    EventbriteAdapter,
    EventbriteAPIError,
)


@pytest.fixture
def adapter_with_key():
    """Create EventbriteAdapter with API key"""
    return EventbriteAdapter(api_key="test-api-key-123")


@pytest.fixture
def adapter_without_key():
    """Create EventbriteAdapter without API key"""
    with patch('src.adapters.eventbrite_adapter.settings') as mock_settings:
        mock_settings.eventbrite_api_key = None
        return EventbriteAdapter()


@pytest.fixture
def sample_event_data():
    """Sample Eventbrite API event data"""
    return {
        "id": "evt-123",
        "name": {"text": "Summer Music Festival"},
        "description": {"text": "A great summer music festival with live bands"},
        "start": {"local": "2025-07-15T18:00:00"},
        "capacity": 1500,
        "venue": {
            "name": "Central Park",
            "address": {
                "latitude": "40.785091",
                "longitude": "-73.968285"
            }
        }
    }


@pytest.fixture
def sample_api_response(sample_event_data):
    """Sample Eventbrite API response"""
    return {
        "events": [sample_event_data],
        "pagination": {"page_count": 1}
    }


class TestEventbriteAdapterInit:
    """Test EventbriteAdapter initialization"""

    def test_init_with_explicit_api_key(self):
        """Test initialization with explicit API key"""
        adapter = EventbriteAdapter(api_key="my-api-key")

        assert adapter.api_key == "my-api-key"

    def test_init_without_api_key_uses_settings(self):
        """Test initialization falls back to settings"""
        with patch('src.adapters.eventbrite_adapter.settings') as mock_settings:
            mock_settings.eventbrite_api_key = "settings-api-key"

            adapter = EventbriteAdapter()

            assert adapter.api_key == "settings-api-key"

    def test_init_without_api_key_and_no_settings_attribute(self):
        """Test initialization when settings has no eventbrite_api_key attribute"""
        with patch('src.adapters.eventbrite_adapter.settings') as mock_settings:
            # Remove the attribute
            if hasattr(mock_settings, 'eventbrite_api_key'):
                delattr(mock_settings, 'eventbrite_api_key')

            adapter = EventbriteAdapter()

            assert adapter.api_key is None


class TestSearchEvents:
    """Test event searching"""

    @pytest.mark.asyncio
    async def test_search_events_without_api_key_returns_empty_list(self, caplog):
        """Test search_events returns empty list when API key is not configured"""
        # Patch settings to ensure no API key
        with patch('src.adapters.eventbrite_adapter.settings') as mock_settings:
            mock_settings.eventbrite_api_key = None
            adapter = EventbriteAdapter(api_key=None)

            start_date = datetime(2025, 7, 1)
            end_date = datetime(2025, 7, 31)

            import logging
            with caplog.at_level(logging.WARNING):
                result = await adapter.search_events(
                    latitude=40.7128,
                    longitude=-74.0060,
                    radius_miles=10.0,
                    start_date=start_date,
                    end_date=end_date
                )

            assert result == []
            assert "Eventbrite API key not configured" in caplog.text

    @pytest.mark.asyncio
    async def test_search_events_successful_request(self, adapter_with_key, sample_api_response, caplog):
        """Test successful API request returns parsed events"""
        start_date = datetime(2025, 7, 1, 0, 0, 0)
        end_date = datetime(2025, 7, 31, 23, 59, 59)

        # Mock httpx client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_api_response

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        import logging
        with patch('httpx.AsyncClient', return_value=mock_client):
            with caplog.at_level(logging.INFO):
                result = await adapter_with_key.search_events(
                    latitude=40.7128,
                    longitude=-74.0060,
                    radius_miles=10.0,
                    start_date=start_date,
                    end_date=end_date
                )

        # Verify request was made correctly
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args

        assert call_args[1]["params"]["location.latitude"] == 40.7128
        assert call_args[1]["params"]["location.longitude"] == -74.0060
        assert call_args[1]["params"]["location.within"] == "16.0934km"  # 10 miles * 1.60934
        assert call_args[1]["params"]["start_date.range_start"] == "2025-07-01T00:00:00"
        assert call_args[1]["params"]["start_date.range_end"] == "2025-07-31T23:59:59"
        assert call_args[1]["headers"]["Authorization"] == "Bearer test-api-key-123"

        # Verify result
        assert len(result) == 1
        assert result[0]["name"] == "Summer Music Festival"
        assert result[0]["source"] == "eventbrite"

        # Verify logging
        assert "Found 1 events from Eventbrite" in caplog.text

    @pytest.mark.asyncio
    async def test_search_events_non_200_status_returns_empty_list(self, adapter_with_key, caplog):
        """Test API returns non-200 status code"""
        start_date = datetime(2025, 7, 1)
        end_date = datetime(2025, 7, 31)

        # Mock 404 response
        mock_response = Mock()
        mock_response.status_code = 404

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        import logging
        with patch('httpx.AsyncClient', return_value=mock_client):
            with caplog.at_level(logging.WARNING):
                result = await adapter_with_key.search_events(
                    latitude=40.7128,
                    longitude=-74.0060,
                    radius_miles=10.0,
                    start_date=start_date,
                    end_date=end_date
                )

        assert result == []
        assert "Eventbrite API returned status 404" in caplog.text

    @pytest.mark.asyncio
    async def test_search_events_timeout_returns_empty_list(self, adapter_with_key, caplog):
        """Test API timeout is handled gracefully"""
        start_date = datetime(2025, 7, 1)
        end_date = datetime(2025, 7, 31)

        # Mock timeout exception
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.TimeoutException("Request timed out")
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        import logging
        with patch('httpx.AsyncClient', return_value=mock_client):
            with caplog.at_level(logging.WARNING):
                result = await adapter_with_key.search_events(
                    latitude=40.7128,
                    longitude=-74.0060,
                    radius_miles=10.0,
                    start_date=start_date,
                    end_date=end_date
                )

        assert result == []
        assert "Eventbrite API timeout after 10s" in caplog.text

    @pytest.mark.asyncio
    async def test_search_events_http_error_returns_empty_list(self, adapter_with_key, caplog):
        """Test HTTP error is handled gracefully"""
        start_date = datetime(2025, 7, 1)
        end_date = datetime(2025, 7, 31)

        # Mock HTTP error
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.HTTPError("Connection failed")
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        import logging
        with patch('httpx.AsyncClient', return_value=mock_client):
            with caplog.at_level(logging.WARNING):
                result = await adapter_with_key.search_events(
                    latitude=40.7128,
                    longitude=-74.0060,
                    radius_miles=10.0,
                    start_date=start_date,
                    end_date=end_date
                )

        assert result == []
        assert "Eventbrite API HTTP error" in caplog.text

    @pytest.mark.asyncio
    async def test_search_events_generic_exception_returns_empty_list(self, adapter_with_key, caplog):
        """Test generic exception is handled gracefully"""
        start_date = datetime(2025, 7, 1)
        end_date = datetime(2025, 7, 31)

        # Mock generic exception
        mock_client = AsyncMock()
        mock_client.get.side_effect = ValueError("Unexpected error")
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        import logging
        with patch('httpx.AsyncClient', return_value=mock_client):
            with caplog.at_level(logging.ERROR):
                result = await adapter_with_key.search_events(
                    latitude=40.7128,
                    longitude=-74.0060,
                    radius_miles=10.0,
                    start_date=start_date,
                    end_date=end_date
                )

        assert result == []
        assert "Unexpected error fetching from Eventbrite" in caplog.text


class TestParseEvent:
    """Test event parsing"""

    def test_parse_event_with_complete_data(self, adapter_with_key, sample_event_data):
        """Test parsing event with all fields present"""
        result = adapter_with_key._parse_event(sample_event_data)

        assert result is not None
        assert result["name"] == "Summer Music Festival"
        assert result["description"] == "A great summer music festival with live bands"
        assert result["event_date"] == datetime(2025, 7, 15, 18, 0, 0)
        assert result["location"] == "Central Park"
        assert result["latitude"] == Decimal("40.785091")
        assert result["longitude"] == Decimal("-73.968285")
        assert result["expected_attendance"] == 1500
        assert result["is_special"] is True  # 1500 >= 1000
        assert result["eventbrite_id"] == "evt-123"
        assert result["source"] == "eventbrite"

    def test_parse_event_without_capacity_defaults_to_500(self, adapter_with_key):
        """Test event without capacity defaults to 500 attendance"""
        event_data = {
            "id": "evt-456",
            "name": {"text": "Small Meetup"},
            "description": {"text": "A small local meetup"},
            "start": {"local": "2025-08-01T19:00:00"},
            # No capacity field
            "venue": {
                "name": "Coffee Shop",
                "address": {}
            }
        }

        result = adapter_with_key._parse_event(event_data)

        assert result is not None
        assert result["expected_attendance"] == 500
        assert result["is_special"] is False  # 500 < 1000

    def test_parse_event_small_event_not_special(self, adapter_with_key):
        """Test event with capacity < 1000 is not marked as special"""
        event_data = {
            "id": "evt-789",
            "name": {"text": "Workshop"},
            "description": {"text": ""},
            "start": {"local": "2025-08-15T10:00:00"},
            "capacity": 50,
            "venue": {
                "name": "Community Center",
                "address": {}
            }
        }

        result = adapter_with_key._parse_event(event_data)

        assert result is not None
        assert result["expected_attendance"] == 50
        assert result["is_special"] is False

    def test_parse_event_without_coordinates(self, adapter_with_key):
        """Test event without latitude/longitude"""
        event_data = {
            "id": "evt-999",
            "name": {"text": "Virtual Event"},
            "description": {"text": "Online only"},
            "start": {"local": "2025-09-01T14:00:00"},
            "capacity": 100,
            "venue": {
                "name": "Online",
                "address": {}  # No latitude/longitude
            }
        }

        result = adapter_with_key._parse_event(event_data)

        assert result is not None
        assert result["latitude"] is None
        assert result["longitude"] is None

    def test_parse_event_without_start_date_returns_none(self, adapter_with_key):
        """Test event without start date returns None"""
        event_data = {
            "id": "evt-invalid",
            "name": {"text": "Invalid Event"},
            "description": {"text": "No date"},
            # Missing start field
            "venue": {"name": "Somewhere"}
        }

        result = adapter_with_key._parse_event(event_data)

        assert result is None

    def test_parse_event_with_long_description_truncates(self, adapter_with_key):
        """Test long description is truncated to 500 chars"""
        long_description = "A" * 1000

        event_data = {
            "id": "evt-long",
            "name": {"text": "Long Description Event"},
            "description": {"text": long_description},
            "start": {"local": "2025-10-01T12:00:00"},
            "venue": {"name": "Venue", "address": {}}
        }

        result = adapter_with_key._parse_event(event_data)

        assert result is not None
        assert len(result["description"]) == 500

    def test_parse_event_with_empty_description(self, adapter_with_key):
        """Test event with empty description"""
        event_data = {
            "id": "evt-no-desc",
            "name": {"text": "No Description Event"},
            "description": {"text": ""},
            "start": {"local": "2025-11-01T15:00:00"},
            "venue": {"name": "Venue", "address": {}}
        }

        result = adapter_with_key._parse_event(event_data)

        assert result is not None
        assert result["description"] == ""

    def test_parse_event_exception_returns_none(self, adapter_with_key, caplog):
        """Test exception during parsing returns None with warning"""
        # Invalid event data that will cause parsing to fail
        event_data = {
            "id": "evt-bad",
            "name": "not-a-dict",  # Should be {"text": "..."}
            "start": {"local": "invalid-date"},
            "venue": None
        }

        import logging
        with caplog.at_level(logging.WARNING):
            result = adapter_with_key._parse_event(event_data)

        assert result is None
        assert "Failed to parse event" in caplog.text


class TestEventbriteAPIError:
    """Test EventbriteAPIError exception"""

    def test_eventbrite_api_error_is_exception(self):
        """Test EventbriteAPIError can be raised and caught"""
        with pytest.raises(EventbriteAPIError, match="API unavailable"):
            raise EventbriteAPIError("API unavailable")

    def test_eventbrite_api_error_inherits_from_exception(self):
        """Test EventbriteAPIError inherits from Exception"""
        error = EventbriteAPIError("Test error")
        assert isinstance(error, Exception)


class TestConstants:
    """Test class constants"""

    def test_base_url_constant(self, adapter_with_key):
        """Test BASE_URL is set correctly"""
        assert adapter_with_key.BASE_URL == "https://www.eventbriteapi.com/v3"

    def test_special_event_threshold_constant(self, adapter_with_key):
        """Test SPECIAL_EVENT_THRESHOLD is set correctly"""
        assert adapter_with_key.SPECIAL_EVENT_THRESHOLD == 1000
