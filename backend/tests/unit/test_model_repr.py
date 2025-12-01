"""
Unit tests for Model __repr__ Methods

Tests __repr__ string representation for various models.
"""

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from src.models.audit_log import AuditLog
from src.models.product import Product
from src.models.sale import Sale
from src.models.venue import Venue
from src.models.square_token import SquareToken
from src.models.event_data import EventData
from src.models.recommendation_feedback import RecommendationFeedback
from src.models.base import BaseModel, TenantModel


class TestBaseModelRepr:
    """Test BaseModel and TenantModel __repr__ methods"""

    def test_base_model_repr(self):
        """Test BaseModel __repr__ method (covers line 65)"""
        # Create a concrete class for testing
        class TestModel(BaseModel):
            __tablename__ = "test_model"

        test_id = uuid4()
        instance = TestModel(id=test_id)

        result = repr(instance)

        assert "TestModel" in result
        assert str(test_id) in result

    def test_tenant_model_repr(self):
        """Test TenantModel __repr__ method (covers line 75)"""
        # Create a concrete class for testing
        class TestTenantModel(TenantModel):
            __tablename__ = "test_tenant_model"

        test_id = uuid4()
        vendor_id = uuid4()
        instance = TestTenantModel(id=test_id, vendor_id=vendor_id)

        result = repr(instance)

        assert "TestTenantModel" in result
        assert str(test_id) in result
        assert str(vendor_id) in result


class TestModelRepr:
    """Test model __repr__ methods"""

    def test_audit_log_repr(self):
        """Test AuditLog __repr__ method"""
        log = AuditLog(
            id="test-id",
            vendor_id="vendor-1",
            action="CREATE",
            user_email="user@test.com",
            timestamp=datetime(2025, 1, 1, 12, 0, 0)
        )

        result = repr(log)

        assert "AuditLog" in result
        assert "test-id" in result
        assert "CREATE" in result
        assert "user@test.com" in result

    def test_product_repr(self):
        """Test Product __repr__ method"""
        product = Product(
            id="prod-1",
            vendor_id="vendor-1",
            name="Apples",
            price=Decimal("2.50")
        )

        result = repr(product)

        assert "Product" in result
        assert "prod-1" in result
        assert "vendor-1" in result
        assert "Apples" in result
        assert "2.50" in result

    def test_sale_repr(self):
        """Test Sale __repr__ method"""
        sale = Sale(
            id="sale-1",
            vendor_id="vendor-1",
            sale_date=datetime(2025, 1, 15, 10, 30, 0),
            total_amount=Decimal("45.00")
        )

        result = repr(sale)

        assert "Sale" in result
        assert "sale-1" in result
        assert "vendor-1" in result
        assert "45.00" in result

    def test_venue_repr(self):
        """Test Venue __repr__ method"""
        venue = Venue(
            id="venue-1",
            vendor_id="vendor-1",
            name="Downtown Farmers Market",
            location="123 Main St"
        )

        result = repr(venue)

        assert "Venue" in result
        assert "venue-1" in result
        assert "vendor-1" in result
        assert "Downtown Farmers Market" in result
        assert "123 Main St" in result

    def test_square_token_repr(self):
        """Test SquareToken __repr__ method"""
        token = SquareToken(
            vendor_id="vendor-1",
            access_token_encrypted="encrypted_access",
            refresh_token_encrypted="encrypted_refresh",
            expires_at=datetime(2025, 12, 31, 23, 59, 59),
            merchant_id="merchant-123",
            scopes="ITEMS_READ ORDERS_READ",
            is_active=True
        )

        result = repr(token)

        assert "SquareToken" in result
        assert "vendor-1" in result
        assert "merchant-123" in result
        assert "True" in result

    def test_event_data_repr(self):
        """Test EventData __repr__ method"""
        event = EventData(
            id="event-1",
            vendor_id="vendor-1",
            name="Summer Festival",
            event_date=datetime(2025, 7, 4, 14, 0, 0),
            expected_attendance=500,
            source="manual"
        )

        result = repr(event)

        assert "EventData" in result
        assert "event-1" in result
        assert "vendor-1" in result
        assert "Summer Festival" in result
        assert "500" in result

    def test_recommendation_feedback_repr(self):
        """Test RecommendationFeedback __repr__ method (covers line 121)"""
        feedback_id = uuid4()
        rec_id = uuid4()
        vendor_id = uuid4()

        feedback = RecommendationFeedback(
            id=feedback_id,
            vendor_id=vendor_id,
            recommendation_id=rec_id,
            rating=4,
            variance_percentage=Decimal("15.5")
        )

        result = repr(feedback)

        assert "RecommendationFeedback" in result
        assert str(feedback_id) in result
        assert str(rec_id) in result
        assert "4" in result
        assert "15.5" in result
