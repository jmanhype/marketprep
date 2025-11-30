"""Unit tests for weather service."""
import pytest
import json
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch
import httpx

from src.services.weather import WeatherService


class TestWeatherServiceInit:
    """Test WeatherService initialization."""

    def test_init_with_redis_available(self):
        """Test initialization when Redis is available."""
        with patch('src.services.weather.redis.from_url') as mock_redis:
            mock_redis_instance = MagicMock()
            mock_redis_instance.ping.return_value = True
            mock_redis.return_value = mock_redis_instance
            
            service = WeatherService()
            
            assert service.cache_enabled is True
            assert service.redis is not None

    def test_init_with_redis_unavailable(self):
        """Test initialization when Redis is unavailable."""
        with patch('src.services.weather.redis.from_url') as mock_redis:
            mock_redis.side_effect = Exception("Redis connection failed")
            
            service = WeatherService()
            
            assert service.cache_enabled is False
            assert service.redis is None


class TestGetCacheKey:
    """Test cache key generation."""

    def test_cache_key_generation(self):
        """Test cache key is generated correctly."""
        with patch('src.services.weather.redis.from_url'):
            service = WeatherService()
            service.cache_enabled = False
            
            key = service._get_cache_key(40.7128, -74.0060, datetime(2025, 6, 15))
            
            assert isinstance(key, str)
            assert len(key) == 32  # MD5 hash length

    def test_cache_key_rounds_coordinates(self):
        """Test coordinates are rounded for cache key."""
        with patch('src.services.weather.redis.from_url'):
            service = WeatherService()
            service.cache_enabled = False
            
            # These should generate same key (rounded to 2 decimals)
            key1 = service._get_cache_key(40.712801, -74.006001, datetime(2025, 6, 15))
            key2 = service._get_cache_key(40.712899, -74.006099, datetime(2025, 6, 15))
            
            assert key1 == key2


class TestGetForecast:
    """Test get_forecast method."""

    @pytest.mark.asyncio
    async def test_get_forecast_no_api_key(self):
        """Test forecast without API key returns defaults."""
        with patch('src.services.weather.redis.from_url'):
            service = WeatherService()
            service.api_key = None
            service.cache_enabled = False
            
            result = await service.get_forecast(40.7128, -74.0060)
            
            assert result["is_fallback"] is True
            assert result["temp_f"] == 70.0

    @pytest.mark.asyncio
    async def test_get_forecast_cache_hit(self):
        """Test forecast returns cached data when available."""
        with patch('src.services.weather.redis.from_url') as mock_redis:
            mock_redis_instance = MagicMock()
            mock_redis_instance.ping.return_value = True
            cached_data = {
                "temp_f": 75.0,
                "feels_like_f": 73.0,
                "humidity": 60.0,
                "condition": "sunny",
                "description": "Clear skies"
            }
            mock_redis_instance.get.return_value = json.dumps(cached_data)
            mock_redis.return_value = mock_redis_instance
            
            service = WeatherService()
            service.api_key = "test_key"
            
            result = await service.get_forecast(40.7128, -74.0060)
            
            assert result == cached_data
            mock_redis_instance.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_forecast_api_success(self):
        """Test successful API call."""
        with patch('src.services.weather.redis.from_url'):
            service = WeatherService()
            service.api_key = "test_key"
            service.cache_enabled = False
            
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "list": [
                    {
                        "main": {
                            "temp": 75.5,
                            "feels_like": 73.2,
                            "humidity": 65
                        },
                        "weather": [
                            {
                                "main": "Clear",
                                "description": "clear sky"
                            }
                        ]
                    }
                ]
            }
            
            with patch('httpx.AsyncClient') as mock_client:
                mock_client_instance = MagicMock()
                mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
                mock_client_instance.__aexit__ = AsyncMock(return_value=None)
                mock_client_instance.get = AsyncMock(return_value=mock_response)
                mock_client.return_value = mock_client_instance
                
                result = await service.get_forecast(40.7128, -74.0060)
                
                assert result["temp_f"] == 75.5
                assert result["feels_like_f"] == 73.2
                assert result["condition"] == "clear"

    @pytest.mark.asyncio
    async def test_get_forecast_api_error(self):
        """Test API error returns defaults."""
        with patch('src.services.weather.redis.from_url'):
            service = WeatherService()
            service.api_key = "test_key"
            service.cache_enabled = False
            
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            
            with patch('httpx.AsyncClient') as mock_client:
                mock_client_instance = MagicMock()
                mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
                mock_client_instance.__aexit__ = AsyncMock(return_value=None)
                mock_client_instance.get = AsyncMock(return_value=mock_response)
                mock_client.return_value = mock_client_instance
                
                result = await service.get_forecast(40.7128, -74.0060)
                
                assert result["is_fallback"] is True

    @pytest.mark.asyncio
    async def test_get_forecast_caches_result(self):
        """Test successful API call caches result."""
        with patch('src.services.weather.redis.from_url') as mock_redis:
            mock_redis_instance = MagicMock()
            mock_redis_instance.ping.return_value = True
            mock_redis_instance.get.return_value = None  # Cache miss
            mock_redis.return_value = mock_redis_instance

            service = WeatherService()
            service.api_key = "test_key"

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "list": [{
                    "main": {"temp": 75.5, "feels_like": 73.2, "humidity": 65},
                    "weather": [{"main": "Clear", "description": "clear sky"}]
                }]
            }

            with patch('httpx.AsyncClient') as mock_client:
                mock_client_instance = MagicMock()
                mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
                mock_client_instance.__aexit__ = AsyncMock(return_value=None)
                mock_client_instance.get = AsyncMock(return_value=mock_response)
                mock_client.return_value = mock_client_instance

                await service.get_forecast(40.7128, -74.0060)

                # Verify cache write was called
                mock_redis_instance.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_forecast_cache_read_error(self):
        """Test cache read error falls through to API call."""
        with patch('src.services.weather.redis.from_url') as mock_redis:
            mock_redis_instance = MagicMock()
            mock_redis_instance.ping.return_value = True
            mock_redis_instance.get.side_effect = Exception("Redis connection lost")
            mock_redis.return_value = mock_redis_instance

            service = WeatherService()
            service.api_key = "test_key"

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "list": [{
                    "main": {"temp": 72.0, "feels_like": 70.0, "humidity": 55},
                    "weather": [{"main": "Cloudy", "description": "overcast"}]
                }]
            }

            with patch('httpx.AsyncClient') as mock_client:
                mock_client_instance = MagicMock()
                mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
                mock_client_instance.__aexit__ = AsyncMock(return_value=None)
                mock_client_instance.get = AsyncMock(return_value=mock_response)
                mock_client.return_value = mock_client_instance

                result = await service.get_forecast(40.7128, -74.0060)

                # Should still get weather from API despite cache error
                assert result["temp_f"] == 72.0
                assert "is_fallback" not in result

    @pytest.mark.asyncio
    async def test_get_forecast_cache_write_error(self):
        """Test cache write error doesn't prevent returning data."""
        with patch('src.services.weather.redis.from_url') as mock_redis:
            mock_redis_instance = MagicMock()
            mock_redis_instance.ping.return_value = True
            mock_redis_instance.get.return_value = None
            mock_redis_instance.setex.side_effect = Exception("Redis write failed")
            mock_redis.return_value = mock_redis_instance

            service = WeatherService()
            service.api_key = "test_key"

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "list": [{
                    "main": {"temp": 68.0, "feels_like": 67.0, "humidity": 45},
                    "weather": [{"main": "Rain", "description": "light rain"}]
                }]
            }

            with patch('httpx.AsyncClient') as mock_client:
                mock_client_instance = MagicMock()
                mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
                mock_client_instance.__aexit__ = AsyncMock(return_value=None)
                mock_client_instance.get = AsyncMock(return_value=mock_response)
                mock_client.return_value = mock_client_instance

                result = await service.get_forecast(40.7128, -74.0060)

                # Should still return weather despite cache write error
                assert result["temp_f"] == 68.0
                assert result["condition"] == "rain"

    @pytest.mark.asyncio
    async def test_get_forecast_http_exception(self):
        """Test HTTP exception returns default weather."""
        with patch('src.services.weather.redis.from_url'):
            service = WeatherService()
            service.api_key = "test_key"
            service.cache_enabled = False

            with patch('httpx.AsyncClient') as mock_client:
                mock_client_instance = MagicMock()
                mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
                mock_client_instance.__aexit__ = AsyncMock(return_value=None)
                mock_client_instance.get = AsyncMock(side_effect=httpx.TimeoutException("Request timeout"))
                mock_client.return_value = mock_client_instance

                result = await service.get_forecast(40.7128, -74.0060)

                # Should return fallback on exception
                assert result["is_fallback"] is True
                assert result["temp_f"] == 70.0


class TestGetForecastWithFallback:
    """Test get_forecast_with_fallback method."""

    @pytest.mark.asyncio
    async def test_fallback_returns_defaults_on_failure(self):
        """Test fallback returns default weather on complete failure."""
        with patch('src.services.weather.redis.from_url'):
            service = WeatherService()
            service.api_key = None
            service.cache_enabled = False

            result = await service.get_forecast_with_fallback(40.7128, -74.0060)

            assert result["is_fallback"] is True
            assert result["temp_f"] == 70.0

    @pytest.mark.asyncio
    async def test_fallback_returns_valid_data(self):
        """Test fallback returns valid API data when available."""
        with patch('src.services.weather.redis.from_url'):
            service = WeatherService()
            service.api_key = "test_key"
            service.cache_enabled = False

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "list": [{
                    "main": {"temp": 65.0, "feels_like": 63.0, "humidity": 70},
                    "weather": [{"main": "Snow", "description": "light snow"}]
                }]
            }

            with patch('httpx.AsyncClient') as mock_client:
                mock_client_instance = MagicMock()
                mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
                mock_client_instance.__aexit__ = AsyncMock(return_value=None)
                mock_client_instance.get = AsyncMock(return_value=mock_response)
                mock_client.return_value = mock_client_instance

                result = await service.get_forecast_with_fallback(40.7128, -74.0060)

                # Should return real data, not fallback
                assert result["temp_f"] == 65.0
                assert result["condition"] == "snow"
                assert "is_fallback" not in result

    @pytest.mark.asyncio
    async def test_fallback_handles_exception(self):
        """Test fallback handles complete API failure gracefully."""
        with patch('src.services.weather.redis.from_url'):
            service = WeatherService()
            service.api_key = "test_key"
            service.cache_enabled = False

            with patch('httpx.AsyncClient') as mock_client:
                mock_client_instance = MagicMock()
                mock_client_instance.__aenter__ = AsyncMock(side_effect=Exception("Network failure"))
                mock_client.return_value = mock_client_instance

                result = await service.get_forecast_with_fallback(40.7128, -74.0060)

                # Should return fallback on complete failure
                assert result["is_fallback"] is True
                assert result["temp_f"] == 70.0

    @pytest.mark.asyncio
    async def test_fallback_handles_get_forecast_exception(self):
        """Test fallback when get_forecast raises exception directly."""
        with patch('src.services.weather.redis.from_url'):
            service = WeatherService()

            # Mock get_forecast to raise an exception
            with patch.object(service, 'get_forecast', side_effect=Exception("Unexpected error")):
                result = await service.get_forecast_with_fallback(40.7128, -74.0060)

                # Should still return fallback
                assert result["is_fallback"] is True
                assert result["temp_f"] == 70.0


class TestDefaultWeather:
    """Test _get_default_weather method."""

    def test_default_weather_values(self):
        """Test default weather has expected values."""
        with patch('src.services.weather.redis.from_url'):
            service = WeatherService()
            service.cache_enabled = False
            
            result = service._get_default_weather()
            
            assert result["temp_f"] == 70.0
            assert result["feels_like_f"] == 70.0
            assert result["humidity"] == 50.0
            assert result["condition"] == "clear"
            assert result["is_fallback"] is True
