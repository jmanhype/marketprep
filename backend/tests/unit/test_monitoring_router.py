"""Unit tests for monitoring router.

Tests monitoring API endpoints:
- GET /health - Basic health check
- GET /health/live - Liveness probe
- GET /health/ready - Readiness probe
- GET /health/detailed - Detailed health checks
- GET /metrics - Prometheus metrics
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from types import SimpleNamespace

from fastapi import status
from sqlalchemy.orm import Session

from src.routers.monitoring import (
    health_check,
    liveness_probe,
    readiness_probe,
    detailed_health_check,
    prometheus_metrics,
)


class TestHealthCheck:
    """Test health_check endpoint."""

    @pytest.mark.asyncio
    async def test_health_check_returns_healthy(self):
        """Test basic health check returns healthy status."""
        with patch('src.routers.monitoring.settings') as mock_settings:
            mock_settings.app_version = "1.0.0"
            mock_settings.environment = "production"

            result = await health_check()

            assert result["status"] == "healthy"
            assert result["version"] == "1.0.0"
            assert result["environment"] == "production"

    @pytest.mark.asyncio
    async def test_health_check_development_environment(self):
        """Test health check in development environment."""
        with patch('src.routers.monitoring.settings') as mock_settings:
            mock_settings.app_version = "0.1.0"
            mock_settings.environment = "development"

            result = await health_check()

            assert result["status"] == "healthy"
            assert result["environment"] == "development"


class TestLivenessProbe:
    """Test liveness_probe endpoint."""

    @pytest.mark.asyncio
    async def test_liveness_probe_returns_alive(self):
        """Test liveness probe returns alive status."""
        with patch('src.routers.monitoring.settings') as mock_settings:
            mock_settings.app_version = "1.0.0"

            result = await liveness_probe()

            assert result["status"] == "alive"
            assert result["version"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_liveness_probe_response_format(self):
        """Test liveness probe response has required fields."""
        with patch('src.routers.monitoring.settings') as mock_settings:
            mock_settings.app_version = "2.5.3"

            result = await liveness_probe()

            assert "status" in result
            assert "version" in result
            assert len(result) == 2  # Should only have these two fields


class TestReadinessProbe:
    """Test readiness_probe endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_readiness_probe_healthy(self, mock_db, mock_redis):
        """Test readiness probe when all services are healthy."""
        with patch('src.routers.monitoring.settings') as mock_settings:
            mock_settings.app_version = "1.0.0"

            with patch('src.routers.monitoring.HealthChecker') as mock_checker_class:
                mock_checker = MagicMock()

                # Mock database check - healthy
                db_check = SimpleNamespace()
                db_check.status = SimpleNamespace(value="healthy")
                mock_checker.check_database = AsyncMock(return_value=db_check)

                # Mock Redis check - healthy
                redis_check = SimpleNamespace()
                redis_check.status = SimpleNamespace(value="healthy")
                mock_checker.check_redis = AsyncMock(return_value=redis_check)

                mock_checker_class.return_value = mock_checker

                result = await readiness_probe(db=mock_db, redis=mock_redis)

                assert result["status"] == "ready"
                assert result["version"] == "1.0.0"
                assert result["database"] == "healthy"
                assert result["redis"] == "healthy"

    @pytest.mark.asyncio
    async def test_readiness_probe_degraded_redis(self, mock_db, mock_redis):
        """Test readiness probe with degraded Redis (should still be ready)."""
        with patch('src.routers.monitoring.settings') as mock_settings:
            mock_settings.app_version = "1.0.0"

            with patch('src.routers.monitoring.HealthChecker') as mock_checker_class:
                mock_checker = MagicMock()

                # Database healthy
                db_check = SimpleNamespace()
                db_check.status = SimpleNamespace(value="healthy")
                mock_checker.check_database = AsyncMock(return_value=db_check)

                # Redis degraded (but we fail-open, so still ready)
                redis_check = SimpleNamespace()
                redis_check.status = SimpleNamespace(value="degraded")
                mock_checker.check_redis = AsyncMock(return_value=redis_check)

                mock_checker_class.return_value = mock_checker

                result = await readiness_probe(db=mock_db, redis=mock_redis)

                assert result["status"] == "ready"
                assert result["redis"] == "degraded"

    @pytest.mark.asyncio
    async def test_readiness_probe_unhealthy_database(self, mock_db, mock_redis):
        """Test readiness probe with unhealthy database (should NOT be ready)."""
        with patch('src.routers.monitoring.settings') as mock_settings:
            mock_settings.app_version = "1.0.0"

            with patch('src.routers.monitoring.HealthChecker') as mock_checker_class:
                mock_checker = MagicMock()

                # Database unhealthy
                db_check = SimpleNamespace()
                db_check.status = SimpleNamespace(value="unhealthy")
                mock_checker.check_database = AsyncMock(return_value=db_check)

                # Redis healthy
                redis_check = SimpleNamespace()
                redis_check.status = SimpleNamespace(value="healthy")
                mock_checker.check_redis = AsyncMock(return_value=redis_check)

                mock_checker_class.return_value = mock_checker

                result = await readiness_probe(db=mock_db, redis=mock_redis)

                assert result.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
                import json
                content = json.loads(result.body)
                assert content["status"] == "not_ready"
                assert content["database"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_readiness_probe_degraded_database(self, mock_db, mock_redis):
        """Test readiness probe with degraded database (should NOT be ready)."""
        with patch('src.routers.monitoring.settings') as mock_settings:
            mock_settings.app_version = "1.0.0"

            with patch('src.routers.monitoring.HealthChecker') as mock_checker_class:
                mock_checker = MagicMock()

                # Database degraded (not healthy)
                db_check = SimpleNamespace()
                db_check.status = SimpleNamespace(value="degraded")
                mock_checker.check_database = AsyncMock(return_value=db_check)

                # Redis healthy
                redis_check = SimpleNamespace()
                redis_check.status = SimpleNamespace(value="healthy")
                mock_checker.check_redis = AsyncMock(return_value=redis_check)

                mock_checker_class.return_value = mock_checker

                result = await readiness_probe(db=mock_db, redis=mock_redis)

                assert result.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


class TestDetailedHealthCheck:
    """Test detailed_health_check endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_detailed_health_check_all_healthy(self, mock_db, mock_redis):
        """Test detailed health check with all services healthy."""
        with patch('src.routers.monitoring.HealthChecker') as mock_checker_class:
            mock_checker = MagicMock()
            mock_checker.check_all = AsyncMock(return_value={
                "status": "healthy",
                "version": "1.0.0",
                "environment": "production",
                "checks": {
                    "database": {
                        "status": "healthy",
                        "latency_ms": 5.23,
                    },
                    "redis": {
                        "status": "healthy",
                        "latency_ms": 2.15,
                    },
                    "square": {
                        "status": "healthy",
                        "latency_ms": 150.42,
                    },
                },
                "total_latency_ms": 157.80,
                "timestamp": "2025-01-30T12:00:00Z",
            })
            mock_checker_class.return_value = mock_checker

            result = await detailed_health_check(db=mock_db, redis=mock_redis)

            assert result["status"] == "healthy"
            assert "checks" in result
            assert "database" in result["checks"]
            assert "redis" in result["checks"]
            assert "total_latency_ms" in result

            # Verify checker was initialized correctly
            mock_checker_class.assert_called_once_with(
                db_session=mock_db,
                redis_client=mock_redis,
            )

    @pytest.mark.asyncio
    async def test_detailed_health_check_degraded(self, mock_db, mock_redis):
        """Test detailed health check with some services degraded."""
        with patch('src.routers.monitoring.HealthChecker') as mock_checker_class:
            mock_checker = MagicMock()
            mock_checker.check_all = AsyncMock(return_value={
                "status": "degraded",
                "version": "1.0.0",
                "environment": "production",
                "checks": {
                    "database": {
                        "status": "healthy",
                        "latency_ms": 5.23,
                    },
                    "redis": {
                        "status": "degraded",
                        "latency_ms": None,
                        "details": "Connection timeout",
                    },
                    "square": {
                        "status": "degraded",
                        "latency_ms": None,
                        "details": "API unavailable",
                    },
                },
                "total_latency_ms": 1250.42,
                "timestamp": "2025-01-30T12:00:00Z",
            })
            mock_checker_class.return_value = mock_checker

            result = await detailed_health_check(db=mock_db, redis=mock_redis)

            assert result["status"] == "degraded"
            assert result["checks"]["redis"]["status"] == "degraded"
            assert result["checks"]["square"]["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_detailed_health_check_unhealthy(self, mock_db, mock_redis):
        """Test detailed health check with critical services unhealthy."""
        with patch('src.routers.monitoring.HealthChecker') as mock_checker_class:
            mock_checker = MagicMock()
            mock_checker.check_all = AsyncMock(return_value={
                "status": "unhealthy",
                "version": "1.0.0",
                "environment": "production",
                "checks": {
                    "database": {
                        "status": "unhealthy",
                        "latency_ms": None,
                        "details": "Connection refused",
                    },
                },
                "total_latency_ms": 5000.0,
                "timestamp": "2025-01-30T12:00:00Z",
            })
            mock_checker_class.return_value = mock_checker

            result = await detailed_health_check(db=mock_db, redis=mock_redis)

            assert result["status"] == "unhealthy"
            assert result["checks"]["database"]["status"] == "unhealthy"


class TestPrometheusMetrics:
    """Test prometheus_metrics endpoint."""

    @pytest.mark.asyncio
    async def test_prometheus_metrics_returns_text_format(self):
        """Test Prometheus metrics returns text format."""
        with patch('src.routers.monitoring.metrics_response') as mock_metrics:
            mock_metrics.return_value = (
                "# HELP marketprep_http_requests_total Total HTTP requests\n"
                "# TYPE marketprep_http_requests_total counter\n"
                "marketprep_http_requests_total{method=\"GET\",status_code=\"200\"} 1523.0\n"
            )

            result = await prometheus_metrics()

            assert "marketprep_http_requests_total" in result
            assert "counter" in result
            assert "1523.0" in result
            mock_metrics.assert_called_once()

    @pytest.mark.asyncio
    async def test_prometheus_metrics_contains_metrics(self):
        """Test Prometheus metrics contains expected metric types."""
        with patch('src.routers.monitoring.metrics_response') as mock_metrics:
            mock_metrics.return_value = (
                "# HELP marketprep_http_requests_total Total HTTP requests\n"
                "# TYPE marketprep_http_requests_total counter\n"
                "marketprep_http_requests_total{method=\"GET\"} 100.0\n"
                "# HELP marketprep_http_request_duration_seconds HTTP request duration\n"
                "# TYPE marketprep_http_request_duration_seconds histogram\n"
                "marketprep_http_request_duration_seconds_bucket{le=\"0.1\"} 50.0\n"
            )

            result = await prometheus_metrics()

            # Verify metrics format
            assert "# HELP" in result
            assert "# TYPE" in result
            assert "counter" in result
            assert "histogram" in result
