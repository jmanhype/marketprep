"""Unit tests for sales router.

Tests sales API endpoints:
- GET /sales - List sales with date filtering
- POST /sales/sync - Sync from Square
- GET /sales/stats - Sales statistics
"""
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4, UUID
from unittest.mock import MagicMock, AsyncMock, patch

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.routers.sales import (
    list_sales,
    sync_sales,
    get_sales_stats,
    SaleResponse,
    SyncResponse,
    SalesStats,
)
from src.models.sale import Sale


class TestListSales:
    """Test list_sales endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    @pytest.fixture
    def sample_sales(self, vendor_id):
        """Sample sales data."""
        sale1 = MagicMock(spec=Sale)
        sale1.id = uuid4()
        sale1.vendor_id = vendor_id
        sale1.sale_date = datetime(2025, 1, 15, 10, 30, 0)
        sale1.total_amount = Decimal("125.50")
        sale1.square_order_id = "order_123"
        sale1.event_name = "Farmers Market"
        sale1.weather_condition = "Sunny"
        sale1.line_items = {"item1": 2, "item2": 3}

        sale2 = MagicMock(spec=Sale)
        sale2.id = uuid4()
        sale2.vendor_id = vendor_id
        sale2.sale_date = datetime(2025, 1, 10, 14, 0, 0)
        sale2.total_amount = Decimal("89.99")
        sale2.square_order_id = "order_456"
        sale2.event_name = None
        sale2.weather_condition = "Cloudy"
        sale2.line_items = None

        sale3 = MagicMock(spec=Sale)
        sale3.id = uuid4()
        sale3.vendor_id = vendor_id
        sale3.sale_date = datetime(2025, 1, 5, 9, 0, 0)
        sale3.total_amount = Decimal("200.00")
        sale3.square_order_id = None
        sale3.event_name = "Street Fair"
        sale3.weather_condition = "Rainy"
        sale3.line_items = {"item3": 5}

        return [sale1, sale2, sale3]

    def test_list_sales_default_period(self, mock_db, vendor_id, sample_sales):
        """Test listing sales with default 30-day period."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.all.return_value = sample_sales

        mock_db.query.return_value = mock_query

        with patch('src.routers.sales.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value = datetime(2025, 1, 20, 12, 0, 0)

            results = list_sales(
                vendor_id=vendor_id,
                db=mock_db,
                days=30,
                limit=100,
                offset=0,
            )

            assert len(results) == 3
            assert results[0].total_amount == 125.50
            assert results[0].event_name == "Farmers Market"

    def test_list_sales_custom_period(self, mock_db, vendor_id, sample_sales):
        """Test listing sales with custom period."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.all.return_value = [sample_sales[0]]

        mock_db.query.return_value = mock_query

        results = list_sales(
            vendor_id=vendor_id,
            db=mock_db,
            days=7,
            limit=100,
            offset=0,
        )

        assert len(results) == 1

    def test_list_sales_with_pagination(self, mock_db, vendor_id, sample_sales):
        """Test sales listing with pagination."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.all.return_value = [sample_sales[1]]

        mock_db.query.return_value = mock_query

        results = list_sales(
            vendor_id=vendor_id,
            db=mock_db,
            days=30,
            limit=1,
            offset=1,
        )

        mock_query.limit.assert_called_with(1)
        mock_query.offset.assert_called_with(1)

    def test_list_sales_response_format(self, mock_db, vendor_id, sample_sales):
        """Test response format matches SaleResponse schema."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.all.return_value = [sample_sales[0]]

        mock_db.query.return_value = mock_query

        results = list_sales(
            vendor_id=vendor_id,
            db=mock_db,
            days=30,
            limit=100,
            offset=0,
        )

        assert isinstance(results[0], SaleResponse)
        assert isinstance(results[0].id, UUID)
        assert results[0].sale_date == "2025-01-15T10:30:00"
        assert results[0].total_amount == 125.50
        assert results[0].square_order_id == "order_123"
        assert results[0].line_items == {"item1": 2, "item2": 3}

    def test_list_sales_handles_null_fields(self, mock_db, vendor_id, sample_sales):
        """Test null optional fields are handled correctly."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.all.return_value = [sample_sales[1]]

        mock_db.query.return_value = mock_query

        results = list_sales(
            vendor_id=vendor_id,
            db=mock_db,
            days=30,
            limit=100,
            offset=0,
        )

        assert results[0].event_name is None
        assert results[0].line_items is None

    def test_list_sales_empty_result(self, mock_db, vendor_id):
        """Test listing sales when no sales exist."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.all.return_value = []

        mock_db.query.return_value = mock_query

        results = list_sales(
            vendor_id=vendor_id,
            db=mock_db,
            days=30,
            limit=100,
            offset=0,
        )

        assert results == []


class TestSyncSales:
    """Test sync_sales endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    @pytest.mark.asyncio
    async def test_sync_sales_success(self, mock_db, vendor_id):
        """Test successful sales sync."""
        with patch('src.routers.sales.SquareSyncService') as mock_sync_class:
            mock_sync = MagicMock()
            mock_sync.sync_sales = AsyncMock(return_value={
                "created": 10,
                "updated": 5,
                "skipped": 2,
                "total": 17,
            })
            mock_sync_class.return_value = mock_sync

            result = await sync_sales(
                vendor_id=vendor_id,
                db=mock_db,
                days_back=30,
            )

            assert isinstance(result, SyncResponse)
            assert result.created == 10
            assert result.updated == 5
            assert result.skipped == 2
            assert result.total == 17

            # Verify service was called with correct days_back
            mock_sync.sync_sales.assert_called_once_with(days_back=30)

    @pytest.mark.asyncio
    async def test_sync_sales_custom_period(self, mock_db, vendor_id):
        """Test sync with custom period."""
        with patch('src.routers.sales.SquareSyncService') as mock_sync_class:
            mock_sync = MagicMock()
            mock_sync.sync_sales = AsyncMock(return_value={
                "created": 3,
                "updated": 1,
                "skipped": 0,
                "total": 4,
            })
            mock_sync_class.return_value = mock_sync

            await sync_sales(
                vendor_id=vendor_id,
                db=mock_db,
                days_back=7,
            )

            mock_sync.sync_sales.assert_called_once_with(days_back=7)

    @pytest.mark.asyncio
    async def test_sync_sales_handles_error(self, mock_db, vendor_id):
        """Test sync error handling."""
        with patch('src.routers.sales.SquareSyncService') as mock_sync_class:
            mock_sync = MagicMock()
            mock_sync.sync_sales = AsyncMock(side_effect=Exception("Square API timeout"))
            mock_sync_class.return_value = mock_sync

            with pytest.raises(HTTPException) as exc_info:
                await sync_sales(vendor_id=vendor_id, db=mock_db, days_back=30)

            assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert "Sync failed" in exc_info.value.detail
            assert "Square API timeout" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_sync_sales_zero_results(self, mock_db, vendor_id):
        """Test sync with no new sales."""
        with patch('src.routers.sales.SquareSyncService') as mock_sync_class:
            mock_sync = MagicMock()
            mock_sync.sync_sales = AsyncMock(return_value={
                "created": 0,
                "updated": 0,
                "skipped": 0,
                "total": 0,
            })
            mock_sync_class.return_value = mock_sync

            result = await sync_sales(vendor_id=vendor_id, db=mock_db, days_back=30)

            assert result.created == 0
            assert result.updated == 0
            assert result.skipped == 0
            assert result.total == 0


class TestGetSalesStats:
    """Test get_sales_stats endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    def test_get_sales_stats_with_data(self, mock_db, vendor_id):
        """Test getting sales statistics."""
        # Mock stats result
        mock_stats = MagicMock()
        mock_stats.total_sales = 25
        mock_stats.total_revenue = Decimal("3250.50")
        mock_stats.average_sale = Decimal("130.02")

        mock_query = MagicMock()
        mock_query.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_stats

        mock_db.query.return_value = mock_query

        with patch('src.routers.sales.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value = datetime(2025, 1, 31, 12, 0, 0)

            result = get_sales_stats(
                vendor_id=vendor_id,
                db=mock_db,
                days=30,
            )

            assert isinstance(result, SalesStats)
            assert result.total_sales == 25
            assert result.total_revenue == 3250.50
            assert result.average_sale == 130.02
            assert "2025-01-01" in result.period_start
            assert "2025-01-31" in result.period_end

    def test_get_sales_stats_no_data(self, mock_db, vendor_id):
        """Test stats when no sales exist."""
        mock_stats = MagicMock()
        mock_stats.total_sales = None
        mock_stats.total_revenue = None
        mock_stats.average_sale = None

        mock_query = MagicMock()
        mock_query.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_stats

        mock_db.query.return_value = mock_query

        result = get_sales_stats(
            vendor_id=vendor_id,
            db=mock_db,
            days=30,
        )

        assert result.total_sales == 0
        assert result.total_revenue == 0.0
        assert result.average_sale == 0.0

    def test_get_sales_stats_custom_period(self, mock_db, vendor_id):
        """Test stats with custom period."""
        mock_stats = MagicMock()
        mock_stats.total_sales = 5
        mock_stats.total_revenue = Decimal("500.00")
        mock_stats.average_sale = Decimal("100.00")

        mock_query = MagicMock()
        mock_query.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_stats

        mock_db.query.return_value = mock_query

        with patch('src.routers.sales.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value = datetime(2025, 1, 14, 12, 0, 0)

            result = get_sales_stats(
                vendor_id=vendor_id,
                db=mock_db,
                days=7,
            )

            assert result.total_sales == 5
            assert "2025-01-07" in result.period_start
            assert "2025-01-14" in result.period_end

    def test_get_sales_stats_response_format(self, mock_db, vendor_id):
        """Test response format matches SalesStats schema."""
        mock_stats = MagicMock()
        mock_stats.total_sales = 10
        mock_stats.total_revenue = Decimal("1000.00")
        mock_stats.average_sale = Decimal("100.00")

        mock_query = MagicMock()
        mock_query.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_stats

        mock_db.query.return_value = mock_query

        result = get_sales_stats(
            vendor_id=vendor_id,
            db=mock_db,
            days=30,
        )

        # Verify all required fields
        assert hasattr(result, 'total_sales')
        assert hasattr(result, 'total_revenue')
        assert hasattr(result, 'average_sale')
        assert hasattr(result, 'period_start')
        assert hasattr(result, 'period_end')
        assert isinstance(result.total_sales, int)
        assert isinstance(result.total_revenue, float)
        assert isinstance(result.average_sale, float)
