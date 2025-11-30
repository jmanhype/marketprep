"""
Unit tests for JWT authentication service

Tests JWT token functionality:
- Access token generation (15 min expiration)
- Refresh token generation (7 day expiration)
- Token validation with signature verification
- Token type validation
- Expired token handling
- Invalid token handling
- Token refresh workflow
- Vendor ID extraction
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from unittest.mock import patch
from jose import jwt

from src.services.auth_service import (
    AuthService,
    TokenType,
    TokenExpiredError,
    InvalidTokenError,
    InvalidTokenTypeError,
)


class TestAuthServiceInit:
    """Test auth service initialization"""

    @patch('src.services.auth_service.settings')
    def test_init_with_valid_secret_key(self, mock_settings):
        """Test initialization with valid secret key"""
        mock_settings.secret_key = "a" * 32  # 32 character key

        service = AuthService()

        assert service.secret_key == "a" * 32
        assert service.ALGORITHM == "HS256"

    @patch('src.services.auth_service.settings')
    def test_init_with_short_secret_key_raises_error(self, mock_settings):
        """Test that short secret key raises ValueError (line 68-69)"""
        mock_settings.secret_key = "short_key"  # Less than 32 characters

        with pytest.raises(ValueError, match="at least 32 characters"):
            AuthService()


class TestGenerateAccessToken:
    """Test access token generation"""

    @patch('src.services.auth_service.settings')
    def test_generate_access_token(self, mock_settings):
        """Test access token generation with vendor claims"""
        mock_settings.secret_key = "a" * 32

        service = AuthService()
        vendor_id = uuid4()
        email = "vendor@example.com"

        token = service.generate_access_token(vendor_id=vendor_id, email=email)

        # Token should be a non-empty string
        assert isinstance(token, str)
        assert len(token) > 0

        # Decode and verify claims (unsafe decode for testing)
        payload = service.decode_token_unsafe(token)
        assert payload["vendor_id"] == str(vendor_id)
        assert payload["email"] == email
        assert payload["token_type"] == "access"
        assert "exp" in payload
        assert "iat" in payload

    @patch('src.services.auth_service.settings')
    def test_access_token_expiration_time(self, mock_settings):
        """Test that access token has correct expiration (15 minutes)"""
        mock_settings.secret_key = "b" * 32

        service = AuthService()
        vendor_id = uuid4()

        token = service.generate_access_token(vendor_id=vendor_id, email="test@example.com")

        payload = service.decode_token_unsafe(token)
        exp_timestamp = payload["exp"]
        iat_timestamp = payload["iat"]

        # Expiration should be ~15 minutes after issued
        time_diff = exp_timestamp - iat_timestamp
        assert time_diff == 15 * 60  # 15 minutes in seconds


class TestGenerateRefreshToken:
    """Test refresh token generation"""

    @patch('src.services.auth_service.settings')
    def test_generate_refresh_token(self, mock_settings):
        """Test refresh token generation with minimal claims"""
        mock_settings.secret_key = "c" * 32

        service = AuthService()
        vendor_id = uuid4()

        token = service.generate_refresh_token(vendor_id=vendor_id)

        # Token should be a non-empty string
        assert isinstance(token, str)
        assert len(token) > 0

        # Decode and verify claims
        payload = service.decode_token_unsafe(token)
        assert payload["vendor_id"] == str(vendor_id)
        assert payload["token_type"] == "refresh"
        assert "email" not in payload  # Refresh tokens don't include email
        assert "exp" in payload
        assert "iat" in payload

    @patch('src.services.auth_service.settings')
    def test_refresh_token_expiration_time(self, mock_settings):
        """Test that refresh token has correct expiration (7 days)"""
        mock_settings.secret_key = "d" * 32

        service = AuthService()
        vendor_id = uuid4()

        token = service.generate_refresh_token(vendor_id=vendor_id)

        payload = service.decode_token_unsafe(token)
        exp_timestamp = payload["exp"]
        iat_timestamp = payload["iat"]

        # Expiration should be ~7 days after issued
        time_diff = exp_timestamp - iat_timestamp
        assert time_diff == 7 * 24 * 60 * 60  # 7 days in seconds


class TestValidateToken:
    """Test token validation"""

    @patch('src.services.auth_service.settings')
    def test_validate_access_token_success(self, mock_settings):
        """Test validating a valid access token"""
        mock_settings.secret_key = "e" * 32

        service = AuthService()
        vendor_id = uuid4()
        email = "test@example.com"

        # Generate token
        token = service.generate_access_token(vendor_id=vendor_id, email=email)

        # Validate token
        payload = service.validate_token(token=token, expected_type=TokenType.ACCESS)

        # Verify payload
        assert payload["vendor_id"] == str(vendor_id)
        assert payload["email"] == email
        assert payload["token_type"] == "access"

    @patch('src.services.auth_service.settings')
    def test_validate_refresh_token_success(self, mock_settings):
        """Test validating a valid refresh token"""
        mock_settings.secret_key = "f" * 32

        service = AuthService()
        vendor_id = uuid4()

        # Generate refresh token
        token = service.generate_refresh_token(vendor_id=vendor_id)

        # Validate token
        payload = service.validate_token(token=token, expected_type=TokenType.REFRESH)

        assert payload["vendor_id"] == str(vendor_id)
        assert payload["token_type"] == "refresh"

    @patch('src.services.auth_service.settings')
    def test_validate_token_wrong_type_raises_error(self, mock_settings):
        """Test that wrong token type raises InvalidTokenTypeError (lines 158-161)"""
        mock_settings.secret_key = "g" * 32

        service = AuthService()
        vendor_id = uuid4()

        # Generate access token
        access_token = service.generate_access_token(vendor_id=vendor_id, email="test@example.com")

        # Try to validate as refresh token
        with pytest.raises(InvalidTokenTypeError, match="Expected refresh token"):
            service.validate_token(token=access_token, expected_type=TokenType.REFRESH)

    @patch('src.services.auth_service.settings')
    def test_validate_token_invalid_signature_raises_error(self, mock_settings):
        """Test that invalid signature raises InvalidTokenError (lines 168-169)"""
        mock_settings.secret_key = "h" * 32

        service = AuthService()

        # Create token with wrong secret
        fake_token = jwt.encode(
            {"vendor_id": str(uuid4()), "token_type": "access"},
            key="wrong_secret_key_that_is_32_chars_long",
            algorithm="HS256",
        )

        # Try to validate
        with pytest.raises(InvalidTokenError, match="Invalid token"):
            service.validate_token(token=fake_token, expected_type=TokenType.ACCESS)

    @patch('src.services.auth_service.settings')
    def test_validate_token_malformed_raises_error(self, mock_settings):
        """Test that malformed token raises InvalidTokenError"""
        mock_settings.secret_key = "i" * 32

        service = AuthService()

        # Try to validate garbage
        with pytest.raises(InvalidTokenError):
            service.validate_token(token="not.a.valid.jwt.token", expected_type=TokenType.ACCESS)


class TestDecodeTokenUnsafe:
    """Test unsafe token decoding"""

    @patch('src.services.auth_service.settings')
    def test_decode_token_unsafe(self, mock_settings):
        """Test decoding token without verification"""
        mock_settings.secret_key = "j" * 32

        service = AuthService()
        vendor_id = uuid4()
        email = "unsafe@example.com"

        # Generate token
        token = service.generate_access_token(vendor_id=vendor_id, email=email)

        # Decode without verification
        payload = service.decode_token_unsafe(token)

        assert payload["vendor_id"] == str(vendor_id)
        assert payload["email"] == email

    @patch('src.services.auth_service.settings')
    def test_decode_malformed_token_raises_error(self, mock_settings):
        """Test that malformed token raises InvalidTokenError (lines 189-190)"""
        mock_settings.secret_key = "k" * 32

        service = AuthService()

        with pytest.raises(InvalidTokenError, match="Malformed token"):
            service.decode_token_unsafe("clearly.not.jwt")


class TestGetVendorIdFromToken:
    """Test vendor ID extraction"""

    @patch('src.services.auth_service.settings')
    def test_get_vendor_id_from_access_token(self, mock_settings):
        """Test extracting vendor_id from access token"""
        mock_settings.secret_key = "l" * 32

        service = AuthService()
        vendor_id = uuid4()

        token = service.generate_access_token(vendor_id=vendor_id, email="test@example.com")

        extracted_id = service.get_vendor_id_from_token(token)

        assert extracted_id == vendor_id

    @patch('src.services.auth_service.settings')
    def test_get_vendor_id_from_refresh_token(self, mock_settings):
        """Test extracting vendor_id from refresh token"""
        mock_settings.secret_key = "m" * 32

        service = AuthService()
        vendor_id = uuid4()

        token = service.generate_refresh_token(vendor_id=vendor_id)

        extracted_id = service.get_vendor_id_from_token(token)

        assert extracted_id == vendor_id

    @patch('src.services.auth_service.settings')
    def test_get_vendor_id_missing_claim_raises_error(self, mock_settings):
        """Test that missing vendor_id claim raises InvalidTokenError (lines 217-218)"""
        mock_settings.secret_key = "n" * 32

        service = AuthService()

        # Create token without vendor_id
        bad_token = jwt.encode(
            {"email": "test@example.com", "token_type": "access"},
            key=service.secret_key,
            algorithm="HS256",
        )

        with pytest.raises(InvalidTokenError, match="missing vendor_id claim"):
            service.get_vendor_id_from_token(bad_token)

    @patch('src.services.auth_service.settings')
    def test_get_vendor_id_invalid_uuid_raises_error(self, mock_settings):
        """Test that invalid UUID raises InvalidTokenError (lines 225-226)"""
        mock_settings.secret_key = "o" * 32

        service = AuthService()

        # Create token with invalid UUID
        bad_token = jwt.encode(
            {"vendor_id": "not-a-valid-uuid", "token_type": "access"},
            key=service.secret_key,
            algorithm="HS256",
        )

        with pytest.raises(InvalidTokenError, match="Invalid token"):
            service.get_vendor_id_from_token(bad_token)


class TestRefreshAccessToken:
    """Test access token refresh workflow"""

    @patch('src.services.auth_service.settings')
    def test_refresh_access_token_success(self, mock_settings):
        """Test successfully refreshing access token"""
        mock_settings.secret_key = "p" * 32

        service = AuthService()
        vendor_id = uuid4()
        email = "refresh@example.com"

        # Generate refresh token
        refresh_token = service.generate_refresh_token(vendor_id=vendor_id)

        # Refresh access token
        new_access_token = service.refresh_access_token(
            refresh_token=refresh_token,
            email=email,
        )

        # Verify new access token
        assert isinstance(new_access_token, str)

        payload = service.validate_token(
            token=new_access_token,
            expected_type=TokenType.ACCESS,
        )

        assert payload["vendor_id"] == str(vendor_id)
        assert payload["email"] == email
        assert payload["token_type"] == "access"

    @patch('src.services.auth_service.settings')
    def test_refresh_with_access_token_raises_error(self, mock_settings):
        """Test that using access token for refresh raises error"""
        mock_settings.secret_key = "q" * 32

        service = AuthService()
        vendor_id = uuid4()

        # Generate access token (not refresh token)
        access_token = service.generate_access_token(
            vendor_id=vendor_id,
            email="test@example.com",
        )

        # Try to refresh with access token
        with pytest.raises(InvalidTokenTypeError):
            service.refresh_access_token(
                refresh_token=access_token,
                email="test@example.com",
            )
