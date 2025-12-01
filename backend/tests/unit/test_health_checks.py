"""
Unit tests for Health Check System

Tests health monitoring functionality:
- HealthCheckResult creation and serialization
- Overall status calculation logic (critical vs non-critical services)
- Database connectivity checks (healthy, degraded, unhealthy)
- Redis connectivity checks with fail-open behavior
- External API health checks (Square, Weather, Events)
- ML model availability checks
- System resource monitoring (disk space, memory)
- Parallel check orchestration
- Error handling and exception recovery
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch
from sqlalchemy import text

from src.monitoring.health_checks import (
    HealthStatus,
    HealthCheckResult,
    HealthChecker,
)


class TestHealthCheckResult:
    """Test HealthCheckResult class"""

    def test_create_result_with_details(self):
        """Test creating health check result with details"""
        result = HealthCheckResult(
            name="test_service",
            status=HealthStatus.HEALTHY,
            latency_ms=15.5,
            details={"connection": "active", "version": "1.0"},
        )

        assert result.name == "test_service"
        assert result.status == HealthStatus.HEALTHY
        assert result.latency_ms == 15.5
        assert result.details == {"connection": "active", "version": "1.0"}
        assert result.timestamp is not None

    def test_create_result_without_details(self):
        """Test creating health check result without details (defaults to empty dict)"""
        result = HealthCheckResult(
            name="test_service",
            status=HealthStatus.DEGRADED,
            latency_ms=100.0,
        )

        assert result.details == {}

    def test_to_dict(self):
        """Test serializing result to dictionary"""
        result = HealthCheckResult(
            name="database",
            status=HealthStatus.HEALTHY,
            latency_ms=12.345,
            details={"query_time": 10},
        )

        result_dict = result.to_dict()

        assert result_dict["name"] == "database"
        assert result_dict["status"] == "healthy"
        assert result_dict["latency_ms"] == 12.35  # Rounded to 2 decimals
        assert result_dict["details"] == {"query_time": 10}
        assert "timestamp" in result_dict
        assert result_dict["timestamp"].endswith("Z")


class TestHealthCheckerDatabase:
    """Test database health checks"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return MagicMock()

    @pytest.fixture
    def checker(self, mock_db):
        """Create health checker with mock db"""
        return HealthChecker(db_session=mock_db)

    def test_database_healthy(self, checker, mock_db):
        """Test healthy database check (fast response)"""
        # Mock successful query
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (1,)
        mock_db.execute.return_value = mock_result

        result = checker.check_database()

        assert result.name == "database"
        assert result.status == HealthStatus.HEALTHY
        assert result.latency_ms < 100  # Fast response
        assert result.details["connection"] == "active"

    def test_database_degraded_slow_query(self, checker, mock_db):
        """Test degraded database (slow query > 100ms)"""
        # Mock slow query
        import time

        def slow_execute(*args):
            time.sleep(0.11)  # 110ms delay
            mock_result = MagicMock()
            mock_result.fetchone.return_value = (1,)
            return mock_result

        mock_db.execute.side_effect = slow_execute

        result = checker.check_database()

        assert result.name == "database"
        assert result.status == HealthStatus.DEGRADED
        assert result.latency_ms > 100

    def test_database_unhealthy_no_session(self):
        """Test unhealthy database when no session provided"""
        checker = HealthChecker(db_session=None)

        result = checker.check_database()

        assert result.name == "database"
        assert result.status == HealthStatus.UNHEALTHY
        assert result.latency_ms == 0
        assert "No database session" in result.details["error"]

    def test_database_unhealthy_query_exception(self, checker, mock_db):
        """Test unhealthy database when query raises exception"""
        mock_db.execute.side_effect = Exception("Connection refused")

        result = checker.check_database()

        assert result.name == "database"
        assert result.status == HealthStatus.UNHEALTHY
        assert "Connection refused" in result.details["error"]

    def test_database_unhealthy_unexpected_result(self, checker, mock_db):
        """Test unhealthy database when query returns unexpected result"""
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (99,)  # Not 1
        mock_db.execute.return_value = mock_result

        result = checker.check_database()

        assert result.name == "database"
        assert result.status == HealthStatus.UNHEALTHY
        assert "unexpected result" in result.details["error"]


class TestHealthCheckerRedis:
    """Test Redis health checks"""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client"""
        return MagicMock()

    @pytest.fixture
    def checker(self, mock_redis):
        """Create health checker with mock redis"""
        return HealthChecker(redis_client=mock_redis)

    def test_redis_healthy(self, checker, mock_redis):
        """Test healthy Redis check (fast ping)"""
        mock_redis.ping.return_value = True

        result = checker.check_redis()

        assert result.name == "redis"
        assert result.status == HealthStatus.HEALTHY
        assert result.details["connection"] == "active"

    def test_redis_degraded_slow_ping(self, checker, mock_redis):
        """Test degraded Redis (slow ping > 50ms)"""
        import time

        def slow_ping():
            time.sleep(0.06)  # 60ms delay
            return True

        mock_redis.ping.side_effect = slow_ping

        result = checker.check_redis()

        assert result.name == "redis"
        assert result.status == HealthStatus.DEGRADED

    def test_redis_degraded_no_client(self):
        """Test degraded Redis when no client provided (fail-open)"""
        checker = HealthChecker(redis_client=None)

        result = checker.check_redis()

        assert result.name == "redis"
        assert result.status == HealthStatus.DEGRADED  # Not unhealthy
        assert "No Redis client" in result.details["error"]
        assert "Rate limiting disabled" in result.details["impact"]

    def test_redis_degraded_ping_exception(self, checker, mock_redis):
        """Test degraded Redis when ping raises exception (fail-open)"""
        mock_redis.ping.side_effect = Exception("Connection timeout")

        result = checker.check_redis()

        assert result.name == "redis"
        assert result.status == HealthStatus.DEGRADED  # Fail-open
        assert "Connection timeout" in result.details["error"]
        assert "Rate limiting disabled" in result.details["impact"]

    def test_redis_degraded_ping_false(self, checker, mock_redis):
        """Test degraded Redis when ping returns False"""
        mock_redis.ping.return_value = False

        result = checker.check_redis()

        assert result.name == "redis"
        assert result.status == HealthStatus.DEGRADED
        assert "PING failed" in result.details["error"]


class TestHealthCheckerSquareAPI:
    """Test Square API health checks"""

    @pytest.fixture
    def checker(self):
        """Create health checker"""
        return HealthChecker()

    @pytest.mark.asyncio
    @patch('src.monitoring.health_checks.settings')
    @patch('src.monitoring.health_checks.httpx.AsyncClient')
    async def test_square_api_healthy(self, mock_client_class, mock_settings, checker):
        """Test healthy Square API check"""
        mock_settings.square_application_id = "test_app_id"
        mock_settings.square_application_secret = "test_secret"
        mock_settings.square_base_url = "https://connect.squareup.com"

        # Mock successful API response
        mock_response = AsyncMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        mock_client_class.return_value = mock_client

        result = await checker.check_square_api()

        assert result.name == "square"
        assert result.status == HealthStatus.HEALTHY
        assert result.details["response_status"] == 200

    @pytest.mark.asyncio
    @patch('src.monitoring.health_checks.settings')
    async def test_square_api_degraded_not_configured(self, mock_settings, checker):
        """Test degraded Square API when not configured"""
        mock_settings.square_application_id = None

        result = await checker.check_square_api()

        assert result.name == "square"
        assert result.status == HealthStatus.DEGRADED
        assert result.details["configured"] is False
        assert "cached data" in result.details["impact"]

    @pytest.mark.asyncio
    @patch('src.monitoring.health_checks.settings')
    @patch('src.monitoring.health_checks.httpx.AsyncClient')
    async def test_square_api_degraded_http_error(self, mock_client_class, mock_settings, checker):
        """Test degraded Square API on HTTP error"""
        mock_settings.square_application_id = "test_app_id"
        mock_settings.square_application_secret = "test_secret"
        mock_settings.square_base_url = "https://connect.squareup.com"

        mock_response = AsyncMock()
        mock_response.status_code = 503

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        mock_client_class.return_value = mock_client

        result = await checker.check_square_api()

        assert result.name == "square"
        assert result.status == HealthStatus.DEGRADED
        assert "HTTP 503" in result.details["error"]

    @pytest.mark.asyncio
    @patch('src.monitoring.health_checks.settings')
    @patch('src.monitoring.health_checks.httpx.AsyncClient')
    async def test_square_api_degraded_exception(self, mock_client_class, mock_settings, checker):
        """Test degraded Square API on exception"""
        mock_settings.square_application_id = "test_app_id"
        mock_settings.square_application_secret = "test_secret"
        mock_settings.square_base_url = "https://connect.squareup.com"

        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("Network error")
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        mock_client_class.return_value = mock_client

        result = await checker.check_square_api()

        assert result.name == "square"
        assert result.status == HealthStatus.DEGRADED
        assert "Network error" in result.details["error"]


class TestHealthCheckerWeatherAPI:
    """Test Weather API health checks"""

    @pytest.fixture
    def checker(self):
        """Create health checker"""
        return HealthChecker()

    @pytest.mark.asyncio
    @patch('src.monitoring.health_checks.settings')
    @patch('src.monitoring.health_checks.httpx.AsyncClient')
    async def test_weather_api_healthy(self, mock_client_class, mock_settings, checker):
        """Test healthy Weather API check"""
        mock_settings.openweather_api_key = "test_api_key"

        mock_response = AsyncMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        mock_client_class.return_value = mock_client

        result = await checker.check_weather_api()

        assert result.name == "weather"
        assert result.status == HealthStatus.HEALTHY
        assert result.details["response_status"] == 200

    @pytest.mark.asyncio
    @patch('src.monitoring.health_checks.settings')
    async def test_weather_api_degraded_not_configured(self, mock_settings, checker):
        """Test degraded Weather API when not configured"""
        mock_settings.openweather_api_key = None

        result = await checker.check_weather_api()

        assert result.name == "weather"
        assert result.status == HealthStatus.DEGRADED
        assert result.details["configured"] is False

    @pytest.mark.asyncio
    @patch('src.monitoring.health_checks.settings')
    @patch('src.monitoring.health_checks.httpx.AsyncClient')
    async def test_weather_api_degraded_http_error(self, mock_client_class, mock_settings, checker):
        """Test degraded Weather API on HTTP error"""
        mock_settings.openweather_api_key = "test_api_key"

        mock_response = AsyncMock()
        mock_response.status_code = 401

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        mock_client_class.return_value = mock_client

        result = await checker.check_weather_api()

        assert result.name == "weather"
        assert result.status == HealthStatus.DEGRADED
        assert "HTTP 401" in result.details["error"]


class TestHealthCheckerEventsAPI:
    """Test Events API health checks"""

    @pytest.fixture
    def checker(self):
        """Create health checker"""
        return HealthChecker()

    @pytest.mark.asyncio
    @patch('src.monitoring.health_checks.settings')
    @patch('src.monitoring.health_checks.httpx.AsyncClient')
    async def test_events_api_healthy(self, mock_client_class, mock_settings, checker):
        """Test healthy Events API check"""
        mock_settings.eventbrite_api_key = "test_api_key"

        mock_response = AsyncMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        mock_client_class.return_value = mock_client

        result = await checker.check_events_api()

        assert result.name == "events"
        assert result.status == HealthStatus.HEALTHY

    @pytest.mark.asyncio
    @patch('src.monitoring.health_checks.settings')
    async def test_events_api_degraded_not_configured(self, mock_settings, checker):
        """Test degraded Events API when not configured"""
        mock_settings.eventbrite_api_key = None

        result = await checker.check_events_api()

        assert result.name == "events"
        assert result.status == HealthStatus.DEGRADED
        assert "database events only" in result.details["impact"]


class TestHealthCheckerMLModel:
    """Test ML model health checks"""

    @pytest.fixture
    def checker(self):
        """Create health checker"""
        return HealthChecker()

    @patch('os.path.exists')
    def test_ml_model_healthy(self, mock_exists, checker):
        """Test healthy ML model check (both files exist)"""
        mock_exists.return_value = True  # Both model and scaler exist

        result = checker.check_ml_model()

        assert result.name == "ml_model"
        assert result.status == HealthStatus.HEALTHY
        assert result.details["model_loaded"] is True
        assert result.details["scaler_loaded"] is True

    @patch('os.path.exists')
    def test_ml_model_degraded_missing_files(self, mock_exists, checker):
        """Test degraded ML model check (files missing)"""
        mock_exists.return_value = False  # Files don't exist

        result = checker.check_ml_model()

        assert result.name == "ml_model"
        assert result.status == HealthStatus.DEGRADED
        assert result.details["model_loaded"] is False
        assert result.details["scaler_loaded"] is False
        assert "fallback heuristics" in result.details["impact"]


class TestHealthCheckerDiskSpace:
    """Test disk space health checks"""

    @pytest.fixture
    def checker(self):
        """Create health checker"""
        return HealthChecker()

    @patch('shutil.disk_usage')
    def test_disk_healthy(self, mock_disk_usage, checker):
        """Test healthy disk check (< 80% used)"""
        mock_usage = MagicMock()
        mock_usage.total = 1000 * (1024 ** 3)  # 1000 GB
        mock_usage.used = 500 * (1024 ** 3)    # 500 GB (50%)
        mock_usage.free = 500 * (1024 ** 3)
        mock_disk_usage.return_value = mock_usage

        result = checker.check_disk_space()

        assert result.name == "disk"
        assert result.status == HealthStatus.HEALTHY
        assert result.details["percent_used"] == 50.0

    @patch('shutil.disk_usage')
    def test_disk_degraded(self, mock_disk_usage, checker):
        """Test degraded disk check (80-90% used)"""
        mock_usage = MagicMock()
        mock_usage.total = 1000 * (1024 ** 3)
        mock_usage.used = 850 * (1024 ** 3)  # 85%
        mock_usage.free = 150 * (1024 ** 3)
        mock_disk_usage.return_value = mock_usage

        result = checker.check_disk_space()

        assert result.name == "disk"
        assert result.status == HealthStatus.DEGRADED
        assert result.details["percent_used"] == 85.0

    @patch('shutil.disk_usage')
    def test_disk_unhealthy(self, mock_disk_usage, checker):
        """Test unhealthy disk check (> 90% used)"""
        mock_usage = MagicMock()
        mock_usage.total = 1000 * (1024 ** 3)
        mock_usage.used = 950 * (1024 ** 3)  # 95%
        mock_usage.free = 50 * (1024 ** 3)
        mock_disk_usage.return_value = mock_usage

        result = checker.check_disk_space()

        assert result.name == "disk"
        assert result.status == HealthStatus.UNHEALTHY
        assert result.details["percent_used"] == 95.0

    @patch('shutil.disk_usage')
    def test_disk_exception(self, mock_disk_usage, checker):
        """Test disk check handles exception"""
        mock_disk_usage.side_effect = Exception("Permission denied")

        result = checker.check_disk_space()

        assert result.name == "disk"
        assert result.status == HealthStatus.UNHEALTHY
        assert "Permission denied" in result.details["error"]


class TestHealthCheckerMemory:
    """Test memory usage health checks"""

    @pytest.fixture
    def checker(self):
        """Create health checker"""
        return HealthChecker()

    @patch('psutil.virtual_memory')
    def test_memory_healthy(self, mock_memory, checker):
        """Test healthy memory check (< 80% used)"""
        mock_mem = MagicMock()
        mock_mem.total = 16 * (1024 ** 3)      # 16 GB
        mock_mem.available = 10 * (1024 ** 3)  # 10 GB available
        mock_mem.percent = 37.5  # 37.5% used
        mock_memory.return_value = mock_mem

        result = checker.check_memory_usage()

        assert result.name == "memory"
        assert result.status == HealthStatus.HEALTHY
        assert result.details["percent_used"] == 37.5

    @patch('psutil.virtual_memory')
    def test_memory_degraded(self, mock_memory, checker):
        """Test degraded memory check (80-90% used)"""
        mock_mem = MagicMock()
        mock_mem.total = 16 * (1024 ** 3)
        mock_mem.available = 2 * (1024 ** 3)
        mock_mem.percent = 85.0
        mock_memory.return_value = mock_mem

        result = checker.check_memory_usage()

        assert result.name == "memory"
        assert result.status == HealthStatus.DEGRADED

    @patch('psutil.virtual_memory')
    def test_memory_unhealthy(self, mock_memory, checker):
        """Test unhealthy memory check (> 90% used)"""
        mock_mem = MagicMock()
        mock_mem.total = 16 * (1024 ** 3)
        mock_mem.available = 1 * (1024 ** 3)
        mock_mem.percent = 95.0
        mock_memory.return_value = mock_mem

        result = checker.check_memory_usage()

        assert result.name == "memory"
        assert result.status == HealthStatus.UNHEALTHY


class TestHealthCheckerOverallStatus:
    """Test overall status calculation"""

    @pytest.fixture
    def checker(self):
        """Create health checker"""
        return HealthChecker()

    def test_overall_healthy(self, checker):
        """Test overall healthy when all checks healthy"""
        checks = {
            "database": {"status": "healthy"},
            "redis": {"status": "healthy"},
            "square": {"status": "healthy"},
            "weather": {"status": "healthy"},
            "events": {"status": "healthy"},
            "ml_model": {"status": "healthy"},
            "disk": {"status": "healthy"},
            "memory": {"status": "healthy"},
        }

        status = checker._calculate_overall_status(checks)

        assert status == HealthStatus.HEALTHY

    def test_overall_unhealthy_critical_service(self, checker):
        """Test overall unhealthy when critical service (database) unhealthy"""
        checks = {
            "database": {"status": "unhealthy"},  # Critical
            "redis": {"status": "healthy"},
            "square": {"status": "healthy"},
            "weather": {"status": "healthy"},
            "events": {"status": "healthy"},
            "ml_model": {"status": "healthy"},
            "disk": {"status": "healthy"},
            "memory": {"status": "healthy"},
        }

        status = checker._calculate_overall_status(checks)

        assert status == HealthStatus.UNHEALTHY

    def test_overall_degraded_critical_service(self, checker):
        """Test overall degraded when critical service (redis) degraded"""
        checks = {
            "database": {"status": "healthy"},
            "redis": {"status": "degraded"},  # Critical
            "square": {"status": "healthy"},
            "weather": {"status": "healthy"},
            "events": {"status": "healthy"},
            "ml_model": {"status": "healthy"},
            "disk": {"status": "healthy"},
            "memory": {"status": "healthy"},
        }

        status = checker._calculate_overall_status(checks)

        assert status == HealthStatus.DEGRADED

    def test_overall_degraded_non_critical_unhealthy(self, checker):
        """Test overall degraded when non-critical service unhealthy"""
        checks = {
            "database": {"status": "healthy"},
            "redis": {"status": "healthy"},
            "square": {"status": "unhealthy"},  # Non-critical
            "weather": {"status": "healthy"},
            "events": {"status": "healthy"},
            "ml_model": {"status": "healthy"},
            "disk": {"status": "healthy"},
            "memory": {"status": "healthy"},
        }

        status = checker._calculate_overall_status(checks)

        assert status == HealthStatus.DEGRADED


class TestHealthCheckerCheckAll:
    """Test orchestrated health check execution"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (1,)
        mock_db.execute.return_value = mock_result
        return mock_db

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client"""
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        return mock_redis

    @pytest.fixture
    def checker(self, mock_db, mock_redis):
        """Create health checker with mocks"""
        return HealthChecker(db_session=mock_db, redis_client=mock_redis)

    @pytest.mark.asyncio
    @patch('src.monitoring.health_checks.settings')
    @patch('shutil.disk_usage')
    @patch('psutil.virtual_memory')
    @patch('os.path.exists')
    async def test_check_all_success(
        self,
        mock_exists,
        mock_memory,
        mock_disk,
        mock_settings,
        checker,
    ):
        """Test successful execution of all health checks"""
        # Mock settings
        mock_settings.version = "1.0.0"
        mock_settings.environment = "test"
        mock_settings.square_application_id = None  # Not configured
        mock_settings.openweather_api_key = None
        mock_settings.eventbrite_api_key = None

        # Mock system checks
        mock_exists.return_value = True

        mock_mem = MagicMock()
        mock_mem.total = 16 * (1024 ** 3)
        mock_mem.available = 10 * (1024 ** 3)
        mock_mem.percent = 37.5
        mock_memory.return_value = mock_mem

        mock_usage = MagicMock()
        mock_usage.total = 1000 * (1024 ** 3)
        mock_usage.used = 500 * (1024 ** 3)
        mock_usage.free = 500 * (1024 ** 3)
        mock_disk.return_value = mock_usage

        result = await checker.check_all()

        # Verify result structure
        assert "status" in result
        assert "version" in result
        assert "environment" in result
        assert "checks" in result
        assert "total_latency_ms" in result
        assert "timestamp" in result

        # Verify all checks present
        assert "database" in result["checks"]
        assert "redis" in result["checks"]
        assert "square" in result["checks"]
        assert "weather" in result["checks"]
        assert "events" in result["checks"]
        assert "ml_model" in result["checks"]
        assert "disk" in result["checks"]
        assert "memory" in result["checks"]

        # Verify version and environment
        assert result["version"] == "1.0.0"
        assert result["environment"] == "test"

    @pytest.mark.asyncio
    @patch('src.monitoring.health_checks.settings')
    @patch('shutil.disk_usage')
    @patch('psutil.virtual_memory')
    @patch('os.path.exists')
    async def test_check_all_handles_exceptions(
        self,
        mock_exists,
        mock_memory,
        mock_disk,
        mock_settings,
    ):
        """Test that check_all handles individual check exceptions"""
        mock_settings.version = "1.0.0"
        mock_settings.environment = "test"
        mock_settings.square_application_id = None
        mock_settings.openweather_api_key = None
        mock_settings.eventbrite_api_key = None

        # Mock system checks
        mock_exists.return_value = True

        mock_mem = MagicMock()
        mock_mem.total = 16 * (1024 ** 3)
        mock_mem.available = 10 * (1024 ** 3)
        mock_mem.percent = 37.5
        mock_memory.return_value = mock_mem

        mock_usage = MagicMock()
        mock_usage.total = 1000 * (1024 ** 3)
        mock_usage.used = 500 * (1024 ** 3)
        mock_usage.free = 500 * (1024 ** 3)
        mock_disk.return_value = mock_usage

        # Create checker with failing database
        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception("Database connection failed")

        mock_redis = MagicMock()
        mock_redis.ping.return_value = True

        checker = HealthChecker(db_session=mock_db, redis_client=mock_redis)

        result = await checker.check_all()

        # Check should still complete
        assert "checks" in result
        assert "database" in result["checks"]

        # Database check should show as unhealthy due to exception
        assert result["checks"]["database"]["status"] == "unhealthy"
        assert "error" in result["checks"]["database"]["details"]


class TestHealthCheckerAdditionalCoverage:
    """Additional tests to reach 100% coverage"""

    @pytest.fixture
    def checker(self):
        """Create health checker"""
        return HealthChecker()

    @pytest.mark.asyncio
    @patch('src.monitoring.health_checks.settings')
    @patch('src.monitoring.health_checks.httpx.AsyncClient')
    @patch('time.time')
    async def test_square_api_degraded_slow_response(self, mock_time, mock_client_class, mock_settings, checker):
        """Test degraded Square API when response is slow (> 2000ms)"""
        mock_settings.square_application_id = "test_app_id"
        mock_settings.square_application_secret = "test_secret"
        mock_settings.square_base_url = "https://connect.squareup.com"

        # Simulate 2.5 second response time
        mock_time.side_effect = [0, 2.5]

        mock_response = AsyncMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        mock_client_class.return_value = mock_client

        result = await checker.check_square_api()

        assert result.name == "square"
        assert result.status == HealthStatus.DEGRADED  # Slow response
        assert result.latency_ms == 2500

    @pytest.mark.asyncio
    @patch('src.monitoring.health_checks.settings')
    @patch('src.monitoring.health_checks.httpx.AsyncClient')
    @patch('time.time')
    async def test_weather_api_degraded_slow_response(self, mock_time, mock_client_class, mock_settings, checker):
        """Test degraded Weather API when response is slow (> 3000ms)"""
        mock_settings.openweather_api_key = "test_api_key"

        # Simulate 3.5 second response time
        mock_time.side_effect = [0, 3.5]

        mock_response = AsyncMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        mock_client_class.return_value = mock_client

        result = await checker.check_weather_api()

        assert result.name == "weather"
        assert result.status == HealthStatus.DEGRADED  # Slow response
        assert result.latency_ms == 3500

    @pytest.mark.asyncio
    @patch('src.monitoring.health_checks.settings')
    @patch('src.monitoring.health_checks.httpx.AsyncClient')
    async def test_weather_api_degraded_exception(self, mock_client_class, mock_settings, checker):
        """Test degraded Weather API on exception"""
        mock_settings.openweather_api_key = "test_api_key"

        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("Timeout error")
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        mock_client_class.return_value = mock_client

        result = await checker.check_weather_api()

        assert result.name == "weather"
        assert result.status == HealthStatus.DEGRADED
        assert "Timeout error" in result.details["error"]

    @pytest.mark.asyncio
    @patch('src.monitoring.health_checks.settings')
    @patch('src.monitoring.health_checks.httpx.AsyncClient')
    @patch('time.time')
    async def test_events_api_degraded_slow_response(self, mock_time, mock_client_class, mock_settings, checker):
        """Test degraded Events API when response is slow (> 3000ms)"""
        mock_settings.eventbrite_api_key = "test_api_key"

        # Simulate 3.2 second response time
        mock_time.side_effect = [0, 3.2]

        mock_response = AsyncMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        mock_client_class.return_value = mock_client

        result = await checker.check_events_api()

        assert result.name == "events"
        assert result.status == HealthStatus.DEGRADED  # Slow response
        assert result.latency_ms == 3200

    @pytest.mark.asyncio
    @patch('src.monitoring.health_checks.settings')
    @patch('src.monitoring.health_checks.httpx.AsyncClient')
    async def test_events_api_degraded_http_error(self, mock_client_class, mock_settings, checker):
        """Test degraded Events API on HTTP error"""
        mock_settings.eventbrite_api_key = "test_api_key"

        mock_response = AsyncMock()
        mock_response.status_code = 403

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        mock_client_class.return_value = mock_client

        result = await checker.check_events_api()

        assert result.name == "events"
        assert result.status == HealthStatus.DEGRADED
        assert "HTTP 403" in result.details["error"]

    @pytest.mark.asyncio
    @patch('src.monitoring.health_checks.settings')
    @patch('src.monitoring.health_checks.httpx.AsyncClient')
    async def test_events_api_degraded_exception(self, mock_client_class, mock_settings, checker):
        """Test degraded Events API on exception"""
        mock_settings.eventbrite_api_key = "test_api_key"

        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("Connection error")
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        mock_client_class.return_value = mock_client

        result = await checker.check_events_api()

        assert result.name == "events"
        assert result.status == HealthStatus.DEGRADED
        assert "Connection error" in result.details["error"]

    @patch('os.path.exists')
    def test_ml_model_degraded_exception(self, mock_exists, checker):
        """Test degraded ML model check on exception"""
        mock_exists.side_effect = Exception("File system error")

        result = checker.check_ml_model()

        assert result.name == "ml_model"
        assert result.status == HealthStatus.DEGRADED
        assert "File system error" in result.details["error"]
        assert "fallback heuristics" in result.details["impact"]

    @patch('psutil.virtual_memory')
    def test_memory_unhealthy_exception(self, mock_memory, checker):
        """Test unhealthy memory check on exception"""
        mock_memory.side_effect = Exception("Memory read error")

        result = checker.check_memory_usage()

        assert result.name == "memory"
        assert result.status == HealthStatus.UNHEALTHY
        assert "Memory read error" in result.details["error"]

    @pytest.mark.asyncio
    @patch('src.monitoring.health_checks.settings')
    @patch('shutil.disk_usage')
    @patch('psutil.virtual_memory')
    @patch('os.path.exists')
    async def test_check_all_with_check_raising_exception(
        self,
        mock_exists,
        mock_memory,
        mock_disk,
        mock_settings,
    ):
        """Test check_all handles exception from individual check"""
        mock_settings.version = "1.0.0"
        mock_settings.environment = "test"
        mock_settings.square_application_id = None
        mock_settings.openweather_api_key = None
        mock_settings.eventbrite_api_key = None

        # Mock system checks - ml_model will fail
        mock_exists.side_effect = Exception("Unexpected error")

        mock_mem = MagicMock()
        mock_mem.total = 16 * (1024 ** 3)
        mock_mem.available = 10 * (1024 ** 3)
        mock_mem.percent = 37.5
        mock_memory.return_value = mock_mem

        mock_usage = MagicMock()
        mock_usage.total = 1000 * (1024 ** 3)
        mock_usage.used = 500 * (1024 ** 3)
        mock_usage.free = 500 * (1024 ** 3)
        mock_disk.return_value = mock_usage

        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (1,)
        mock_db.execute.return_value = mock_result

        mock_redis = MagicMock()
        mock_redis.ping.return_value = True

        checker = HealthChecker(db_session=mock_db, redis_client=mock_redis)

        result = await checker.check_all()

        # Check should still complete
        assert "checks" in result
        # ML model check should show degraded due to exception caught in check_ml_model
        assert "ml_model" in result["checks"]
        assert result["checks"]["ml_model"]["status"] == "degraded"

    @pytest.mark.asyncio
    @patch('src.monitoring.health_checks.settings')
    @patch('src.monitoring.health_checks.logger')
    @patch('shutil.disk_usage')
    @patch('psutil.virtual_memory')
    @patch('os.path.exists')
    async def test_check_all_handles_check_method_exception(
        self,
        mock_exists,
        mock_memory,
        mock_disk,
        mock_logger,
        mock_settings,
    ):
        """Test check_all handles exception raised by check method itself.

        This covers lines 134-135 where asyncio.gather with return_exceptions=True
        catches an exception that is NOT handled by the individual check method,
        and logs the error before creating an unhealthy check result.
        """
        mock_settings.version = "1.0.0"
        mock_settings.environment = "test"
        mock_settings.square_application_id = None
        mock_settings.openweather_api_key = None
        mock_settings.eventbrite_api_key = None

        # Mock system checks to work normally
        mock_exists.return_value = True

        mock_mem = MagicMock()
        mock_mem.total = 16 * (1024 ** 3)
        mock_mem.available = 10 * (1024 ** 3)
        mock_mem.percent = 37.5
        mock_memory.return_value = mock_mem

        mock_usage = MagicMock()
        mock_usage.total = 1000 * (1024 ** 3)
        mock_usage.used = 500 * (1024 ** 3)
        mock_usage.free = 500 * (1024 ** 3)
        mock_disk.return_value = mock_usage

        # Create checker with normal database and redis
        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (1,)
        mock_db.execute.return_value = mock_result

        mock_redis = MagicMock()
        mock_redis.ping.return_value = True

        checker = HealthChecker(db_session=mock_db, redis_client=mock_redis)

        # Mock check_database to raise an exception directly
        # (not caught by check_database's own try/except)
        with patch.object(checker, 'check_database', side_effect=RuntimeError("Unexpected check failure")):
            result = await checker.check_all()

            # Check should still complete
            assert "checks" in result
            assert "database" in result["checks"]

            # Database check should show as unhealthy with error details
            assert result["checks"]["database"]["status"] == "unhealthy"
            assert "error" in result["checks"]["database"]["details"]
            assert "Unexpected check failure" in result["checks"]["database"]["details"]["error"]

            # Verify logger.error was called for the failure (line 134)
            mock_logger.error.assert_called_once()
            error_call_args = mock_logger.error.call_args[0][0]
            assert "database" in error_call_args
            assert "Unexpected check failure" in str(error_call_args)
