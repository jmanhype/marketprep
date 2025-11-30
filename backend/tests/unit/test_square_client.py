"""
Unit tests for Square API client

Tests Square API integration:
- Authentication header generation with token refresh
- Catalog items listing
- Order search with date filters
- Location listing
- Payment listing
- Merchant info retrieval
- Error handling for API failures
"""

import pytest
from datetime import datetime
from uuid import uuid4
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import HTTPException

from src.services.square_client import SquareAPIClient


class TestSquareClientInit:
    """Test Square client initialization"""

    @patch('src.services.square_client.settings')
    def test_init_sandbox_environment(self, mock_settings):
        """Test client initializes with sandbox URL"""
        mock_settings.square_environment = "sandbox"

        vendor_id = uuid4()
        mock_db = MagicMock()

        client = SquareAPIClient(vendor_id=vendor_id, db=mock_db)

        assert client.vendor_id == vendor_id
        assert client.db == mock_db
        assert client.base_url == "https://connect.squareupsandbox.com"
        assert client.api_version == "2024-11-20"

    @patch('src.services.square_client.settings')
    def test_init_production_environment(self, mock_settings):
        """Test client initializes with production URL"""
        mock_settings.square_environment = "production"

        vendor_id = uuid4()
        mock_db = MagicMock()

        client = SquareAPIClient(vendor_id=vendor_id, db=mock_db)

        assert client.base_url == "https://connect.squareup.com"


class TestGetHeaders:
    """Test authorization header generation"""

    @patch('src.services.square_client.square_oauth_service')
    @patch('src.services.square_client.settings')
    def test_get_headers(self, mock_settings, mock_oauth_service):
        """Test headers include access token from OAuth service"""
        mock_settings.square_environment = "sandbox"

        vendor_id = uuid4()
        mock_db = MagicMock()

        # Mock OAuth service to return access token
        mock_oauth_service.get_access_token.return_value = "test_access_token_123"

        client = SquareAPIClient(vendor_id=vendor_id, db=mock_db)
        headers = client._get_headers()

        # Verify OAuth service was called
        mock_oauth_service.get_access_token.assert_called_once_with(
            vendor_id=vendor_id,
            db=mock_db,
        )

        # Verify headers
        assert headers["Authorization"] == "Bearer test_access_token_123"
        assert headers["Content-Type"] == "application/json"
        assert headers["Square-Version"] == "2024-11-20"


class TestListCatalogItems:
    """Test catalog items listing"""

    @pytest.mark.asyncio
    @patch('src.services.square_client.httpx')
    @patch('src.services.square_client.square_oauth_service')
    @patch('src.services.square_client.settings')
    async def test_list_catalog_items_success(self, mock_settings, mock_oauth_service, mock_httpx):
        """Test successful catalog items retrieval"""
        mock_settings.square_environment = "sandbox"
        mock_oauth_service.get_access_token.return_value = "token123"

        # Mock successful API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "objects": [
                {
                    "type": "ITEM",
                    "id": "item_1",
                    "item_data": {"name": "Coffee"},
                },
                {
                    "type": "ITEM",
                    "id": "item_2",
                    "item_data": {"name": "Tea"},
                },
            ]
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        client = SquareAPIClient(vendor_id=uuid4(), db=MagicMock())
        result = await client.list_catalog_items(limit=100)

        # Verify result
        assert len(result["objects"]) == 2
        assert result["objects"][0]["id"] == "item_1"

        # Verify API call
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert "/v2/catalog/list" in call_args[0][0]
        assert call_args[1]["params"]["limit"] == 100

    @pytest.mark.asyncio
    @patch('src.services.square_client.httpx')
    @patch('src.services.square_client.square_oauth_service')
    @patch('src.services.square_client.settings')
    async def test_list_catalog_items_with_types_filter(self, mock_settings, mock_oauth_service, mock_httpx):
        """Test catalog items with type filter"""
        mock_settings.square_environment = "sandbox"
        mock_oauth_service.get_access_token.return_value = "token123"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"objects": []}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        client = SquareAPIClient(vendor_id=uuid4(), db=MagicMock())
        await client.list_catalog_items(limit=50, types=["ITEM", "CATEGORY"])

        # Verify types filter was applied
        call_args = mock_client.get.call_args
        assert call_args[1]["params"]["types"] == "ITEM,CATEGORY"

    @pytest.mark.asyncio
    @patch('src.services.square_client.httpx')
    @patch('src.services.square_client.square_oauth_service')
    @patch('src.services.square_client.settings')
    async def test_list_catalog_items_limits_max(self, mock_settings, mock_oauth_service, mock_httpx):
        """Test catalog items enforces max limit of 1000"""
        mock_settings.square_environment = "sandbox"
        mock_oauth_service.get_access_token.return_value = "token123"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"objects": []}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        client = SquareAPIClient(vendor_id=uuid4(), db=MagicMock())
        await client.list_catalog_items(limit=5000)  # Try to request more than max

        # Verify limit was capped at 1000
        call_args = mock_client.get.call_args
        assert call_args[1]["params"]["limit"] == 1000

    @pytest.mark.asyncio
    @patch('src.services.square_client.httpx')
    @patch('src.services.square_client.square_oauth_service')
    @patch('src.services.square_client.settings')
    async def test_list_catalog_items_api_error(self, mock_settings, mock_oauth_service, mock_httpx):
        """Test catalog items handles API error"""
        mock_settings.square_environment = "sandbox"
        mock_oauth_service.get_access_token.return_value = "token123"

        # Mock API error response
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        client = SquareAPIClient(vendor_id=uuid4(), db=MagicMock())

        # Should raise HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await client.list_catalog_items()

        assert exc_info.value.status_code == 500
        assert "Square API error" in exc_info.value.detail


class TestSearchOrders:
    """Test order search"""

    @pytest.mark.asyncio
    @patch('src.services.square_client.httpx')
    @patch('src.services.square_client.square_oauth_service')
    @patch('src.services.square_client.settings')
    async def test_search_orders_success(self, mock_settings, mock_oauth_service, mock_httpx):
        """Test successful order search"""
        mock_settings.square_environment = "sandbox"
        mock_oauth_service.get_access_token.return_value = "token123"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "orders": [
                {"id": "order_1", "total_money": {"amount": 1500}},
                {"id": "order_2", "total_money": {"amount": 2500}},
            ]
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        client = SquareAPIClient(vendor_id=uuid4(), db=MagicMock())
        result = await client.search_orders(
            location_ids=["loc_1", "loc_2"],
            limit=100,
        )

        # Verify result
        assert len(result["orders"]) == 2

        # Verify API call
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/v2/orders/search" in call_args[0][0]
        assert call_args[1]["json"]["location_ids"] == ["loc_1", "loc_2"]
        assert call_args[1]["json"]["limit"] == 100

    @pytest.mark.asyncio
    @patch('src.services.square_client.httpx')
    @patch('src.services.square_client.square_oauth_service')
    @patch('src.services.square_client.settings')
    async def test_search_orders_with_date_filters(self, mock_settings, mock_oauth_service, mock_httpx):
        """Test order search with date filters"""
        mock_settings.square_environment = "sandbox"
        mock_oauth_service.get_access_token.return_value = "token123"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"orders": []}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        client = SquareAPIClient(vendor_id=uuid4(), db=MagicMock())

        start_date = datetime(2025, 1, 1, 0, 0, 0)
        end_date = datetime(2025, 6, 30, 23, 59, 59)

        await client.search_orders(
            location_ids=["loc_1"],
            start_date=start_date,
            end_date=end_date,
        )

        # Verify date filter in request
        call_args = mock_client.post.call_args
        query = call_args[1]["json"]

        assert "filter" in query
        assert "date_time_filter" in query["filter"]

    @pytest.mark.asyncio
    @patch('src.services.square_client.httpx')
    @patch('src.services.square_client.square_oauth_service')
    @patch('src.services.square_client.settings')
    async def test_search_orders_limits_max(self, mock_settings, mock_oauth_service, mock_httpx):
        """Test order search enforces max limit of 500"""
        mock_settings.square_environment = "sandbox"
        mock_oauth_service.get_access_token.return_value = "token123"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"orders": []}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        client = SquareAPIClient(vendor_id=uuid4(), db=MagicMock())
        await client.search_orders(location_ids=["loc_1"], limit=1000)

        # Verify limit was capped at 500
        call_args = mock_client.post.call_args
        assert call_args[1]["json"]["limit"] == 500

    @pytest.mark.asyncio
    @patch('src.services.square_client.httpx')
    @patch('src.services.square_client.square_oauth_service')
    @patch('src.services.square_client.settings')
    async def test_search_orders_api_error(self, mock_settings, mock_oauth_service, mock_httpx):
        """Test order search handles API error"""
        mock_settings.square_environment = "sandbox"
        mock_oauth_service.get_access_token.return_value = "token123"

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        client = SquareAPIClient(vendor_id=uuid4(), db=MagicMock())

        with pytest.raises(HTTPException) as exc_info:
            await client.search_orders(location_ids=["loc_1"])

        assert exc_info.value.status_code == 500


class TestListLocations:
    """Test location listing"""

    @pytest.mark.asyncio
    @patch('src.services.square_client.httpx')
    @patch('src.services.square_client.square_oauth_service')
    @patch('src.services.square_client.settings')
    async def test_list_locations_success(self, mock_settings, mock_oauth_service, mock_httpx):
        """Test successful location listing"""
        mock_settings.square_environment = "sandbox"
        mock_oauth_service.get_access_token.return_value = "token123"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "locations": [
                {"id": "loc_1", "name": "Main Store"},
                {"id": "loc_2", "name": "Downtown"},
            ]
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        client = SquareAPIClient(vendor_id=uuid4(), db=MagicMock())
        result = await client.list_locations()

        # Verify result
        assert len(result["locations"]) == 2
        assert result["locations"][0]["name"] == "Main Store"

        # Verify API call
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert "/v2/locations" in call_args[0][0]

    @pytest.mark.asyncio
    @patch('src.services.square_client.httpx')
    @patch('src.services.square_client.square_oauth_service')
    @patch('src.services.square_client.settings')
    async def test_list_locations_api_error(self, mock_settings, mock_oauth_service, mock_httpx):
        """Test location listing handles API error"""
        mock_settings.square_environment = "sandbox"
        mock_oauth_service.get_access_token.return_value = "token123"

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        client = SquareAPIClient(vendor_id=uuid4(), db=MagicMock())

        with pytest.raises(HTTPException) as exc_info:
            await client.list_locations()

        assert exc_info.value.status_code == 500


class TestListPayments:
    """Test payment listing"""

    @pytest.mark.asyncio
    @patch('src.services.square_client.httpx')
    @patch('src.services.square_client.square_oauth_service')
    @patch('src.services.square_client.settings')
    async def test_list_payments_success(self, mock_settings, mock_oauth_service, mock_httpx):
        """Test successful payment listing"""
        mock_settings.square_environment = "sandbox"
        mock_oauth_service.get_access_token.return_value = "token123"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "payments": [
                {"id": "pay_1", "amount_money": {"amount": 1000}},
                {"id": "pay_2", "amount_money": {"amount": 2000}},
            ]
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        client = SquareAPIClient(vendor_id=uuid4(), db=MagicMock())
        result = await client.list_payments(location_id="loc_1", limit=100)

        # Verify result
        assert len(result["payments"]) == 2

        # Verify API call
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert "/v2/payments" in call_args[0][0]
        assert call_args[1]["params"]["location_id"] == "loc_1"
        assert call_args[1]["params"]["limit"] == 100

    @pytest.mark.asyncio
    @patch('src.services.square_client.httpx')
    @patch('src.services.square_client.square_oauth_service')
    @patch('src.services.square_client.settings')
    async def test_list_payments_with_date_filters(self, mock_settings, mock_oauth_service, mock_httpx):
        """Test payment listing with date filters"""
        mock_settings.square_environment = "sandbox"
        mock_oauth_service.get_access_token.return_value = "token123"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"payments": []}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        client = SquareAPIClient(vendor_id=uuid4(), db=MagicMock())

        start_date = datetime(2025, 1, 1)
        end_date = datetime(2025, 6, 30)

        await client.list_payments(
            location_id="loc_1",
            start_date=start_date,
            end_date=end_date,
        )

        # Verify date parameters
        call_args = mock_client.get.call_args
        params = call_args[1]["params"]
        assert "begin_time" in params
        assert "end_time" in params
        assert params["begin_time"] == "2025-01-01T00:00:00Z"
        assert params["end_time"] == "2025-06-30T00:00:00Z"

    @pytest.mark.asyncio
    @patch('src.services.square_client.httpx')
    @patch('src.services.square_client.square_oauth_service')
    @patch('src.services.square_client.settings')
    async def test_list_payments_limits_max(self, mock_settings, mock_oauth_service, mock_httpx):
        """Test payment listing enforces max limit of 500"""
        mock_settings.square_environment = "sandbox"
        mock_oauth_service.get_access_token.return_value = "token123"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"payments": []}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        client = SquareAPIClient(vendor_id=uuid4(), db=MagicMock())
        await client.list_payments(location_id="loc_1", limit=2000)

        # Verify limit was capped at 500
        call_args = mock_client.get.call_args
        assert call_args[1]["params"]["limit"] == 500

    @pytest.mark.asyncio
    @patch('src.services.square_client.httpx')
    @patch('src.services.square_client.square_oauth_service')
    @patch('src.services.square_client.settings')
    async def test_list_payments_api_error(self, mock_settings, mock_oauth_service, mock_httpx):
        """Test payment listing handles API error"""
        mock_settings.square_environment = "sandbox"
        mock_oauth_service.get_access_token.return_value = "token123"

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        client = SquareAPIClient(vendor_id=uuid4(), db=MagicMock())

        with pytest.raises(HTTPException) as exc_info:
            await client.list_payments(location_id="loc_1")

        assert exc_info.value.status_code == 500


class TestGetMerchantInfo:
    """Test merchant info retrieval"""

    @pytest.mark.asyncio
    @patch('src.services.square_client.httpx')
    @patch('src.services.square_client.square_oauth_service')
    @patch('src.services.square_client.settings')
    async def test_get_merchant_info_success(self, mock_settings, mock_oauth_service, mock_httpx):
        """Test successful merchant info retrieval"""
        mock_settings.square_environment = "sandbox"
        mock_oauth_service.get_access_token.return_value = "token123"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "merchant": {
                "id": "merchant_123",
                "business_name": "My Business",
                "country": "US",
            }
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        client = SquareAPIClient(vendor_id=uuid4(), db=MagicMock())
        result = await client.get_merchant_info()

        # Verify result
        assert result["merchant"]["business_name"] == "My Business"

        # Verify API call
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert "/v2/merchants" in call_args[0][0]

    @pytest.mark.asyncio
    @patch('src.services.square_client.httpx')
    @patch('src.services.square_client.square_oauth_service')
    @patch('src.services.square_client.settings')
    async def test_get_merchant_info_api_error(self, mock_settings, mock_oauth_service, mock_httpx):
        """Test merchant info handles API error"""
        mock_settings.square_environment = "sandbox"
        mock_oauth_service.get_access_token.return_value = "token123"

        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.text = "Service Unavailable"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        client = SquareAPIClient(vendor_id=uuid4(), db=MagicMock())

        with pytest.raises(HTTPException) as exc_info:
            await client.get_merchant_info()

        assert exc_info.value.status_code == 500
