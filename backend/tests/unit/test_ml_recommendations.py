"""
Unit tests for ML Recommendations Service

Tests ML-powered inventory recommendation functionality:
- Venue feature extraction (sales patterns, confidence, embeddings)
- Seasonality detection using statistical analysis
- Feature engineering (temporal, weather, event, venue, seasonal)
- Model training with sufficient/insufficient data
- Prediction with graceful degradation fallbacks
- Batch recommendations for multiple products
- Feedback retrieval for model retraining
- Confidence scoring based on data availability
"""

import pytest
import numpy as np
from datetime import datetime, timedelta
from uuid import uuid4
from decimal import Decimal
from unittest.mock import MagicMock, patch
from collections import defaultdict

from src.services.ml_recommendations import (
    MLRecommendationService,
    VenueFeatureEngineer,
    MLModelError,
)


class TestVenueFeatureEngineer:
    """Test venue-specific feature extraction"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return MagicMock()

    @pytest.fixture
    def engineer(self, mock_db):
        """Create venue feature engineer"""
        vendor_id = uuid4()
        return VenueFeatureEngineer(vendor_id=vendor_id, db=mock_db)

    def test_extract_venue_features_with_sales_history(self, engineer, mock_db):
        """Test extracting features when venue has sales history"""
        venue_id = uuid4()
        product_id = uuid4()
        market_date = datetime(2025, 6, 1)

        # Mock sales data
        mock_sales = [
            MagicMock(
                sale_date=market_date - timedelta(days=10),
                line_items=[{'product_id': str(product_id), 'quantity': '8'}],
            ),
            MagicMock(
                sale_date=market_date - timedelta(days=20),
                line_items=[{'product_id': str(product_id), 'quantity': '12'}],
            ),
            MagicMock(
                sale_date=market_date - timedelta(days=30),
                line_items=[{'product_id': str(product_id), 'quantity': '10'}],
            ),
        ]

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = mock_sales

        # Extract features
        features = engineer.extract_venue_features(
            venue_id=venue_id,
            product_id=product_id,
            market_date=market_date,
        )

        # Verify features
        assert features['venue_avg_sales'] == 10.0  # (8+12+10)/3
        assert features['venue_max_sales'] == 12.0
        assert features['venue_sales_count'] == 3.0
        assert features['venue_last_sale_days_ago'] == 10.0  # Most recent sale

    def test_extract_venue_features_no_sales_history(self, engineer, mock_db):
        """Test extracting features for new venue/product combination"""
        venue_id = uuid4()
        product_id = uuid4()
        market_date = datetime(2025, 6, 1)

        # Mock no sales
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []

        features = engineer.extract_venue_features(
            venue_id=venue_id,
            product_id=product_id,
            market_date=market_date,
        )

        # Verify default values
        assert features['venue_avg_sales'] == 0.0
        assert features['venue_max_sales'] == 0.0
        assert features['venue_sales_count'] == 0.0
        assert features['venue_last_sale_days_ago'] == 999.0

    def test_is_seasonal_product_true(self, engineer, mock_db):
        """Test detecting seasonal product (z-score > 1.5)"""
        product_id = uuid4()

        # Mock sales with strong seasonal pattern
        mock_sales = []
        # Summer months (Jun, Jul, Aug) have very high sales, others very low
        for month in range(1, 13):
            # Create 10 sales per month for more data
            for _ in range(10):
                sale = MagicMock()
                sale.sale_date = datetime(2025, month, 1)
                if month in [6, 7, 8]:  # Summer - 5x higher sales
                    sale.line_items = [{'product_id': str(product_id), 'quantity': '50'}]
                else:
                    sale.line_items = [{'product_id': str(product_id), 'quantity': '10'}]
                mock_sales.append(sale)

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = mock_sales

        # Check if June is seasonal (should be True with large z-score)
        is_seasonal = engineer.is_seasonal_product(product_id=product_id, month=6)

        assert is_seasonal == True

    def test_is_seasonal_product_false_insufficient_data(self, engineer, mock_db):
        """Test seasonality detection with insufficient data"""
        product_id = uuid4()

        # Mock only 2 months of data
        mock_sales = [
            MagicMock(
                sale_date=datetime(2025, 1, 1),
                line_items=[{'product_id': str(product_id), 'quantity': '10'}],
            ),
            MagicMock(
                sale_date=datetime(2025, 2, 1),
                line_items=[{'product_id': str(product_id), 'quantity': '12'}],
            ),
        ]

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = mock_sales

        is_seasonal = engineer.is_seasonal_product(product_id=product_id, month=1)

        # Should return False due to insufficient data
        assert is_seasonal is False

    def test_is_seasonal_product_false_no_variance(self, engineer, mock_db):
        """Test seasonality when all months have same sales (std = 0)"""
        product_id = uuid4()

        # Mock sales with no variance
        mock_sales = []
        for month in range(1, 13):
            sale = MagicMock()
            sale.sale_date = datetime(2025, month, 1)
            sale.line_items = [{'product_id': str(product_id), 'quantity': '10'}]
            mock_sales.append(sale)

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = mock_sales

        is_seasonal = engineer.is_seasonal_product(product_id=product_id, month=6)

        # Should return False because std = 0
        assert is_seasonal is False

    def test_calculate_venue_confidence_new_venue(self, engineer, mock_db):
        """Test confidence score for new venue (no sales)"""
        venue_id = uuid4()
        product_id = uuid4()
        market_date = datetime(2025, 6, 1)

        # Mock no sales
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []

        confidence = engineer.calculate_venue_confidence(
            venue_id=venue_id,
            product_id=product_id,
            market_date=market_date,
        )

        # New venue should have low confidence
        assert confidence == 0.3

    def test_calculate_venue_confidence_stale_venue(self, engineer, mock_db):
        """Test confidence score for stale venue (> 6 months since last sale)"""
        venue_id = uuid4()
        product_id = uuid4()
        market_date = datetime(2025, 6, 1)

        # Mock old sale (8 months ago)
        mock_sales = [
            MagicMock(
                sale_date=market_date - timedelta(days=240),  # 8 months
                line_items=[{'product_id': str(product_id), 'quantity': '10'}],
            ),
        ]

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = mock_sales

        confidence = engineer.calculate_venue_confidence(
            venue_id=venue_id,
            product_id=product_id,
            market_date=market_date,
        )

        # Stale venue should have medium confidence
        assert confidence == 0.5

    def test_calculate_venue_confidence_high(self, engineer, mock_db):
        """Test high confidence score (>= 20 sales)"""
        venue_id = uuid4()
        product_id = uuid4()
        market_date = datetime(2025, 6, 1)

        # Mock 25 recent sales
        mock_sales = []
        for i in range(25):
            mock_sales.append(
                MagicMock(
                    sale_date=market_date - timedelta(days=i+1),
                    line_items=[{'product_id': str(product_id), 'quantity': '10'}],
                )
            )

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = mock_sales

        confidence = engineer.calculate_venue_confidence(
            venue_id=venue_id,
            product_id=product_id,
            market_date=market_date,
        )

        # High sales count should give high confidence
        assert confidence == 0.85

    def test_calculate_venue_confidence_medium(self, engineer, mock_db):
        """Test medium confidence score (between 3 and 20 sales)"""
        venue_id = uuid4()
        product_id = uuid4()
        market_date = datetime(2025, 6, 1)

        # Mock 10 recent sales
        mock_sales = []
        for i in range(10):
            mock_sales.append(
                MagicMock(
                    sale_date=market_date - timedelta(days=i+1),
                    line_items=[{'product_id': str(product_id), 'quantity': '10'}],
                )
            )

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = mock_sales

        confidence = engineer.calculate_venue_confidence(
            venue_id=venue_id,
            product_id=product_id,
            market_date=market_date,
        )

        # Should be between 0.6 and 0.85
        assert 0.6 < confidence < 0.85

    @patch('src.services.ml_recommendations.VenueFeatureEngineer._get_venue_total_sales')
    @patch('src.services.ml_recommendations.VenueFeatureEngineer._get_venue_first_sale_date')
    def test_generate_venue_embedding_with_venue(self, mock_first_sale, mock_total_sales, engineer, mock_db):
        """Test generating venue embedding with full venue data"""
        venue_id = uuid4()

        # Mock venue with full data
        mock_venue = MagicMock()
        mock_venue.typical_attendance = 500
        mock_venue.latitude = 45.0
        mock_venue.longitude = 90.0  # Positive longitude for 0-1 normalization

        # Mock venue query
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_venue

        # Mock helper method returns
        mock_total_sales.return_value = 100.0
        mock_first_sale.return_value = datetime.utcnow() - timedelta(days=365)

        embedding = engineer.generate_venue_embedding(venue_id=venue_id)

        # Verify embedding structure
        assert len(embedding) == 5
        assert all(isinstance(val, float) for val in embedding)

    def test_generate_venue_embedding_no_venue(self, engineer, mock_db):
        """Test generating venue embedding when venue not found"""
        venue_id = uuid4()

        # Mock no venue
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        embedding = engineer.generate_venue_embedding(venue_id=venue_id)

        # Should return zero embedding
        assert len(embedding) == 5
        assert all(val == 0.0 for val in embedding)


class TestMLRecommendationService:
    """Test ML recommendation service"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return MagicMock()

    @pytest.fixture
    def ml_service(self, mock_db):
        """Create ML service"""
        vendor_id = uuid4()
        return MLRecommendationService(vendor_id=vendor_id, db=mock_db)

    def test_init(self, ml_service):
        """Test service initialization"""
        assert ml_service.model is not None
        assert ml_service.scaler is not None
        assert ml_service.model_trained is False
        assert ml_service.scaler_fitted is False
        assert ml_service.venue_engineer is not None

    @patch('src.services.ml_recommendations.VenueFeatureEngineer.generate_venue_embedding')
    @patch('src.services.ml_recommendations.VenueFeatureEngineer.extract_venue_features')
    @patch('src.services.ml_recommendations.VenueFeatureEngineer.is_seasonal_product')
    @patch('src.services.ml_recommendations.VenueFeatureEngineer._get_monthly_sales_pattern')
    def test_extract_features_with_all_data(
        self,
        mock_monthly_pattern,
        mock_is_seasonal,
        mock_venue_features,
        mock_venue_embedding,
        ml_service,
        mock_db,
    ):
        """Test feature extraction with weather, event, and venue data"""
        product_id = uuid4()
        venue_id = uuid4()
        market_date = datetime(2025, 6, 15)

        weather_data = {
            'temp_f': 75.0,
            'feels_like_f': 78.0,
            'humidity': 60.0,
            'condition': 'sunny',
        }

        event_data = {
            'expected_attendance': 500,
        }

        # Mock sales data
        mock_sales = [
            MagicMock(
                sale_date=market_date - timedelta(days=i),
                line_items=[{'product_id': str(product_id), 'quantity': '10'}],
            )
            for i in range(1, 31)
        ]

        # Mock venue feature extraction methods
        mock_venue_features.return_value = {
            'venue_avg_sales': 8.0,
            'venue_max_sales': 12.0,
            'venue_sales_count': 5.0,
            'venue_last_sale_days_ago': 10.0,
        }
        mock_venue_embedding.return_value = [0.5, 0.5, 0.5, 0.5, 0.5]
        mock_is_seasonal.return_value = False
        mock_monthly_pattern.return_value = {6: 10.0}

        # Mock sales query
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = mock_sales

        features_df = ml_service._extract_features(
            product_id=product_id,
            market_date=market_date,
            weather_data=weather_data,
            event_data=event_data,
            venue_id=venue_id,
        )

        # Verify temporal features
        assert features_df['day_of_week'].values[0] == 6  # Sunday (2025-06-15 is a Sunday)
        assert features_df['month'].values[0] == 6
        assert features_df['day_of_month'].values[0] == 15

        # Verify weather features
        assert features_df['temp_f'].values[0] == 75.0
        assert features_df['is_sunny'].values[0] == 1
        assert features_df['is_rainy'].values[0] == 0

        # Verify event features
        assert features_df['is_special_event'].values[0] == 1
        assert features_df['expected_attendance'].values[0] == 500

    def test_extract_features_no_optional_data(self, ml_service, mock_db):
        """Test feature extraction with no weather/event/venue"""
        product_id = uuid4()
        market_date = datetime(2025, 3, 10)

        # Mock no sales
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []

        features_df = ml_service._extract_features(
            product_id=product_id,
            market_date=market_date,
        )

        # Verify defaults
        assert features_df['temp_f'].values[0] == 70.0
        assert features_df['is_special_event'].values[0] == 0
        assert features_df['venue_avg_sales'].values[0] == 0.0
        assert features_df['avg_sales_last_7d'].values[0] == 0

    def test_train_model_success(self, ml_service, mock_db):
        """Test successful model training with sufficient data"""
        product_id = uuid4()

        # Mock sufficient sales data (20 sales)
        mock_sales = []
        for i in range(20):
            sale = MagicMock()
            sale.sale_date = datetime(2025, 1, 1) + timedelta(days=i)
            sale.weather_temp_f = 70.0
            sale.weather_condition = 'clear'
            sale.line_items = [{'quantity': '10'}]
            mock_sales.append(sale)

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = mock_sales

        success = ml_service._train_model(product_id=product_id)

        assert success is True
        assert ml_service.model_trained is True
        assert ml_service.scaler_fitted is True

    def test_train_model_insufficient_data(self, ml_service, mock_db):
        """Test model training with insufficient sales data"""
        product_id = uuid4()

        # Mock only 5 sales (less than MIN_HISTORY_DAYS=14)
        mock_sales = []
        for i in range(5):
            sale = MagicMock()
            sale.sale_date = datetime(2025, 1, 1) + timedelta(days=i)
            sale.weather_temp_f = 70.0
            sale.weather_condition = 'clear'
            sale.line_items = [{'quantity': '10'}]
            mock_sales.append(sale)

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = mock_sales

        success = ml_service._train_model(product_id=product_id)

        assert success is False
        assert ml_service.model_trained is False

    @patch('src.services.ml_recommendations.logger')
    def test_train_model_no_training_samples_extracted(self, mock_logger, ml_service, mock_db):
        """Test model training when feature extraction fails for all sales

        This tests the scenario where sales exist but feature extraction
        fails for all of them, resulting in no training samples (empty X_list).
        """
        product_id = uuid4()

        # Mock sufficient sales (20 sales)
        mock_sales = []
        for i in range(20):
            sale = MagicMock()
            sale.sale_date = datetime(2025, 1, 1) + timedelta(days=i)
            sale.weather_temp_f = 70.0
            sale.weather_condition = 'clear'
            sale.line_items = [{'quantity': '10'}]
            mock_sales.append(sale)

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = mock_sales

        # Mock _extract_features to raise exception for all sales
        # This will cause all sales to be skipped, leaving X_list empty
        with patch.object(ml_service, '_extract_features', side_effect=Exception("Feature extraction failed")):
            success = ml_service._train_model(product_id=product_id)

            # Should return False when no samples extracted
            assert success is False

            # Should log the warning about no training samples
            mock_logger.warning.assert_any_call("No training samples extracted")

    def test_generate_fallback_recommendation_with_sales_history(self, ml_service, mock_db):
        """Test fallback heuristics with sales history"""
        product_id = uuid4()
        market_date = datetime(2025, 6, 1)

        # Mock sales history
        mock_sales = []
        for i in range(10):
            sale = MagicMock()
            sale.sale_date = market_date - timedelta(days=i+1)
            sale.line_items = [{'product_id': str(product_id), 'quantity': '8'}]
            mock_sales.append(sale)

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = mock_sales

        recommended_qty = ml_service._generate_fallback_recommendation(
            product_id=product_id,
            market_date=market_date,
        )

        # Should use average of recent sales (8)
        assert recommended_qty == 8

    def test_generate_fallback_recommendation_no_sales_history(self, ml_service, mock_db):
        """Test fallback heuristics with no sales history"""
        product_id = uuid4()
        market_date = datetime(2025, 6, 1)

        # Mock no sales
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []

        recommended_qty = ml_service._generate_fallback_recommendation(
            product_id=product_id,
            market_date=market_date,
        )

        # Should use conservative default (5)
        assert recommended_qty == 5

    def test_generate_fallback_recommendation_with_event(self, ml_service, mock_db):
        """Test fallback with event data multiplier"""
        product_id = uuid4()
        market_date = datetime(2025, 6, 1)

        # Mock sales history with average of 10
        mock_sales = [
            MagicMock(
                sale_date=market_date - timedelta(days=1),
                line_items=[{'product_id': str(product_id), 'quantity': '10'}],
            )
        ]

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = mock_sales

        event_data = {'expected_attendance': 1500}  # Large event

        recommended_qty = ml_service._generate_fallback_recommendation(
            product_id=product_id,
            market_date=market_date,
            event_data=event_data,
        )

        # Should apply 1.5x multiplier for attendance >= 1000
        assert recommended_qty == 15  # 10 * 1.5

    def test_generate_fallback_recommendation_with_weather(self, ml_service, mock_db):
        """Test fallback with weather adjustment"""
        product_id = uuid4()
        market_date = datetime(2025, 6, 1)

        # Mock sales history
        mock_sales = [
            MagicMock(
                sale_date=market_date - timedelta(days=1),
                line_items=[{'product_id': str(product_id), 'quantity': '10'}],
            )
        ]

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = mock_sales

        weather_data = {'condition': 'rainy'}

        recommended_qty = ml_service._generate_fallback_recommendation(
            product_id=product_id,
            market_date=market_date,
            weather_data=weather_data,
        )

        # Should apply 0.8x multiplier for rain
        assert recommended_qty == 8  # 10 * 0.8

    def test_generate_recommendation_uses_fallback_when_model_not_trained(self, ml_service, mock_db):
        """Test that fallback is used when model training fails"""
        product_id = uuid4()
        market_date = datetime(2025, 6, 1)

        # Mock product for revenue calculation
        mock_product = MagicMock()
        mock_product.id = product_id
        mock_product.price = Decimal("10.00")

        # Mock insufficient sales for training
        mock_sales = [
            MagicMock(
                sale_date=market_date - timedelta(days=1),
                line_items=[{'product_id': str(product_id), 'quantity': '10'}],
            )
        ]

        def query_side_effect(model):
            if hasattr(model, '__tablename__') and model.__tablename__ == 'products':
                return MagicMock(filter=MagicMock(return_value=MagicMock(first=MagicMock(return_value=mock_product))))
            else:  # Sales query
                return MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            order_by=MagicMock(return_value=MagicMock(all=MagicMock(return_value=mock_sales))),
                            all=MagicMock(return_value=mock_sales),
                        )
                    )
                )

        mock_db.query.side_effect = query_side_effect

        recommendation = ml_service.generate_recommendation(
            product_id=product_id,
            market_date=market_date,
        )

        # Verify fallback was used
        assert recommendation is not None
        assert recommendation.recommended_quantity == 10
        assert recommendation.confidence_score == Decimal("0.5")  # Fallback confidence
        assert recommendation.historical_features['using_fallback'] is True

    def test_generate_recommendations_for_date(self, ml_service, mock_db):
        """Test batch recommendations for all active products"""
        market_date = datetime(2025, 6, 1)

        # Mock active products
        mock_products = [
            MagicMock(id=uuid4(), is_active=True, price=Decimal("10.00")),
            MagicMock(id=uuid4(), is_active=True, price=Decimal("15.00")),
            MagicMock(id=uuid4(), is_active=True, price=Decimal("20.00")),
        ]

        # Mock sales for fallback
        mock_sales = [
            MagicMock(
                sale_date=market_date - timedelta(days=1),
                line_items=[{'quantity': '10'}],
            )
        ]

        call_count = {'count': 0}

        def query_side_effect(model):
            if hasattr(model, '__tablename__') and model.__tablename__ == 'products':
                # First call - list products query
                query = MagicMock()
                query.filter.return_value = query
                query.limit.return_value = query
                query.all.return_value = mock_products
                return query
            elif hasattr(model, '__tablename__') and model.__tablename__ == 'products' and call_count['count'] > 0:
                # Subsequent calls - individual product queries for recommendations
                call_count['count'] += 1
                return MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(first=MagicMock(return_value=mock_products[call_count['count'] % 3]))
                    )
                )
            else:  # Sales queries
                return MagicMock(
                    filter=MagicMock(
                        return_value=MagicMock(
                            order_by=MagicMock(return_value=MagicMock(all=MagicMock(return_value=mock_sales))),
                            all=MagicMock(return_value=mock_sales),
                        )
                    )
                )

        mock_db.query.side_effect = query_side_effect

        recommendations = ml_service.generate_recommendations_for_date(
            market_date=market_date,
            limit=10,
        )

        # Should generate recommendations for all 3 products
        assert len(recommendations) == 3

    def test_get_feedback_for_training(self, ml_service, mock_db):
        """Test retrieving feedback data for model retraining"""

        # Mock recommendations with feedback
        mock_recs_feedback = []
        for i in range(5):
            rec = MagicMock()
            rec.id = uuid4()
            rec.product_id = uuid4()
            rec.market_date = datetime(2025, 1, 1) + timedelta(days=i)
            rec.recommended_quantity = 10
            rec.weather_features = {'temp_f': 70.0}
            rec.event_features = {'is_special_event': 0}
            rec.historical_features = {'avg_sales': 8.0}

            feedback = MagicMock()
            feedback.actual_quantity_sold = 9
            feedback.actual_revenue = Decimal("90.00")
            feedback.variance_percentage = Decimal("10.0")
            feedback.was_accurate = True
            feedback.rating = 4

            mock_recs_feedback.append((rec, feedback))

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = mock_recs_feedback

        training_examples = ml_service.get_feedback_for_training(
            days_back=90,
            min_rating=3,
        )

        # Verify training examples
        assert len(training_examples) == 5
        for example in training_examples:
            assert 'recommendation_id' in example
            assert 'product_id' in example
            assert 'features' in example
            assert 'actual_quantity_sold' in example
            assert 'rating' in example
