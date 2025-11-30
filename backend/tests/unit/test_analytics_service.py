"""
Unit tests for analytics service

Tests user metrics collection:
- User satisfaction calculations (SC-003)
- Task completion calculations (SC-008)
- Adoption rate calculations (SC-012)
- Engagement metrics
- Vendor-specific metrics
- Feature usage tracking
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock
from sqlalchemy import func

from src.services.analytics_service import AnalyticsService, UserMetrics, collect_and_log_metrics


class TestUserMetricsCollection:
    """Test comprehensive user metrics collection"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return MagicMock()

    @pytest.fixture
    def analytics_service(self, mock_db):
        """Create analytics service with mocked db"""
        return AnalyticsService(db=mock_db)

    def test_collect_user_metrics_all_success_criteria_met(self, analytics_service, mock_db):
        """Test collecting metrics when all success criteria are met"""
        # Mock satisfaction metrics (≥80% target)
        mock_ratings = [(5,), (5,), (4,), (4,), (5,)]  # 100% satisfied (all ≥4)

        # Mock task completion (≥90% target)
        mock_total_recs = 100
        mock_completed = 95  # 95% completion

        # Mock adoption (≥60% target)
        mock_vendors = [("vendor1",), ("vendor2",), ("vendor3",)]
        mock_active = [("vendor1",), ("vendor2",)]  # 67% adoption

        # Mock engagement
        mock_recs_generated = 100
        mock_recs_used = 80

        # Setup query mocks with call tracking
        call_count = [0]

        def mock_query_side_effect(model_or_func):
            result = MagicMock()
            result.filter.return_value = result
            result.join.return_value = result
            result.scalar.return_value = None
            result.all.return_value = []

            call_count[0] += 1

            # Satisfaction ratings query (call 1)
            if call_count[0] == 1:
                result.all.return_value = mock_ratings
            # Task completion - total recommendations (call 2)
            elif call_count[0] == 2:
                result.scalar.return_value = mock_total_recs
            # Task completion - completed workflows (call 3)
            elif call_count[0] == 3:
                result.scalar.return_value = mock_completed
            # Adoption - vendors with sales (call 4)
            elif call_count[0] == 4:
                result.all.return_value = mock_vendors
            # Adoption - vendors using recommendations (call 5)
            elif call_count[0] == 5:
                result.all.return_value = mock_active
            # Engagement - recommendations generated (call 6)
            elif call_count[0] == 6:
                result.scalar.return_value = mock_recs_generated
            # Engagement - recommendations used (call 7)
            elif call_count[0] == 7:
                result.scalar.return_value = mock_recs_used

            return result

        mock_db.query.side_effect = mock_query_side_effect

        # Collect metrics
        metrics = analytics_service.collect_user_metrics(days_back=30)

        # Verify all success criteria met
        assert isinstance(metrics, UserMetrics)
        assert metrics.meets_sc003 is True  # 100% satisfaction
        assert metrics.meets_sc008 is True  # 95% completion
        assert metrics.meets_sc012 is True  # 67% adoption
        assert metrics.avg_rating == 4.6
        assert metrics.satisfaction_rate == 100.0
        assert metrics.task_completion_rate == 95.0
        assert metrics.adoption_rate == 66.67

    def test_calculate_satisfaction_no_ratings(self, analytics_service, mock_db):
        """Test satisfaction calculation with no ratings"""
        # Mock query to return no ratings
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        cutoff_date = datetime.utcnow() - timedelta(days=30)
        result = analytics_service._calculate_satisfaction(cutoff_date)

        assert result["avg_rating"] == 0.0
        assert result["total_ratings"] == 0
        assert result["satisfaction_rate"] == 0.0

    def test_calculate_satisfaction_with_ratings(self, analytics_service, mock_db):
        """Test satisfaction calculation with mixed ratings"""
        # Mock ratings: 5, 4, 4, 3, 2 -> 3 satisfied (≥4), 2 unsatisfied
        mock_ratings = [(5,), (4,), (4,), (3,), (2,)]

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = mock_ratings

        cutoff_date = datetime.utcnow() - timedelta(days=30)
        result = analytics_service._calculate_satisfaction(cutoff_date)

        # Avg: (5+4+4+3+2)/5 = 3.6
        # Satisfied: 3/5 = 60%
        assert result["avg_rating"] == 3.6
        assert result["total_ratings"] == 5
        assert result["satisfaction_rate"] == 60.0

    def test_calculate_task_completion_no_recommendations(self, analytics_service, mock_db):
        """Test task completion with no recommendations"""
        # Mock query to return 0 recommendations
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.scalar.return_value = 0

        cutoff_date = datetime.utcnow() - timedelta(days=30)
        result = analytics_service._calculate_task_completion(cutoff_date)

        assert result == 0.0

    def test_calculate_task_completion_with_feedback(self, analytics_service, mock_db):
        """Test task completion calculation"""
        # Mock queries
        call_count = [0]

        def mock_query_side_effect(*args):
            result = MagicMock()
            result.filter.return_value = result
            result.join.return_value = result

            call_count[0] += 1
            if call_count[0] == 1:
                # Total recommendations
                result.scalar.return_value = 100
            else:
                # Completed workflows
                result.scalar.return_value = 85

            return result

        mock_db.query.side_effect = mock_query_side_effect

        cutoff_date = datetime.utcnow() - timedelta(days=30)
        result = analytics_service._calculate_task_completion(cutoff_date)

        # 85/100 = 85%
        assert result == 85.0

    def test_calculate_adoption_rate_no_vendors(self, analytics_service, mock_db):
        """Test adoption rate with no vendors"""
        # Mock query to return no vendors
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        cutoff_date = datetime.utcnow() - timedelta(days=30)
        result = analytics_service._calculate_adoption_rate(cutoff_date)

        assert result["adoption_rate"] == 0.0
        assert result["active_vendors"] == 0
        assert result["total_vendors"] == 0

    def test_calculate_adoption_rate_with_vendors(self, analytics_service, mock_db):
        """Test adoption rate calculation"""
        call_count = [0]

        def mock_query_side_effect(*args):
            result = MagicMock()
            result.filter.return_value = result

            call_count[0] += 1
            if call_count[0] == 1:
                # Vendors with sales (potential users)
                result.all.return_value = [("v1",), ("v2",), ("v3",), ("v4",), ("v5",)]
            else:
                # Vendors using recommendations (adopters)
                result.all.return_value = [("v1",), ("v2",), ("v3",)]

            return result

        mock_db.query.side_effect = mock_query_side_effect

        cutoff_date = datetime.utcnow() - timedelta(days=30)
        result = analytics_service._calculate_adoption_rate(cutoff_date)

        # 3/5 = 60%
        assert result["adoption_rate"] == 60.0
        assert result["active_vendors"] == 3
        assert result["total_vendors"] == 5

    def test_calculate_engagement(self, analytics_service, mock_db):
        """Test engagement metrics calculation"""
        call_count = [0]

        def mock_query_side_effect(*args):
            result = MagicMock()
            result.filter.return_value = result
            result.join.return_value = result

            call_count[0] += 1
            if call_count[0] == 1:
                # Recommendations generated
                result.scalar.return_value = 200
            else:
                # Recommendations used
                result.scalar.return_value = 150

            return result

        mock_db.query.side_effect = mock_query_side_effect

        cutoff_date = datetime.utcnow() - timedelta(days=30)
        result = analytics_service._calculate_engagement(cutoff_date)

        # 150/200 = 75%
        assert result["recommendations_generated"] == 200
        assert result["recommendations_used"] == 150
        assert result["conversion_rate"] == 75.0

    def test_calculate_engagement_no_recommendations(self, analytics_service, mock_db):
        """Test engagement with no recommendations"""
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.scalar.return_value = 0

        cutoff_date = datetime.utcnow() - timedelta(days=30)
        result = analytics_service._calculate_engagement(cutoff_date)

        assert result["recommendations_generated"] == 0
        assert result["conversion_rate"] == 0.0


class TestVendorEngagement:
    """Test vendor-specific engagement metrics"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return MagicMock()

    @pytest.fixture
    def analytics_service(self, mock_db):
        """Create analytics service"""
        return AnalyticsService(db=mock_db)

    def test_get_vendor_engagement(self, analytics_service, mock_db):
        """Test getting vendor engagement metrics"""
        vendor_id = "vendor-123"

        call_count = [0]

        def mock_query_side_effect(*args):
            result = MagicMock()
            result.filter.return_value = result
            result.join.return_value = result

            call_count[0] += 1
            if call_count[0] == 1:
                # Recommendations generated
                result.scalar.return_value = 50
            elif call_count[0] == 2:
                # Feedback count
                result.scalar.return_value = 40
            else:
                # Average rating
                result.scalar.return_value = 4.5

            return result

        mock_db.query.side_effect = mock_query_side_effect

        result = analytics_service.get_vendor_engagement(vendor_id, days_back=30)

        assert result["vendor_id"] == vendor_id
        assert result["days_analyzed"] == 30
        assert result["recommendations_generated"] == 50
        assert result["feedback_provided"] == 40
        assert result["feedback_rate"] == 80.0  # 40/50
        assert result["avg_rating"] == 4.5

    def test_get_vendor_engagement_no_recommendations(self, analytics_service, mock_db):
        """Test vendor engagement with no recommendations"""
        vendor_id = "vendor-456"

        call_count = [0]

        def mock_query_side_effect(*args):
            result = MagicMock()
            result.filter.return_value = result
            result.join.return_value = result

            call_count[0] += 1
            if call_count[0] == 1:
                # No recommendations
                result.scalar.return_value = 0
            elif call_count[0] == 2:
                # No feedback
                result.scalar.return_value = 0
            else:
                # No rating
                result.scalar.return_value = None

            return result

        mock_db.query.side_effect = mock_query_side_effect

        result = analytics_service.get_vendor_engagement(vendor_id, days_back=30)

        assert result["recommendations_generated"] == 0
        assert result["feedback_rate"] == 0
        assert result["avg_rating"] is None


class TestFeatureUsage:
    """Test feature usage statistics"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return MagicMock()

    @pytest.fixture
    def analytics_service(self, mock_db):
        """Create analytics service"""
        return AnalyticsService(db=mock_db)

    def test_get_feature_usage(self, analytics_service, mock_db):
        """Test getting feature usage statistics"""
        call_count = [0]

        def mock_query_side_effect(*args):
            result = MagicMock()
            result.filter.return_value = result

            call_count[0] += 1
            if call_count[0] == 1:
                # Recommendations generated
                result.scalar.return_value = 500
            elif call_count[0] == 2:
                # Feedback submitted
                result.scalar.return_value = 400
            elif call_count[0] == 3:
                # Products added
                result.scalar.return_value = 100
            else:
                # Vendors onboarded
                result.scalar.return_value = 25

            return result

        mock_db.query.side_effect = mock_query_side_effect

        result = analytics_service.get_feature_usage(days_back=30)

        assert result["recommendations_generated"] == 500
        assert result["feedback_submitted"] == 400
        assert result["products_added"] == 100
        assert result["vendors_onboarded"] == 25


class TestCollectAndLogMetrics:
    """Test scheduled metrics collection function"""

    def test_collect_and_log_metrics(self):
        """Test metrics collection and logging"""
        mock_db = MagicMock()

        # Mock all the queries
        call_count = [0]

        def mock_query_side_effect(*args):
            result = MagicMock()
            result.filter.return_value = result
            result.join.return_value = result

            call_count[0] += 1

            # Satisfaction ratings
            if call_count[0] == 1:
                result.all.return_value = [(5,), (5,), (4,), (4,), (5,)]
            # Task completion - total
            elif call_count[0] == 2:
                result.scalar.return_value = 100
            # Task completion - completed
            elif call_count[0] == 3:
                result.scalar.return_value = 95
            # Adoption - total vendors
            elif call_count[0] == 4:
                result.all.return_value = [("v1",), ("v2",)]
            # Adoption - active vendors
            elif call_count[0] == 5:
                result.all.return_value = [("v1",), ("v2",)]
            # Engagement - generated
            elif call_count[0] == 6:
                result.scalar.return_value = 100
            # Engagement - used
            elif call_count[0] == 7:
                result.scalar.return_value = 80
            # Feature usage calls (4 queries)
            else:
                result.scalar.return_value = 10

            return result

        mock_db.query.side_effect = mock_query_side_effect

        report = collect_and_log_metrics(mock_db)

        # Verify report structure
        assert "collected_at" in report
        assert "period_days" in report
        assert "success_criteria" in report
        assert "engagement" in report
        assert "feature_usage" in report
        assert "overall_health" in report

        # Verify success criteria
        assert report["success_criteria"]["sc003_user_satisfaction"]["status"] == "PASS"
        assert report["success_criteria"]["sc008_task_completion"]["status"] == "PASS"
        assert report["success_criteria"]["sc012_adoption_rate"]["status"] == "PASS"

        # Verify overall health
        assert report["overall_health"] == "HEALTHY"
