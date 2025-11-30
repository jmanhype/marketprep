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


class TestVenueProductSales:
    """Test venue-specific product sales extraction."""

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
    def db_session(self):
        return MagicMock()

    @pytest.fixture
    def engineer(self, vendor_id, db_session):
        return VenueFeatureEngineer(vendor_id=vendor_id, db=db_session)

    def test_get_venue_product_sales_with_line_items(self, engineer, venue_id, product_id):
        """Test extracting sales with line items matching product_id."""
        # Mock sale with line items
        mock_sale1 = MagicMock()
        mock_sale1.sale_date = datetime(2025, 5, 1)
        mock_sale1.line_items = [
            {'product_id': str(product_id), 'quantity': '10'},
            {'product_id': str(uuid4()), 'quantity': '5'},  # Different product
        ]

        mock_sale2 = MagicMock()
        mock_sale2.sale_date = datetime(2025, 5, 5)
        mock_sale2.line_items = [
            {'product_id': str(product_id), 'quantity': '8'},
        ]

        # Mock query chain
        mock_query = MagicMock()
        engineer.db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [mock_sale1, mock_sale2]

        sales = engineer._get_venue_product_sales(
            venue_id=venue_id,
            product_id=product_id,
            before_date=datetime(2025, 6, 1),
            days_back=30,
        )

        # Should only include matching product
        assert len(sales) == 2
        assert sales[0]['quantity'] == 10
        assert sales[0]['date'] == datetime(2025, 5, 1)
        assert sales[1]['quantity'] == 8
        assert sales[1]['date'] == datetime(2025, 5, 5)

    def test_get_venue_product_sales_no_line_items(self, engineer, venue_id, product_id):
        """Test sales without line items are skipped."""
        mock_sale = MagicMock()
        mock_sale.line_items = None

        mock_query = MagicMock()
        engineer.db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [mock_sale]

        sales = engineer._get_venue_product_sales(
            venue_id=venue_id,
            product_id=product_id,
            before_date=datetime(2025, 6, 1),
        )

        assert len(sales) == 0

    def test_get_venue_product_sales_no_matching_product(self, engineer, venue_id, product_id):
        """Test sales with line items but no matching product_id."""
        mock_sale = MagicMock()
        mock_sale.sale_date = datetime(2025, 5, 1)
        mock_sale.line_items = [
            {'product_id': str(uuid4()), 'quantity': '10'},  # Different product
        ]

        mock_query = MagicMock()
        engineer.db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [mock_sale]

        sales = engineer._get_venue_product_sales(
            venue_id=venue_id,
            product_id=product_id,
            before_date=datetime(2025, 6, 1),
        )

        assert len(sales) == 0


class TestMonthlySalesPattern:
    """Test monthly sales pattern extraction."""

    @pytest.fixture
    def vendor_id(self):
        return uuid4()

    @pytest.fixture
    def product_id(self):
        return uuid4()

    @pytest.fixture
    def db_session(self):
        return MagicMock()

    @pytest.fixture
    def engineer(self, vendor_id, db_session):
        return VenueFeatureEngineer(vendor_id=vendor_id, db=db_session)

    def test_get_monthly_sales_pattern(self, engineer, product_id):
        """Test monthly sales pattern calculation."""
        # Create sales across multiple months
        sales = []

        # January - 2 sales
        for i in range(2):
            sale = MagicMock()
            sale.sale_date = datetime(2025, 1, i + 1)
            sale.line_items = [{'product_id': str(product_id), 'quantity': '10'}]
            sales.append(sale)

        # February - 3 sales
        for i in range(3):
            sale = MagicMock()
            sale.sale_date = datetime(2025, 2, i + 1)
            sale.line_items = [{'product_id': str(product_id), 'quantity': '15'}]
            sales.append(sale)

        mock_query = MagicMock()
        engineer.db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = sales

        pattern = engineer._get_monthly_sales_pattern(product_id)

        # January: avg of [10, 10] = 10.0
        # February: avg of [15, 15, 15] = 15.0
        assert pattern[1] == 10.0
        assert pattern[2] == 15.0

    def test_get_monthly_sales_pattern_skip_empty_line_items(self, engineer, product_id):
        """Test sales without line items are skipped."""
        sale1 = MagicMock()
        sale1.sale_date = datetime(2025, 1, 1)
        sale1.line_items = None

        sale2 = MagicMock()
        sale2.sale_date = datetime(2025, 1, 2)
        sale2.line_items = [{'product_id': str(product_id), 'quantity': '10'}]

        mock_query = MagicMock()
        engineer.db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [sale1, sale2]

        pattern = engineer._get_monthly_sales_pattern(product_id)

        # Only sale2 should be counted
        assert pattern[1] == 10.0


class TestVenueHelperMethods:
    """Test venue helper methods."""

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

    def test_get_venue_total_sales(self, engineer, venue_id):
        """Test getting total sales count for a venue."""
        mock_query = MagicMock()
        engineer.db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.scalar.return_value = 42

        total = engineer._get_venue_total_sales(venue_id)

        assert total == 42.0

    def test_get_venue_total_sales_none(self, engineer, venue_id):
        """Test getting total sales when none exist."""
        mock_query = MagicMock()
        engineer.db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.scalar.return_value = None

        total = engineer._get_venue_total_sales(venue_id)

        assert total == 0.0

    def test_get_venue_first_sale_date(self, engineer, venue_id):
        """Test getting first sale date for a venue."""
        first_date = datetime(2024, 1, 1)

        mock_query = MagicMock()
        engineer.db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = (first_date,)

        result = engineer._get_venue_first_sale_date(venue_id)

        assert result == first_date

    def test_get_venue_first_sale_date_no_sales(self, engineer, venue_id):
        """Test getting first sale date when no sales exist."""
        mock_query = MagicMock()
        engineer.db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = None

        result = engineer._get_venue_first_sale_date(venue_id)

        assert result is None


class TestRecentSalesForProduct:
    """Test recent sales extraction for product."""

    @pytest.fixture
    def vendor_id(self):
        return uuid4()

    @pytest.fixture
    def product_id(self):
        return uuid4()

    @pytest.fixture
    def db_session(self):
        return MagicMock()

    @pytest.fixture
    def ml_service(self, vendor_id, db_session):
        return MLRecommendationService(vendor_id=vendor_id, db=db_session)

    def test_get_recent_sales_for_product(self, ml_service, product_id):
        """Test extracting recent sales for a product."""
        # Create sales with line items
        sale1 = MagicMock()
        sale1.sale_date = datetime(2025, 5, 1)
        sale1.line_items = [
            {'quantity': '10'},
            {'quantity': '5'},
        ]

        sale2 = MagicMock()
        sale2.sale_date = datetime(2025, 5, 5)
        sale2.line_items = [
            {'quantity': '8'},
        ]

        mock_query = MagicMock()
        ml_service.db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [sale1, sale2]

        sales = ml_service._get_recent_sales_for_product(
            product_id=product_id,
            before_date=datetime(2025, 6, 1),
            days_back=30,
        )

        # Should extract all line items (3 total)
        assert len(sales) == 3
        assert sales[0]['quantity'] == 10
        assert sales[1]['quantity'] == 5
        assert sales[2]['quantity'] == 8

    def test_get_recent_sales_for_product_no_line_items(self, ml_service, product_id):
        """Test extracting sales when line items are missing."""
        sale = MagicMock()
        sale.sale_date = datetime(2025, 5, 1)
        sale.line_items = None

        mock_query = MagicMock()
        ml_service.db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [sale]

        sales = ml_service._get_recent_sales_for_product(
            product_id=product_id,
            before_date=datetime(2025, 6, 1),
        )

        assert len(sales) == 0


class TestModelTraining:
    """Test ML model training."""

    @pytest.fixture
    def vendor_id(self):
        return uuid4()

    @pytest.fixture
    def product_id(self):
        return uuid4()

    @pytest.fixture
    def db_session(self):
        return MagicMock()

    @pytest.fixture
    def ml_service(self, vendor_id, db_session):
        return MLRecommendationService(vendor_id=vendor_id, db=db_session)

    def test_train_model_insufficient_data(self, ml_service, product_id):
        """Test training fails with insufficient data."""
        # Return fewer sales than MIN_HISTORY_DAYS (14)
        mock_query = MagicMock()
        ml_service.db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [MagicMock()] * 10  # Only 10 sales

        result = ml_service._train_model(product_id)

        assert result is False
        assert ml_service.model_trained is False

    def test_train_model_no_training_samples(self, ml_service, product_id):
        """Test training fails when no samples can be extracted."""
        # Create sales with no line items
        sales = []
        for i in range(20):
            sale = MagicMock()
            sale.sale_date = datetime(2025, 1, i + 1)
            sale.line_items = None  # No line items
            sale.weather_temp_f = 70.0
            sale.weather_condition = 'clear'
            sales.append(sale)

        mock_query = MagicMock()
        ml_service.db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = sales

        # Mock _extract_features to avoid errors
        ml_service._extract_features = MagicMock(return_value=pd.DataFrame([{}]))

        result = ml_service._train_model(product_id)

        # Should fail because no quantities extracted (all sales have no line items)
        assert result is False

    def test_train_model_scaler_fit_fails(self, ml_service, product_id):
        """Test training fails when scaler fit fails."""
        # Create valid sales
        sales = []
        for i in range(20):
            sale = MagicMock()
            sale.sale_date = datetime(2025, 1, i + 1)
            sale.line_items = [{'quantity': '10'}]
            sale.weather_temp_f = 70.0
            sale.weather_condition = 'clear'
            sales.append(sale)

        mock_query = MagicMock()
        ml_service.db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = sales

        # Mock _extract_features
        ml_service._extract_features = MagicMock(return_value=pd.DataFrame([{'feature': 1.0}]))

        # Make scaler fit_transform fail
        ml_service.scaler.fit_transform = MagicMock(side_effect=ValueError("Scaler error"))

        result = ml_service._train_model(product_id)

        assert result is False
        assert ml_service.scaler_fitted is False

    def test_train_model_fit_fails(self, ml_service, product_id):
        """Test training fails when model fit fails."""
        # Create valid sales
        sales = []
        for i in range(20):
            sale = MagicMock()
            sale.sale_date = datetime(2025, 1, i + 1)
            sale.line_items = [{'quantity': '10'}]
            sale.weather_temp_f = 70.0
            sale.weather_condition = 'clear'
            sales.append(sale)

        mock_query = MagicMock()
        ml_service.db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = sales

        # Mock _extract_features
        ml_service._extract_features = MagicMock(return_value=pd.DataFrame([{'feature': 1.0}]))

        # Scaler succeeds but model fit fails
        ml_service.scaler.fit_transform = MagicMock(return_value=np.array([[1.0]]))
        ml_service.model.fit = MagicMock(side_effect=Exception("Model fit error"))

        result = ml_service._train_model(product_id)

        assert result is False
        assert ml_service.model_trained is False


class TestUnexpectedExceptions:
    """Test exception handling in generate_recommendation."""

    @pytest.fixture
    def vendor_id(self):
        return uuid4()

    @pytest.fixture
    def product_id(self):
        return uuid4()

    @pytest.fixture
    def db_session(self):
        # Mock product query for revenue calculation
        mock_db = MagicMock()
        mock_product = MagicMock()
        mock_product.price = Decimal("5.99")
        mock_db.query.return_value.filter.return_value.first.return_value = mock_product
        return mock_db

    @pytest.fixture
    def ml_service(self, vendor_id, db_session):
        return MLRecommendationService(vendor_id=vendor_id, db=db_session)

    def test_generate_recommendation_unexpected_exception(self, ml_service, product_id):
        """Test unexpected exception falls back to heuristics."""
        # Make _train_model raise an unexpected exception
        ml_service._train_model = MagicMock(side_effect=RuntimeError("Unexpected error"))
        ml_service._get_recent_sales_for_product = MagicMock(return_value=[{'quantity': 10}] * 3)

        recommendation = ml_service.generate_recommendation(
            product_id=product_id,
            market_date=datetime(2025, 6, 15),
        )

        # Should fall back to heuristics
        assert recommendation.recommended_quantity >= 1
        assert recommendation.confidence_score == Decimal("0.5")


class TestFeedbackForTraining:
    """Test feedback retrieval for model retraining."""

    @pytest.fixture
    def vendor_id(self):
        return uuid4()

    @pytest.fixture
    def db_session(self):
        return MagicMock()

    @pytest.fixture
    def ml_service(self, vendor_id, db_session):
        return MLRecommendationService(vendor_id=vendor_id, db=db_session)

    def test_get_feedback_for_training(self, ml_service):
        """Test retrieving feedback with features."""
        # Create mock recommendation and feedback
        rec = MagicMock()
        rec.id = uuid4()
        rec.product_id = uuid4()
        rec.market_date = datetime(2025, 5, 15)
        rec.recommended_quantity = 10
        rec.weather_features = {'temp_f': 75.0, 'condition': 'sunny'}
        rec.event_features = {'expected_attendance': 500}
        rec.historical_features = {'avg_sales_last_7d': 8.0}

        feedback = MagicMock()
        feedback.actual_quantity_sold = 12
        feedback.actual_revenue = Decimal("71.88")
        feedback.variance_percentage = Decimal("20.0")
        feedback.was_accurate = True
        feedback.rating = 5

        # Mock query chain
        mock_query = MagicMock()
        ml_service.db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [(rec, feedback)]

        examples = ml_service.get_feedback_for_training(days_back=90, min_rating=3)

        assert len(examples) == 1
        assert examples[0]['actual_quantity_sold'] == 12
        assert examples[0]['recommended_quantity'] == 10
        assert examples[0]['rating'] == 5
        assert 'temp_f' in examples[0]['features']
        assert 'expected_attendance' in examples[0]['features']
        assert examples[0]['features']['day_of_week'] == 3  # Thursday

    def test_get_feedback_for_training_empty(self, ml_service):
        """Test retrieving feedback when none exists."""
        mock_query = MagicMock()
        ml_service.db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        examples = ml_service.get_feedback_for_training()

        assert len(examples) == 0


class TestSeasonalStrength:
    """Test seasonal strength calculation in feature extraction."""

    @pytest.fixture
    def vendor_id(self):
        return uuid4()

    @pytest.fixture
    def product_id(self):
        return uuid4()

    @pytest.fixture
    def db_session(self):
        return MagicMock()

    @pytest.fixture
    def ml_service(self, vendor_id, db_session):
        return MLRecommendationService(vendor_id=vendor_id, db=db_session)

    def test_extract_features_seasonal_strength(self, ml_service, product_id):
        """Test seasonal strength calculation when monthly pattern exists."""
        ml_service._get_recent_sales_for_product = MagicMock(return_value=[])
        ml_service.venue_engineer.extract_venue_features = MagicMock(return_value={})
        ml_service.venue_engineer.generate_venue_embedding = MagicMock(return_value=[0.0] * 5)
        ml_service.venue_engineer.is_seasonal_product = MagicMock(return_value=True)

        # Mock monthly pattern: June (month 6) has 20.0 avg, overall avg is 10.0
        ml_service.venue_engineer._get_monthly_sales_pattern = MagicMock(return_value={
            1: 5.0,
            2: 8.0,
            3: 10.0,
            4: 12.0,
            5: 15.0,
            6: 20.0,  # June - higher than average
            7: 18.0,
            8: 10.0,
            9: 8.0,
            10: 6.0,
            11: 5.0,
            12: 5.0,
        })

        features_df = ml_service._extract_features(
            product_id=product_id,
            market_date=datetime(2025, 6, 15),  # June
        )

        # Seasonal strength = (20.0 - 10.17) / (10.17 + 1) ≈ 0.88
        assert features_df['seasonal_strength'].values[0] > 0.5  # Significantly positive
        assert features_df['month_avg_sales'].values[0] == 20.0


class TestExtractFeaturesWithVenue:
    """Test _extract_features with venue_id to cover venue feature integration."""

    @pytest.fixture
    def vendor_id(self):
        return uuid4()

    @pytest.fixture
    def product_id(self):
        return uuid4()

    @pytest.fixture
    def venue_id(self):
        return uuid4()

    @pytest.fixture
    def db_session(self):
        return MagicMock()

    @pytest.fixture
    def ml_service(self, vendor_id, db_session):
        return MLRecommendationService(vendor_id=vendor_id, db=db_session)

    def test_extract_features_with_venue_id(self, ml_service, product_id, venue_id):
        """Test feature extraction with venue_id calls venue methods."""
        # Mock the venue engineer methods to avoid database calls
        ml_service._get_recent_sales_for_product = MagicMock(return_value=[])

        # Mock venue features extraction
        ml_service.venue_engineer.extract_venue_features = MagicMock(return_value={
            'venue_avg_sales': 12.0,
            'venue_max_sales': 20.0,
            'venue_sales_count': 5.0,
            'venue_last_sale_days_ago': 3.0,
        })

        # Mock venue embedding generation
        ml_service.venue_engineer.generate_venue_embedding = MagicMock(return_value=[0.1, 0.2, 0.3, 0.4, 0.5])

        ml_service.venue_engineer.is_seasonal_product = MagicMock(return_value=False)
        ml_service.venue_engineer._get_monthly_sales_pattern = MagicMock(return_value={})

        # Call _extract_features WITH venue_id to cover lines 467-477
        features_df = ml_service._extract_features(
            product_id=product_id,
            market_date=datetime(2025, 6, 15),
            venue_id=venue_id,  # This triggers the venue feature extraction path
        )

        # Verify venue methods were called
        ml_service.venue_engineer.extract_venue_features.assert_called_once()
        ml_service.venue_engineer.generate_venue_embedding.assert_called_once_with(venue_id)

        # Verify venue features are in the dataframe
        assert features_df['venue_avg_sales'].values[0] == 12.0
        assert features_df['venue_max_sales'].values[0] == 20.0
        assert features_df['venue_sales_count'].values[0] == 5.0
        assert features_df['venue_last_sale_days_ago'].values[0] == 3.0

        # Verify venue embeddings are included
        assert features_df['venue_emb_0'].values[0] == 0.1
        assert features_df['venue_emb_1'].values[0] == 0.2
        assert features_df['venue_emb_2'].values[0] == 0.3
        assert features_df['venue_emb_3'].values[0] == 0.4
        assert features_df['venue_emb_4'].values[0] == 0.5


class TestModelTrainingSuccess:
    """Test successful model training path."""

    @pytest.fixture
    def vendor_id(self):
        return uuid4()

    @pytest.fixture
    def product_id(self):
        return uuid4()

    @pytest.fixture
    def db_session(self):
        return MagicMock()

    @pytest.fixture
    def ml_service(self, vendor_id, db_session):
        return MLRecommendationService(vendor_id=vendor_id, db=db_session)

    def test_train_model_success(self, ml_service, product_id):
        """Test successful model training to cover success path lines 627-629."""
        # Create valid sales with line items (20 sales to meet MIN_HISTORY_DAYS)
        sales = []
        for i in range(20):
            sale = MagicMock()
            sale.sale_date = datetime(2025, 1, i + 1)
            sale.line_items = [
                {'quantity': '10'},
                {'quantity': '5'},
            ]
            sale.weather_temp_f = 70.0 + i  # Vary temperature
            sale.weather_condition = 'sunny' if i % 2 == 0 else 'clear'
            sales.append(sale)

        # Mock query chain
        mock_query = MagicMock()
        ml_service.db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = sales

        # Mock _extract_features to return valid dataframe
        mock_features = pd.DataFrame([{
            'day_of_week': 5,
            'month': 6,
            'temp_f': 75.0,
            'humidity': 50.0,
        }])
        ml_service._extract_features = MagicMock(return_value=mock_features)

        # Mock scaler and model to succeed
        ml_service.scaler.fit_transform = MagicMock(return_value=np.array([[0.5, 0.6, 0.7, 0.8]] * 20))
        ml_service.model.fit = MagicMock(return_value=None)  # fit() returns None on success

        # Train model
        result = ml_service._train_model(product_id)

        # Should succeed and set flags
        assert result is True
        assert ml_service.model_trained is True
        assert ml_service.scaler_fitted is True

        # Verify fit was called
        ml_service.model.fit.assert_called_once()
