"""Unit tests for auth router.

Tests authentication API endpoints:
- POST /auth/register - Register new vendor
- POST /auth/login - Authenticate vendor
- POST /auth/refresh - Refresh access token
"""
import pytest
from uuid import uuid4
from unittest.mock import MagicMock, patch

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.routers.auth import (
    register,
    login,
    refresh_access_token,
    RegisterRequest,
)
from src.schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
    RefreshResponse,
)
from src.models.vendor import Vendor


class TestRegister:
    """Test register endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def valid_registration(self):
        """Valid registration data."""
        return RegisterRequest(
            email="vendor@example.com",
            password="SecurePass123",
            business_name="Test Market",
        )

    def test_register_success(self, mock_db, valid_registration):
        """Test successful vendor registration."""
        # Mock no existing vendor
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        # Mock vendor creation
        vendor_id = uuid4()

        def mock_refresh(vendor):
            vendor.id = vendor_id

        mock_db.refresh.side_effect = mock_refresh

        # Mock auth service token generation
        with patch('src.routers.auth.auth_service') as mock_auth:
            mock_auth.generate_access_token.return_value = "access_token_123"
            mock_auth.generate_refresh_token.return_value = "refresh_token_456"

            # Mock password hashing
            with patch('src.routers.auth.pwd_context') as mock_pwd:
                mock_pwd.hash.return_value = "hashed_password"

                result = register(registration=valid_registration, db=mock_db)

                # Verify database operations
                mock_db.add.assert_called_once()
                mock_db.commit.assert_called_once()
                mock_db.refresh.assert_called_once()

                # Verify response
                assert isinstance(result, TokenResponse)
                assert result.access_token == "access_token_123"
                assert result.refresh_token == "refresh_token_456"
                assert result.token_type == "bearer"
                assert result.vendor.email == "vendor@example.com"
                assert result.vendor.business_name == "Test Market"
                assert result.vendor.subscription_tier == "mvp"
                assert result.vendor.subscription_status == "trial"

    def test_register_duplicate_email(self, mock_db, valid_registration):
        """Test registration with duplicate email."""
        # Mock existing vendor
        existing_vendor = MagicMock(spec=Vendor)
        existing_vendor.email = "vendor@example.com"

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = existing_vendor
        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            register(registration=valid_registration, db=mock_db)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "Email already registered" in exc_info.value.detail

    def test_register_weak_password(self, mock_db):
        """Test registration with weak password."""
        weak_registration = RegisterRequest(
            email="vendor@example.com",
            password="short",  # Less than 8 characters
            business_name="Test Market",
        )

        # Mock no existing vendor
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            register(registration=weak_registration, db=mock_db)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "at least 8 characters" in exc_info.value.detail

    def test_register_creates_vendor_with_correct_defaults(self, mock_db, valid_registration):
        """Test vendor is created with correct default values."""
        # Mock no existing vendor
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        # Mock refresh
        def mock_refresh(vendor):
            vendor.id = uuid4()

        mock_db.refresh.side_effect = mock_refresh

        with patch('src.routers.auth.auth_service') as mock_auth:
            mock_auth.generate_access_token.return_value = "token"
            mock_auth.generate_refresh_token.return_value = "refresh"

            with patch('src.routers.auth.pwd_context') as mock_pwd:
                mock_pwd.hash.return_value = "hashed"

                register(registration=valid_registration, db=mock_db)

                # Verify vendor creation
                added_vendor = mock_db.add.call_args[0][0]
                assert isinstance(added_vendor, Vendor)
                assert added_vendor.email == "vendor@example.com"
                assert added_vendor.business_name == "Test Market"
                assert added_vendor.subscription_tier == "mvp"
                assert added_vendor.subscription_status == "trial"


class TestLogin:
    """Test login endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def valid_credentials(self):
        """Valid login credentials."""
        return LoginRequest(
            email="vendor@example.com",
            password="SecurePass123",
        )

    @pytest.fixture
    def existing_vendor(self):
        """Existing vendor in database."""
        vendor = MagicMock(spec=Vendor)
        vendor.id = uuid4()
        vendor.email = "vendor@example.com"
        vendor.password_hash = "hashed_password"
        vendor.business_name = "Test Market"
        vendor.subscription_tier = "pro"
        vendor.subscription_status = "active"
        return vendor

    def test_login_success(self, mock_db, valid_credentials, existing_vendor):
        """Test successful vendor login."""
        # Mock vendor query
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = existing_vendor
        mock_db.query.return_value = mock_query

        # Mock password verification
        with patch('src.routers.auth.pwd_context') as mock_pwd:
            mock_pwd.verify.return_value = True

            # Mock auth service
            with patch('src.routers.auth.auth_service') as mock_auth:
                mock_auth.generate_access_token.return_value = "access_token_789"
                mock_auth.generate_refresh_token.return_value = "refresh_token_012"

                result = login(credentials=valid_credentials, db=mock_db)

                # Verify response
                assert isinstance(result, TokenResponse)
                assert result.access_token == "access_token_789"
                assert result.refresh_token == "refresh_token_012"
                assert result.token_type == "bearer"
                assert result.vendor.email == "vendor@example.com"
                assert result.vendor.business_name == "Test Market"

    def test_login_vendor_not_found(self, mock_db, valid_credentials):
        """Test login with non-existent vendor."""
        # Mock vendor not found
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            login(credentials=valid_credentials, db=mock_db)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Invalid email or password" in exc_info.value.detail

    def test_login_invalid_password(self, mock_db, valid_credentials, existing_vendor):
        """Test login with incorrect password."""
        # Mock vendor query
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = existing_vendor
        mock_db.query.return_value = mock_query

        # Mock password verification - fails
        with patch('src.routers.auth.pwd_context') as mock_pwd:
            mock_pwd.verify.return_value = False

            with pytest.raises(HTTPException) as exc_info:
                login(credentials=valid_credentials, db=mock_db)

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Invalid email or password" in exc_info.value.detail

    def test_login_generates_tokens(self, mock_db, valid_credentials, existing_vendor):
        """Test login generates tokens with correct vendor info."""
        # Mock vendor query
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = existing_vendor
        mock_db.query.return_value = mock_query

        with patch('src.routers.auth.pwd_context') as mock_pwd:
            mock_pwd.verify.return_value = True

            with patch('src.routers.auth.auth_service') as mock_auth:
                mock_auth.generate_access_token.return_value = "access"
                mock_auth.generate_refresh_token.return_value = "refresh"

                login(credentials=valid_credentials, db=mock_db)

                # Verify token generation was called with correct params
                mock_auth.generate_access_token.assert_called_once_with(
                    vendor_id=existing_vendor.id,
                    email=existing_vendor.email,
                )
                mock_auth.generate_refresh_token.assert_called_once_with(
                    vendor_id=existing_vendor.id,
                )


class TestRefreshAccessToken:
    """Test refresh_access_token endpoint."""

    @pytest.fixture
    def valid_refresh_request(self):
        """Valid refresh token request."""
        return RefreshTokenRequest(
            refresh_token="valid_refresh_token",
            email="vendor@example.com",
        )

    def test_refresh_success(self, valid_refresh_request):
        """Test successful token refresh."""
        with patch('src.routers.auth.auth_service') as mock_auth:
            mock_auth.refresh_access_token.return_value = "new_access_token_345"

            result = refresh_access_token(request=valid_refresh_request)

            assert isinstance(result, RefreshResponse)
            assert result.access_token == "new_access_token_345"
            assert result.token_type == "bearer"

            # Verify service was called correctly
            mock_auth.refresh_access_token.assert_called_once_with(
                refresh_token="valid_refresh_token",
                email="vendor@example.com",
            )

    def test_refresh_expired_token(self, valid_refresh_request):
        """Test refresh with expired token."""
        from src.services.auth_service import TokenExpiredError

        with patch('src.routers.auth.auth_service') as mock_auth:
            mock_auth.refresh_access_token.side_effect = TokenExpiredError(
                "Token expired at 2025-01-30"
            )

            with pytest.raises(HTTPException) as exc_info:
                refresh_access_token(request=valid_refresh_request)

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Refresh token expired" in exc_info.value.detail

    def test_refresh_invalid_token(self, valid_refresh_request):
        """Test refresh with invalid token."""
        from src.services.auth_service import InvalidTokenError

        with patch('src.routers.auth.auth_service') as mock_auth:
            mock_auth.refresh_access_token.side_effect = InvalidTokenError(
                "Invalid token signature"
            )

            with pytest.raises(HTTPException) as exc_info:
                refresh_access_token(request=valid_refresh_request)

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Invalid refresh token" in exc_info.value.detail

    def test_refresh_invalid_token_type(self, valid_refresh_request):
        """Test refresh with wrong token type."""
        from src.services.auth_service import InvalidTokenTypeError

        with patch('src.routers.auth.auth_service') as mock_auth:
            mock_auth.refresh_access_token.side_effect = InvalidTokenTypeError(
                "Expected refresh token, got access token"
            )

            with pytest.raises(HTTPException) as exc_info:
                refresh_access_token(request=valid_refresh_request)

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "Invalid refresh token" in exc_info.value.detail
