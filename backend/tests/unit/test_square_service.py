"""Unit tests for Square service.

Tests Square POS integration including:
- OAuth authentication flow
- Token management
- Product/sales import
- Connection status
- Sync scheduling
"""
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4
from unittest.mock import MagicMock, patch, AsyncMock

from src.services.square_service import SquareService
from src.models.square_token import SquareToken


class TestSquareServiceAuthentication:
    """Test Square OAuth authentication."""

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return str(uuid4())

    @pytest.fixture
    def db_session(self):
        """Mock database session."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        return mock_db

    @pytest.fixture
    def square_service(self, db_session):
        """Create Square service instance."""
        with patch('src.services.square_service.SquareOAuthService'):
            service = SquareService(db=db_session)
            service.oauth_service = MagicMock()  # Replace with mock
            return service

    def test_get_authorization_url(self, square_service, vendor_id):
        """Test generation of Square OAuth authorization URL."""
        state = "test_csrf_state"

        with patch.object(square_service.oauth_service, 'get_authorization_url', return_value="https://connect.squareup.com/oauth2/authorize?client_id=test&state=test_csrf_state") as mock_auth:
            url = square_service.get_authorization_url(vendor_id, state)

            assert "squareup.com/oauth2/authorize" in url
            assert state in url
            mock_auth.assert_called_once_with(state)

    @pytest.mark.asyncio
    async def test_handle_oauth_callback_success(self, square_service, vendor_id, db_session):
        """Test successful OAuth callback handling."""
        code = "test_auth_code"
        state = "test_state"

        token_data = {
            "access_token": "sq0atp-test_access_token",
            "refresh_token": "sq0rtp-test_refresh_token",
            "expires_in": 2592000,  # 30 days
            "merchant_id": "TEST_MERCHANT_123",
        }

        # Mock SquareToken to avoid model initialization issues
        with patch.object(square_service.oauth_service, 'exchange_code_for_token', new_callable=AsyncMock, return_value=token_data), \
             patch('src.services.square_service.SquareToken') as MockToken:

            mock_token_instance = MagicMock()
            mock_token_instance.expires_at = datetime.utcnow() + timedelta(seconds=2592000)
            MockToken.return_value = mock_token_instance

            result = await square_service.handle_oauth_callback(vendor_id, code, state)

            assert result["connected"] == True
            assert result["merchant_id"] == "TEST_MERCHANT_123"
            assert "expires_at" in result

            # Verify token was added to database
            db_session.add.assert_called_once()
            db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_revokes_token(self, square_service, vendor_id, db_session):
        """Test disconnecting Square integration revokes token."""
        mock_token = MagicMock(spec=SquareToken)
        mock_token.access_token = "sq0atp-test_token"
        mock_token.vendor_id = vendor_id

        db_session.query.return_value.filter.return_value.first.return_value = mock_token

        with patch.object(square_service.oauth_service, 'revoke_token', new_callable=AsyncMock) as mock_revoke:
            result = await square_service.disconnect(vendor_id)

            assert result == True
            mock_revoke.assert_called_once_with("sq0atp-test_token")
            db_session.delete.assert_called_once_with(mock_token)
            db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_handles_revoke_failure(self, square_service, vendor_id, db_session):
        """Test disconnect continues even if revoke fails."""
        mock_token = MagicMock(spec=SquareToken)
        mock_token.access_token = "sq0atp-test_token"

        db_session.query.return_value.filter.return_value.first.return_value = mock_token

        with patch.object(square_service.oauth_service, 'revoke_token', new_callable=AsyncMock, side_effect=Exception("API error")):
            result = await square_service.disconnect(vendor_id)

            # Should still delete from database
            assert result == True
            db_session.delete.assert_called_once_with(mock_token)

    @pytest.mark.asyncio
    async def test_disconnect_no_token_returns_false(self, square_service, vendor_id, db_session):
        """Test disconnect returns False when no token exists."""
        db_session.query.return_value.filter.return_value.first.return_value = None

        result = await square_service.disconnect(vendor_id)

        assert result == False
        db_session.delete.assert_not_called()


class TestSquareServiceConnectionStatus:
    """Test Square connection status management."""

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return str(uuid4())

    @pytest.fixture
    def db_session(self):
        """Mock database session."""
        return MagicMock()

    @pytest.fixture
    def square_service(self, db_session):
        """Create Square service instance."""
        with patch('src.services.square_service.SquareOAuthService'):
            service = SquareService(db=db_session)
            service.oauth_service = MagicMock()
            return service

    def test_get_connection_status_not_connected(self, square_service, vendor_id, db_session):
        """Test status when Square not connected."""
        db_session.query.return_value.filter.return_value.first.return_value = None

        status = square_service.get_connection_status(vendor_id)

        assert status["connected"] == False
        assert status["needs_reauth"] == False

    def test_get_connection_status_connected_valid(self, square_service, vendor_id, db_session):
        """Test status when Square connected with valid token."""
        mock_token = MagicMock(spec=SquareToken)
        mock_token.merchant_id = "TEST_MERCHANT"
        mock_token.expires_at = datetime.utcnow() + timedelta(days=20)  # Fresh token

        db_session.query.return_value.filter.return_value.first.return_value = mock_token

        status = square_service.get_connection_status(vendor_id)

        assert status["connected"] == True
        assert status["merchant_id"] == "TEST_MERCHANT"
        assert status["is_expired"] == False
        assert status["needs_refresh"] == False
        assert status["needs_reauth"] == False

    def test_get_connection_status_needs_refresh(self, square_service, vendor_id, db_session):
        """Test status when token needs refresh (< 7 days)."""
        mock_token = MagicMock(spec=SquareToken)
        mock_token.merchant_id = "TEST_MERCHANT"
        mock_token.expires_at = datetime.utcnow() + timedelta(days=3)  # Expiring soon

        db_session.query.return_value.filter.return_value.first.return_value = mock_token

        status = square_service.get_connection_status(vendor_id)

        assert status["connected"] == True
        assert status["is_expired"] == False
        assert status["needs_refresh"] == True

    def test_get_connection_status_expired(self, square_service, vendor_id, db_session):
        """Test status when token is expired."""
        mock_token = MagicMock(spec=SquareToken)
        mock_token.merchant_id = "TEST_MERCHANT"
        mock_token.expires_at = datetime.utcnow() - timedelta(days=1)  # Expired

        db_session.query.return_value.filter.return_value.first.return_value = mock_token

        status = square_service.get_connection_status(vendor_id)

        assert status["connected"] == True
        assert status["is_expired"] == True
        assert status["needs_reauth"] == True


class TestSquareServiceTokenRefresh:
    """Test token refresh functionality."""

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return str(uuid4())

    @pytest.fixture
    def db_session(self):
        """Mock database session."""
        return MagicMock()

    @pytest.fixture
    def square_service(self, db_session):
        """Create Square service instance."""
        with patch('src.services.square_service.SquareOAuthService'):
            service = SquareService(db=db_session)
            service.oauth_service = MagicMock()
            return service

    @pytest.mark.asyncio
    async def test_refresh_token_if_needed_no_token(self, square_service, vendor_id, db_session):
        """Test refresh when no token exists."""
        db_session.query.return_value.filter.return_value.first.return_value = None

        result = await square_service.refresh_token_if_needed(vendor_id)

        assert result == False

    @pytest.mark.asyncio
    async def test_refresh_token_if_needed_fresh_token(self, square_service, vendor_id, db_session):
        """Test refresh skipped for fresh token."""
        mock_token = MagicMock(spec=SquareToken)
        mock_token.expires_at = datetime.utcnow() + timedelta(days=20)  # Fresh

        db_session.query.return_value.filter.return_value.first.return_value = mock_token

        result = await square_service.refresh_token_if_needed(vendor_id)

        assert result == False  # No refresh needed

    @pytest.mark.asyncio
    async def test_refresh_token_if_needed_expiring_soon(self, square_service, vendor_id, db_session):
        """Test token refresh when expiring soon."""
        mock_token = MagicMock(spec=SquareToken)
        mock_token.expires_at = datetime.utcnow() + timedelta(days=3)  # < 7 days
        mock_token.refresh_token = "sq0rtp-test_refresh"
        mock_token.access_token = "sq0atp-old_token"

        db_session.query.return_value.filter.return_value.first.return_value = mock_token

        new_token_data = {
            "access_token": "sq0atp-new_token",
            "expires_in": 2592000,
        }

        with patch.object(square_service.oauth_service, 'refresh_access_token', new_callable=AsyncMock, return_value=new_token_data):
            result = await square_service.refresh_token_if_needed(vendor_id)

            assert result == True
            assert mock_token.access_token == "sq0atp-new_token"
            db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_token_handles_failure(self, square_service, vendor_id, db_session):
        """Test refresh handles API failure gracefully."""
        mock_token = MagicMock(spec=SquareToken)
        mock_token.expires_at = datetime.utcnow() + timedelta(days=3)
        mock_token.refresh_token = "sq0rtp-test_refresh"

        db_session.query.return_value.filter.return_value.first.return_value = mock_token

        with patch.object(square_service.oauth_service, 'refresh_access_token', new_callable=AsyncMock, side_effect=Exception("API error")):
            result = await square_service.refresh_token_if_needed(vendor_id)

            assert result == False
            db_session.commit.assert_not_called()


class TestSquareServiceDataImport:
    """Test data import functionality."""

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return str(uuid4())

    @pytest.fixture
    def db_session(self):
        """Mock database session."""
        return MagicMock()

    @pytest.fixture
    def square_service(self, db_session):
        """Create Square service instance."""
        with patch('src.services.square_service.SquareOAuthService'):
            service = SquareService(db=db_session)
            service.oauth_service = MagicMock()
            return service

    @pytest.fixture
    def valid_token(self, vendor_id):
        """Mock valid Square token."""
        token = MagicMock(spec=SquareToken)
        token.vendor_id = vendor_id
        token.expires_at = datetime.utcnow() + timedelta(days=20)
        token.access_token = "sq0atp-valid_token"
        return token

    @pytest.mark.asyncio
    async def test_import_products_success(self, square_service, vendor_id, db_session, valid_token):
        """Test successful product import."""
        db_session.query.return_value.filter.return_value.first.return_value = valid_token

        sync_result = {
            "products_created": 10,
            "products_updated": 5,
            "products_skipped": 2,
        }

        with patch('src.services.square_service.SquareSyncService') as MockSync:
            mock_sync_instance = AsyncMock()
            mock_sync_instance.sync_products = AsyncMock(return_value=sync_result)
            MockSync.return_value = mock_sync_instance

            result = await square_service.import_products(vendor_id)

            assert result["products_created"] == 10
            assert result["products_updated"] == 5
            mock_sync_instance.sync_products.assert_called_once()

    @pytest.mark.asyncio
    async def test_import_products_no_connection(self, square_service, vendor_id, db_session):
        """Test import fails when not connected."""
        db_session.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(ValueError, match="not connected"):
            await square_service.import_products(vendor_id)

    @pytest.mark.asyncio
    async def test_import_products_expired_token(self, square_service, vendor_id, db_session):
        """Test import fails with expired token."""
        expired_token = MagicMock(spec=SquareToken)
        expired_token.expires_at = datetime.utcnow() - timedelta(days=1)

        db_session.query.return_value.filter.return_value.first.return_value = expired_token

        with pytest.raises(ValueError, match="expired"):
            await square_service.import_products(vendor_id)

    @pytest.mark.asyncio
    async def test_import_sales_success(self, square_service, vendor_id, db_session, valid_token):
        """Test successful sales import."""
        db_session.query.return_value.filter.return_value.first.return_value = valid_token

        sync_result = {
            "sales_created": 25,
            "sales_updated": 3,
        }

        with patch('src.services.square_service.SquareSyncService') as MockSync:
            mock_sync_instance = AsyncMock()
            mock_sync_instance.sync_sales = AsyncMock(return_value=sync_result)
            MockSync.return_value = mock_sync_instance

            result = await square_service.import_sales(vendor_id, days_back=30)

            assert result["sales_created"] == 25
            mock_sync_instance.sync_sales.assert_called_once_with(days_back=30)

    @pytest.mark.asyncio
    async def test_full_import_success(self, square_service, vendor_id, db_session, valid_token):
        """Test successful full import (products + sales)."""
        db_session.query.return_value.filter.return_value.first.return_value = valid_token

        sync_result = {
            "products_created": 10,
            "sales_created": 25,
        }

        with patch('src.services.square_service.SquareSyncService') as MockSync:
            mock_sync_instance = AsyncMock()
            mock_sync_instance.full_sync = AsyncMock(return_value=sync_result)
            MockSync.return_value = mock_sync_instance

            result = await square_service.full_import(vendor_id, days_back=30)

            assert result["products_created"] == 10
            assert result["sales_created"] == 25
            mock_sync_instance.full_sync.assert_called_once_with(days_back=30)


class TestSquareServiceSyncManagement:
    """Test sync scheduling and history."""

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return str(uuid4())

    @pytest.fixture
    def db_session(self):
        """Mock database session."""
        return MagicMock()

    @pytest.fixture
    def square_service(self, db_session):
        """Create Square service instance."""
        with patch('src.services.square_service.SquareOAuthService'):
            service = SquareService(db=db_session)
            service.oauth_service = MagicMock()
            return service

    @pytest.mark.asyncio
    async def test_schedule_daily_sync(self, square_service, vendor_id):
        """Test scheduling daily sync."""
        # Mock the tasks module that doesn't exist yet
        with patch.dict('sys.modules', {'src.tasks': MagicMock(), 'src.tasks.square_sync': MagicMock()}):
            result = await square_service.schedule_daily_sync(vendor_id)

            assert result["vendor_id"] == vendor_id
            assert result["sync_frequency"] == "daily"
            assert "next_sync" in result

    def test_get_sync_history(self, square_service, vendor_id, db_session):
        """Test retrieving sync history."""
        # Mock product syncs
        product_sync = MagicMock()
        product_sync.synced_at = datetime(2025, 6, 15, 10, 0)
        product_sync.count = 10

        # Mock sale syncs
        sale_sync = MagicMock()
        sale_sync.synced_at = datetime(2025, 6, 14, 10, 0)
        sale_sync.count = 25

        # Setup query mocks - need different chains for products (1 filter) vs sales (2 filters)
        mock_product_query = MagicMock()
        mock_product_query.all.return_value = [product_sync]

        mock_sale_query = MagicMock()
        mock_sale_query.all.return_value = [sale_sync]

        # Mock the query chains
        # First call (products): query().filter().group_by().order_by().limit().all()
        # Second call (sales): query().filter().filter().group_by().order_by().limit().all()

        call_count = [0]
        def mock_query_side_effect(*args):
            mock_q = MagicMock()
            if call_count[0] == 0:
                # First query (products - single filter)
                mock_q.filter.return_value.group_by.return_value.order_by.return_value.limit.return_value = mock_product_query
            else:
                # Second query (sales - double filter)
                mock_q.filter.return_value.filter.return_value.group_by.return_value.order_by.return_value.limit.return_value = mock_sale_query
            call_count[0] += 1
            return mock_q

        db_session.query.side_effect = mock_query_side_effect

        history = square_service.get_sync_history(vendor_id, limit=10)

        assert len(history) == 2
        assert history[0]["type"] == "products"
        assert history[0]["count"] == 10
        assert history[1]["type"] == "sales"
        assert history[1]["count"] == 25

    def test_validate_connection_valid(self, square_service, vendor_id, db_session):
        """Test connection validation for valid connection."""
        mock_token = MagicMock(spec=SquareToken)
        mock_token.expires_at = datetime.utcnow() + timedelta(days=20)

        db_session.query.return_value.filter.return_value.first.return_value = mock_token

        is_valid = square_service.validate_connection(vendor_id)

        assert is_valid == True

    def test_validate_connection_expired(self, square_service, vendor_id, db_session):
        """Test connection validation for expired token."""
        mock_token = MagicMock(spec=SquareToken)
        mock_token.expires_at = datetime.utcnow() - timedelta(days=1)

        db_session.query.return_value.filter.return_value.first.return_value = mock_token

        is_valid = square_service.validate_connection(vendor_id)

        assert is_valid == False

    def test_validate_connection_not_connected(self, square_service, vendor_id, db_session):
        """Test connection validation when not connected."""
        db_session.query.return_value.filter.return_value.first.return_value = None

        is_valid = square_service.validate_connection(vendor_id)

        assert is_valid == False
