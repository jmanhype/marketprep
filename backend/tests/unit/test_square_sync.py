"""
Unit tests for Square Sync Service

Tests Square data synchronization:
- Product sync from Square catalog
- Sales sync from Square orders
- Graceful degradation with cached data
- Error handling and recovery
- Full sync operations
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.square_sync import SquareSyncService, SquareAPIError
from src.models.product import Product
from src.models.sale import Sale


class TestSquareSyncServiceInit:
    """Test SquareSyncService initialization"""

    def test_init_creates_square_client(self):
        """Test initialization creates Square API client"""
        vendor_id = uuid4()
        mock_db = MagicMock()

        with patch('src.services.square_sync.SquareAPIClient') as mock_client_class:
            service = SquareSyncService(vendor_id=vendor_id, db=mock_db)

            assert service.vendor_id == vendor_id
            assert service.db == mock_db
            mock_client_class.assert_called_once_with(vendor_id=vendor_id, db=mock_db)


class TestSyncProducts:
    """Test product synchronization"""

    @pytest.fixture
    def vendor_id(self):
        return uuid4()

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        return db

    @pytest.fixture
    def service(self, vendor_id, mock_db):
        with patch('src.services.square_sync.SquareAPIClient'):
            return SquareSyncService(vendor_id=vendor_id, db=mock_db)

    @pytest.mark.asyncio
    async def test_sync_products_success_creates_new(self, service, mock_db):
        """Test successful product sync creates new products"""
        catalog_response = {
            "objects": [
                {
                    "type": "ITEM",
                    "id": "item-123",
                    "item_data": {
                        "name": "Coffee",
                        "variations": [
                            {
                                "id": "var-456",
                                "item_variation_data": {
                                    "name": "Large",
                                    "price_money": {"amount": 550},  # $5.50
                                },
                            }
                        ],
                    },
                }
            ]
        }

        service.square_client.list_catalog_items = AsyncMock(return_value=catalog_response)

        result = await service.sync_products()

        assert result["created"] == 1
        assert result["updated"] == 0
        assert result["skipped"] == 0
        assert result["total"] == 1
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_products_success_updates_existing(self, service, vendor_id, mock_db):
        """Test successful product sync updates existing products"""
        existing_product = MagicMock(spec=Product)
        existing_product.name = "Old Name"
        existing_product.price = Decimal("4.00")

        mock_db.query.return_value.filter.return_value.first.return_value = existing_product

        catalog_response = {
            "objects": [
                {
                    "type": "ITEM",
                    "id": "item-123",
                    "item_data": {
                        "name": "Coffee",
                        "variations": [
                            {
                                "id": "var-456",
                                "item_variation_data": {
                                    "name": "Large",
                                    "price_money": {"amount": 550},
                                },
                            }
                        ],
                    },
                }
            ]
        }

        service.square_client.list_catalog_items = AsyncMock(return_value=catalog_response)

        result = await service.sync_products()

        assert result["created"] == 0
        assert result["updated"] == 1
        assert result["total"] == 1
        assert existing_product.name == "Coffee - Large"
        assert existing_product.price == Decimal("5.50")
        assert existing_product.is_active is True

    @pytest.mark.asyncio
    async def test_sync_products_skips_non_item_types(self, service, mock_db):
        """Test sync skips non-ITEM catalog objects"""
        catalog_response = {
            "objects": [
                {
                    "type": "CATEGORY",  # Not an ITEM
                    "id": "cat-123",
                },
                {
                    "type": "ITEM",
                    "id": "item-456",
                    "item_data": {
                        "name": "Product",
                        "variations": [
                            {
                                "id": "var-789",
                                "item_variation_data": {
                                    "name": "Default",
                                    "price_money": {"amount": 1000},
                                },
                            }
                        ],
                    },
                },
            ]
        }

        service.square_client.list_catalog_items = AsyncMock(return_value=catalog_response)

        result = await service.sync_products()

        # Should only create 1 product (skipping CATEGORY)
        assert result["created"] == 1
        assert mock_db.add.call_count == 1

    @pytest.mark.asyncio
    async def test_sync_products_handles_item_processing_error(self, service, mock_db):
        """Test sync handles errors processing individual items"""
        # Item with missing variations will have empty list, causing no products to be created
        # But won't raise an error - will just skip
        catalog_response = {
            "objects": [
                {
                    "type": "ITEM",
                    "id": "item-no-variations",
                    "item_data": {
                        "name": "Product",
                        "variations": [],  # Empty variations - nothing to create
                    },
                },
                {
                    "type": "ITEM",
                    "id": "item-good",
                    "item_data": {
                        "name": "Product",
                        "variations": [
                            {
                                "id": "var-123",
                                "item_variation_data": {
                                    "name": "Default",
                                    "price_money": {"amount": 500},
                                },
                            }
                        ],
                    },
                },
            ]
        }

        service.square_client.list_catalog_items = AsyncMock(return_value=catalog_response)

        result = await service.sync_products()

        # First item has no variations, second item creates 1 product
        assert result["created"] == 1
        assert result["skipped"] == 0  # No errors, just empty variations

    @pytest.mark.asyncio
    async def test_sync_products_api_error_with_recent_cache(self, service, vendor_id, mock_db):
        """Test API failure falls back to recent cached data"""
        # Simulate API error
        service.square_client.list_catalog_items = AsyncMock(
            side_effect=Exception("API unavailable")
        )

        # Mock recent cache (synced 2 hours ago)
        recent_sync = datetime.utcnow() - timedelta(hours=2)
        mock_db.query.return_value.filter.return_value.scalar.return_value = recent_sync

        result = await service.sync_products()

        assert result["cached"] is True
        assert result["cache_age_hours"] < 24
        assert "error" in result
        assert result["created"] == 0

    @pytest.mark.asyncio
    async def test_sync_products_api_error_without_cache(self, service, mock_db):
        """Test API failure without cache raises SquareAPIError"""
        service.square_client.list_catalog_items = AsyncMock(
            side_effect=Exception("API unavailable")
        )

        # No cache available
        mock_db.query.return_value.filter.return_value.scalar.return_value = None

        with pytest.raises(SquareAPIError, match="Square API unavailable"):
            await service.sync_products()

    @pytest.mark.asyncio
    async def test_sync_products_api_error_with_stale_cache(self, service, mock_db):
        """Test API failure with stale cache (>24h) raises error"""
        service.square_client.list_catalog_items = AsyncMock(
            side_effect=Exception("API unavailable")
        )

        # Mock stale cache (synced 30 hours ago)
        stale_sync = datetime.utcnow() - timedelta(hours=30)
        mock_db.query.return_value.filter.return_value.scalar.return_value = stale_sync

        with pytest.raises(SquareAPIError):
            await service.sync_products()

    @pytest.mark.asyncio
    async def test_sync_products_empty_response(self, service, mock_db):
        """Test sync handles empty catalog response"""
        catalog_response = {"objects": []}

        service.square_client.list_catalog_items = AsyncMock(return_value=catalog_response)

        result = await service.sync_products()

        assert result["created"] == 0
        assert result["updated"] == 0
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_sync_products_multiple_variations(self, service, mock_db):
        """Test sync handles products with multiple variations"""
        catalog_response = {
            "objects": [
                {
                    "type": "ITEM",
                    "id": "item-123",
                    "item_data": {
                        "name": "Coffee",
                        "variations": [
                            {
                                "id": "var-small",
                                "item_variation_data": {
                                    "name": "Small",
                                    "price_money": {"amount": 350},
                                },
                            },
                            {
                                "id": "var-large",
                                "item_variation_data": {
                                    "name": "Large",
                                    "price_money": {"amount": 550},
                                },
                            },
                        ],
                    },
                }
            ]
        }

        service.square_client.list_catalog_items = AsyncMock(return_value=catalog_response)

        result = await service.sync_products()

        # Should create 2 products (one per variation)
        assert result["created"] == 2
        assert mock_db.add.call_count == 2

    @pytest.mark.asyncio
    async def test_sync_products_catches_catalog_item_exception(self, service, mock_db):
        """Test sync catches and logs exceptions during catalog item processing (covers lines 163-166)"""
        catalog_response = {
            "objects": [
                {
                    "type": "ITEM",
                    # Missing "id" field - will raise KeyError on line 109
                    "item_data": {
                        "name": "Malformed Product",
                        "variations": [{"id": "var-123"}],
                    },
                },
                {
                    "type": "ITEM",
                    "id": "item-good",
                    "item_data": {
                        "name": "Good Product",
                        "variations": [
                            {
                                "id": "var-456",
                                "item_variation_data": {
                                    "name": "Default",
                                    "price_money": {"amount": 1000},
                                },
                            }
                        ],
                    },
                },
            ]
        }

        service.square_client.list_catalog_items = AsyncMock(return_value=catalog_response)

        result = await service.sync_products()

        # First item should be skipped due to error, second should be created
        assert result["created"] == 1
        assert result["skipped"] == 1  # Exception caught and item skipped
        assert result["total"] == 1


class TestSyncSales:
    """Test sales synchronization"""

    @pytest.fixture
    def vendor_id(self):
        return uuid4()

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        return db

    @pytest.fixture
    def service(self, vendor_id, mock_db):
        with patch('src.services.square_sync.SquareAPIClient'):
            return SquareSyncService(vendor_id=vendor_id, db=mock_db)

    @pytest.mark.asyncio
    async def test_sync_sales_success(self, service, mock_db):
        """Test successful sales sync"""
        locations_response = {
            "locations": [{"id": "loc-123", "name": "Main Store"}]
        }

        orders_response = {
            "orders": [
                {
                    "id": "order-456",
                    "created_at": "2024-01-15T10:30:00Z",
                    "total_money": {"amount": 2550},  # $25.50
                    "line_items": [
                        {
                            "name": "Coffee - Large",
                            "quantity": "2",
                            "total_money": {"amount": 1100},
                        }
                    ],
                }
            ]
        }

        service.square_client.list_locations = AsyncMock(return_value=locations_response)
        service.square_client.search_orders = AsyncMock(return_value=orders_response)

        result = await service.sync_sales(days_back=30)

        assert result["created"] == 1
        assert result["updated"] == 0
        assert result["skipped"] == 0
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_sales_skips_existing(self, service, vendor_id, mock_db):
        """Test sync skips already-synced sales"""
        existing_sale = MagicMock(spec=Sale)
        mock_db.query.return_value.filter.return_value.first.return_value = existing_sale

        locations_response = {
            "locations": [{"id": "loc-123", "name": "Main Store"}]
        }

        orders_response = {
            "orders": [
                {
                    "id": "order-456",
                    "created_at": "2024-01-15T10:30:00Z",
                    "total_money": {"amount": 1000},
                    "line_items": [],
                }
            ]
        }

        service.square_client.list_locations = AsyncMock(return_value=locations_response)
        service.square_client.search_orders = AsyncMock(return_value=orders_response)

        result = await service.sync_sales()

        assert result["created"] == 0
        assert result["skipped"] == 1
        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_sales_no_locations(self, service, mock_db):
        """Test sync handles no locations"""
        locations_response = {"locations": []}

        service.square_client.list_locations = AsyncMock(return_value=locations_response)

        result = await service.sync_sales()

        assert result["created"] == 0
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_sync_sales_handles_order_processing_error(self, service, mock_db):
        """Test sync handles errors processing individual orders"""
        locations_response = {
            "locations": [{"id": "loc-123"}]
        }

        orders_response = {
            "orders": [
                {
                    "id": "order-bad",
                    # Missing created_at - will cause error
                },
                {
                    "id": "order-good",
                    "created_at": "2024-01-15T10:30:00Z",
                    "total_money": {"amount": 1000},
                    "line_items": [],
                },
            ]
        }

        service.square_client.list_locations = AsyncMock(return_value=locations_response)
        service.square_client.search_orders = AsyncMock(return_value=orders_response)

        result = await service.sync_sales()

        assert result["created"] == 1
        assert result["skipped"] == 1

    @pytest.mark.asyncio
    async def test_sync_sales_handles_location_fetch_error(self, service, mock_db):
        """Test sync continues if one location fails"""
        locations_response = {
            "locations": [
                {"id": "loc-123"},
                {"id": "loc-456"},
            ]
        }

        service.square_client.list_locations = AsyncMock(return_value=locations_response)

        # First location fails, second succeeds
        service.square_client.search_orders = AsyncMock(
            side_effect=[
                Exception("Network error"),
                {"orders": []},
            ]
        )

        result = await service.sync_sales()

        # Should complete despite error on first location
        assert result["created"] == 0
        assert result["skipped"] == 0


class TestFullSync:
    """Test full synchronization"""

    @pytest.fixture
    def vendor_id(self):
        return uuid4()

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.fixture
    def service(self, vendor_id, mock_db):
        with patch('src.services.square_sync.SquareAPIClient'):
            return SquareSyncService(vendor_id=vendor_id, db=mock_db)

    @pytest.mark.asyncio
    async def test_full_sync_success(self, service):
        """Test successful full sync"""
        service.sync_products = AsyncMock(return_value={
            "created": 5,
            "updated": 3,
            "total": 8,
        })

        service.sync_sales = AsyncMock(return_value={
            "created": 10,
            "updated": 0,
            "total": 10,
        })

        result = await service.full_sync(days_back=30)

        assert result["products"]["created"] == 5
        assert result["sales"]["created"] == 10
        assert result["has_errors"] is False
        assert "completed_at" in result

    @pytest.mark.asyncio
    async def test_full_sync_handles_product_sync_error(self, service):
        """Test full sync continues if product sync fails"""
        service.sync_products = AsyncMock(
            side_effect=SquareAPIError("Product sync failed")
        )

        service.sync_sales = AsyncMock(return_value={
            "created": 5,
            "total": 5,
        })

        result = await service.full_sync()

        assert result["products"]["error"] == "Product sync failed"
        assert result["sales"]["created"] == 5
        assert result["has_errors"] is True

    @pytest.mark.asyncio
    async def test_full_sync_handles_sales_sync_error(self, service):
        """Test full sync continues if sales sync fails"""
        service.sync_products = AsyncMock(return_value={
            "created": 3,
            "total": 3,
        })

        service.sync_sales = AsyncMock(
            side_effect=SquareAPIError("Sales sync failed")
        )

        result = await service.full_sync()

        assert result["products"]["created"] == 3
        assert result["sales"]["error"] == "Sales sync failed"
        assert result["has_errors"] is True

    @pytest.mark.asyncio
    async def test_full_sync_handles_both_errors(self, service):
        """Test full sync handles both syncs failing"""
        service.sync_products = AsyncMock(
            side_effect=SquareAPIError("Products failed")
        )

        service.sync_sales = AsyncMock(
            side_effect=SquareAPIError("Sales failed")
        )

        result = await service.full_sync()

        assert result["products"]["error"] == "Products failed"
        assert result["sales"]["error"] == "Sales failed"
        assert result["has_errors"] is True


class TestHelperMethods:
    """Test helper methods"""

    @pytest.fixture
    def vendor_id(self):
        return uuid4()

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.fixture
    def service(self, vendor_id, mock_db):
        with patch('src.services.square_sync.SquareAPIClient'):
            return SquareSyncService(vendor_id=vendor_id, db=mock_db)

    @pytest.mark.asyncio
    async def test_get_last_successful_product_sync(self, service, mock_db):
        """Test getting last successful product sync timestamp"""
        last_sync = datetime.utcnow() - timedelta(hours=5)
        mock_db.query.return_value.filter.return_value.scalar.return_value = last_sync

        result = await service._get_last_successful_product_sync()

        assert result == last_sync

    @pytest.mark.asyncio
    async def test_get_last_successful_product_sync_none(self, service, mock_db):
        """Test getting last sync when no products synced"""
        mock_db.query.return_value.filter.return_value.scalar.return_value = None

        result = await service._get_last_successful_product_sync()

        assert result is None

    @pytest.mark.asyncio
    async def test_get_last_successful_sales_sync(self, service, mock_db):
        """Test getting last successful sales sync timestamp"""
        last_sync = datetime.utcnow() - timedelta(days=1)
        mock_db.query.return_value.filter.return_value.scalar.return_value = last_sync

        result = await service._get_last_successful_sales_sync()

        assert result == last_sync

    @pytest.mark.asyncio
    async def test_get_last_successful_sales_sync_none(self, service, mock_db):
        """Test getting last sales sync when no sales synced"""
        mock_db.query.return_value.filter.return_value.scalar.return_value = None

        result = await service._get_last_successful_sales_sync()

        assert result is None
