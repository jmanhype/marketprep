"""
Unit tests for RecommendationFeedback Model

Tests the calculate_variance method and variance calculations.
"""

from decimal import Decimal
from uuid import uuid4

from src.models.recommendation_feedback import RecommendationFeedback


class TestRecommendationFeedbackCalculateVariance:
    """Test calculate_variance method"""

    def test_calculate_variance_with_no_actual_quantity_sold(self):
        """Test calculate_variance returns early when actual_quantity_sold is None (covers line 137)"""
        feedback = RecommendationFeedback(
            id=uuid4(),
            vendor_id=uuid4(),
            recommendation_id=uuid4(),
            actual_quantity_sold=None  # None value
        )

        # Call calculate_variance
        feedback.calculate_variance(recommended_quantity=10)

        # Should return early, no values calculated
        assert feedback.quantity_variance is None
        assert feedback.variance_percentage is None
        assert feedback.was_accurate is None
        assert feedback.was_overstocked is None
        assert feedback.was_understocked is None

    def test_calculate_variance_with_zero_recommended_quantity(self):
        """Test calculate_variance when recommended_quantity is 0 (covers line 150)"""
        feedback = RecommendationFeedback(
            id=uuid4(),
            vendor_id=uuid4(),
            recommendation_id=uuid4(),
            actual_quantity_sold=5
        )

        # Call with recommended_quantity = 0
        feedback.calculate_variance(recommended_quantity=0)

        # Should handle division by zero gracefully
        assert feedback.quantity_variance == Decimal(5)
        assert feedback.variance_percentage == Decimal(0)
        # With 0% variance, should be accurate
        assert feedback.was_accurate is True
        assert feedback.was_overstocked is False
        assert feedback.was_understocked is False

    def test_calculate_variance_normal_case(self):
        """Test calculate_variance with normal values"""
        feedback = RecommendationFeedback(
            id=uuid4(),
            vendor_id=uuid4(),
            recommendation_id=uuid4(),
            actual_quantity_sold=12
        )

        # Recommended 10, sold 12 = +20% variance
        feedback.calculate_variance(recommended_quantity=10)

        assert feedback.quantity_variance == Decimal(2)
        assert feedback.variance_percentage == Decimal(20)
        assert feedback.was_accurate is True  # Exactly at 20% threshold
        assert feedback.was_overstocked is False
        assert feedback.was_understocked is False

    def test_calculate_variance_understocked(self):
        """Test calculate_variance identifies understock situation"""
        feedback = RecommendationFeedback(
            id=uuid4(),
            vendor_id=uuid4(),
            recommendation_id=uuid4(),
            actual_quantity_sold=15
        )

        # Recommended 10, sold 15 = +50% variance (understock)
        feedback.calculate_variance(recommended_quantity=10)

        assert feedback.quantity_variance == Decimal(5)
        assert feedback.variance_percentage == Decimal(50)
        assert feedback.was_accurate is False
        assert feedback.was_overstocked is False
        assert feedback.was_understocked is True

    def test_calculate_variance_overstocked(self):
        """Test calculate_variance identifies overstock situation"""
        feedback = RecommendationFeedback(
            id=uuid4(),
            vendor_id=uuid4(),
            recommendation_id=uuid4(),
            actual_quantity_sold=5
        )

        # Recommended 10, sold 5 = -50% variance (overstock)
        feedback.calculate_variance(recommended_quantity=10)

        assert feedback.quantity_variance == Decimal(-5)
        assert feedback.variance_percentage == Decimal(-50)
        assert feedback.was_accurate is False
        assert feedback.was_overstocked is True
        assert feedback.was_understocked is False
