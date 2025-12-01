"""
Unit tests for Health Check Schemas

Tests Pydantic schemas for health endpoints:
- DatabaseStatus enum values
- HealthResponse model validation
- Schema examples
"""

import pytest
from pydantic import ValidationError

from src.schemas.health import DatabaseStatus, HealthResponse


class TestDatabaseStatus:
    """Test DatabaseStatus enum"""

    def test_database_status_values(self):
        """Test all DatabaseStatus enum values"""
        assert DatabaseStatus.HEALTHY == "healthy"
        assert DatabaseStatus.UNHEALTHY == "unhealthy"
        assert DatabaseStatus.UNKNOWN == "unknown"

    def test_database_status_iteration(self):
        """Test DatabaseStatus can be iterated"""
        statuses = list(DatabaseStatus)
        assert len(statuses) == 3
        assert DatabaseStatus.HEALTHY in statuses


class TestHealthResponse:
    """Test HealthResponse schema"""

    def test_health_response_valid(self):
        """Test creating valid HealthResponse"""
        response = HealthResponse(
            status="healthy",
            version="1.0.0",
            environment="production",
            database="healthy",
            database_message="Database connected"
        )

        assert response.status == "healthy"
        assert response.version == "1.0.0"
        assert response.environment == "production"
        assert response.database == "healthy"
        assert response.database_message == "Database connected"

    def test_health_response_from_dict(self):
        """Test creating HealthResponse from dictionary"""
        data = {
            "status": "degraded",
            "version": "2.0.0",
            "environment": "development",
            "database": "unhealthy",
            "database_message": "Connection failed"
        }

        response = HealthResponse(**data)

        assert response.status == "degraded"
        assert response.database == "unhealthy"

    def test_health_response_missing_required_field(self):
        """Test HealthResponse validation fails with missing field"""
        with pytest.raises(ValidationError):
            HealthResponse(
                status="healthy",
                version="1.0.0",
                # Missing environment, database, database_message
            )

    def test_health_response_example_schema(self):
        """Test example schema is valid"""
        example = HealthResponse.model_config["json_schema_extra"]["example"]

        response = HealthResponse(**example)

        assert response.status == "healthy"
        assert response.version == "0.1.0"
        assert response.environment == "development"
        assert response.database == "healthy"
        assert response.database_message == "Database connected"

    def test_health_response_to_dict(self):
        """Test HealthResponse can be converted to dict"""
        response = HealthResponse(
            status="healthy",
            version="1.0.0",
            environment="test",
            database="healthy",
            database_message="OK"
        )

        response_dict = response.model_dump()

        assert response_dict["status"] == "healthy"
        assert response_dict["version"] == "1.0.0"
        assert response_dict["environment"] == "test"
        assert response_dict["database"] == "healthy"
        assert response_dict["database_message"] == "OK"

    def test_health_response_to_json(self):
        """Test HealthResponse can be serialized to JSON"""
        response = HealthResponse(
            status="healthy",
            version="1.0.0",
            environment="production",
            database="healthy",
            database_message="Connected"
        )

        json_str = response.model_dump_json()

        assert "healthy" in json_str
        assert "1.0.0" in json_str
        assert "production" in json_str
