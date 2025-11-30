"""Unit tests for ML recommendation service.

Tests ML-powered inventory recommendations including:
- Feature extraction
- Model training
- Prediction generation
- Fallback heuristics
- Venue-specific features
- Seasonal detection
"""
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4, UUID
from unittest.mock import MagicMock, patch
import numpy as np
import pandas as pd

from src.services.ml_recommendations import (
    MLRecommendationService,
    VenueFeatureEngineer,
    MLModelError,
)


class TestVenueFeatureEngineer:
    """Test venue feature engineering."""

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    @pytest.fixture
    def venue_id(self):
        """Test venue ID."""
        return uuid4()

    @pytest.fixture
    def product_id(self):
        """Test product ID."""
        return uuid4()

    @pytest.fixture
    def db_session(self):
        """Mock database session."""
        return MagicMock()

    @pytest.fixture
    def engineer(self, vendor_id, db_session):
        """Create venue feature engineer."""
        return VenueFeatureEngineer(vendor_id=vendor_id, db=db_session)

    def test_extract_venue_features_new_venue(self, engineer, venue_id, product_id):
        """Test feature extraction for new venue with no sales history."""
        engineer._get_venue_product_sales = MagicMock(return_value=[])

        features = engineer.extract_venue_features(
            venue_id=venue_id,
            product_id=product_id,
            market_date=datetime(2025, 6, 15),
        )

        assert features['venue_avg_sales'] == 0.0
        assert features['venue_max_sales'] == 0.0
        assert features['venue_sales_count'] == 0.0
        assert features['venue_last_sale_days_ago'] == 999.0

    def test_extract_venue_features_with_history(self, engineer, venue_id, product_id):
        """Test feature extraction for venue with sales history."""
        mock_sales = [
            {'date': datetime(2025, 5, 1), 'quantity': 10},
            {'date': datetime(2025, 5, 8), 'quantity': 15},
            {'date': datetime(2025, 5, 15), 'quantity': 12},
        ]
        engineer._get_venue_product_sales = MagicMock(return_value=mock_sales)

        market_date = datetime(2025, 6, 15)
        features = engineer.extract_venue_features(
            venue_id=venue_id,
            product_id=product_id,
            market_date=market_date,
        )

        assert features['venue_avg_sales'] == pytest.approx(12.33, rel=0.01)
        assert features['venue_max_sales'] == 15.0
        assert features['venue_sales_count'] == 3.0
        assert features['venue_last_sale_days_ago'] == 31.0  # Days from May 15 to June 15

    def test_calculate_venue_confidence_new_venue(self, engineer, venue_id, product_id):
        """Test confidence calculation for new venue."""
        engineer._get_venue_product_sales = MagicMock(return_value=[])

        confidence = engineer.calculate_venue_confidence(
            venue_id=venue_id,
            product_id=product_id,
            market_date=datetime(2025, 6, 15),
        )

        assert confidence == 0.3  # New venue = low confidence

    def test_calculate_venue_confidence_stale_venue(self, engineer, venue_id, product_id):
        """Test confidence for venue with stale data (>6 months)."""
        old_sales = [
            {'date': datetime(2024, 10, 1), 'quantity': 10},
        ]
        engineer._get_venue_product_sales = MagicMock(return_value=old_sales)

        confidence = engineer.calculate_venue_confidence(
            venue_id=venue_id,
            product_id=product_id,
            market_date=datetime(2025, 6, 15),
        )

        assert confidence == 0.5  # Stale venue = medium confidence

    def test_calculate_venue_confidence_high(self, engineer, venue_id, product_id):
        """Test high confidence for established venue."""
        # Create 20+ recent sales
        recent_sales = [
            {'date': datetime(2025, 5, i), 'quantity': 10}
            for i in range(1, 22)
        ]
        engineer._get_venue_product_sales = MagicMock(return_value=recent_sales)

        confidence = engineer.calculate_venue_confidence(
            venue_id=venue_id,
            product_id=product_id,
            market_date=datetime(2025, 6, 15),
        )

        assert confidence == 0.85  # High confidence

    def test_is_seasonal_product_insufficient_data(self, engineer, product_id):
        """Test seasonal detection with insufficient data."""
        # Only 1 month of data (< 3 required)
        with patch.object(engineer, '_get_monthly_sales_pattern', return_value={1: 10.0}):
            is_seasonal = engineer.is_seasonal_product(
                product_id=product_id,
                month=6,
            )

        assert is_seasonal == False

    def test_is_seasonal_product_detected(self, vendor_id, db_session, product_id):
        """Test detection of seasonal product."""
        # Summer months have much higher sales (seasonal)
        # Mean = 12.25, Std = 9.52
        # July (35.0): z-score = 2.39 (> 1.5, so seasonal)
        monthly_pattern = {
            1: 5.0,   # Winter
            2: 5.0,
            3: 8.0,   # Spring
            4: 10.0,
            5: 10.0,
            6: 15.0,  # Pre-summer
            7: 35.0,  # Summer - peak (z-score = 2.39)
            8: 30.0,  # Summer - peak
            9: 10.0,  # Fall
            10: 8.0,
            11: 6.0,
            12: 5.0,  # Winter
        }

        # Create new engineer instance and mock the method
        engineer = VenueFeatureEngineer(vendor_id=vendor_id, db=db_session)

        with patch.object(engineer, '_get_monthly_sales_pattern', return_value=monthly_pattern) as mock_method:
            # July should be detected as seasonal (high peak)
            is_seasonal = engineer.is_seasonal_product(
                product_id=product_id,
                month=7,
            )

            # Verify mock was called
            assert mock_method.called

        # Use == instead of 'is' since numpy.bool_ != Python bool
        assert is_seasonal == True

    def test_is_seasonal_product_not_seasonal(self, engineer, product_id):
        """Test non-seasonal product."""
        # Consistent sales year-round (z-score = 0 for all months)
        monthly_pattern = {i: 10.0 for i in range(1, 13)}

        with patch.object(engineer, '_get_monthly_sales_pattern', return_value=monthly_pattern):
            is_seasonal = engineer.is_seasonal_product(
                product_id=product_id,
                month=6,
            )

        assert is_seasonal == False


class TestMLRecommendationService:
    """Test ML recommendation service."""

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    @pytest.fixture
    def product_id(self):
        """Test product ID."""
        return uuid4()

    @pytest.fixture
    def venue_id(self):
        """Test venue ID."""
        return uuid4()

    @pytest.fixture
    def db_session(self):
        """Mock database session."""
        mock_db = MagicMock()

        # Mock product query
        mock_product = MagicMock()
        mock_product.id = uuid4()
        mock_product.price = Decimal("5.99")
        mock_product.is_active = True

        mock_db.query.return_value.filter.return_value.first.return_value = mock_product
        mock_db.query.return_value.filter.return_value.limit.return_value.all.return_value = [mock_product]

        return mock_db

    @pytest.fixture
    def ml_service(self, vendor_id, db_session):
        """Create ML service instance."""
        return MLRecommendationService(vendor_id=vendor_id, db=db_session)

    def test_extract_features_basic(self, ml_service, product_id):
        """Test basic feature extraction."""
        ml_service._get_recent_sales_for_product = MagicMock(return_value=[])
        ml_service.venue_engineer.extract_venue_features = MagicMock(return_value={
            'venue_avg_sales': 0.0,
            'venue_max_sales': 0.0,
            'venue_sales_count': 0.0,
            'venue_last_sale_days_ago': 0.0,
        })
        ml_service.venue_engineer.generate_venue_embedding = MagicMock(return_value=[0.0] * 5)
        ml_service.venue_engineer.is_seasonal_product = MagicMock(return_value=False)
        ml_service.venue_engineer._get_monthly_sales_pattern = MagicMock(return_value={})

        market_date = datetime(2025, 6, 14, 10, 0)  # Saturday

        features_df = ml_service._extract_features(
            product_id=product_id,
            market_date=market_date,
        )

        assert isinstance(features_df, pd.DataFrame)
        assert 'day_of_week' in features_df.columns
        assert 'month' in features_df.columns
        assert features_df['day_of_week'].values[0] == 5  # Saturday (weekday() == 5)
        assert features_df['month'].values[0] == 6

    def test_extract_features_with_weather(self, ml_service, product_id):
        """Test feature extraction with weather data."""
        ml_service._get_recent_sales_for_product = MagicMock(return_value=[])
        ml_service.venue_engineer.extract_venue_features = MagicMock(return_value={})
        ml_service.venue_engineer.generate_venue_embedding = MagicMock(return_value=[0.0] * 5)
        ml_service.venue_engineer.is_seasonal_product = MagicMock(return_value=False)
        ml_service.venue_engineer._get_monthly_sales_pattern = MagicMock(return_value={})

        weather_data = {
            'temp_f': 85.0,
            'feels_like_f': 90.0,
            'humidity': 70.0,
            'condition': 'sunny',
        }

        features_df = ml_service._extract_features(
            product_id=product_id,
            market_date=datetime(2025, 6, 15),
            weather_data=weather_data,
        )

        assert features_df['temp_f'].values[0] == 85.0
        assert features_df['feels_like_f'].values[0] == 90.0
        assert features_df['humidity'].values[0] == 70.0
        assert features_df['is_sunny'].values[0] == 1
        assert features_df['is_rainy'].values[0] == 0

    def test_extract_features_with_event(self, ml_service, product_id):
        """Test feature extraction with event data."""
        ml_service._get_recent_sales_for_product = MagicMock(return_value=[])
        ml_service.venue_engineer.extract_venue_features = MagicMock(return_value={})
        ml_service.venue_engineer.generate_venue_embedding = MagicMock(return_value=[0.0] * 5)
        ml_service.venue_engineer.is_seasonal_product = MagicMock(return_value=False)
        ml_service.venue_engineer._get_monthly_sales_pattern = MagicMock(return_value={})

        event_data = {
            'expected_attendance': 2000,
            'is_special': True,
        }

        features_df = ml_service._extract_features(
            product_id=product_id,
            market_date=datetime(2025, 6, 15),
            event_data=event_data,
        )

        assert features_df['is_special_event'].values[0] == 1
        assert features_df['expected_attendance'].values[0] == 2000

    def test_fallback_recommendation_no_history(self, ml_service, product_id):
        """Test fallback recommendation with no sales history."""
        ml_service._get_recent_sales_for_product = MagicMock(return_value=[])

        quantity = ml_service._generate_fallback_recommendation(
            product_id=product_id,
            market_date=datetime(2025, 6, 15),
        )

        assert quantity == 5  # Conservative default

    def test_fallback_recommendation_with_history(self, ml_service, product_id):
        """Test fallback recommendation with sales history."""
        mock_sales = [
            {'quantity': 10},
            {'quantity': 12},
            {'quantity': 8},
        ]
        ml_service._get_recent_sales_for_product = MagicMock(return_value=mock_sales)

        quantity = ml_service._generate_fallback_recommendation(
            product_id=product_id,
            market_date=datetime(2025, 6, 15),
        )

        assert quantity == 10  # Average of [10, 12, 8]

    def test_fallback_recommendation_with_event(self, ml_service, product_id):
        """Test fallback recommendation applies event multiplier."""
        mock_sales = [{'quantity': 10}] * 5
        ml_service._get_recent_sales_for_product = MagicMock(return_value=mock_sales)

        event_data = {'expected_attendance': 1500}

        quantity = ml_service._generate_fallback_recommendation(
            product_id=product_id,
            market_date=datetime(2025, 6, 15),
            event_data=event_data,
        )

        assert quantity == 15  # 10 * 1.5 (large event multiplier)

    def test_fallback_recommendation_with_weather(self, ml_service, product_id):
        """Test fallback recommendation applies weather adjustment."""
        mock_sales = [{'quantity': 10}] * 5
        ml_service._get_recent_sales_for_product = MagicMock(return_value=mock_sales)

        # Rainy weather
        weather_data = {'condition': 'rainy'}

        quantity = ml_service._generate_fallback_recommendation(
            product_id=product_id,
            market_date=datetime(2025, 6, 15),
            weather_data=weather_data,
        )

        assert quantity == 8  # 10 * 0.8 (rainy penalty)

    def test_generate_recommendation_uses_fallback_when_not_trained(
        self, ml_service, product_id
    ):
        """Test recommendation generation falls back when model not trained."""
        ml_service._get_recent_sales_for_product = MagicMock(return_value=[{'quantity': 10}] * 5)
        ml_service._train_model = MagicMock(return_value=False)  # Training fails

        recommendation = ml_service.generate_recommendation(
            product_id=product_id,
            market_date=datetime(2025, 6, 15),
        )

        assert recommendation.recommended_quantity >= 1
        assert recommendation.confidence_score == Decimal("0.5")  # Fallback confidence

    def test_generate_recommendation_with_ml_model(self, ml_service, product_id):
        """Test recommendation generation with trained ML model."""
        # Mock successful training
        ml_service.model_trained = True
        ml_service.scaler_fitted = True

        # Mock feature extraction with all required columns
        mock_features = pd.DataFrame([{
            'day_of_week': 5,
            'month': 6,
            'temp_f': 75.0,
            'humidity': 50.0,
            'avg_sales_last_7d': 10.0,
            'avg_sales_last_14d': 12.0,
            'venue_avg_sales': 11.0,
            'venue_sales_count': 5.0,
            'venue_last_sale_days_ago': 3.0,
            'is_seasonal': 0,
            'seasonal_strength': 0.0,
            'month_avg_sales': 10.0,
        }])
        ml_service._extract_features = MagicMock(return_value=mock_features)

        # Mock scaler and model prediction
        ml_service.scaler.transform = MagicMock(return_value=np.array([[0.5] * 12]))
        ml_service.model.predict = MagicMock(return_value=np.array([12.6]))

        # Mock venue engineer confidence
        ml_service.venue_engineer.calculate_venue_confidence = MagicMock(return_value=0.75)

        recommendation = ml_service.generate_recommendation(
            product_id=product_id,
            market_date=datetime(2025, 6, 15),
            venue_id=uuid4(),
        )

        assert recommendation.recommended_quantity == 13  # Rounded from 12.6
        assert recommendation.confidence_score == Decimal("0.75")

    def test_generate_recommendations_for_date_batch(self, ml_service, db_session):
        """Test batch recommendation generation for multiple products."""
        # Mock successful ML prediction
        ml_service.model_trained = True
        ml_service.scaler_fitted = True

        # Mock with all required columns
        mock_features = pd.DataFrame([{
            'day_of_week': 5,
            'avg_sales_last_7d': 10.0,
            'avg_sales_last_14d': 12.0,
            'is_seasonal': 0,
            'seasonal_strength': 0.0,
            'month_avg_sales': 11.0,
        }])
        ml_service._extract_features = MagicMock(return_value=mock_features)
        ml_service.scaler.transform = MagicMock(return_value=np.array([[0.5] * 6]))
        ml_service.model.predict = MagicMock(return_value=np.array([10.0]))

        # Mock 3 products
        mock_products = [MagicMock(id=uuid4(), price=Decimal("5.99")) for _ in range(3)]
        db_session.query.return_value.filter.return_value.limit.return_value.all.return_value = mock_products

        recommendations = ml_service.generate_recommendations_for_date(
            market_date=datetime(2025, 6, 15),
            limit=10,
        )

        assert len(recommendations) == 3
        for rec in recommendations:
            assert rec.recommended_quantity > 0

    def test_model_version_tracking(self, ml_service, product_id):
        """Test that recommendations include model version."""
        ml_service._get_recent_sales_for_product = MagicMock(return_value=[{'quantity': 10}])
        ml_service._train_model = MagicMock(return_value=False)

        recommendation = ml_service.generate_recommendation(
            product_id=product_id,
            market_date=datetime(2025, 6, 15),
        )

        assert recommendation.model_version == "v1.0.0"

    def test_minimum_quantity_enforced(self, ml_service, product_id):
        """Test that recommended quantity is always at least 1."""
        ml_service.model_trained = True
        ml_service.scaler_fitted = True

        # Mock with all required columns
        mock_features = pd.DataFrame([{
            'day_of_week': 5,
            'avg_sales_last_7d': 0.5,
            'avg_sales_last_14d': 0.3,
            'is_seasonal': 0,
            'seasonal_strength': 0.0,
            'month_avg_sales': 0.2,
        }])
        ml_service._extract_features = MagicMock(return_value=mock_features)
        ml_service.scaler.transform = MagicMock(return_value=np.array([[0.5] * 6]))
        ml_service.model.predict = MagicMock(return_value=np.array([0.1]))  # Very low prediction

        recommendation = ml_service.generate_recommendation(
            product_id=product_id,
            market_date=datetime(2025, 6, 15),
        )

        assert recommendation.recommended_quantity >= 1  # Minimum enforced

    def test_generate_recommendation_scaler_not_fitted(self, ml_service, product_id):
        """Test recommendation falls back when scaler not fitted."""
        ml_service.model_trained = True
        ml_service.scaler_fitted = False
        ml_service._get_recent_sales_for_product = MagicMock(return_value=[{'quantity': 8}] * 3)

        recommendation = ml_service.generate_recommendation(
            product_id=product_id,
            market_date=datetime(2025, 6, 15),
        )

        # Should use fallback
        assert recommendation.confidence_score == Decimal("0.5")

    def test_generate_recommendation_scaling_fails(self, ml_service, product_id):
        """Test recommendation falls back when feature scaling fails."""
        ml_service.model_trained = True
        ml_service.scaler_fitted = True

        mock_features = pd.DataFrame([{'day_of_week': 5}])
        ml_service._extract_features = MagicMock(return_value=mock_features)
        ml_service.scaler.transform = MagicMock(side_effect=ValueError("Scaling error"))
        ml_service._get_recent_sales_for_product = MagicMock(return_value=[{'quantity': 10}])

        recommendation = ml_service.generate_recommendation(
            product_id=product_id,
            market_date=datetime(2025, 6, 15),
        )

        # Should fall back to heuristics
        assert recommendation.recommended_quantity >= 1
        assert recommendation.confidence_score == Decimal("0.5")

    def test_generate_recommendation_prediction_fails(self, ml_service, product_id):
        """Test recommendation falls back when model prediction fails."""
        ml_service.model_trained = True
        ml_service.scaler_fitted = True

        mock_features = pd.DataFrame([{'day_of_week': 5}])
        ml_service._extract_features = MagicMock(return_value=mock_features)
        ml_service.scaler.transform = MagicMock(return_value=np.array([[0.5]]))
        ml_service.model.predict = MagicMock(side_effect=Exception("Prediction error"))
        ml_service._get_recent_sales_for_product = MagicMock(return_value=[{'quantity': 7}] * 2)

        recommendation = ml_service.generate_recommendation(
            product_id=product_id,
            market_date=datetime(2025, 6, 15),
        )

        # Should fall back to heuristics
        assert recommendation.recommended_quantity >= 1
        assert recommendation.confidence_score == Decimal("0.5")

    def test_generate_recommendations_for_date_handles_individual_failures(self, ml_service, db_session):
        """Test batch generation continues when individual recommendations fail."""
        # Mock 3 products
        product1 = MagicMock(id=uuid4(), price=Decimal("5.99"))
        product2 = MagicMock(id=uuid4(), price=Decimal("7.99"))
        product3 = MagicMock(id=uuid4(), price=Decimal("3.99"))

        db_session.query.return_value.filter.return_value.limit.return_value.all.return_value = [
            product1, product2, product3
        ]

        # Make second product fail
        def mock_generate_rec(product_id, **kwargs):
            if product_id == product2.id:
                raise Exception("Generation failed")

            rec = MagicMock()
            rec.recommended_quantity = 10
            return rec

        ml_service.generate_recommendation = MagicMock(side_effect=mock_generate_rec)

        recommendations = ml_service.generate_recommendations_for_date(
            market_date=datetime(2025, 6, 15),
            limit=10,
        )

        # Should have 2 recommendations (product2 failed)
        assert len(recommendations) == 2

    def test_fallback_sunny_weather_boost(self, ml_service, product_id):
        """Test fallback applies sunny weather boost."""
        mock_sales = [{'quantity': 10}] * 5
        ml_service._get_recent_sales_for_product = MagicMock(return_value=mock_sales)

        weather_data = {'condition': 'sunny'}

        quantity = ml_service._generate_fallback_recommendation(
            product_id=product_id,
            market_date=datetime(2025, 6, 15),
            weather_data=weather_data,
        )

        assert quantity == 11  # 10 * 1.1 (sunny boost)

    def test_fallback_snow_weather_penalty(self, ml_service, product_id):
        """Test fallback applies snow weather penalty."""
        mock_sales = [{'quantity': 10}] * 5
        ml_service._get_recent_sales_for_product = MagicMock(return_value=mock_sales)

        weather_data = {'condition': 'snow'}

        quantity = ml_service._generate_fallback_recommendation(
            product_id=product_id,
            market_date=datetime(2025, 6, 15),
            weather_data=weather_data,
        )

        assert quantity == 8  # 10 * 0.8 (snow penalty)

    def test_fallback_medium_event_multiplier(self, ml_service, product_id):
        """Test fallback applies medium event multiplier."""
        mock_sales = [{'quantity': 10}] * 5
        ml_service._get_recent_sales_for_product = MagicMock(return_value=mock_sales)

        event_data = {'expected_attendance': 600}

        quantity = ml_service._generate_fallback_recommendation(
            product_id=product_id,
            market_date=datetime(2025, 6, 15),
            event_data=event_data,
        )

        assert quantity == 13  # 10 * 1.3 (medium event)


class TestVenueEmbedding:
    """Test venue embedding generation."""

    @pytest.fixture
    def vendor_id(self):
        return uuid4()

    @pytest.fixture
    def venue_id(self):
        return uuid4()

    @pytest.fixture
    def db_session(self):
        return MagicMock()

    @pytest.fixture
    def engineer(self, vendor_id, db_session):
        return VenueFeatureEngineer(vendor_id=vendor_id, db=db_session)

    def test_generate_venue_embedding_no_venue(self, engineer, venue_id):
        """Test embedding for non-existent venue."""
        engineer.db.query.return_value.filter.return_value.first.return_value = None

        embedding = engineer.generate_venue_embedding(venue_id)

        assert embedding == [0.0] * 5
        assert len(embedding) == 5

    def test_generate_venue_embedding_with_location(self, engineer, venue_id):
        """Test embedding for venue with location data."""
        mock_venue = MagicMock()
        mock_venue.typical_attendance = 500
        mock_venue.latitude = Decimal("40.7128")
        mock_venue.longitude = Decimal("-74.0060")

        engineer.db.query.return_value.filter.return_value.first.return_value = mock_venue
        engineer._get_venue_total_sales = MagicMock(return_value=250.0)
        engineer._get_venue_first_sale_date = MagicMock(return_value=datetime(2024, 1, 1))

        embedding = engineer.generate_venue_embedding(venue_id)

        assert len(embedding) == 5
        # Check attendance feature (500/1000 = 0.5)
        assert embedding[0] == pytest.approx(0.5, rel=0.01)
        # Latitude normalized (40.7128 / 90.0 ≈ 0.452)
        assert embedding[1] == pytest.approx(40.7128 / 90.0, rel=0.01)
        # Longitude normalized (-74.0060 / 180.0 ≈ -0.411)
        # Note: This can be negative since longitude ranges from -180 to 180
        assert embedding[2] == pytest.approx(-74.0060 / 180.0, rel=0.01)

    def test_generate_venue_embedding_no_location(self, engineer, venue_id):
        """Test embedding for venue without location data."""
        mock_venue = MagicMock()
        mock_venue.typical_attendance = 200
        mock_venue.latitude = None
        mock_venue.longitude = None

        engineer.db.query.return_value.filter.return_value.first.return_value = mock_venue
        engineer._get_venue_total_sales = MagicMock(return_value=100.0)
        engineer._get_venue_first_sale_date = MagicMock(return_value=None)

        embedding = engineer.generate_venue_embedding(venue_id)

        assert len(embedding) == 5
        # Should use default 0.5 for missing location
        assert embedding[1] == 0.5
        assert embedding[2] == 0.5
        # Should use 0.0 for missing first sale date
        assert embedding[4] == 0.0


class TestVenueConfidenceInterpolation:
    """Test venue confidence calculation edge cases."""

    @pytest.fixture
    def vendor_id(self):
        return uuid4()

    @pytest.fixture
    def venue_id(self):
        return uuid4()

    @pytest.fixture
    def product_id(self):
        return uuid4()

    @pytest.fixture
    def engineer(self, vendor_id):
        return VenueFeatureEngineer(vendor_id=vendor_id, db=MagicMock())

    def test_calculate_venue_confidence_interpolation(self, engineer, venue_id, product_id):
        """Test confidence interpolation between MIN and HIGH thresholds."""
        # Create 10 sales (between MIN_VENUE_SALES=3 and HIGH_CONFIDENCE_SALES=20)
        recent_sales = [
            {'date': datetime(2025, 5, i), 'quantity': 10}
            for i in range(1, 11)
        ]
        engineer._get_venue_product_sales = MagicMock(return_value=recent_sales)

        confidence = engineer.calculate_venue_confidence(
            venue_id=venue_id,
            product_id=product_id,
            market_date=datetime(2025, 6, 15),
        )

        # Should be between 0.6 and 0.85 (interpolated)
        # With 10 sales: progress = (10-3)/(20-3) = 7/17 ≈ 0.41
        # confidence = 0.6 + (0.25 * 0.41) ≈ 0.70
        assert 0.6 < confidence < 0.85

    def test_calculate_venue_confidence_low(self, engineer, venue_id, product_id):
        """Test confidence for venue with insufficient sales."""
        # Only 2 sales (< MIN_VENUE_SALES=3)
        recent_sales = [
            {'date': datetime(2025, 5, 1), 'quantity': 10},
            {'date': datetime(2025, 5, 2), 'quantity': 12},
        ]
        engineer._get_venue_product_sales = MagicMock(return_value=recent_sales)

        confidence = engineer.calculate_venue_confidence(
            venue_id=venue_id,
            product_id=product_id,
            market_date=datetime(2025, 6, 15),
        )

        assert confidence == 0.4  # Low confidence
