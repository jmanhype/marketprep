"""
Unit tests for Subscription Model

Tests subscription model methods:
- is_active() - Check if subscription is active
- is_trialing() - Check if subscription is in trial
- has_reached_limit() - Check if usage limits are reached
- get_tier_limits() - Get limits for subscription tiers
"""

import pytest
from decimal import Decimal

from src.models.subscription import Subscription, SubscriptionTier, SubscriptionStatus


class TestSubscriptionStatus:
    """Test subscription status methods"""

    def test_is_active_when_status_active(self):
        """Test is_active returns True when status is active"""
        subscription = Subscription(
            vendor_id="test-vendor",
            tier="pro",
            status="active"
        )

        assert subscription.is_active() is True

    def test_is_active_when_status_not_active(self):
        """Test is_active returns False when status is not active"""
        subscription = Subscription(
            vendor_id="test-vendor",
            tier="pro",
            status="canceled"
        )

        assert subscription.is_active() is False

    def test_is_trialing_when_status_trialing(self):
        """Test is_trialing returns True when status is trialing"""
        subscription = Subscription(
            vendor_id="test-vendor",
            tier="pro",
            status="trialing"
        )

        assert subscription.is_trialing() is True

    def test_is_trialing_when_status_not_trialing(self):
        """Test is_trialing returns False when status is not trialing"""
        subscription = Subscription(
            vendor_id="test-vendor",
            tier="pro",
            status="active"
        )

        assert subscription.is_trialing() is False


class TestSubscriptionLimits:
    """Test subscription usage limit checking"""

    def test_has_reached_limit_recommendations_below_limit(self):
        """Test has_reached_limit returns False when below limit"""
        subscription = Subscription(
            vendor_id="test-vendor",
            tier="pro",
            status="active",
            recommendations_limit=500
        )

        result = subscription.has_reached_limit("recommendations", 250)

        assert result is False

    def test_has_reached_limit_recommendations_at_limit(self):
        """Test has_reached_limit returns True when at limit"""
        subscription = Subscription(
            vendor_id="test-vendor",
            tier="pro",
            status="active",
            recommendations_limit=500
        )

        result = subscription.has_reached_limit("recommendations", 500)

        assert result is True

    def test_has_reached_limit_recommendations_above_limit(self):
        """Test has_reached_limit returns True when above limit"""
        subscription = Subscription(
            vendor_id="test-vendor",
            tier="pro",
            status="active",
            recommendations_limit=500
        )

        result = subscription.has_reached_limit("recommendations", 600)

        assert result is True

    def test_has_reached_limit_unlimited(self):
        """Test has_reached_limit returns False when limit is None (unlimited)"""
        subscription = Subscription(
            vendor_id="test-vendor",
            tier="enterprise",
            status="active",
            recommendations_limit=None  # Unlimited
        )

        result = subscription.has_reached_limit("recommendations", 10000)

        assert result is False

    def test_has_reached_limit_products(self):
        """Test has_reached_limit works for products limit"""
        subscription = Subscription(
            vendor_id="test-vendor",
            tier="free",
            status="active",
            products_limit=20
        )

        result = subscription.has_reached_limit("products", 20)

        assert result is True

    def test_has_reached_limit_venues(self):
        """Test has_reached_limit works for venues limit"""
        subscription = Subscription(
            vendor_id="test-vendor",
            tier="pro",
            status="active",
            venues_limit=10
        )

        result = subscription.has_reached_limit("venues", 5)

        assert result is False

    def test_has_reached_limit_unknown_type(self):
        """Test has_reached_limit returns False for unknown limit type"""
        subscription = Subscription(
            vendor_id="test-vendor",
            tier="pro",
            status="active",
            recommendations_limit=500
        )

        # Unknown limit type should return False (limit is None)
        result = subscription.has_reached_limit("unknown_type", 100)

        assert result is False


class TestGetTierLimits:
    """Test get_tier_limits static method"""

    def test_get_tier_limits_free(self):
        """Test get_tier_limits returns correct limits for free tier"""
        limits = Subscription.get_tier_limits("free")

        assert limits["recommendations_limit"] == 50
        assert limits["products_limit"] == 20
        assert limits["venues_limit"] == 2
        assert limits["price_monthly"] == Decimal("0.00")
        assert limits["price_yearly"] == Decimal("0.00")

    def test_get_tier_limits_pro(self):
        """Test get_tier_limits returns correct limits for pro tier"""
        limits = Subscription.get_tier_limits("pro")

        assert limits["recommendations_limit"] == 500
        assert limits["products_limit"] == 100
        assert limits["venues_limit"] == 10
        assert limits["price_monthly"] == Decimal("29.00")
        assert limits["price_yearly"] == Decimal("290.00")

    def test_get_tier_limits_enterprise(self):
        """Test get_tier_limits returns correct limits for enterprise tier"""
        limits = Subscription.get_tier_limits("enterprise")

        assert limits["recommendations_limit"] is None  # Unlimited
        assert limits["products_limit"] is None
        assert limits["venues_limit"] is None
        assert limits["price_monthly"] == Decimal("99.00")
        assert limits["price_yearly"] == Decimal("990.00")

    def test_get_tier_limits_unknown_tier_returns_free(self):
        """Test get_tier_limits returns free tier limits for unknown tier"""
        limits = Subscription.get_tier_limits("unknown_tier")

        # Should default to free tier
        assert limits["recommendations_limit"] == 50
        assert limits["products_limit"] == 20
        assert limits["venues_limit"] == 2
