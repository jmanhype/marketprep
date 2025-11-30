"""Unit tests for Square OAuth router.

Tests Square OAuth API endpoints:
- GET /square/connect - Initiate OAuth flow
- POST /square/callback - OAuth callback handler
- GET /square/status - Connection status
- DELETE /square/disconnect - Disconnect Square account
"""
import pytest
from datetime import datetime
from uuid import uuid4
from unittest.mock import MagicMock, AsyncMock, patch

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.routers.square import (
    initiate_oauth_flow,
    handle_oauth_callback,
    get_connection_status,
    disconnect_square,
    ConnectResponse,
    CallbackRequest,
    ConnectionStatus,
)
from src.models.vendor import Vendor
from src.models.square_token import SquareToken


class TestInitiateOAuthFlow:
    """Test initiate_oauth_flow endpoint."""

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    def test_initiate_oauth_flow_success(self, vendor_id):
        """Test successful OAuth flow initiation."""
        with patch('src.routers.square.square_oauth_service') as mock_oauth:
            mock_oauth.generate_authorization_url.return_value = {
                "url": "https://connect.squareup.com/oauth2/authorize?client_id=test&state=abc123",
                "state": "abc123",
            }

            result = initiate_oauth_flow(vendor_id=vendor_id)

            assert isinstance(result, ConnectResponse)
            assert "squareup.com" in result.authorization_url
            assert result.state == "abc123"

            # Verify service was called
            mock_oauth.generate_authorization_url.assert_called_once()

    def test_initiate_oauth_flow_generates_unique_state(self, vendor_id):
        """Test that each OAuth flow gets a unique state token."""
        with patch('src.routers.square.square_oauth_service') as mock_oauth:
            mock_oauth.generate_authorization_url.side_effect = [
                {"url": "https://square.com?state=state1", "state": "state1"},
                {"url": "https://square.com?state=state2", "state": "state2"},
            ]

            result1 = initiate_oauth_flow(vendor_id=vendor_id)
            result2 = initiate_oauth_flow(vendor_id=vendor_id)

            assert result1.state != result2.state


class TestHandleOAuthCallback:
    """Test handle_oauth_callback endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    @pytest.fixture
    def callback_request(self):
        """Test callback request."""
        return CallbackRequest(
            code="auth_code_123",
            state="state_abc123",
        )

    @pytest.mark.asyncio
    async def test_handle_callback_success(self, mock_db, vendor_id, callback_request):
        """Test successful OAuth callback handling."""
        mock_token = MagicMock(spec=SquareToken)
        mock_token.merchant_id = "merchant_123"
        mock_token.created_at = datetime(2025, 1, 15, 12, 0, 0)

        with patch('src.routers.square.square_oauth_service') as mock_oauth:
            mock_oauth.exchange_code_for_tokens = AsyncMock(return_value=mock_token)

            result = await handle_oauth_callback(
                callback=callback_request,
                vendor_id=vendor_id,
                db=mock_db,
            )

            assert result["message"] == "Square connected successfully"
            assert result["merchant_id"] == "merchant_123"
            assert "2025-01-15" in result["connected_at"]

            # Verify service was called with correct params
            mock_oauth.exchange_code_for_tokens.assert_called_once_with(
                authorization_code="auth_code_123",
                vendor_id=vendor_id,
                db=mock_db,
            )

    @pytest.mark.asyncio
    async def test_handle_callback_service_error(self, mock_db, vendor_id, callback_request):
        """Test callback handling with service error."""
        with patch('src.routers.square.square_oauth_service') as mock_oauth:
            mock_oauth.exchange_code_for_tokens = AsyncMock(
                side_effect=Exception("Invalid authorization code")
            )

            with pytest.raises(HTTPException) as exc_info:
                await handle_oauth_callback(
                    callback=callback_request,
                    vendor_id=vendor_id,
                    db=mock_db,
                )

            assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert "Failed to connect Square" in exc_info.value.detail
            assert "Invalid authorization code" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_handle_callback_http_exception_propagated(self, mock_db, vendor_id, callback_request):
        """Test that HTTPException from service is propagated."""
        with patch('src.routers.square.square_oauth_service') as mock_oauth:
            http_exception = HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )
            mock_oauth.exchange_code_for_tokens = AsyncMock(side_effect=http_exception)

            with pytest.raises(HTTPException) as exc_info:
                await handle_oauth_callback(
                    callback=callback_request,
                    vendor_id=vendor_id,
                    db=mock_db,
                )

            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert exc_info.value.detail == "Invalid credentials"


class TestGetConnectionStatus:
    """Test get_connection_status endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    @pytest.fixture
    def existing_vendor(self, vendor_id):
        """Existing vendor."""
        vendor = MagicMock(spec=Vendor)
        vendor.id = vendor_id
        vendor.email = "vendor@example.com"
        return vendor

    @pytest.fixture
    def active_square_token(self, vendor_id):
        """Active Square token."""
        token = MagicMock(spec=SquareToken)
        token.vendor_id = vendor_id
        token.merchant_id = "merchant_456"
        token.is_active = True
        token.scopes = "ITEMS_READ ITEMS_WRITE ORDERS_READ"
        token.created_at = datetime(2025, 1, 10, 9, 0, 0)
        return token

    def test_get_status_connected(self, mock_db, vendor_id, existing_vendor, active_square_token):
        """Test getting status when Square is connected."""
        def query_side_effect(model):
            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            if model == Vendor:
                mock_query.first.return_value = existing_vendor
            elif model == SquareToken:
                mock_query.first.return_value = active_square_token
            return mock_query

        mock_db.query.side_effect = query_side_effect

        result = get_connection_status(vendor_id=vendor_id, db=mock_db)

        assert isinstance(result, ConnectionStatus)
        assert result.is_connected is True
        assert result.merchant_id == "merchant_456"
        assert "2025-01-10" in result.connected_at
        assert result.scopes == ["ITEMS_READ", "ITEMS_WRITE", "ORDERS_READ"]

    def test_get_status_not_connected(self, mock_db, vendor_id, existing_vendor):
        """Test getting status when Square is not connected."""
        def query_side_effect(model):
            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            if model == Vendor:
                mock_query.first.return_value = existing_vendor
            elif model == SquareToken:
                mock_query.first.return_value = None
            return mock_query

        mock_db.query.side_effect = query_side_effect

        result = get_connection_status(vendor_id=vendor_id, db=mock_db)

        assert result.is_connected is False
        assert result.merchant_id is None
        assert result.connected_at is None
        assert result.scopes is None

    def test_get_status_vendor_not_found(self, mock_db, vendor_id):
        """Test getting status when vendor doesn't exist."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            get_connection_status(vendor_id=vendor_id, db=mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "Vendor not found" in exc_info.value.detail

    def test_get_status_no_scopes(self, mock_db, vendor_id, existing_vendor):
        """Test getting status when token has no scopes."""
        token = MagicMock(spec=SquareToken)
        token.vendor_id = vendor_id
        token.merchant_id = "merchant_789"
        token.is_active = True
        token.scopes = None
        token.created_at = datetime(2025, 1, 15, 10, 0, 0)

        def query_side_effect(model):
            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            if model == Vendor:
                mock_query.first.return_value = existing_vendor
            elif model == SquareToken:
                mock_query.first.return_value = token
            return mock_query

        mock_db.query.side_effect = query_side_effect

        result = get_connection_status(vendor_id=vendor_id, db=mock_db)

        assert result.is_connected is True
        assert result.scopes == []


class TestDisconnectSquare:
    """Test disconnect_square endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    @pytest.fixture
    def existing_vendor(self, vendor_id):
        """Existing vendor."""
        vendor = MagicMock(spec=Vendor)
        vendor.id = vendor_id
        vendor.square_connected = True
        vendor.square_merchant_id = "merchant_123"
        return vendor

    @pytest.fixture
    def active_square_token(self, vendor_id):
        """Active Square token."""
        token = MagicMock(spec=SquareToken)
        token.vendor_id = vendor_id
        token.is_active = True
        return token

    def test_disconnect_square_success(self, mock_db, vendor_id, existing_vendor, active_square_token):
        """Test successful Square disconnection."""
        def query_side_effect(model):
            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            if model == Vendor:
                mock_query.first.return_value = existing_vendor
            elif model == SquareToken:
                mock_query.first.return_value = active_square_token
            return mock_query

        mock_db.query.side_effect = query_side_effect

        result = disconnect_square(vendor_id=vendor_id, db=mock_db)

        assert result["message"] == "Square disconnected successfully"

        # Verify token was marked inactive
        assert active_square_token.is_active is False

        # Verify vendor was updated
        assert existing_vendor.square_connected is False
        assert existing_vendor.square_merchant_id is None

        # Verify commit was called
        mock_db.commit.assert_called_once()

    def test_disconnect_square_no_token(self, mock_db, vendor_id, existing_vendor):
        """Test disconnecting when no token exists."""
        def query_side_effect(model):
            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            if model == Vendor:
                mock_query.first.return_value = existing_vendor
            elif model == SquareToken:
                mock_query.first.return_value = None
            return mock_query

        mock_db.query.side_effect = query_side_effect

        result = disconnect_square(vendor_id=vendor_id, db=mock_db)

        assert result["message"] == "Square disconnected successfully"

        # Still updates vendor
        assert existing_vendor.square_connected is False
        mock_db.commit.assert_called_once()

    def test_disconnect_square_no_vendor(self, mock_db, vendor_id, active_square_token):
        """Test disconnecting when vendor doesn't exist."""
        def query_side_effect(model):
            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            if model == Vendor:
                mock_query.first.return_value = None
            elif model == SquareToken:
                mock_query.first.return_value = active_square_token
            return mock_query

        mock_db.query.side_effect = query_side_effect

        result = disconnect_square(vendor_id=vendor_id, db=mock_db)

        # Still succeeds and marks token inactive
        assert result["message"] == "Square disconnected successfully"
        assert active_square_token.is_active is False
        mock_db.commit.assert_called_once()

    def test_disconnect_square_idempotent(self, mock_db, vendor_id, existing_vendor):
        """Test that disconnecting is idempotent."""
        token = MagicMock(spec=SquareToken)
        token.vendor_id = vendor_id
        token.is_active = False  # Already inactive

        def query_side_effect(model):
            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            if model == Vendor:
                mock_query.first.return_value = existing_vendor
            elif model == SquareToken:
                mock_query.first.return_value = token
            return mock_query

        mock_db.query.side_effect = query_side_effect

        result = disconnect_square(vendor_id=vendor_id, db=mock_db)

        assert result["message"] == "Square disconnected successfully"
        assert token.is_active is False  # Still False
        mock_db.commit.assert_called_once()
