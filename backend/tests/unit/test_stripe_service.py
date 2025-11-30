"""Unit tests for Stripe service.

Tests MUST fail before implementation (TDD).
"""
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

import stripe

from src.services.stripe_service import StripeService
from src.models.subscription import (
    Subscription,
    Invoice,
    PaymentMethod,
    UsageRecord,
)


@pytest.fixture
def mock_db():
    """Mock database session."""
    db = MagicMock()
    db.query = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock()
    return db


@pytest.fixture
def stripe_service(mock_db):
    """Create StripeService instance with mocked database."""
    return StripeService(db=mock_db)


@pytest.fixture
def vendor_id():
    """Generate vendor ID."""
    return str(uuid4())


@pytest.fixture
def subscription_id():
    """Generate subscription ID."""
    return str(uuid4())


class TestCreateCustomer:
    """Test Stripe customer creation."""

    @pytest.mark.asyncio
    async def test_create_customer_success(self, stripe_service, vendor_id):
        """Test successful customer creation."""
        email = "vendor@example.com"
        name = "Test Vendor"

        mock_customer = MagicMock()
        mock_customer.id = "cus_test123"

        with patch('stripe.Customer.create', return_value=mock_customer) as mock_create:
            customer_id = await stripe_service.create_customer(
                vendor_id=vendor_id,
                email=email,
                name=name,
            )

            assert customer_id == "cus_test123"
            mock_create.assert_called_once_with(
                email=email,
                name=name,
                metadata={'vendor_id': vendor_id},
            )

    @pytest.mark.asyncio
    async def test_create_customer_with_metadata(self, stripe_service, vendor_id):
        """Test customer creation with additional metadata."""
        email = "vendor@example.com"
        name = "Test Vendor"
        metadata = {'business_type': 'farmers_market', 'region': 'northeast'}

        mock_customer = MagicMock()
        mock_customer.id = "cus_test456"

        with patch('stripe.Customer.create', return_value=mock_customer) as mock_create:
            customer_id = await stripe_service.create_customer(
                vendor_id=vendor_id,
                email=email,
                name=name,
                metadata=metadata,
            )

            assert customer_id == "cus_test456"
            # Should merge vendor_id into metadata
            expected_metadata = {'business_type': 'farmers_market', 'region': 'northeast', 'vendor_id': vendor_id}
            mock_create.assert_called_once_with(
                email=email,
                name=name,
                metadata=expected_metadata,
            )

    @pytest.mark.asyncio
    async def test_create_customer_stripe_error(self, stripe_service, vendor_id):
        """Test customer creation with Stripe error."""
        with patch('stripe.Customer.create', side_effect=stripe.error.InvalidRequestError(
            message="Invalid email",
            param="email",
        )):
            with pytest.raises(stripe.error.InvalidRequestError):
                await stripe_service.create_customer(
                    vendor_id=vendor_id,
                    email="invalid_email",
                    name="Test Vendor",
                )


class TestCreateSubscription:
    """Test subscription creation."""

    @pytest.mark.asyncio
    async def test_create_subscription_success(self, stripe_service, mock_db, vendor_id):
        """Test successful subscription creation."""
        customer_id = "cus_test123"
        price_id = "price_pro_monthly"

        # Mock Stripe subscription
        mock_stripe_sub = MagicMock()
        mock_stripe_sub.id = "sub_test123"
        mock_stripe_sub.status = "active"
        mock_stripe_sub.current_period_start = int(datetime(2025, 1, 1).timestamp())
        mock_stripe_sub.current_period_end = int(datetime(2025, 2, 1).timestamp())
        mock_stripe_sub.trial_start = None
        mock_stripe_sub.trial_end = None

        # Mock database operations
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        mock_db.refresh = MagicMock()

        with patch('stripe.Subscription.create', return_value=mock_stripe_sub):
            subscription = await stripe_service.create_subscription(
                vendor_id=vendor_id,
                stripe_customer_id=customer_id,
                price_id=price_id,
            )

            # Verify subscription object created
            assert mock_db.add.called
            assert mock_db.commit.called

            # Verify Stripe API called correctly
            stripe.Subscription.create.assert_called_once_with(
                customer=customer_id,
                items=[{'price': price_id}],
                expand=['latest_invoice.payment_intent'],
            )

    @pytest.mark.asyncio
    async def test_create_subscription_with_trial(self, stripe_service, mock_db, vendor_id):
        """Test subscription creation with trial period."""
        customer_id = "cus_test123"
        price_id = "price_pro_monthly"
        trial_days = 14

        # Mock Stripe subscription with trial
        mock_stripe_sub = MagicMock()
        mock_stripe_sub.id = "sub_test456"
        mock_stripe_sub.status = "trialing"
        mock_stripe_sub.current_period_start = int(datetime(2025, 1, 1).timestamp())
        mock_stripe_sub.current_period_end = int(datetime(2025, 2, 1).timestamp())
        mock_stripe_sub.trial_start = int(datetime(2025, 1, 1).timestamp())
        mock_stripe_sub.trial_end = int(datetime(2025, 1, 15).timestamp())

        with patch('stripe.Subscription.create', return_value=mock_stripe_sub) as mock_create:
            subscription = await stripe_service.create_subscription(
                vendor_id=vendor_id,
                stripe_customer_id=customer_id,
                price_id=price_id,
                trial_days=trial_days,
            )

            # Verify trial_period_days passed to Stripe
            call_args = mock_create.call_args[1]
            assert call_args['trial_period_days'] == trial_days

    @pytest.mark.asyncio
    async def test_create_subscription_tier_mapping(self, stripe_service, mock_db, vendor_id):
        """Test subscription tier is correctly mapped from price_id."""
        customer_id = "cus_test123"

        # Mock Stripe subscription
        mock_stripe_sub = MagicMock()
        mock_stripe_sub.id = "sub_test789"
        mock_stripe_sub.status = "active"
        mock_stripe_sub.current_period_start = int(datetime(2025, 1, 1).timestamp())
        mock_stripe_sub.current_period_end = int(datetime(2025, 2, 1).timestamp())
        mock_stripe_sub.trial_start = None
        mock_stripe_sub.trial_end = None

        # Store the created subscription
        created_subscription = None
        def capture_subscription(sub):
            nonlocal created_subscription
            created_subscription = sub

        mock_db.add.side_effect = capture_subscription

        with patch('stripe.Subscription.create', return_value=mock_stripe_sub):
            # Test pro tier
            await stripe_service.create_subscription(
                vendor_id=vendor_id,
                stripe_customer_id=customer_id,
                price_id='price_pro_monthly',
            )

            assert created_subscription.tier == 'pro'
            assert created_subscription.recommendations_limit == 500
            assert created_subscription.products_limit == 100

    @pytest.mark.asyncio
    async def test_create_subscription_stripe_error(self, stripe_service, vendor_id):
        """Test subscription creation with Stripe error."""
        with patch('stripe.Subscription.create', side_effect=stripe.error.CardError(
            message="Card declined",
            param="card",
            code="card_declined",
        )):
            with pytest.raises(stripe.error.CardError):
                await stripe_service.create_subscription(
                    vendor_id=vendor_id,
                    stripe_customer_id="cus_test123",
                    price_id="price_pro_monthly",
                )


class TestCancelSubscription:
    """Test subscription cancellation."""

    @pytest.mark.asyncio
    async def test_cancel_subscription_at_period_end(self, stripe_service, mock_db, subscription_id):
        """Test canceling subscription at end of billing period."""
        # Mock existing subscription
        mock_subscription = MagicMock()
        mock_subscription.id = subscription_id
        mock_subscription.stripe_subscription_id = "sub_test123"

        mock_db.query.return_value.filter.return_value.first.return_value = mock_subscription

        # Mock Stripe modification
        mock_stripe_sub = MagicMock()

        with patch('stripe.Subscription.modify', return_value=mock_stripe_sub):
            result = await stripe_service.cancel_subscription(
                subscription_id=subscription_id,
                cancel_at_period_end=True,
            )

            # Verify subscription updated
            assert mock_subscription.cancel_at_period_end is True
            assert mock_db.commit.called

            # Verify Stripe API called
            stripe.Subscription.modify.assert_called_once_with(
                "sub_test123",
                cancel_at_period_end=True,
            )

    @pytest.mark.asyncio
    async def test_cancel_subscription_immediately(self, stripe_service, mock_db, subscription_id):
        """Test canceling subscription immediately."""
        # Mock existing subscription
        mock_subscription = MagicMock()
        mock_subscription.id = subscription_id
        mock_subscription.stripe_subscription_id = "sub_test456"

        mock_db.query.return_value.filter.return_value.first.return_value = mock_subscription

        # Mock Stripe deletion
        mock_stripe_sub = MagicMock()

        with patch('stripe.Subscription.delete', return_value=mock_stripe_sub):
            result = await stripe_service.cancel_subscription(
                subscription_id=subscription_id,
                cancel_at_period_end=False,
            )

            # Verify subscription canceled immediately
            assert mock_subscription.status == "canceled"
            assert mock_subscription.canceled_at is not None
            assert mock_db.commit.called

            # Verify Stripe API called
            stripe.Subscription.delete.assert_called_once_with("sub_test456")

    @pytest.mark.asyncio
    async def test_cancel_subscription_not_found(self, stripe_service, mock_db, subscription_id):
        """Test canceling non-existent subscription."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(ValueError) as exc_info:
            await stripe_service.cancel_subscription(subscription_id=subscription_id)

        assert "not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_cancel_subscription_stripe_error(self, stripe_service, mock_db, subscription_id):
        """Test subscription cancellation with Stripe error."""
        # Mock existing subscription
        mock_subscription = MagicMock()
        mock_subscription.id = subscription_id
        mock_subscription.stripe_subscription_id = "sub_test789"

        mock_db.query.return_value.filter.return_value.first.return_value = mock_subscription

        with patch('stripe.Subscription.modify', side_effect=stripe.error.InvalidRequestError(
            message="Subscription already canceled",
            param="subscription",
        )):
            with pytest.raises(stripe.error.InvalidRequestError):
                await stripe_service.cancel_subscription(subscription_id=subscription_id)


class TestAddPaymentMethod:
    """Test adding payment methods."""

    @pytest.mark.asyncio
    async def test_add_card_payment_method(self, stripe_service, mock_db, vendor_id):
        """Test adding card payment method."""
        customer_id = "cus_test123"
        payment_method_id = "pm_test123"

        # Mock Stripe payment method
        mock_pm = MagicMock()
        mock_pm.type = "card"
        mock_pm.card.brand = "visa"
        mock_pm.card.last4 = "4242"
        mock_pm.card.exp_month = 12
        mock_pm.card.exp_year = 2025

        # Mock database query for existing default payment methods
        mock_db.query.return_value.filter.return_value.update.return_value = None

        with patch('stripe.PaymentMethod.attach') as mock_attach, \
             patch('stripe.PaymentMethod.retrieve', return_value=mock_pm), \
             patch('stripe.Customer.modify') as mock_customer_modify:

            payment_method = await stripe_service.add_payment_method(
                vendor_id=vendor_id,
                stripe_customer_id=customer_id,
                stripe_payment_method_id=payment_method_id,
                set_as_default=True,
            )

            # Verify Stripe API calls
            mock_attach.assert_called_once_with(
                payment_method_id,
                customer=customer_id,
            )

            # Verify set as default in Stripe
            mock_customer_modify.assert_called_once_with(
                customer_id,
                invoice_settings={'default_payment_method': payment_method_id},
            )

            # Verify database operations
            assert mock_db.add.called
            assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_add_payment_method_not_default(self, stripe_service, mock_db, vendor_id):
        """Test adding payment method without setting as default."""
        customer_id = "cus_test123"
        payment_method_id = "pm_test456"

        # Mock Stripe payment method
        mock_pm = MagicMock()
        mock_pm.type = "card"
        mock_pm.card.brand = "mastercard"
        mock_pm.card.last4 = "5555"
        mock_pm.card.exp_month = 6
        mock_pm.card.exp_year = 2026

        # Store the created payment method
        created_pm = None
        def capture_pm(pm):
            nonlocal created_pm
            created_pm = pm

        mock_db.add.side_effect = capture_pm

        with patch('stripe.PaymentMethod.attach'), \
             patch('stripe.PaymentMethod.retrieve', return_value=mock_pm), \
             patch('stripe.Customer.modify') as mock_customer_modify:

            payment_method = await stripe_service.add_payment_method(
                vendor_id=vendor_id,
                stripe_customer_id=customer_id,
                stripe_payment_method_id=payment_method_id,
                set_as_default=False,
            )

            # Should NOT set as default in Stripe
            mock_customer_modify.assert_not_called()

            # Verify is_default is False
            assert created_pm.is_default is False

    @pytest.mark.asyncio
    async def test_add_payment_method_updates_existing_default(self, stripe_service, mock_db, vendor_id):
        """Test adding payment method updates existing default."""
        customer_id = "cus_test123"
        payment_method_id = "pm_new_default"

        # Mock Stripe payment method
        mock_pm = MagicMock()
        mock_pm.type = "card"
        mock_pm.card.brand = "amex"
        mock_pm.card.last4 = "0005"
        mock_pm.card.exp_month = 3
        mock_pm.card.exp_year = 2027

        # Mock database query for updating existing defaults
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_query.filter.return_value = mock_filter
        mock_db.query.return_value = mock_query

        with patch('stripe.PaymentMethod.attach'), \
             patch('stripe.PaymentMethod.retrieve', return_value=mock_pm), \
             patch('stripe.Customer.modify'):

            await stripe_service.add_payment_method(
                vendor_id=vendor_id,
                stripe_customer_id=customer_id,
                stripe_payment_method_id=payment_method_id,
                set_as_default=True,
            )

            # Verify existing defaults were updated
            mock_filter.update.assert_called_once_with({'is_default': False})

    @pytest.mark.asyncio
    async def test_add_payment_method_stripe_error(self, stripe_service, vendor_id):
        """Test adding payment method with Stripe error."""
        with patch('stripe.PaymentMethod.attach', side_effect=stripe.error.InvalidRequestError(
            message="Payment method already attached",
            param="payment_method",
        )):
            with pytest.raises(stripe.error.InvalidRequestError):
                await stripe_service.add_payment_method(
                    vendor_id=vendor_id,
                    stripe_customer_id="cus_test123",
                    stripe_payment_method_id="pm_test123",
                )


class TestCreateInvoice:
    """Test invoice creation."""

    @pytest.mark.asyncio
    async def test_create_invoice_success(self, stripe_service, mock_db, vendor_id, subscription_id):
        """Test successful invoice creation."""
        # Mock subscription
        mock_subscription = MagicMock()
        mock_subscription.id = subscription_id
        mock_subscription.vendor_id = vendor_id

        mock_db.query.return_value.filter.return_value.first.return_value = mock_subscription

        # Mock Stripe invoice
        mock_stripe_invoice = MagicMock()
        mock_stripe_invoice.id = "in_test123"
        mock_stripe_invoice.payment_intent = "pi_test123"
        mock_stripe_invoice.number = "INV-2025-001"
        mock_stripe_invoice.amount_due = 2900  # $29.00 in cents
        mock_stripe_invoice.amount_paid = 2900
        mock_stripe_invoice.currency = "usd"
        mock_stripe_invoice.status = "paid"
        mock_stripe_invoice.paid = True
        mock_stripe_invoice.created = int(datetime(2025, 1, 1).timestamp())
        mock_stripe_invoice.due_date = int(datetime(2025, 1, 15).timestamp())
        mock_stripe_invoice.status_transitions.paid_at = int(datetime(2025, 1, 5).timestamp())
        mock_stripe_invoice.period_start = int(datetime(2025, 1, 1).timestamp())
        mock_stripe_invoice.period_end = int(datetime(2025, 2, 1).timestamp())
        mock_stripe_invoice.invoice_pdf = "https://stripe.com/invoice.pdf"
        mock_stripe_invoice.hosted_invoice_url = "https://stripe.com/invoice"

        invoice = await stripe_service.create_invoice(
            subscription_id=subscription_id,
            stripe_invoice=mock_stripe_invoice,
        )

        # Verify database operations
        assert mock_db.add.called
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_create_invoice_subscription_not_found(self, stripe_service, mock_db, subscription_id):
        """Test invoice creation with non-existent subscription."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        mock_stripe_invoice = MagicMock()

        with pytest.raises(ValueError) as exc_info:
            await stripe_service.create_invoice(
                subscription_id=subscription_id,
                stripe_invoice=mock_stripe_invoice,
            )

        assert "not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_create_invoice_amounts_converted_from_cents(self, stripe_service, mock_db, vendor_id, subscription_id):
        """Test invoice amounts are correctly converted from cents to dollars."""
        # Mock subscription
        mock_subscription = MagicMock()
        mock_subscription.id = subscription_id
        mock_subscription.vendor_id = vendor_id

        mock_db.query.return_value.filter.return_value.first.return_value = mock_subscription

        # Mock Stripe invoice with amounts in cents
        mock_stripe_invoice = MagicMock()
        mock_stripe_invoice.id = "in_test456"
        mock_stripe_invoice.payment_intent = None
        mock_stripe_invoice.number = "INV-2025-002"
        mock_stripe_invoice.amount_due = 9900  # $99.00 in cents
        mock_stripe_invoice.amount_paid = 0    # Not paid yet
        mock_stripe_invoice.currency = "usd"
        mock_stripe_invoice.status = "open"
        mock_stripe_invoice.paid = False
        mock_stripe_invoice.created = int(datetime(2025, 1, 1).timestamp())
        mock_stripe_invoice.due_date = None
        mock_stripe_invoice.status_transitions.paid_at = None
        mock_stripe_invoice.period_start = int(datetime(2025, 1, 1).timestamp())
        mock_stripe_invoice.period_end = int(datetime(2025, 2, 1).timestamp())
        mock_stripe_invoice.invoice_pdf = None
        mock_stripe_invoice.hosted_invoice_url = "https://stripe.com/invoice2"

        # Capture created invoice
        created_invoice = None
        def capture_invoice(inv):
            nonlocal created_invoice
            created_invoice = inv

        mock_db.add.side_effect = capture_invoice

        await stripe_service.create_invoice(
            subscription_id=subscription_id,
            stripe_invoice=mock_stripe_invoice,
        )

        # Verify amounts converted to dollars
        assert created_invoice.amount_due == Decimal("99.00")
        assert created_invoice.amount_paid == Decimal("0.00")


class TestRecordUsage:
    """Test usage recording."""

    @pytest.mark.asyncio
    async def test_record_usage_success(self, stripe_service, mock_db, vendor_id, subscription_id):
        """Test successful usage recording."""
        # Mock subscription
        mock_subscription = MagicMock()
        mock_subscription.id = subscription_id
        mock_subscription.vendor_id = vendor_id
        mock_subscription.current_period_start = datetime(2025, 1, 1)
        mock_subscription.current_period_end = datetime(2025, 2, 1)

        mock_db.query.return_value.filter.return_value.first.return_value = mock_subscription

        usage_record = await stripe_service.record_usage(
            subscription_id=subscription_id,
            usage_type="recommendations",
            quantity=5,
        )

        # Verify database operations
        assert mock_db.add.called
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_record_usage_default_quantity(self, stripe_service, mock_db, vendor_id, subscription_id):
        """Test usage recording with default quantity."""
        # Mock subscription
        mock_subscription = MagicMock()
        mock_subscription.id = subscription_id
        mock_subscription.vendor_id = vendor_id
        mock_subscription.current_period_start = datetime(2025, 1, 1)
        mock_subscription.current_period_end = datetime(2025, 2, 1)

        mock_db.query.return_value.filter.return_value.first.return_value = mock_subscription

        # Capture created usage record
        created_usage = None
        def capture_usage(usage):
            nonlocal created_usage
            created_usage = usage

        mock_db.add.side_effect = capture_usage

        await stripe_service.record_usage(
            subscription_id=subscription_id,
            usage_type="api_calls",
        )

        # Default quantity should be 1
        assert created_usage.quantity == 1
        assert created_usage.usage_type == "api_calls"

    @pytest.mark.asyncio
    async def test_record_usage_subscription_not_found(self, stripe_service, mock_db, subscription_id):
        """Test usage recording with non-existent subscription."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(ValueError) as exc_info:
            await stripe_service.record_usage(
                subscription_id=subscription_id,
                usage_type="recommendations",
            )

        assert "not found" in str(exc_info.value).lower()


class TestGetUsageSummary:
    """Test usage summary retrieval."""

    @pytest.mark.asyncio
    async def test_get_usage_summary_all_types(self, stripe_service, mock_db, vendor_id, subscription_id):
        """Test getting usage summary for all types."""
        # Mock subscription
        mock_subscription = MagicMock()
        mock_subscription.id = subscription_id
        mock_subscription.vendor_id = vendor_id
        mock_subscription.current_period_start = datetime(2025, 1, 1)

        # Mock usage records
        mock_records = [
            MagicMock(usage_type="recommendations", quantity=10),
            MagicMock(usage_type="recommendations", quantity=5),
            MagicMock(usage_type="products", quantity=3),
            MagicMock(usage_type="api_calls", quantity=100),
            MagicMock(usage_type="api_calls", quantity=50),
        ]

        # Setup query mocks - need separate mocks for Subscription and UsageRecord queries
        # First query: Subscription lookup
        subscription_query = MagicMock()
        subscription_query.first.return_value = mock_subscription

        # Second query: UsageRecord lookup with ONE .filter(arg1, arg2) call then .all()
        usage_query = MagicMock()
        usage_query.all.return_value = mock_records

        # Mock db.query to return different results for Subscription vs UsageRecord
        def query_side_effect(model):
            if model.__name__ == 'Subscription':
                return MagicMock(filter=MagicMock(return_value=subscription_query))
            else:  # UsageRecord
                return MagicMock(filter=MagicMock(return_value=usage_query))

        mock_db.query.side_effect = query_side_effect

        summary = await stripe_service.get_usage_summary(subscription_id=subscription_id)

        # Verify summary aggregation
        assert summary["recommendations"] == 15  # 10 + 5
        assert summary["products"] == 3
        assert summary["api_calls"] == 150  # 100 + 50

    @pytest.mark.asyncio
    async def test_get_usage_summary_filtered_by_type(self, stripe_service, mock_db, vendor_id, subscription_id):
        """Test getting usage summary filtered by type."""
        # Mock subscription
        mock_subscription = MagicMock()
        mock_subscription.id = subscription_id
        mock_subscription.vendor_id = vendor_id
        mock_subscription.current_period_start = datetime(2025, 1, 1)

        # Mock usage records (only recommendations)
        mock_records = [
            MagicMock(usage_type="recommendations", quantity=10),
            MagicMock(usage_type="recommendations", quantity=5),
        ]

        # Setup query mocks - need separate mocks for Subscription and UsageRecord queries
        # First query: Subscription lookup
        subscription_query = MagicMock()
        subscription_query.first.return_value = mock_subscription

        # Second query: UsageRecord with ONE .filter(arg1, arg2) call, then another .filter(usage_type), then .all()
        usage_query = MagicMock()
        usage_query.all.return_value = mock_records
        usage_filter1 = MagicMock()
        usage_filter1.filter.return_value = usage_query  # Second filter for usage_type

        # Mock db.query to return different results for Subscription vs UsageRecord
        def query_side_effect(model):
            if model.__name__ == 'Subscription':
                return MagicMock(filter=MagicMock(return_value=subscription_query))
            else:  # UsageRecord
                return MagicMock(filter=MagicMock(return_value=usage_filter1))

        mock_db.query.side_effect = query_side_effect

        summary = await stripe_service.get_usage_summary(
            subscription_id=subscription_id,
            usage_type="recommendations",
        )

        # Verify only recommendations in summary
        assert summary["recommendations"] == 15
        assert "products" not in summary
        assert "api_calls" not in summary

    @pytest.mark.asyncio
    async def test_get_usage_summary_empty(self, stripe_service, mock_db, vendor_id, subscription_id):
        """Test getting usage summary with no usage."""
        # Mock subscription
        mock_subscription = MagicMock()
        mock_subscription.id = subscription_id
        mock_subscription.vendor_id = vendor_id
        mock_subscription.current_period_start = datetime(2025, 1, 1)

        # Setup query mocks - need separate mocks for Subscription and UsageRecord queries
        # First query: Subscription lookup
        subscription_query = MagicMock()
        subscription_query.first.return_value = mock_subscription

        # Second query: UsageRecord lookup returns empty list
        usage_query = MagicMock()
        usage_query.all.return_value = []

        # Mock db.query to return different results for Subscription vs UsageRecord
        def query_side_effect(model):
            if model.__name__ == 'Subscription':
                return MagicMock(filter=MagicMock(return_value=subscription_query))
            else:  # UsageRecord
                return MagicMock(filter=MagicMock(return_value=usage_query))

        mock_db.query.side_effect = query_side_effect

        summary = await stripe_service.get_usage_summary(subscription_id=subscription_id)

        # Should return empty dict
        assert summary == {}

    @pytest.mark.asyncio
    async def test_get_usage_summary_subscription_not_found(self, stripe_service, mock_db, subscription_id):
        """Test usage summary with non-existent subscription."""
        # Setup query mock for Subscription lookup that returns None
        subscription_query = MagicMock()
        subscription_query.first.return_value = None

        def query_side_effect(model):
            return MagicMock(filter=MagicMock(return_value=subscription_query))

        mock_db.query.side_effect = query_side_effect

        with pytest.raises(ValueError) as exc_info:
            await stripe_service.get_usage_summary(subscription_id=subscription_id)

        assert "not found" in str(exc_info.value).lower()


class TestGetTierFromPriceId:
    """Test tier mapping from price ID."""

    def test_get_tier_pro_monthly(self, stripe_service):
        """Test mapping pro monthly price to tier."""
        tier = stripe_service._get_tier_from_price_id('price_pro_monthly')
        assert tier == 'pro'

    def test_get_tier_pro_yearly(self, stripe_service):
        """Test mapping pro yearly price to tier."""
        tier = stripe_service._get_tier_from_price_id('price_pro_yearly')
        assert tier == 'pro'

    def test_get_tier_enterprise_monthly(self, stripe_service):
        """Test mapping enterprise monthly price to tier."""
        tier = stripe_service._get_tier_from_price_id('price_enterprise_monthly')
        assert tier == 'enterprise'

    def test_get_tier_free(self, stripe_service):
        """Test mapping free price to tier."""
        tier = stripe_service._get_tier_from_price_id('price_free')
        assert tier == 'free'

    def test_get_tier_unknown_defaults_to_free(self, stripe_service):
        """Test unknown price ID defaults to free tier."""
        tier = stripe_service._get_tier_from_price_id('price_unknown_xyz')
        assert tier == 'free'
