"""Pytest configuration and shared fixtures."""
import pytest
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from fastapi.testclient import TestClient

from src.models.base import Base
from src.config import Settings


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Override settings for testing."""
    import os

    # Use environment variables if available (for CI), otherwise use local defaults
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://marketprep:devpassword@localhost:5433/marketprep_test"
    )
    redis_url = os.getenv(
        "REDIS_URL",
        "redis://localhost:6379/15"
    )

    return Settings(
        database_url=database_url,
        redis_url=redis_url,
        environment="development",  # Must be development|staging|production
        debug=True,
    )


@pytest.fixture(scope="session")
def test_engine(test_settings: Settings):
    """Create test database engine."""
    engine = create_engine(str(test_settings.database_url), echo=False)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(test_engine) -> Generator[Session, None, None]:
    """Create a new database session for each test."""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="function")
def db(db_session) -> Generator[Session, None, None]:
    """Alias for db_session fixture (used by integration tests)."""
    yield db_session


@pytest.fixture(scope="module")
def test_client() -> Generator[TestClient, None, None]:
    """Create FastAPI test client."""
    from src.main import app

    with TestClient(app) as client:
        yield client


class AuthenticatedClient:
    """Test client with authentication and vendor_id."""

    def __init__(self, client: TestClient, access_token: str, vendor_id: str):
        self.client = client
        self.access_token = access_token
        self.vendor_id = vendor_id
        self.headers = {"Authorization": f"Bearer {access_token}"}

    def get(self, *args, **kwargs):
        """GET request with auth headers."""
        kwargs.setdefault("headers", {}).update(self.headers)
        return self.client.get(*args, **kwargs)

    def post(self, *args, **kwargs):
        """POST request with auth headers."""
        kwargs.setdefault("headers", {}).update(self.headers)
        return self.client.post(*args, **kwargs)

    def put(self, *args, **kwargs):
        """PUT request with auth headers."""
        kwargs.setdefault("headers", {}).update(self.headers)
        return self.client.put(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """DELETE request with auth headers."""
        kwargs.setdefault("headers", {}).update(self.headers)
        return self.client.delete(*args, **kwargs)


@pytest.fixture
def authenticated_client(test_client, db_session) -> AuthenticatedClient:
    """Create an authenticated test client with a test vendor."""
    from uuid import uuid4
    from passlib.context import CryptContext
    from src.models.vendor import Vendor

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    # Create test vendor
    password = "TestPassword123!"
    password_hash = pwd_context.hash(password)
    vendor_id = uuid4()

    vendor = Vendor(
        id=vendor_id,
        email=f"test-{vendor_id}@example.com",
        password_hash=password_hash,
        business_name="Test Business",
        subscription_tier="mvp",
        subscription_status="active",
    )
    db_session.add(vendor)
    db_session.commit()

    # Login to get access token
    login_response = test_client.post(
        "/api/v1/auth/login",
        json={
            "email": vendor.email,
            "password": password,
        },
    )

    if login_response.status_code != 200:
        raise Exception(f"Login failed: {login_response.text}")

    access_token = login_response.json()["access_token"]

    return AuthenticatedClient(test_client, access_token, str(vendor_id))


@pytest.fixture
def mock_square_api(mocker):
    """Mock Square API responses."""
    return mocker.patch("src.adapters.square_adapter.SquareAdapter")


@pytest.fixture
def mock_weather_api(mocker):
    """Mock Weather API responses."""
    return mocker.patch("src.adapters.weather_adapter.WeatherAdapter")


@pytest.fixture
def mock_redis(mocker):
    """Mock Redis client."""
    return mocker.patch("redis.Redis")
