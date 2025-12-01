"""
Integration tests for recommendation generation flow.

Tests the complete flow from product/sales data to recommendations.
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4


@pytest.mark.integration
class TestRecommendationFlow:
    """Integration tests for recommendation generation."""

    def test_create_product_and_generate_recommendation(self, authenticated_client, db_session):
        """Test complete flow: create product, sales, generate recommendation."""
        from src.models.product import Product
        from src.models.sale import Sale
        from src.models.venue import Venue

        # Create a venue
        venue = Venue(
            id=uuid4(),
            name="Test Market",
            location="Downtown Test City",
            vendor_id=authenticated_client.vendor_id,
        )
        db_session.add(venue)
        db_session.commit()

        # Create a product via API
        product_data = {
            "name": "Organic Tomatoes",
            "category": "vegetables",
            "unit": "lb",
            "typical_price": 4.99,
        }

        product_response = authenticated_client.post(
            "/api/v1/products",
            json=product_data,
        )
        assert product_response.status_code == 201
        product_id = product_response.json()["id"]

        # Create sales history
        for days_ago in range(7):
            sale_date = datetime.now() - timedelta(days=days_ago)
            sale = Sale(
                id=uuid4(),
                vendor_id=authenticated_client.vendor_id,
                product_id=product_id,
                venue_id=str(venue.id),
                quantity_sold=10 + days_ago,  # Vary quantities
                unit_price=4.99,
                sale_date=sale_date.date(),
            )
            db_session.add(sale)

        db_session.commit()

        # Generate recommendation
        recommendation_response = authenticated_client.post(
            "/api/v1/recommendations/generate",
            json={
                "venue_id": str(venue.id),
                "market_date": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
            },
        )

        assert recommendation_response.status_code == 200
        recommendations = recommendation_response.json()

        # Verify recommendations include our product
        assert len(recommendations) > 0
        product_ids = [r["product_id"] for r in recommendations]
        assert product_id in product_ids

        # Verify recommendation structure
        for rec in recommendations:
            assert "product_id" in rec
            assert "recommended_quantity" in rec
            assert "confidence_score" in rec
            assert rec["confidence_score"] >= 0
            assert rec["confidence_score"] <= 1


@pytest.mark.integration
class TestProductSalesIntegration:
    """Integration tests for product and sales management."""

    def test_create_product_record_sale_retrieve_analytics(self, authenticated_client, db_session):
        """Test complete product lifecycle with sales and analytics."""
        from src.models.venue import Venue

        # Create venue
        venue = Venue(
            id=uuid4(),
            name="Analytics Test Market",
            location="Test Location",
            vendor_id=authenticated_client.vendor_id,
        )
        db_session.add(venue)
        db_session.commit()

        # Step 1: Create product
        product_data = {
            "name": "Fresh Strawberries",
            "category": "fruits",
            "unit": "lb",
            "typical_price": 6.99,
        }

        product_response = authenticated_client.post("/api/v1/products", json=product_data)
        assert product_response.status_code == 201
        product = product_response.json()
        product_id = product["id"]

        # Step 2: Record multiple sales
        for i in range(3):
            sale_data = {
                "product_id": product_id,
                "venue_id": str(venue.id),
                "quantity_sold": 15 + i * 5,
                "unit_price": 6.99,
                "sale_date": (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d"),
            }

            sale_response = authenticated_client.post("/api/v1/sales", json=sale_data)
            assert sale_response.status_code == 201

        # Step 3: Retrieve product with sales history
        product_detail_response = authenticated_client.get(f"/api/v1/products/{product_id}")
        assert product_detail_response.status_code == 200

        # Step 4: Get sales analytics
        sales_response = authenticated_client.get(f"/api/v1/sales?product_id={product_id}")
        assert sales_response.status_code == 200
        sales = sales_response.json()
        assert len(sales) == 3

        # Verify sales data
        total_quantity = sum(sale["quantity_sold"] for sale in sales)
        assert total_quantity == 15 + 20 + 25  # 60 total
