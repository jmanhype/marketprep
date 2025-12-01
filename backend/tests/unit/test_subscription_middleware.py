"""
Unit tests for Subscription Enforcement Middleware

Tests subscription tier limit enforcement:
- Request filtering (POST vs GET, limited vs unlimited endpoints)
- Limit checking (exceeded vs not exceeded)
- Usage tracking and recording
- Billing period calculations
- Free tier defaults
- Helper functions for programmatic access
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import Request
from fastapi.responses import JSONResponse

from src.middleware.subscription import (
    SubscriptionEnforcementMiddleware,
    check_subscription_limit,
    record_usage,
)
from src.models.subscription import Subscription, UsageRecord
from src.models.product import Product
from src.models.venue import Venue
from src.models.recommendation import Recommendation


class TestSubscriptionEnforcementMiddlewareInit:
    """Test middleware initialization"""

    def test_middleware_has_limit_checks_defined(self):
        """Test LIMIT_CHECKS mapping is defined"""
        middleware = SubscriptionEnforcementMiddleware(app=None)

        assert "/api/recommendations" in middleware.LIMIT_CHECKS
        assert middleware.LIMIT_CHECKS["/api/recommendations"] == "recommendations"
        assert "/api/products" in middleware.LIMIT_CHECKS
        assert middleware.LIMIT_CHECKS["/api/products"] == "products"
        assert "/api/venues" in middleware.LIMIT_CHECKS
        assert middleware.LIMIT_CHECKS["/api/venues"] == "venues"


class TestGetLimitType:
    """Test _get_limit_type path matching"""

    def test_get_limit_type_recommendations(self):
        """Test recommendations endpoint is detected"""
        middleware = SubscriptionEnforcementMiddleware(app=None)

        result = middleware._get_limit_type("/api/recommendations")
        assert result == "recommendations"

        result = middleware._get_limit_type("/api/recommendations/123")
        assert result == "recommendations"

    def test_get_limit_type_products(self):
        """Test products endpoint is detected"""
        middleware = SubscriptionEnforcementMiddleware(app=None)

        result = middleware._get_limit_type("/api/products")
        assert result == "products"

        result = middleware._get_limit_type("/api/products/abc")
        assert result == "products"

    def test_get_limit_type_venues(self):
        """Test venues endpoint is detected"""
        middleware = SubscriptionEnforcementMiddleware(app=None)

        result = middleware._get_limit_type("/api/venues")
        assert result == "venues"

        result = middleware._get_limit_type("/api/venues/xyz")
        assert result == "venues"

    def test_get_limit_type_no_match(self):
        """Test non-limited endpoints return None"""
        middleware = SubscriptionEnforcementMiddleware(app=None)

        result = middleware._get_limit_type("/api/auth/login")
        assert result is None

        result = middleware._get_limit_type("/api/health")
        assert result is None


class TestCheckLimit:
    """Test _check_limit subscription checking"""

    @pytest.fixture
    def vendor_id(self):
        return uuid4()

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.fixture
    def middleware(self):
        return SubscriptionEnforcementMiddleware(app=None)

    def test_check_limit_with_active_subscription_not_exceeded(
        self, middleware, vendor_id, mock_db
    ):
        """Test limit check with active subscription under limit"""
        subscription = MagicMock(spec=Subscription)
        subscription.tier = "pro"
        subscription.recommendations_limit = 1000
        subscription.products_limit = 500
        subscription.venues_limit = 50
        subscription.current_period_start = datetime.utcnow()
        subscription.current_period_end = datetime.utcnow() + timedelta(days=30)
        subscription.has_reached_limit = MagicMock(return_value=False)

        mock_db.query.return_value.filter.return_value.first.return_value = subscription

        with patch.object(middleware, '_get_current_usage', return_value=100):
            limit_exceeded, limit_info = middleware._check_limit(
                mock_db, vendor_id, "recommendations"
            )

            assert limit_exceeded is False
            assert limit_info["tier"] == "pro"
            assert limit_info["current"] == 100
            assert limit_info["limit"] == 1000

    def test_check_limit_with_active_subscription_exceeded(
        self, middleware, vendor_id, mock_db
    ):
        """Test limit check with active subscription over limit"""
        subscription = MagicMock(spec=Subscription)
        subscription.tier = "starter"
        subscription.recommendations_limit = 100
        subscription.has_reached_limit = MagicMock(return_value=True)
        subscription.current_period_start = datetime.utcnow()
        subscription.current_period_end = datetime.utcnow() + timedelta(days=30)

        mock_db.query.return_value.filter.return_value.first.return_value = subscription

        with patch.object(middleware, '_get_current_usage', return_value=100):
            limit_exceeded, limit_info = middleware._check_limit(
                mock_db, vendor_id, "recommendations"
            )

            assert limit_exceeded is True
            assert limit_info["current"] == 100
            assert limit_info["limit"] == 100

    def test_check_limit_no_subscription_uses_free_tier(
        self, middleware, vendor_id, mock_db
    ):
        """Test limit check with no subscription defaults to free tier"""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch.object(
            Subscription, 'get_tier_limits', return_value={'recommendations_limit': 10}
        ):
            with patch.object(middleware, '_get_current_usage', return_value=5):
                with patch.object(
                    Subscription, 'has_reached_limit', return_value=False
                ):
                    limit_exceeded, limit_info = middleware._check_limit(
                        mock_db, vendor_id, "recommendations"
                    )

                    assert limit_info["tier"] == "free"


class TestGetCurrentUsage:
    """Test _get_current_usage counting"""

    @pytest.fixture
    def vendor_id(self):
        return uuid4()

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.fixture
    def middleware(self):
        return SubscriptionEnforcementMiddleware(app=None)

    @pytest.fixture
    def subscription_with_period(self):
        subscription = MagicMock(spec=Subscription)
        subscription.current_period_start = datetime(2024, 1, 1)
        subscription.current_period_end = datetime(2024, 2, 1)
        return subscription

    @pytest.fixture
    def subscription_no_period(self):
        subscription = MagicMock(spec=Subscription)
        subscription.current_period_start = None
        subscription.current_period_end = None
        return subscription

    def test_get_current_usage_recommendations_with_period(
        self, middleware, vendor_id, mock_db, subscription_with_period
    ):
        """Test counting recommendations with billing period set"""
        mock_db.query.return_value.filter.return_value.scalar.return_value = 42

        count = middleware._get_current_usage(
            mock_db, vendor_id, "recommendations", subscription_with_period
        )

        assert count == 42
        # Verify filter was called (recommendations use date filtering)
        mock_db.query.return_value.filter.assert_called()

    def test_get_current_usage_products_with_period(
        self, middleware, vendor_id, mock_db, subscription_with_period
    ):
        """Test counting products with billing period set"""
        mock_db.query.return_value.filter.return_value.scalar.return_value = 25

        count = middleware._get_current_usage(
            mock_db, vendor_id, "products", subscription_with_period
        )

        assert count == 25

    def test_get_current_usage_venues_with_period(
        self, middleware, vendor_id, mock_db, subscription_with_period
    ):
        """Test counting venues with billing period set"""
        mock_db.query.return_value.filter.return_value.scalar.return_value = 5

        count = middleware._get_current_usage(
            mock_db, vendor_id, "venues", subscription_with_period
        )

        assert count == 5

    def test_get_current_usage_without_period_uses_current_month(
        self, middleware, vendor_id, mock_db, subscription_no_period
    ):
        """Test usage calculation defaults to current month"""
        mock_db.query.return_value.filter.return_value.scalar.return_value = 10

        with patch('src.middleware.subscription.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value = datetime(2024, 6, 15)

            count = middleware._get_current_usage(
                mock_db, vendor_id, "recommendations", subscription_no_period
            )

            assert count == 10

    def test_get_current_usage_december_month_rollover(
        self, middleware, vendor_id, mock_db, subscription_no_period
    ):
        """Test December to January month rollover"""
        mock_db.query.return_value.filter.return_value.scalar.return_value = 15

        with patch('src.middleware.subscription.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value = datetime(2024, 12, 25)

            count = middleware._get_current_usage(
                mock_db, vendor_id, "recommendations", subscription_no_period
            )

            assert count == 15

    def test_get_current_usage_unknown_limit_type_returns_zero(
        self, middleware, vendor_id, mock_db, subscription_with_period
    ):
        """Test unknown limit type returns 0"""
        count = middleware._get_current_usage(
            mock_db, vendor_id, "unknown_type", subscription_with_period
        )

        assert count == 0

    def test_get_current_usage_null_result_returns_zero(
        self, middleware, vendor_id, mock_db, subscription_with_period
    ):
        """Test null query result returns 0"""
        mock_db.query.return_value.filter.return_value.scalar.return_value = None

        count = middleware._get_current_usage(
            mock_db, vendor_id, "recommendations", subscription_with_period
        )

        assert count == 0


class TestRecordUsage:
    """Test _record_usage tracking"""

    @pytest.fixture
    def vendor_id(self):
        return uuid4()

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        db.rollback = MagicMock()
        return db

    @pytest.fixture
    def middleware(self):
        return SubscriptionEnforcementMiddleware(app=None)

    def test_record_usage_with_active_subscription(
        self, middleware, vendor_id, mock_db
    ):
        """Test usage recording with active subscription"""
        subscription = MagicMock(spec=Subscription)
        subscription.id = uuid4()
        subscription.current_period_start = datetime.utcnow()
        subscription.current_period_end = datetime.utcnow() + timedelta(days=30)

        mock_db.query.return_value.filter.return_value.first.return_value = subscription

        middleware._record_usage(mock_db, vendor_id, "recommendations")

        # Should add usage record and commit
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

        # Verify UsageRecord was created
        added_record = mock_db.add.call_args[0][0]
        assert isinstance(added_record, UsageRecord)
        assert added_record.vendor_id == vendor_id
        assert added_record.subscription_id == subscription.id
        assert added_record.usage_type == "recommendations"
        assert added_record.quantity == 1

    def test_record_usage_no_subscription_returns_early(
        self, middleware, vendor_id, mock_db
    ):
        """Test usage recording with no subscription returns without error"""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # Should not raise exception
        middleware._record_usage(mock_db, vendor_id, "recommendations")

        # Should not add or commit
        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_called()

    def test_record_usage_handles_exceptions(self, middleware, vendor_id, mock_db):
        """Test usage recording handles database exceptions"""
        subscription = MagicMock(spec=Subscription)
        subscription.id = uuid4()
        subscription.current_period_start = datetime.utcnow()
        subscription.current_period_end = datetime.utcnow() + timedelta(days=30)

        mock_db.query.return_value.filter.return_value.first.return_value = subscription
        mock_db.commit.side_effect = Exception("Database error")

        # Should not raise exception
        middleware._record_usage(mock_db, vendor_id, "recommendations")

        # Should call rollback on error
        mock_db.rollback.assert_called_once()


class TestDispatchMethod:
    """Test middleware dispatch method"""

    @pytest.fixture
    def middleware(self):
        return SubscriptionEnforcementMiddleware(app=None)

    @pytest.fixture
    def vendor_id(self):
        return uuid4()

    @pytest.mark.asyncio
    async def test_dispatch_get_request_passes_through(self, middleware):
        """Test GET requests bypass limit checking"""
        request = MagicMock(spec=Request)
        request.method = "GET"
        request.url.path = "/api/recommendations"

        call_next = AsyncMock(return_value=MagicMock())

        response = await middleware.dispatch(request, call_next)

        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_dispatch_post_non_limited_endpoint_passes_through(self, middleware):
        """Test POST to non-limited endpoint bypasses checking"""
        request = MagicMock(spec=Request)
        request.method = "POST"
        request.url.path = "/api/auth/login"

        call_next = AsyncMock(return_value=MagicMock())

        with patch.object(middleware, '_get_limit_type', return_value=None):
            response = await middleware.dispatch(request, call_next)

            call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_dispatch_post_without_vendor_id_passes_through(self, middleware):
        """Test POST without vendor_id bypasses checking (for auth)"""
        request = MagicMock(spec=Request)
        request.method = "POST"
        request.url.path = "/api/recommendations"
        request.state = MagicMock()
        request.state.vendor_id = None

        call_next = AsyncMock(return_value=MagicMock())

        with patch.object(middleware, '_get_limit_type', return_value="recommendations"):
            response = await middleware.dispatch(request, call_next)

            call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_dispatch_limit_exceeded_returns_402(self, middleware, vendor_id):
        """Test POST with limit exceeded returns 402 Payment Required"""
        request = MagicMock(spec=Request)
        request.method = "POST"
        request.url.path = "/api/recommendations"
        request.state = MagicMock()
        request.state.vendor_id = vendor_id

        limit_info = {
            "tier": "free",
            "current": 10,
            "limit": 10,
            "period_start": datetime.utcnow(),
            "period_end": datetime.utcnow() + timedelta(days=30),
        }

        with patch.object(middleware, '_get_limit_type', return_value="recommendations"):
            with patch.object(
                middleware, '_check_limit', return_value=(True, limit_info)
            ):
                with patch('src.middleware.subscription.SessionLocal') as mock_session:
                    mock_db = MagicMock()
                    mock_session.return_value = mock_db

                    response = await middleware.dispatch(request, AsyncMock())

                    assert isinstance(response, JSONResponse)
                    assert response.status_code == 402

                    # Check response content
                    import json
                    content = json.loads(response.body)
                    assert content["error"] == "subscription_limit_exceeded"
                    assert content["limit_type"] == "recommendations"
                    assert content["current_usage"] == 10
                    assert content["limit"] == 10

    @pytest.mark.asyncio
    async def test_dispatch_limit_not_exceeded_continues(self, middleware, vendor_id):
        """Test POST with limit not exceeded continues to handler"""
        request = MagicMock(spec=Request)
        request.method = "POST"
        request.url.path = "/api/recommendations"
        request.state = MagicMock()
        request.state.vendor_id = vendor_id

        limit_info = {
            "tier": "pro",
            "current": 50,
            "limit": 1000,
            "period_start": datetime.utcnow(),
            "period_end": datetime.utcnow() + timedelta(days=30),
        }

        mock_response = MagicMock()
        mock_response.status_code = 200

        call_next = AsyncMock(return_value=mock_response)

        with patch.object(middleware, '_get_limit_type', return_value="recommendations"):
            with patch.object(
                middleware, '_check_limit', return_value=(False, limit_info)
            ):
                with patch('src.middleware.subscription.SessionLocal') as mock_session:
                    mock_db = MagicMock()
                    mock_session.return_value = mock_db

                    response = await middleware.dispatch(request, call_next)

                    call_next.assert_called_once_with(request)
                    assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dispatch_records_usage_on_201_response(self, middleware, vendor_id):
        """Test usage is recorded when resource created (201)"""
        request = MagicMock(spec=Request)
        request.method = "POST"
        request.url.path = "/api/recommendations"
        request.state = MagicMock()
        request.state.vendor_id = vendor_id

        limit_info = {
            "tier": "pro",
            "current": 50,
            "limit": 1000,
            "period_start": datetime.utcnow(),
            "period_end": datetime.utcnow() + timedelta(days=30),
        }

        mock_response = MagicMock()
        mock_response.status_code = 201

        call_next = AsyncMock(return_value=mock_response)

        with patch.object(middleware, '_get_limit_type', return_value="recommendations"):
            with patch.object(
                middleware, '_check_limit', return_value=(False, limit_info)
            ):
                with patch.object(middleware, '_record_usage') as mock_record:
                    with patch(
                        'src.middleware.subscription.SessionLocal'
                    ) as mock_session:
                        mock_db = MagicMock()
                        mock_session.return_value = mock_db

                        response = await middleware.dispatch(request, call_next)

                        # Should record usage
                        mock_record.assert_called_once_with(
                            mock_db, vendor_id, "recommendations"
                        )

    @pytest.mark.asyncio
    async def test_dispatch_exception_fails_open(self, middleware, vendor_id):
        """Test exceptions cause fail-open (don't block requests)"""
        request = MagicMock(spec=Request)
        request.method = "POST"
        request.url.path = "/api/recommendations"
        request.state = MagicMock()
        request.state.vendor_id = vendor_id

        call_next = AsyncMock(return_value=MagicMock(status_code=200))

        with patch.object(middleware, '_get_limit_type', return_value="recommendations"):
            with patch.object(
                middleware, '_check_limit', side_effect=Exception("Database error")
            ):
                with patch('src.middleware.subscription.SessionLocal') as mock_session:
                    mock_db = MagicMock()
                    mock_session.return_value = mock_db

                    # Should not raise exception
                    response = await middleware.dispatch(request, call_next)

                    # Should continue to handler
                    call_next.assert_called_once_with(request)


class TestHelperFunctions:
    """Test helper functions for programmatic access"""

    @pytest.fixture
    def vendor_id(self):
        return uuid4()

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    def test_check_subscription_limit_calls_middleware_method(
        self, vendor_id, mock_db
    ):
        """Test check_subscription_limit helper function"""
        limit_info = {"tier": "pro", "current": 50, "limit": 1000}

        with patch.object(
            SubscriptionEnforcementMiddleware,
            '_check_limit',
            return_value=(False, limit_info),
        ):
            limit_exceeded, info = check_subscription_limit(
                mock_db, vendor_id, "recommendations"
            )

            assert limit_exceeded is False
            assert info["tier"] == "pro"

    def test_record_usage_calls_middleware_method(self, vendor_id, mock_db):
        """Test record_usage helper function"""
        with patch.object(
            SubscriptionEnforcementMiddleware, '_record_usage'
        ) as mock_record:
            record_usage(mock_db, vendor_id, "recommendations")

            mock_record.assert_called_once_with(mock_db, vendor_id, "recommendations")
