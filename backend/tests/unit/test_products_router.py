"""Unit tests for products router.

Tests product API endpoints:
- GET /products - List products with filtering
- POST /products/sync - Sync from Square
- GET /products/{id} - Get product details
"""
import pytest
from datetime import datetime
from decimal import Decimal
from uuid import uuid4, UUID
from unittest.mock import MagicMock, AsyncMock, patch

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.routers.products import (
    list_products,
    sync_products,
    get_product,
    ProductResponse,
    SyncResponse,
)
from src.models.product import Product


class TestListProducts:
    """Test list_products endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    @pytest.fixture
    def sample_products(self, vendor_id):
        """Sample product data."""
        # Create mocks with properly configured attributes
        product_a = MagicMock(spec=Product)
        product_a.id = uuid4()
        product_a.vendor_id = vendor_id
        product_a.name = "Product A"
        product_a.description = "Description A"
        product_a.price = Decimal("10.50")
        product_a.category = "Category1"
        product_a.is_active = True
        product_a.is_seasonal = False
        product_a.square_item_id = "square_123"
        product_a.square_synced_at = datetime(2025, 1, 1, 12, 0, 0)

        product_b = MagicMock(spec=Product)
        product_b.id = uuid4()
        product_b.vendor_id = vendor_id
        product_b.name = "Product B"
        product_b.description = "Description B"
        product_b.price = Decimal("20.00")
        product_b.category = "Category2"
        product_b.is_active = True
        product_b.is_seasonal = True
        product_b.square_item_id = "square_456"
        product_b.square_synced_at = None

        product_c = MagicMock(spec=Product)
        product_c.id = uuid4()
        product_c.vendor_id = vendor_id
        product_c.name = "Product C"
        product_c.description = None
        product_c.price = Decimal("15.75")
        product_c.category = "Category1"
        product_c.is_active = False
        product_c.is_seasonal = False
        product_c.square_item_id = None
        product_c.square_synced_at = None

        return [product_a, product_b, product_c]

    def test_list_all_products(self, mock_db, vendor_id, sample_products):
        """Test listing all products."""
        # Setup mock query chain
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.all.return_value = sample_products[:2]  # Only active products

        mock_db.query.return_value = mock_query

        # Call endpoint
        results = list_products(
            vendor_id=vendor_id,
            db=mock_db,
            category=None,
            active_only=True,
            limit=100,
            offset=0,
        )

        # Verify
        assert len(results) == 2
        assert results[0].name == "Product A"
        assert results[1].name == "Product B"

        # Check database query was called correctly
        mock_db.query.assert_called_once_with(Product)

    def test_list_products_with_category_filter(self, mock_db, vendor_id, sample_products):
        """Test filtering products by category."""
        # Setup mock
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.all.return_value = [sample_products[0]]

        mock_db.query.return_value = mock_query

        # Call with category filter
        results = list_products(
            vendor_id=vendor_id,
            db=mock_db,
            category="Category1",
            active_only=True,
            limit=100,
            offset=0,
        )

        # Verify filtering was applied
        assert len(results) == 1
        assert results[0].category == "Category1"

    def test_list_products_include_inactive(self, mock_db, vendor_id, sample_products):
        """Test listing products including inactive ones."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.all.return_value = sample_products

        mock_db.query.return_value = mock_query

        # Call with active_only=False
        results = list_products(
            vendor_id=vendor_id,
            db=mock_db,
            category=None,
            active_only=False,
            limit=100,
            offset=0,
        )

        # Verify all products returned
        assert len(results) == 3

    def test_list_products_with_pagination(self, mock_db, vendor_id, sample_products):
        """Test product listing with pagination."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.all.return_value = [sample_products[1]]

        mock_db.query.return_value = mock_query

        # Call with pagination
        results = list_products(
            vendor_id=vendor_id,
            db=mock_db,
            category=None,
            active_only=True,
            limit=1,
            offset=1,
        )

        # Verify limit and offset were called
        mock_query.limit.assert_called_with(1)
        mock_query.offset.assert_called_with(1)

    def test_list_products_response_format(self, mock_db, vendor_id, sample_products):
        """Test response format matches ProductResponse schema."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.all.return_value = [sample_products[0]]

        mock_db.query.return_value = mock_query

        results = list_products(
            vendor_id=vendor_id,
            db=mock_db,
            category=None,
            active_only=True,
            limit=100,
            offset=0,
        )

        # Verify response fields
        assert isinstance(results[0], ProductResponse)
        assert isinstance(results[0].id, UUID)
        assert results[0].name == "Product A"
        assert results[0].price == 10.50
        assert results[0].square_synced_at == "2025-01-01T12:00:00"

    def test_list_products_handles_null_square_synced_at(self, mock_db, vendor_id, sample_products):
        """Test null square_synced_at is handled correctly."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.all.return_value = [sample_products[1]]  # Has None square_synced_at

        mock_db.query.return_value = mock_query

        results = list_products(
            vendor_id=vendor_id,
            db=mock_db,
            category=None,
            active_only=True,
            limit=100,
            offset=0,
        )

        assert results[0].square_synced_at is None


class TestSyncProducts:
    """Test sync_products endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    @pytest.mark.asyncio
    async def test_sync_products_success(self, mock_db, vendor_id):
        """Test successful product sync."""
        with patch('src.routers.products.SquareSyncService') as mock_sync_class:
            mock_sync = MagicMock()
            mock_sync.sync_products = AsyncMock(return_value={
                "created": 5,
                "updated": 3,
                "skipped": 2,
                "total": 10,
            })
            mock_sync_class.return_value = mock_sync

            result = await sync_products(vendor_id=vendor_id, db=mock_db)

            assert isinstance(result, SyncResponse)
            assert result.created == 5
            assert result.updated == 3
            assert result.skipped == 2
            assert result.total == 10

            # Verify service was initialized correctly
            mock_sync_class.assert_called_once_with(vendor_id=vendor_id, db=mock_db)

    @pytest.mark.asyncio
    async def test_sync_products_handles_error(self, mock_db, vendor_id):
        """Test sync error handling."""
        with patch('src.routers.products.SquareSyncService') as mock_sync_class:
            mock_sync = MagicMock()
            mock_sync.sync_products = AsyncMock(side_effect=Exception("Square API error"))
            mock_sync_class.return_value = mock_sync

            with pytest.raises(HTTPException) as exc_info:
                await sync_products(vendor_id=vendor_id, db=mock_db)

            assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert "Sync failed" in exc_info.value.detail
            assert "Square API error" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_sync_products_zero_results(self, mock_db, vendor_id):
        """Test sync with zero results."""
        with patch('src.routers.products.SquareSyncService') as mock_sync_class:
            mock_sync = MagicMock()
            mock_sync.sync_products = AsyncMock(return_value={
                "created": 0,
                "updated": 0,
                "skipped": 0,
                "total": 0,
            })
            mock_sync_class.return_value = mock_sync

            result = await sync_products(vendor_id=vendor_id, db=mock_db)

            assert result.created == 0
            assert result.updated == 0
            assert result.skipped == 0
            assert result.total == 0


class TestGetProduct:
    """Test get_product endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    @pytest.fixture
    def product_id(self):
        """Test product ID."""
        return uuid4()

    @pytest.fixture
    def sample_product(self, product_id, vendor_id):
        """Sample product."""
        product = MagicMock(spec=Product)
        product.id = product_id
        product.vendor_id = vendor_id
        product.name = "Test Product"
        product.description = "Test Description"
        product.price = Decimal("25.99")
        product.category = "TestCategory"
        product.is_active = True
        product.is_seasonal = False
        product.square_item_id = "square_789"
        product.square_synced_at = datetime(2025, 1, 15, 10, 30, 0)
        return product

    def test_get_product_success(self, mock_db, vendor_id, product_id, sample_product):
        """Test getting product by ID."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = sample_product

        mock_db.query.return_value = mock_query

        result = get_product(
            product_id=product_id,
            vendor_id=vendor_id,
            db=mock_db,
        )

        assert isinstance(result, ProductResponse)
        assert result.id == product_id
        assert result.name == "Test Product"
        assert result.price == 25.99
        assert result.description == "Test Description"

    def test_get_product_not_found(self, mock_db, vendor_id, product_id):
        """Test getting non-existent product."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            get_product(
                product_id=product_id,
                vendor_id=vendor_id,
                db=mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert exc_info.value.detail == "Product not found"

    def test_get_product_wrong_vendor(self, mock_db, product_id):
        """Test accessing product from wrong vendor."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None  # No match due to vendor filter

        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            get_product(
                product_id=product_id,
                vendor_id=uuid4(),  # Different vendor
                db=mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    def test_get_product_response_format(self, mock_db, vendor_id, product_id, sample_product):
        """Test response format for get_product."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = sample_product

        mock_db.query.return_value = mock_query

        result = get_product(
            product_id=product_id,
            vendor_id=vendor_id,
            db=mock_db,
        )

        # Verify all expected fields
        assert result.id == product_id
        assert result.name == "Test Product"
        assert result.description == "Test Description"
        assert result.price == 25.99
        assert result.category == "TestCategory"
        assert result.is_active is True
        assert result.is_seasonal is False
        assert result.square_item_id == "square_789"
        assert result.square_synced_at == "2025-01-15T10:30:00"

    def test_get_product_with_null_fields(self, mock_db, vendor_id, product_id):
        """Test getting product with null optional fields."""
        product = MagicMock(spec=Product)
        product.id = product_id
        product.vendor_id = vendor_id
        product.name = "Minimal Product"
        product.description = None
        product.price = Decimal("10.00")
        product.category = None
        product.is_active = True
        product.is_seasonal = False
        product.square_item_id = None
        product.square_synced_at = None

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = product

        mock_db.query.return_value = mock_query

        result = get_product(
            product_id=product_id,
            vendor_id=vendor_id,
            db=mock_db,
        )

        assert result.description is None
        assert result.category is None
        assert result.square_item_id is None
        assert result.square_synced_at is None
