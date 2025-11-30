"""Unit tests for recommendations router.

Tests recommendations API endpoints:
- POST /recommendations/generate - Generate recommendations
- GET /recommendations - List recommendations
- PUT /recommendations/{id}/feedback - Update feedback
"""
import pytest
from datetime import datetime, timedelta, date
from decimal import Decimal
from uuid import uuid4, UUID
from unittest.mock import MagicMock, AsyncMock, patch

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.routers.recommendations import (
    generate_recommendations,
    list_recommendations,
    update_feedback,
    GenerateRequest,
    FeedbackRequest,
    RecommendationResponse,
)
from src.models.recommendation import Recommendation
from src.models.product import Product
from src.models.venue import Venue


class TestGenerateRecommendations:
    """Test generate_recommendations endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    @pytest.mark.asyncio
    async def test_generate_recommendations_success(self, mock_db, vendor_id):
        """Test successful recommendation generation."""
        request_data = GenerateRequest(
            market_date="2025-06-15",
            latitude=40.7128,
            longitude=-74.0060,
        )

        # Mock weather service
        with patch('src.routers.recommendations.weather_service') as mock_weather:
            mock_weather.get_forecast = AsyncMock(return_value={
                "condition": "Sunny",
                "temp_f": 75.0,
            })

            # Mock events service
            with patch('src.routers.recommendations.events_service') as mock_events:
                mock_events.get_event_for_date.return_value = {
                    "is_special": False,
                }

                # Mock ML service
                with patch('src.routers.recommendations.MLRecommendationService') as mock_ml_class:
                    mock_rec1 = MagicMock(spec=Recommendation)
                    mock_rec2 = MagicMock(spec=Recommendation)

                    mock_ml = MagicMock()
                    mock_ml.generate_recommendations_for_date.return_value = [mock_rec1, mock_rec2]
                    mock_ml_class.return_value = mock_ml

                    result = await generate_recommendations(
                        request=request_data,
                        vendor_id=vendor_id,
                        db=mock_db,
                    )

                    # Verify result
                    assert result["message"] == "Recommendations generated successfully"
                    assert result["count"] == 2
                    assert "2025-06-15" in result["market_date"]

                    # Verify database operations
                    assert mock_db.add.call_count == 2
                    mock_db.commit.assert_called_once()

                    # Verify ML service was called correctly
                    mock_ml.generate_recommendations_for_date.assert_called_once()
                    call_kwargs = mock_ml.generate_recommendations_for_date.call_args[1]
                    assert call_kwargs["venue_id"] is None
                    assert call_kwargs["limit"] == 20

    @pytest.mark.asyncio
    async def test_generate_recommendations_with_venue(self, mock_db, vendor_id):
        """Test generation with venue specified."""
        venue_id = uuid4()
        request_data = GenerateRequest(
            market_date="2025-06-15",
            venue_id=venue_id,
        )

        with patch('src.routers.recommendations.weather_service') as mock_weather:
            mock_weather.get_forecast = AsyncMock(return_value=None)

            with patch('src.routers.recommendations.events_service') as mock_events:
                mock_events.get_event_for_date.return_value = None

                with patch('src.routers.recommendations.MLRecommendationService') as mock_ml_class:
                    mock_ml = MagicMock()
                    mock_ml.generate_recommendations_for_date.return_value = []
                    mock_ml_class.return_value = mock_ml

                    result = await generate_recommendations(
                        request=request_data,
                        vendor_id=vendor_id,
                        db=mock_db,
                    )

                    # Verify venue_id was passed to ML service
                    call_kwargs = mock_ml.generate_recommendations_for_date.call_args[1]
                    assert call_kwargs["venue_id"] == venue_id

    @pytest.mark.asyncio
    async def test_generate_recommendations_invalid_date(self, mock_db, vendor_id):
        """Test generation with invalid date format."""
        request_data = GenerateRequest(
            market_date="not-a-date",
        )

        with pytest.raises(HTTPException) as exc_info:
            await generate_recommendations(
                request=request_data,
                vendor_id=vendor_id,
                db=mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid market_date format" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_generate_recommendations_without_location(self, mock_db, vendor_id):
        """Test generation without location (no weather data)."""
        request_data = GenerateRequest(
            market_date="2025-06-15",
        )

        with patch('src.routers.recommendations.weather_service') as mock_weather:
            with patch('src.routers.recommendations.events_service') as mock_events:
                mock_events.get_event_for_date.return_value = None

                with patch('src.routers.recommendations.MLRecommendationService') as mock_ml_class:
                    mock_ml = MagicMock()
                    mock_ml.generate_recommendations_for_date.return_value = []
                    mock_ml_class.return_value = mock_ml

                    await generate_recommendations(
                        request=request_data,
                        vendor_id=vendor_id,
                        db=mock_db,
                    )

                    # Verify weather service was NOT called
                    mock_weather.get_forecast.assert_not_called()


class TestListRecommendations:
    """Test list_recommendations endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    @pytest.fixture
    def sample_recommendations(self, vendor_id):
        """Sample recommendations with products."""
        product = MagicMock(spec=Product)
        product.id = uuid4()
        product.name = "Tomatoes"
        product.price = Decimal("4.50")
        product.category = "Vegetables"

        rec = MagicMock(spec=Recommendation)
        rec.id = uuid4()
        rec.vendor_id = vendor_id
        rec.product_id = product.id
        rec.market_date = date(2025, 6, 15)
        rec.recommended_quantity = 50
        rec.confidence_score = Decimal("0.85")
        rec.predicted_revenue = Decimal("225.00")
        rec.weather_features = {
            "condition": "Sunny",
            "temp_f": 75.0,
            "feels_like_f": 73.0,
            "humidity": 60.0,
            "description": "Clear skies",
        }
        rec.event_features = {"is_special": False}
        rec.historical_features = {"is_seasonal": 1}
        rec.generated_at = datetime(2025, 1, 15, 12, 0, 0)
        rec.venue_id = None

        return rec, product

    def test_list_recommendations_default(self, mock_db, vendor_id, sample_recommendations):
        """Test listing recommendations with default parameters."""
        rec, product = sample_recommendations

        # Mock recommendation query
        mock_rec_query = MagicMock()
        mock_rec_query.filter.return_value = mock_rec_query
        mock_rec_query.order_by.return_value = mock_rec_query
        mock_rec_query.limit.return_value = mock_rec_query
        mock_rec_query.all.return_value = [rec]

        # Mock product query
        mock_product_query = MagicMock()
        mock_product_query.filter.return_value = mock_product_query
        mock_product_query.first.return_value = product

        # Setup query routing
        def query_side_effect(model):
            if model == Recommendation:
                return mock_rec_query
            elif model == Product:
                return mock_product_query
            return MagicMock()

        mock_db.query.side_effect = query_side_effect

        with patch('src.routers.recommendations.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value = datetime(2025, 6, 1, 12, 0, 0)

            results = list_recommendations(
                vendor_id=vendor_id,
                db=mock_db,
                market_date=None,
                days_ahead=7,
                limit=20,
            )

            assert len(results) == 1
            assert isinstance(results[0], RecommendationResponse)
            assert results[0].product.name == "Tomatoes"
            assert results[0].recommended_quantity == 50
            assert results[0].confidence_score == 0.85
            assert results[0].confidence_level == "high"
            assert results[0].is_seasonal is True

    def test_list_recommendations_specific_date(self, mock_db, vendor_id, sample_recommendations):
        """Test listing recommendations for specific date."""
        rec, product = sample_recommendations

        mock_rec_query = MagicMock()
        mock_rec_query.filter.return_value = mock_rec_query
        mock_rec_query.order_by.return_value = mock_rec_query
        mock_rec_query.limit.return_value = mock_rec_query
        mock_rec_query.all.return_value = [rec]

        mock_product_query = MagicMock()
        mock_product_query.filter.return_value = mock_product_query
        mock_product_query.first.return_value = product

        def query_side_effect(model):
            if model == Recommendation:
                return mock_rec_query
            elif model == Product:
                return mock_product_query

        mock_db.query.side_effect = query_side_effect

        results = list_recommendations(
            vendor_id=vendor_id,
            db=mock_db,
            market_date="2025-06-15",
            days_ahead=7,
            limit=20,
        )

        assert len(results) == 1

    def test_list_recommendations_invalid_date(self, mock_db, vendor_id):
        """Test listing with invalid date format."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            list_recommendations(
                vendor_id=vendor_id,
                db=mock_db,
                market_date="invalid-date",
                days_ahead=7,
                limit=20,
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid market_date format" in exc_info.value.detail

    def test_list_recommendations_with_venue(self, mock_db, vendor_id):
        """Test recommendations with venue information."""
        venue = MagicMock(spec=Venue)
        venue.id = uuid4()
        venue.name = "Farmers Market Downtown"

        product = MagicMock(spec=Product)
        product.id = uuid4()
        product.name = "Tomatoes"
        product.price = Decimal("4.50")
        product.category = "Vegetables"

        rec = MagicMock(spec=Recommendation)
        rec.id = uuid4()
        rec.product_id = product.id
        rec.venue_id = venue.id
        rec.market_date = date(2025, 6, 15)
        rec.recommended_quantity = 50
        rec.confidence_score = Decimal("0.60")
        rec.predicted_revenue = None
        rec.weather_features = None
        rec.event_features = None
        rec.historical_features = None
        rec.generated_at = datetime(2025, 1, 15, 12, 0, 0)

        mock_rec_query = MagicMock()
        mock_rec_query.filter.return_value = mock_rec_query
        mock_rec_query.order_by.return_value = mock_rec_query
        mock_rec_query.limit.return_value = mock_rec_query
        mock_rec_query.all.return_value = [rec]

        mock_product_query = MagicMock()
        mock_product_query.filter.return_value = mock_product_query
        mock_product_query.first.return_value = product

        mock_venue_query = MagicMock()
        mock_venue_query.filter.return_value = mock_venue_query
        mock_venue_query.first.return_value = venue

        def query_side_effect(model):
            if model == Recommendation:
                return mock_rec_query
            elif model == Product:
                return mock_product_query
            elif model == Venue:
                return mock_venue_query

        mock_db.query.side_effect = query_side_effect

        results = list_recommendations(
            vendor_id=vendor_id,
            db=mock_db,
            market_date="2025-06-15",
            days_ahead=7,
            limit=20,
        )

        assert results[0].venue_id == venue.id
        assert results[0].venue_name == "Farmers Market Downtown"
        assert results[0].confidence_level == "medium"

    def test_list_recommendations_empty(self, mock_db, vendor_id):
        """Test listing when no recommendations exist."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        results = list_recommendations(
            vendor_id=vendor_id,
            db=mock_db,
            market_date=None,
            days_ahead=7,
            limit=20,
        )

        assert results == []


class TestUpdateFeedback:
    """Test update_feedback endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    @pytest.fixture
    def recommendation_id(self):
        """Test recommendation ID."""
        return uuid4()

    @pytest.fixture
    def existing_recommendation(self, recommendation_id, vendor_id):
        """Existing recommendation."""
        rec = MagicMock(spec=Recommendation)
        rec.id = recommendation_id
        rec.vendor_id = vendor_id
        rec.user_accepted = None
        rec.actual_quantity_brought = None
        return rec

    def test_update_feedback_accepted(self, mock_db, vendor_id, recommendation_id, existing_recommendation):
        """Test updating feedback with accepted recommendation."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = existing_recommendation
        mock_db.query.return_value = mock_query

        feedback_data = FeedbackRequest(
            accepted=True,
            actual_quantity=45,
        )

        result = update_feedback(
            recommendation_id=recommendation_id,
            feedback=feedback_data,
            vendor_id=vendor_id,
            db=mock_db,
        )

        assert result["message"] == "Feedback updated successfully"
        assert existing_recommendation.user_accepted is True
        assert existing_recommendation.actual_quantity_brought == 45
        mock_db.commit.assert_called_once()

    def test_update_feedback_rejected(self, mock_db, vendor_id, recommendation_id, existing_recommendation):
        """Test updating feedback with rejected recommendation."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = existing_recommendation
        mock_db.query.return_value = mock_query

        feedback_data = FeedbackRequest(
            accepted=False,
        )

        result = update_feedback(
            recommendation_id=recommendation_id,
            feedback=feedback_data,
            vendor_id=vendor_id,
            db=mock_db,
        )

        assert existing_recommendation.user_accepted is False
        assert existing_recommendation.actual_quantity_brought is None

    def test_update_feedback_not_found(self, mock_db, vendor_id, recommendation_id):
        """Test updating feedback for non-existent recommendation."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        feedback_data = FeedbackRequest(accepted=True)

        with pytest.raises(HTTPException) as exc_info:
            update_feedback(
                recommendation_id=recommendation_id,
                feedback=feedback_data,
                vendor_id=vendor_id,
                db=mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in exc_info.value.detail

    def test_update_feedback_wrong_vendor(self, mock_db, recommendation_id):
        """Test updating feedback from wrong vendor."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        feedback_data = FeedbackRequest(accepted=True)

        with pytest.raises(HTTPException) as exc_info:
            update_feedback(
                recommendation_id=recommendation_id,
                feedback=feedback_data,
                vendor_id=uuid4(),  # Different vendor
                db=mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
