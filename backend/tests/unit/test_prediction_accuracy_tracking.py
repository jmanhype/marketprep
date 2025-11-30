"""
Unit tests for prediction accuracy tracking

Tests accuracy monitoring:
- Vendor accuracy calculations (SC-002)
- Product-level accuracy
- Overall system accuracy
- Accuracy trends over time
- Poor performing product identification
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock
from sqlalchemy import func

from src.services.prediction_accuracy_tracking import (
    PredictionAccuracyTracker,
    AccuracyMetrics,
    monitor_prediction_accuracy,
)


class TestVendorAccuracy:
    """Test vendor-level accuracy calculations"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return MagicMock()

    @pytest.fixture
    def tracker(self, mock_db):
        """Create prediction accuracy tracker"""
        return PredictionAccuracyTracker(db=mock_db)

    def test_calculate_vendor_accuracy_with_feedback(self, tracker, mock_db):
        """Test vendor accuracy calculation with feedback data"""
        vendor_id = "vendor-123"

        # Mock feedback records (8 accurate out of 10 = 80%)
        mock_feedback = []
        for i in range(10):
            feedback = MagicMock()
            feedback.was_accurate = i < 8  # First 8 are accurate
            feedback.was_overstocked = i >= 8 and i < 9
            feedback.was_understocked = i >= 9
            feedback.variance_percentage = 15.0 if i < 8 else 25.0
            mock_feedback.append(feedback)

        # Mock queries
        call_count = [0]

        def mock_query_side_effect(*args):
            result = MagicMock()
            result.join.return_value = result
            result.filter.return_value = result
            result.all.return_value = mock_feedback

            call_count[0] += 1
            if call_count[0] == 1:
                # First call: feedback records
                result.all.return_value = mock_feedback
            else:
                # Second call: total predictions count
                result.scalar.return_value = 50

            return result

        mock_db.query.side_effect = mock_query_side_effect

        # Calculate accuracy
        metrics = tracker.calculate_vendor_accuracy(vendor_id, days_back=30)

        # Verify metrics
        assert isinstance(metrics, AccuracyMetrics)
        assert metrics.total_predictions == 50
        assert metrics.predictions_with_feedback == 10
        assert metrics.accurate_predictions == 8
        assert metrics.accuracy_rate == 80.0
        assert metrics.overstock_rate == 10.0  # 1/10
        assert metrics.understock_rate == 10.0  # 1/10
        assert metrics.meets_success_criterion is True  # 80% ≥ 70%

    def test_calculate_vendor_accuracy_no_feedback(self, tracker, mock_db):
        """Test vendor accuracy with no feedback data"""
        vendor_id = "vendor-456"

        # Mock queries to return no feedback
        call_count = [0]

        def mock_query_side_effect(*args):
            result = MagicMock()
            result.join.return_value = result
            result.filter.return_value = result

            call_count[0] += 1
            if call_count[0] == 1:
                # Feedback query
                result.all.return_value = []
            else:
                # Total predictions
                result.scalar.return_value = 20

            return result

        mock_db.query.side_effect = mock_query_side_effect

        # Calculate accuracy
        metrics = tracker.calculate_vendor_accuracy(vendor_id)

        assert metrics.total_predictions == 20
        assert metrics.predictions_with_feedback == 0
        assert metrics.accurate_predictions == 0
        assert metrics.accuracy_rate == 0.0
        assert metrics.meets_success_criterion is False

    def test_calculate_vendor_accuracy_below_threshold(self, tracker, mock_db):
        """Test vendor accuracy below SC-002 threshold"""
        vendor_id = "vendor-789"

        # Mock feedback records (5 accurate out of 10 = 50%)
        mock_feedback = []
        for i in range(10):
            feedback = MagicMock()
            feedback.was_accurate = i < 5  # Only 5 accurate (50%)
            feedback.was_overstocked = False
            feedback.was_understocked = False
            feedback.variance_percentage = 30.0
            mock_feedback.append(feedback)

        # Mock queries
        call_count = [0]

        def mock_query_side_effect(*args):
            result = MagicMock()
            result.join.return_value = result
            result.filter.return_value = result

            call_count[0] += 1
            if call_count[0] == 1:
                result.all.return_value = mock_feedback
            else:
                result.scalar.return_value = 15

            return result

        mock_db.query.side_effect = mock_query_side_effect

        metrics = tracker.calculate_vendor_accuracy(vendor_id)

        assert metrics.accuracy_rate == 50.0
        assert metrics.meets_success_criterion is False  # 50% < 70%


class TestProductAccuracy:
    """Test product-level accuracy calculations"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return MagicMock()

    @pytest.fixture
    def tracker(self, mock_db):
        """Create prediction accuracy tracker"""
        return PredictionAccuracyTracker(db=mock_db)

    def test_calculate_product_accuracy_with_feedback(self, tracker, mock_db):
        """Test product accuracy with feedback"""
        vendor_id = "vendor-123"
        product_id = "product-456"

        # Mock feedback records
        mock_feedback = []
        for i in range(5):
            feedback = MagicMock()
            feedback.was_accurate = i < 4  # 4 out of 5 accurate (80%)
            feedback.variance_percentage = 10.0
            mock_feedback.append(feedback)

        # Mock queries
        call_count = [0]

        def mock_query_side_effect(*args):
            result = MagicMock()
            result.join.return_value = result
            result.filter.return_value = result

            call_count[0] += 1
            if call_count[0] == 1:
                result.all.return_value = mock_feedback
            else:
                result.scalar.return_value = 10

            return result

        mock_db.query.side_effect = mock_query_side_effect

        metrics = tracker.calculate_product_accuracy(vendor_id, product_id)

        assert metrics.total_predictions == 10
        assert metrics.predictions_with_feedback == 5
        assert metrics.accurate_predictions == 4
        assert metrics.accuracy_rate == 80.0
        assert metrics.meets_success_criterion is True

    def test_calculate_product_accuracy_no_feedback(self, tracker, mock_db):
        """Test product accuracy with no feedback"""
        vendor_id = "vendor-123"
        product_id = "product-789"

        # Mock queries
        call_count = [0]

        def mock_query_side_effect(*args):
            result = MagicMock()
            result.join.return_value = result
            result.filter.return_value = result

            call_count[0] += 1
            if call_count[0] == 1:
                result.all.return_value = []
            else:
                result.scalar.return_value = 5

            return result

        mock_db.query.side_effect = mock_query_side_effect

        metrics = tracker.calculate_product_accuracy(vendor_id, product_id)

        assert metrics.total_predictions == 5
        assert metrics.predictions_with_feedback == 0
        assert metrics.accuracy_rate == 0.0


class TestOverallAccuracy:
    """Test overall system accuracy calculations"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return MagicMock()

    @pytest.fixture
    def tracker(self, mock_db):
        """Create prediction accuracy tracker"""
        return PredictionAccuracyTracker(db=mock_db)

    def test_calculate_overall_accuracy_with_feedback(self, tracker, mock_db):
        """Test overall system accuracy"""
        # Mock feedback records (70 accurate out of 100 = 70%)
        mock_feedback = []
        for i in range(100):
            feedback = MagicMock()
            feedback.was_accurate = i < 70
            feedback.was_overstocked = i >= 70 and i < 85
            feedback.was_understocked = i >= 85
            feedback.variance_percentage = 18.0
            mock_feedback.append(feedback)

        # Mock queries
        call_count = [0]

        def mock_query_side_effect(*args):
            result = MagicMock()
            result.filter.return_value = result

            call_count[0] += 1
            if call_count[0] == 1:
                result.all.return_value = mock_feedback
            else:
                result.scalar.return_value = 500

            return result

        mock_db.query.side_effect = mock_query_side_effect

        metrics = tracker.calculate_overall_accuracy()

        assert metrics.total_predictions == 500
        assert metrics.predictions_with_feedback == 100
        assert metrics.accurate_predictions == 70
        assert metrics.accuracy_rate == 70.0
        assert metrics.overstock_rate == 15.0  # 15/100
        assert metrics.understock_rate == 15.0  # 15/100
        assert metrics.meets_success_criterion is True  # Exactly at 70% threshold

    def test_calculate_overall_accuracy_no_feedback(self, tracker, mock_db):
        """Test overall accuracy with no feedback"""
        # Mock queries
        call_count = [0]

        def mock_query_side_effect(*args):
            result = MagicMock()
            result.filter.return_value = result

            call_count[0] += 1
            if call_count[0] == 1:
                result.all.return_value = []
            else:
                result.scalar.return_value = 200

            return result

        mock_db.query.side_effect = mock_query_side_effect

        metrics = tracker.calculate_overall_accuracy()

        assert metrics.total_predictions == 200
        assert metrics.predictions_with_feedback == 0
        assert metrics.meets_success_criterion is False


class TestAccuracyTrend:
    """Test accuracy trend analysis"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return MagicMock()

    @pytest.fixture
    def tracker(self, mock_db):
        """Create prediction accuracy tracker"""
        return PredictionAccuracyTracker(db=mock_db)

    def test_get_accuracy_trend(self, tracker, mock_db):
        """Test getting accuracy trend over weeks"""
        vendor_id = "vendor-123"

        # Mock feedback for each week query
        def mock_query_side_effect(*args):
            result = MagicMock()
            result.join.return_value = result
            result.filter.return_value = result

            # Return different feedback for each week
            mock_feedback = []
            for i in range(5):
                feedback = MagicMock()
                feedback.was_accurate = i < 4  # 4/5 = 80%
                mock_feedback.append(feedback)

            result.all.return_value = mock_feedback
            return result

        mock_db.query.side_effect = mock_query_side_effect

        trend = tracker.get_accuracy_trend(vendor_id, weeks=2)

        # Should have data for 2 weeks
        assert len(trend) == 2
        for week_data in trend:
            assert "week_start" in week_data
            assert "week_end" in week_data
            assert "feedback_count" in week_data
            assert "accurate_count" in week_data
            assert "accuracy_rate" in week_data
            assert "meets_criterion" in week_data
            assert week_data["accuracy_rate"] == 80.0
            assert week_data["meets_criterion"] is True

    def test_get_accuracy_trend_no_data(self, tracker, mock_db):
        """Test accuracy trend with no data"""
        vendor_id = "vendor-456"

        # Mock query to return no feedback
        def mock_query_side_effect(*args):
            result = MagicMock()
            result.join.return_value = result
            result.filter.return_value = result
            result.all.return_value = []
            return result

        mock_db.query.side_effect = mock_query_side_effect

        trend = tracker.get_accuracy_trend(vendor_id, weeks=4)

        # Should have empty trend
        assert len(trend) == 0


class TestPoorPerformingProducts:
    """Test identification of poorly performing products"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return MagicMock()

    @pytest.fixture
    def tracker(self, mock_db):
        """Create prediction accuracy tracker"""
        return PredictionAccuracyTracker(db=mock_db)

    def test_get_poorly_performing_products(self, tracker, mock_db):
        """Test identifying poorly performing products"""
        vendor_id = "vendor-123"

        # Mock products query
        mock_products = [("product-1",), ("product-2",), ("product-3",)]

        # Mock queries
        call_count = [0]

        def mock_query_side_effect(*args):
            result = MagicMock()
            result.join.return_value = result
            result.filter.return_value = result
            result.distinct.return_value = result

            call_count[0] += 1

            # First call: get all products
            if call_count[0] == 1:
                result.all.return_value = mock_products
            # Subsequent calls: feedback for each product
            elif call_count[0] in [2, 4, 6]:
                # Feedback records - alternating poor and good performance
                product_num = (call_count[0] - 2) // 2
                if product_num == 0:
                    # Product 1: Poor (40% accuracy)
                    mock_feedback = []
                    for i in range(10):
                        feedback = MagicMock()
                        feedback.was_accurate = i < 4
                        feedback.variance_percentage = 35.0
                        mock_feedback.append(feedback)
                    result.all.return_value = mock_feedback
                elif product_num == 1:
                    # Product 2: Good (90% accuracy)
                    mock_feedback = []
                    for i in range(10):
                        feedback = MagicMock()
                        feedback.was_accurate = i < 9
                        feedback.variance_percentage = 10.0
                        mock_feedback.append(feedback)
                    result.all.return_value = mock_feedback
                else:
                    # Product 3: Poor (30% accuracy)
                    mock_feedback = []
                    for i in range(10):
                        feedback = MagicMock()
                        feedback.was_accurate = i < 3
                        feedback.variance_percentage = 40.0
                        mock_feedback.append(feedback)
                    result.all.return_value = mock_feedback
            # Total predictions count
            else:
                result.scalar.return_value = 15

            return result

        mock_db.query.side_effect = mock_query_side_effect

        # Get poorly performing products (< 50% accuracy)
        poor_performers = tracker.get_poorly_performing_products(
            vendor_id,
            min_predictions=5,
            accuracy_threshold=50.0
        )

        # Should have 2 poor performers (product-1 and product-3)
        assert len(poor_performers) == 2
        assert poor_performers[0]["accuracy_rate"] < 50.0
        assert poor_performers[1]["accuracy_rate"] < 50.0

        # Should be sorted by accuracy (worst first)
        assert poor_performers[0]["accuracy_rate"] <= poor_performers[1]["accuracy_rate"]


class TestMonitoringFunction:
    """Test scheduled monitoring function"""

    def test_monitor_prediction_accuracy(self):
        """Test prediction accuracy monitoring"""
        mock_db = MagicMock()

        # Mock overall feedback (75% accurate)
        mock_overall_feedback = []
        for i in range(100):
            feedback = MagicMock()
            feedback.was_accurate = i < 75
            feedback.was_overstocked = False
            feedback.was_understocked = False
            feedback.variance_percentage = 15.0
            mock_overall_feedback.append(feedback)

        # Mock vendor query to return 2 vendors
        mock_vendors = [("vendor-1",), ("vendor-2",)]

        # Mock vendor-specific feedback
        mock_vendor_feedback = []
        for i in range(10):
            feedback = MagicMock()
            feedback.was_accurate = i < 8  # 80% accurate
            feedback.was_overstocked = False
            feedback.was_understocked = False
            feedback.variance_percentage = 12.0
            mock_vendor_feedback.append(feedback)

        # Mock queries
        call_count = [0]

        def mock_query_side_effect(*args):
            result = MagicMock()
            result.join.return_value = result
            result.filter.return_value = result
            result.distinct.return_value = result

            call_count[0] += 1

            # Overall accuracy queries
            if call_count[0] == 1:
                result.all.return_value = mock_overall_feedback
            elif call_count[0] == 2:
                result.scalar.return_value = 500
            # Vendor list query
            elif call_count[0] == 3:
                result.all.return_value = mock_vendors
            # Vendor 1 feedback
            elif call_count[0] == 4:
                result.all.return_value = mock_vendor_feedback
            elif call_count[0] == 5:
                result.scalar.return_value = 20
            # Vendor 2 feedback
            elif call_count[0] == 6:
                result.all.return_value = mock_vendor_feedback
            else:
                result.scalar.return_value = 20

            return result

        mock_db.query.side_effect = mock_query_side_effect

        report = monitor_prediction_accuracy(mock_db)

        # Verify report structure
        assert "monitored_at" in report
        assert "overall_accuracy" in report
        assert "vendor_count" in report
        assert "vendors_meeting_sc002" in report
        assert "vendors_failing_sc002" in report

        # Verify overall accuracy
        assert report["overall_accuracy"]["meets_sc002"] is True
        assert report["overall_accuracy"]["accuracy_rate"] == 75.0

        # Verify vendor counts
        assert report["vendor_count"] == 2
        assert report["vendors_meeting_sc002"] == 2  # Both vendors at 80%
        assert report["vendors_failing_sc002"] == 0
