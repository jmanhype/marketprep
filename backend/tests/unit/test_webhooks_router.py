"""Unit tests for webhooks router.

Tests webhook endpoints:
- POST /webhooks/stripe - Stripe webhook handler
"""
import pytest
from datetime import datetime
from uuid import uuid4
from unittest.mock import MagicMock, AsyncMock, patch

from fastapi import HTTPException
from sqlalchemy.orm import Session
import stripe

from src.routers.webhooks import (
    stripe_webhook,
    handle_invoice_payment_succeeded,
    handle_invoice_payment_failed,
    handle_subscription_updated,
    handle_subscription_deleted,
)
from src.models.subscription import Subscription, Invoice


class TestStripeWebhook:
    """Test stripe_webhook endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def mock_request(self):
        """Mock FastAPI request."""
        request = MagicMock()
        request.body = AsyncMock(return_value=b'{"type": "test.event"}')
        return request

    @pytest.fixture
    def stripe_signature(self):
        """Test Stripe signature."""
        return "t=1234567890,v1=signature_hash"

    @pytest.mark.asyncio
    async def test_webhook_invalid_payload(self, mock_request, mock_db, stripe_signature):
        """Test webhook with invalid payload."""
        with patch('src.routers.webhooks.stripe.Webhook.construct_event') as mock_construct:
            mock_construct.side_effect = ValueError("Invalid payload")

            with pytest.raises(HTTPException) as exc_info:
                await stripe_webhook(
                    request=mock_request,
                    db=mock_db,
                    stripe_signature=stripe_signature,
                )

            assert exc_info.value.status_code == 400
            assert "Invalid payload" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_webhook_invalid_signature(self, mock_request, mock_db, stripe_signature):
        """Test webhook with invalid signature."""
        with patch('src.routers.webhooks.stripe.Webhook.construct_event') as mock_construct:
            mock_construct.side_effect = stripe.error.SignatureVerificationError(
                "Invalid signature", "sig"
            )

            with pytest.raises(HTTPException) as exc_info:
                await stripe_webhook(
                    request=mock_request,
                    db=mock_db,
                    stripe_signature=stripe_signature,
                )

            assert exc_info.value.status_code == 400
            assert "Invalid signature" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_webhook_invoice_payment_succeeded(self, mock_request, mock_db, stripe_signature):
        """Test successful invoice payment webhook."""
        event = {
            'type': 'invoice.payment_succeeded',
            'data': {
                'object': {
                    'id': 'inv_123',
                    'subscription': 'sub_123',
                }
            }
        }

        with patch('src.routers.webhooks.stripe.Webhook.construct_event') as mock_construct:
            mock_construct.return_value = event

            with patch('src.routers.webhooks.StripeService') as mock_stripe_service:
                with patch('src.routers.webhooks.handle_invoice_payment_succeeded') as mock_handler:
                    mock_handler.return_value = None

                    result = await stripe_webhook(
                        request=mock_request,
                        db=mock_db,
                        stripe_signature=stripe_signature,
                    )

                    assert result["status"] == "success"
                    mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_webhook_invoice_payment_failed(self, mock_request, mock_db, stripe_signature):
        """Test failed invoice payment webhook."""
        event = {
            'type': 'invoice.payment_failed',
            'data': {
                'object': {
                    'id': 'inv_456',
                    'subscription': 'sub_456',
                }
            }
        }

        with patch('src.routers.webhooks.stripe.Webhook.construct_event') as mock_construct:
            mock_construct.return_value = event

            with patch('src.routers.webhooks.StripeService'):
                with patch('src.routers.webhooks.handle_invoice_payment_failed') as mock_handler:
                    mock_handler.return_value = None

                    result = await stripe_webhook(
                        request=mock_request,
                        db=mock_db,
                        stripe_signature=stripe_signature,
                    )

                    assert result["status"] == "success"
                    mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_webhook_subscription_updated(self, mock_request, mock_db, stripe_signature):
        """Test subscription updated webhook."""
        event = {
            'type': 'customer.subscription.updated',
            'data': {
                'object': {
                    'id': 'sub_789',
                    'status': 'active',
                }
            }
        }

        with patch('src.routers.webhooks.stripe.Webhook.construct_event') as mock_construct:
            mock_construct.return_value = event

            with patch('src.routers.webhooks.StripeService'):
                with patch('src.routers.webhooks.handle_subscription_updated') as mock_handler:
                    mock_handler.return_value = None

                    result = await stripe_webhook(
                        request=mock_request,
                        db=mock_db,
                        stripe_signature=stripe_signature,
                    )

                    assert result["status"] == "success"
                    mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_webhook_subscription_deleted(self, mock_request, mock_db, stripe_signature):
        """Test subscription deleted webhook."""
        event = {
            'type': 'customer.subscription.deleted',
            'data': {
                'object': {
                    'id': 'sub_canceled',
                }
            }
        }

        with patch('src.routers.webhooks.stripe.Webhook.construct_event') as mock_construct:
            mock_construct.return_value = event

            with patch('src.routers.webhooks.StripeService'):
                with patch('src.routers.webhooks.handle_subscription_deleted') as mock_handler:
                    mock_handler.return_value = None

                    result = await stripe_webhook(
                        request=mock_request,
                        db=mock_db,
                        stripe_signature=stripe_signature,
                    )

                    assert result["status"] == "success"
                    mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_webhook_payment_method_attached(self, mock_request, mock_db, stripe_signature):
        """Test payment method attached webhook."""
        event = {
            'type': 'payment_method.attached',
            'data': {
                'object': {
                    'id': 'pm_123',
                }
            }
        }

        with patch('src.routers.webhooks.stripe.Webhook.construct_event') as mock_construct:
            mock_construct.return_value = event

            with patch('src.routers.webhooks.StripeService'):
                result = await stripe_webhook(
                    request=mock_request,
                    db=mock_db,
                    stripe_signature=stripe_signature,
                )

                assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_webhook_payment_method_detached(self, mock_request, mock_db, stripe_signature):
        """Test payment method detached webhook."""
        event = {
            'type': 'payment_method.detached',
            'data': {
                'object': {
                    'id': 'pm_456',
                }
            }
        }

        with patch('src.routers.webhooks.stripe.Webhook.construct_event') as mock_construct:
            mock_construct.return_value = event

            with patch('src.routers.webhooks.StripeService'):
                result = await stripe_webhook(
                    request=mock_request,
                    db=mock_db,
                    stripe_signature=stripe_signature,
                )

                assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_webhook_unhandled_event_type(self, mock_request, mock_db, stripe_signature):
        """Test unhandled webhook event type."""
        event = {
            'type': 'some.unknown.event',
            'data': {
                'object': {}
            }
        }

        with patch('src.routers.webhooks.stripe.Webhook.construct_event') as mock_construct:
            mock_construct.return_value = event

            with patch('src.routers.webhooks.StripeService'):
                result = await stripe_webhook(
                    request=mock_request,
                    db=mock_db,
                    stripe_signature=stripe_signature,
                )

                # Still returns success for unhandled events
                assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_webhook_processing_error(self, mock_request, mock_db, stripe_signature):
        """Test webhook processing error."""
        event = {
            'type': 'invoice.payment_succeeded',
            'data': {
                'object': {
                    'id': 'inv_error',
                }
            }
        }

        with patch('src.routers.webhooks.stripe.Webhook.construct_event') as mock_construct:
            mock_construct.return_value = event

            with patch('src.routers.webhooks.StripeService'):
                with patch('src.routers.webhooks.handle_invoice_payment_succeeded') as mock_handler:
                    mock_handler.side_effect = Exception("Database error")

                    with pytest.raises(HTTPException) as exc_info:
                        await stripe_webhook(
                            request=mock_request,
                            db=mock_db,
                            stripe_signature=stripe_signature,
                        )

                    assert exc_info.value.status_code == 500
                    assert "Webhook processing failed" in exc_info.value.detail


class TestHandleInvoicePaymentSucceeded:
    """Test handle_invoice_payment_succeeded helper."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def mock_stripe_service(self):
        """Mock Stripe service."""
        service = MagicMock()
        service.create_invoice = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_handle_payment_succeeded_existing_invoice(self, mock_db, mock_stripe_service):
        """Test handling payment for existing invoice."""
        event = {
            'data': {
                'object': {
                    'id': 'inv_123',
                    'subscription': 'sub_123',
                }
            }
        }

        existing_invoice = MagicMock(spec=Invoice)
        existing_invoice.amount_due = 1000
        existing_invoice.status = 'pending'

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = existing_invoice
        mock_db.query.return_value = mock_query

        await handle_invoice_payment_succeeded(event, mock_stripe_service, mock_db)

        assert existing_invoice.status == 'paid'
        assert existing_invoice.paid is True
        assert existing_invoice.amount_paid == 1000
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_handle_payment_succeeded_new_invoice(self, mock_db, mock_stripe_service):
        """Test handling payment for new invoice."""
        event = {
            'data': {
                'object': {
                    'id': 'inv_new',
                    'subscription': 'sub_123',
                }
            }
        }

        subscription = MagicMock(spec=Subscription)
        subscription.id = uuid4()

        def query_side_effect(model):
            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            if model == Invoice:
                mock_query.first.return_value = None  # Invoice doesn't exist
            elif model == Subscription:
                mock_query.first.return_value = subscription
            return mock_query

        mock_db.query.side_effect = query_side_effect

        with patch('src.routers.webhooks.stripe.Invoice') as mock_stripe_invoice:
            mock_stripe_invoice.retrieve.return_value = {"id": "inv_new"}

            await handle_invoice_payment_succeeded(event, mock_stripe_service, mock_db)

            # Verify new invoice was created
            mock_stripe_service.create_invoice.assert_called_once_with(
                subscription.id,
                {"id": "inv_new"},
            )


class TestHandleInvoicePaymentFailed:
    """Test handle_invoice_payment_failed helper."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def mock_stripe_service(self):
        """Mock Stripe service."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_handle_payment_failed_with_invoice(self, mock_db, mock_stripe_service):
        """Test handling failed payment with existing invoice."""
        event = {
            'data': {
                'object': {
                    'id': 'inv_failed',
                    'subscription': 'sub_123',
                }
            }
        }

        invoice = MagicMock(spec=Invoice)
        invoice.status = 'pending'
        invoice.paid = False

        subscription = MagicMock(spec=Subscription)
        subscription.id = uuid4()
        subscription.status = 'active'

        def query_side_effect(model):
            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            if model == Invoice:
                mock_query.first.return_value = invoice
            elif model == Subscription:
                mock_query.first.return_value = subscription
            return mock_query

        mock_db.query.side_effect = query_side_effect

        await handle_invoice_payment_failed(event, mock_stripe_service, mock_db)

        assert invoice.status == 'uncollectible'
        assert invoice.paid is False
        assert subscription.status == 'past_due'
        assert mock_db.commit.call_count == 2  # Once for invoice, once for subscription

    @pytest.mark.asyncio
    async def test_handle_payment_failed_no_invoice(self, mock_db, mock_stripe_service):
        """Test handling failed payment without existing invoice."""
        event = {
            'data': {
                'object': {
                    'id': 'inv_unknown',
                    'subscription': 'sub_456',
                }
            }
        }

        subscription = MagicMock(spec=Subscription)
        subscription.id = uuid4()

        def query_side_effect(model):
            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            if model == Invoice:
                mock_query.first.return_value = None
            elif model == Subscription:
                mock_query.first.return_value = subscription
            return mock_query

        mock_db.query.side_effect = query_side_effect

        await handle_invoice_payment_failed(event, mock_stripe_service, mock_db)

        # Still updates subscription
        assert subscription.status == 'past_due'
        mock_db.commit.assert_called()


class TestHandleSubscriptionUpdated:
    """Test handle_subscription_updated helper."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def mock_stripe_service(self):
        """Mock Stripe service."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_handle_subscription_updated(self, mock_db, mock_stripe_service):
        """Test handling subscription update."""
        event = {
            'data': {
                'object': {
                    'id': 'sub_123',
                    'status': 'active',
                    'current_period_start': 1704067200,  # 2025-01-01
                    'current_period_end': 1706745600,    # 2025-02-01
                    'cancel_at_period_end': False,
                    'canceled_at': None,
                }
            }
        }

        subscription = MagicMock(spec=Subscription)
        subscription.id = uuid4()

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = subscription
        mock_db.query.return_value = mock_query

        await handle_subscription_updated(event, mock_stripe_service, mock_db)

        assert subscription.status == 'active'
        assert subscription.cancel_at_period_end is False
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_subscription_updated_with_cancellation(self, mock_db, mock_stripe_service):
        """Test handling subscription update with cancellation."""
        event = {
            'data': {
                'object': {
                    'id': 'sub_canceled',
                    'status': 'active',
                    'current_period_start': 1704067200,
                    'current_period_end': 1706745600,
                    'cancel_at_period_end': True,
                    'canceled_at': 1705327200,  # 2025-01-15
                }
            }
        }

        subscription = MagicMock(spec=Subscription)
        subscription.id = uuid4()

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = subscription
        mock_db.query.return_value = mock_query

        await handle_subscription_updated(event, mock_stripe_service, mock_db)

        assert subscription.cancel_at_period_end is True
        mock_db.commit.assert_called_once()


class TestHandleSubscriptionDeleted:
    """Test handle_subscription_deleted helper."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def mock_stripe_service(self):
        """Mock Stripe service."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_handle_subscription_deleted(self, mock_db, mock_stripe_service):
        """Test handling subscription deletion."""
        event = {
            'data': {
                'object': {
                    'id': 'sub_deleted',
                }
            }
        }

        subscription = MagicMock(spec=Subscription)
        subscription.id = uuid4()
        subscription.status = 'active'

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = subscription
        mock_db.query.return_value = mock_query

        await handle_subscription_deleted(event, mock_stripe_service, mock_db)

        assert subscription.status == 'canceled'
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_subscription_deleted_not_found(self, mock_db, mock_stripe_service):
        """Test handling deletion for non-existent subscription."""
        event = {
            'data': {
                'object': {
                    'id': 'sub_unknown',
                }
            }
        }

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        # Should not raise an error
        await handle_subscription_deleted(event, mock_stripe_service, mock_db)

        # No commit since subscription wasn't found
        mock_db.commit.assert_not_called()
