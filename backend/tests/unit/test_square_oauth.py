"""
Unit tests for Square OAuth Service

Tests Square OAuth 2.0 integration:
- Authorization URL generation
- Token exchange (code for tokens)
- Token refresh
- Automatic token refresh on expiry
- Token encryption/decryption
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from src.services.square_oauth import SquareOAuthService, square_oauth_service
from src.models.square_token import SquareToken
from src.models.vendor import Vendor


class TestSquareOAuthServiceInit:
    """Test SquareOAuthService initialization"""

    def test_init_sets_credentials_from_settings(self):
        """Test initialization loads credentials from settings"""
        with patch('src.services.square_oauth.settings') as mock_settings:
            mock_settings.square_application_id = "test-app-id"
            mock_settings.square_application_secret = "test-secret"
            mock_settings.square_oauth_redirect_uri = "https://app.test/callback"

            service = SquareOAuthService()

            assert service.client_id == "test-app-id"
            assert service.client_secret == "test-secret"
            assert service.redirect_uri == "https://app.test/callback"

    def test_required_scopes_defined(self):
        """Test required OAuth scopes are defined"""
        service = SquareOAuthService()

        assert "ITEMS_READ" in service.REQUIRED_SCOPES
        assert "ORDERS_READ" in service.REQUIRED_SCOPES
        assert "PAYMENTS_READ" in service.REQUIRED_SCOPES


class TestGenerateAuthorizationUrl:
    """Test authorization URL generation"""

    def test_generate_url_with_provided_state(self):
        """Test URL generation with provided CSRF state"""
        service = SquareOAuthService()
        state = "custom-csrf-token"

        result = service.generate_authorization_url(state=state)

        assert result["state"] == state
        assert "authorize" in result["url"]
        assert state in result["url"]
        assert service.client_id in result["url"]

    def test_generate_url_without_state_creates_one(self):
        """Test URL generation creates CSRF state if not provided"""
        service = SquareOAuthService()

        result = service.generate_authorization_url()

        assert result["state"] is not None
        assert len(result["state"]) > 20  # Should be a secure random token
        assert result["state"] in result["url"]

    def test_generate_url_includes_required_scopes(self):
        """Test URL includes all required OAuth scopes"""
        service = SquareOAuthService()

        result = service.generate_authorization_url(state="test")

        # Scopes should be space-separated in URL
        assert "ITEMS_READ" in result["url"]
        assert "ORDERS_READ" in result["url"]
        assert "PAYMENTS_READ" in result["url"]

    def test_generate_url_includes_client_id(self):
        """Test URL includes client ID"""
        with patch('src.services.square_oauth.settings') as mock_settings:
            mock_settings.square_application_id = "app-123"
            mock_settings.square_application_secret = "secret"
            mock_settings.square_oauth_redirect_uri = "https://test.com/callback"

            service = SquareOAuthService()
            result = service.generate_authorization_url(state="test")

            assert "app-123" in result["url"]


class TestExchangeCodeForTokens:
    """Test authorization code exchange"""

    @pytest.fixture
    def vendor_id(self):
        return uuid4()

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        return db

    @pytest.fixture
    def service(self):
        return SquareOAuthService()

    @pytest.mark.asyncio
    async def test_exchange_code_success_creates_new_token(self, service, vendor_id, mock_db):
        """Test successful token exchange creates new token"""
        token_response = {
            "access_token": "sq-access-123",
            "refresh_token": "sq-refresh-456",
            "expires_at": "2024-12-31T23:59:59Z",
            "merchant_id": "merchant-789",
        }

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()  # Response is NOT async
            mock_response.status_code = 200
            mock_response.json.return_value = token_response

            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            with patch('src.services.square_oauth.encryption_service') as mock_encryption:
                mock_encryption.encrypt.side_effect = lambda x: f"encrypted_{x}"

                result = await service.exchange_code_for_tokens(
                    authorization_code="auth-code-123",
                    vendor_id=vendor_id,
                    db=mock_db,
                )

                # Should create new token
                mock_db.add.assert_called_once()
                mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_exchange_code_success_updates_existing_token(self, service, vendor_id, mock_db):
        """Test successful token exchange updates existing token"""
        existing_token = MagicMock(spec=SquareToken)
        existing_token.vendor_id = vendor_id

        mock_db.query.return_value.filter.return_value.first.return_value = existing_token

        token_response = {
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "expires_at": "2024-12-31T23:59:59Z",
            "merchant_id": "merchant-123",
        }

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()  # Response is NOT async
            mock_response.status_code = 200
            mock_response.json.return_value = token_response

            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            with patch('src.services.square_oauth.encryption_service') as mock_encryption:
                mock_encryption.encrypt.side_effect = lambda x: f"encrypted_{x}"

                result = await service.exchange_code_for_tokens(
                    authorization_code="auth-code",
                    vendor_id=vendor_id,
                    db=mock_db,
                )

                # Should update existing token
                assert existing_token.is_active is True
                assert existing_token.merchant_id == "merchant-123"
                mock_db.add.assert_not_called()  # Not adding new, updating existing

    @pytest.mark.asyncio
    async def test_exchange_code_updates_vendor_connection_status(self, service, vendor_id, mock_db):
        """Test token exchange updates vendor's square_connected flag"""
        vendor = MagicMock(spec=Vendor)
        vendor.id = vendor_id

        # Mock query to return vendor on second call
        def query_side_effect(model):
            query_mock = MagicMock()
            if model == Vendor:
                query_mock.filter.return_value.first.return_value = vendor
            else:
                query_mock.filter.return_value.first.return_value = None
            return query_mock

        mock_db.query.side_effect = query_side_effect

        token_response = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expires_at": "2024-12-31T23:59:59Z",
            "merchant_id": "merchant-abc",
        }

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()  # Response is NOT async
            mock_response.status_code = 200
            mock_response.json.return_value = token_response

            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            with patch('src.services.square_oauth.encryption_service') as mock_encryption:
                mock_encryption.encrypt.side_effect = lambda x: f"encrypted_{x}"

                await service.exchange_code_for_tokens(
                    authorization_code="code",
                    vendor_id=vendor_id,
                    db=mock_db,
                )

                assert vendor.square_connected is True
                assert vendor.square_merchant_id == "merchant-abc"

    @pytest.mark.asyncio
    async def test_exchange_code_failure_raises_exception(self, service, vendor_id, mock_db):
        """Test failed token exchange raises HTTPException"""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()  # Response is NOT async
            mock_response.status_code = 400
            mock_response.text = "Invalid authorization code"

            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            with pytest.raises(HTTPException) as exc_info:
                await service.exchange_code_for_tokens(
                    authorization_code="invalid-code",
                    vendor_id=vendor_id,
                    db=mock_db,
                )

            assert exc_info.value.status_code == 400
            assert "Failed to exchange code" in str(exc_info.value.detail)


class TestRefreshAccessToken:
    """Test access token refresh"""

    @pytest.fixture
    def vendor_id(self):
        return uuid4()

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.fixture
    def service(self):
        return SquareOAuthService()

    @pytest.mark.asyncio
    async def test_refresh_token_success(self, service, vendor_id, mock_db):
        """Test successful token refresh"""
        existing_token = MagicMock(spec=SquareToken)
        existing_token.refresh_token_encrypted = "encrypted_refresh_token"

        mock_db.query.return_value.filter.return_value.first.return_value = existing_token

        token_response = {
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "expires_at": "2024-12-31T23:59:59Z",
        }

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()  # Response is NOT async
            mock_response.status_code = 200
            mock_response.json.return_value = token_response

            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            with patch('src.services.square_oauth.encryption_service') as mock_encryption:
                mock_encryption.decrypt.return_value = "decrypted_refresh_token"
                mock_encryption.encrypt.side_effect = lambda x: f"encrypted_{x}"

                result = await service.refresh_access_token(vendor_id, mock_db)

                assert result == "new-access-token"
                mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_refresh_token_no_token_found(self, service, vendor_id, mock_db):
        """Test refresh fails when no token exists"""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await service.refresh_access_token(vendor_id, mock_db)

        assert exc_info.value.status_code == 404
        assert "Square token not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_refresh_token_failure_marks_inactive(self, service, vendor_id, mock_db):
        """Test failed refresh marks token as inactive"""
        existing_token = MagicMock(spec=SquareToken)
        existing_token.refresh_token_encrypted = "encrypted_refresh"
        existing_token.is_active = True

        mock_db.query.return_value.filter.return_value.first.return_value = existing_token

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()  # Response is NOT async
            mock_response.status_code = 400
            mock_response.text = "Invalid refresh token"

            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            with patch('src.services.square_oauth.encryption_service') as mock_encryption:
                mock_encryption.decrypt.return_value = "refresh_token"

                with pytest.raises(HTTPException):
                    await service.refresh_access_token(vendor_id, mock_db)

                # Token should be marked inactive
                assert existing_token.is_active is False
                mock_db.commit.assert_called()


class TestGetAccessToken:
    """Test get access token with auto-refresh"""

    @pytest.fixture
    def vendor_id(self):
        return uuid4()

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.fixture
    def service(self):
        return SquareOAuthService()

    def test_get_access_token_valid_token(self, service, vendor_id, mock_db):
        """Test getting valid non-expired token"""
        # Token expires in 2 hours (not expiring soon)
        future_expiry = datetime.utcnow() + timedelta(hours=2)

        existing_token = MagicMock(spec=SquareToken)
        existing_token.expires_at = future_expiry
        existing_token.access_token_encrypted = "encrypted_access_token"
        existing_token.is_active = True

        mock_db.query.return_value.filter.return_value.first.return_value = existing_token

        with patch('src.services.square_oauth.encryption_service') as mock_encryption:
            mock_encryption.decrypt.return_value = "decrypted_access_token"

            result = service.get_access_token(vendor_id, mock_db)

            assert result == "decrypted_access_token"
            mock_encryption.decrypt.assert_called_once_with("encrypted_access_token")

    def test_get_access_token_no_token_raises_exception(self, service, vendor_id, mock_db):
        """Test get token raises exception when no token found"""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            service.get_access_token(vendor_id, mock_db)

        assert exc_info.value.status_code == 404
        assert "Square not connected" in str(exc_info.value.detail)

    def test_get_access_token_expired_refreshes(self, service, vendor_id, mock_db):
        """Test expired token triggers automatic refresh"""
        # Token expired 1 hour ago
        past_expiry = datetime.utcnow() - timedelta(hours=1)

        existing_token = MagicMock(spec=SquareToken)
        existing_token.expires_at = past_expiry
        existing_token.is_active = True

        mock_db.query.return_value.filter.return_value.first.return_value = existing_token

        with patch.object(service, 'refresh_access_token', new=AsyncMock(return_value="refreshed_token")):
            with patch('asyncio.run', return_value="refreshed_token"):
                result = service.get_access_token(vendor_id, mock_db)

                assert result == "refreshed_token"

    def test_get_access_token_expiring_soon_refreshes(self, service, vendor_id, mock_db):
        """Test token expiring within 1 hour triggers refresh"""
        # Token expires in 30 minutes (within 1 hour buffer)
        soon_expiry = datetime.utcnow() + timedelta(minutes=30)

        existing_token = MagicMock(spec=SquareToken)
        existing_token.expires_at = soon_expiry
        existing_token.is_active = True

        mock_db.query.return_value.filter.return_value.first.return_value = existing_token

        with patch.object(service, 'refresh_access_token', new=AsyncMock(return_value="refreshed_token")):
            with patch('asyncio.run', return_value="refreshed_token"):
                result = service.get_access_token(vendor_id, mock_db)

                assert result == "refreshed_token"


class TestGlobalServiceInstance:
    """Test global square_oauth_service instance"""

    def test_global_instance_exists(self):
        """Test global service instance is created"""
        assert square_oauth_service is not None
        assert isinstance(square_oauth_service, SquareOAuthService)
