"""Unit tests for feedback router.

Tests feedback API endpoints:
- POST /feedback - Create feedback
- GET /feedback - List feedback
- GET /feedback/stats - Get statistics
- GET /feedback/{id} - Get specific feedback
"""
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4, UUID
from unittest.mock import MagicMock, patch

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.routers.feedback import (
    create_feedback,
    list_feedback,
    get_feedback_stats,
    get_feedback,
    FeedbackCreateRequest,
    FeedbackResponse,
    FeedbackStats,
)
from src.models.recommendation import Recommendation
from src.models.recommendation_feedback import RecommendationFeedback


class TestCreateFeedback:
    """Test create_feedback endpoint."""

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
        rec.recommended_quantity = 50
        return rec

    def test_create_feedback_success(self, mock_db, vendor_id, recommendation_id, existing_recommendation):
        """Test successful feedback creation."""
        # Mock recommendation query
        mock_rec_query = MagicMock()
        mock_rec_query.filter.return_value = mock_rec_query
        mock_rec_query.first.return_value = existing_recommendation

        # Mock feedback query (no existing)
        mock_feedback_query = MagicMock()
        mock_feedback_query.filter.return_value = mock_feedback_query
        mock_feedback_query.first.return_value = None

        # Setup query routing
        def query_side_effect(model):
            if model == Recommendation:
                return mock_rec_query
            elif model == RecommendationFeedback:
                return mock_feedback_query
            return MagicMock()

        mock_db.query.side_effect = query_side_effect

        # Mock refresh
        feedback_id = uuid4()
        submitted_at = datetime(2025, 1, 15, 12, 0, 0)

        def mock_refresh(feedback):
            feedback.id = feedback_id
            feedback.submitted_at = submitted_at

        mock_db.refresh.side_effect = mock_refresh

        request_data = FeedbackCreateRequest(
            recommendation_id=recommendation_id,
            actual_quantity_brought=60,
            actual_quantity_sold=48,
            actual_revenue=240.50,
            rating=4,
            comments="Good recommendation",
        )

        result = create_feedback(
            request=request_data,
            vendor_id=vendor_id,
            db=mock_db,
        )

        # Verify database operations
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

        # Verify feedback was created
        added_feedback = mock_db.add.call_args[0][0]
        assert isinstance(added_feedback, RecommendationFeedback)
        assert added_feedback.vendor_id == vendor_id
        assert added_feedback.recommendation_id == recommendation_id
        assert added_feedback.actual_quantity_brought == 60
        assert added_feedback.actual_quantity_sold == 48
        assert added_feedback.actual_revenue == 240.50
        assert added_feedback.rating == 4
        assert added_feedback.comments == "Good recommendation"

    def test_create_feedback_recommendation_not_found(self, mock_db, vendor_id, recommendation_id):
        """Test feedback creation when recommendation doesn't exist."""
        # Mock recommendation not found
        mock_rec_query = MagicMock()
        mock_rec_query.filter.return_value = mock_rec_query
        mock_rec_query.first.return_value = None
        mock_db.query.return_value = mock_rec_query

        request_data = FeedbackCreateRequest(
            recommendation_id=recommendation_id,
            actual_quantity_sold=40,
        )

        with pytest.raises(HTTPException) as exc_info:
            create_feedback(
                request=request_data,
                vendor_id=vendor_id,
                db=mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "Recommendation not found" in exc_info.value.detail

    def test_create_feedback_duplicate(self, mock_db, vendor_id, recommendation_id, existing_recommendation):
        """Test feedback creation when feedback already exists."""
        # Mock recommendation exists
        mock_rec_query = MagicMock()
        mock_rec_query.filter.return_value = mock_rec_query
        mock_rec_query.first.return_value = existing_recommendation

        # Mock existing feedback
        existing_feedback = MagicMock(spec=RecommendationFeedback)
        mock_feedback_query = MagicMock()
        mock_feedback_query.filter.return_value = mock_feedback_query
        mock_feedback_query.first.return_value = existing_feedback

        def query_side_effect(model):
            if model == Recommendation:
                return mock_rec_query
            elif model == RecommendationFeedback:
                return mock_feedback_query

        mock_db.query.side_effect = query_side_effect

        request_data = FeedbackCreateRequest(
            recommendation_id=recommendation_id,
            actual_quantity_sold=40,
        )

        with pytest.raises(HTTPException) as exc_info:
            create_feedback(
                request=request_data,
                vendor_id=vendor_id,
                db=mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert "already exists" in exc_info.value.detail

    def test_create_feedback_without_quantity_sold(self, mock_db, vendor_id, recommendation_id, existing_recommendation):
        """Test feedback creation without quantity sold (no variance calculation)."""
        # Mock queries
        mock_rec_query = MagicMock()
        mock_rec_query.filter.return_value = mock_rec_query
        mock_rec_query.first.return_value = existing_recommendation

        mock_feedback_query = MagicMock()
        mock_feedback_query.filter.return_value = mock_feedback_query
        mock_feedback_query.first.return_value = None

        def query_side_effect(model):
            if model == Recommendation:
                return mock_rec_query
            elif model == RecommendationFeedback:
                return mock_feedback_query

        mock_db.query.side_effect = query_side_effect

        def mock_refresh(feedback):
            feedback.id = uuid4()
            feedback.submitted_at = datetime(2025, 1, 15, 12, 0, 0)

        mock_db.refresh.side_effect = mock_refresh

        request_data = FeedbackCreateRequest(
            recommendation_id=recommendation_id,
            actual_quantity_brought=60,
            rating=5,
        )

        result = create_feedback(
            request=request_data,
            vendor_id=vendor_id,
            db=mock_db,
        )

        # Verify feedback was created without quantity_sold
        added_feedback = mock_db.add.call_args[0][0]
        assert added_feedback.actual_quantity_sold is None


class TestListFeedback:
    """Test list_feedback endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    @pytest.fixture
    def sample_feedback(self, vendor_id):
        """Sample feedback data."""
        feedback1 = MagicMock(spec=RecommendationFeedback)
        feedback1.id = uuid4()
        feedback1.recommendation_id = uuid4()
        feedback1.actual_quantity_brought = 50
        feedback1.actual_quantity_sold = 45
        feedback1.actual_revenue = Decimal("225.00")
        feedback1.quantity_variance = Decimal("-5.0")
        feedback1.variance_percentage = Decimal("-10.0")
        feedback1.rating = 4
        feedback1.comments = "Good"
        feedback1.was_accurate = True
        feedback1.was_overstocked = False
        feedback1.was_understocked = False
        feedback1.submitted_at = datetime(2025, 1, 15, 12, 0, 0)

        feedback2 = MagicMock(spec=RecommendationFeedback)
        feedback2.id = uuid4()
        feedback2.recommendation_id = uuid4()
        feedback2.actual_quantity_brought = None
        feedback2.actual_quantity_sold = None
        feedback2.actual_revenue = None
        feedback2.quantity_variance = None
        feedback2.variance_percentage = None
        feedback2.rating = None
        feedback2.comments = None
        feedback2.was_accurate = None
        feedback2.was_overstocked = None
        feedback2.was_understocked = None
        feedback2.submitted_at = datetime(2025, 1, 10, 12, 0, 0)

        return [feedback1, feedback2]

    def test_list_feedback_default(self, mock_db, vendor_id, sample_feedback):
        """Test listing feedback with default parameters."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.all.return_value = sample_feedback

        mock_db.query.return_value = mock_query

        results = list_feedback(vendor_id=vendor_id, db=mock_db, limit=100, offset=0)

        assert len(results) == 2
        assert isinstance(results[0], FeedbackResponse)
        assert results[0].actual_quantity_sold == 45
        assert results[0].rating == 4

    def test_list_feedback_with_pagination(self, mock_db, vendor_id, sample_feedback):
        """Test feedback listing with pagination."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.all.return_value = [sample_feedback[1]]

        mock_db.query.return_value = mock_query

        results = list_feedback(vendor_id=vendor_id, db=mock_db, limit=1, offset=1)

        mock_query.limit.assert_called_with(1)
        mock_query.offset.assert_called_with(1)

    def test_list_feedback_empty(self, mock_db, vendor_id):
        """Test listing feedback when none exist."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.all.return_value = []

        mock_db.query.return_value = mock_query

        results = list_feedback(vendor_id=vendor_id, db=mock_db, limit=100, offset=0)

        assert results == []


class TestGetFeedbackStats:
    """Test get_feedback_stats endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    def test_get_feedback_stats_with_data(self, mock_db, vendor_id):
        """Test getting stats with feedback data."""
        # Create sample feedback
        feedback1 = MagicMock(spec=RecommendationFeedback)
        feedback1.rating = 4
        feedback1.was_accurate = True
        feedback1.was_overstocked = False
        feedback1.was_understocked = False
        feedback1.variance_percentage = Decimal("10.5")

        feedback2 = MagicMock(spec=RecommendationFeedback)
        feedback2.rating = 5
        feedback2.was_accurate = True
        feedback2.was_overstocked = False
        feedback2.was_understocked = False
        feedback2.variance_percentage = Decimal("-5.2")

        feedback3 = MagicMock(spec=RecommendationFeedback)
        feedback3.rating = 3
        feedback3.was_accurate = False
        feedback3.was_overstocked = False
        feedback3.was_understocked = True
        feedback3.variance_percentage = Decimal("25.0")

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [feedback1, feedback2, feedback3]
        mock_db.query.return_value = mock_query

        with patch('src.routers.feedback.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value = datetime(2025, 1, 30, 12, 0, 0)

            result = get_feedback_stats(vendor_id=vendor_id, db=mock_db, days_back=30)

            assert isinstance(result, FeedbackStats)
            assert result.total_feedback_count == 3
            assert result.avg_rating == 4.0  # (4+5+3)/3
            assert result.accuracy_rate == 66.67  # 2/3 * 100
            assert result.overstock_rate == 0.0
            assert result.understock_rate == 33.33  # 1/3 * 100
            assert result.avg_variance_percentage == 10.1  # (10.5 + -5.2 + 25.0) / 3

    def test_get_feedback_stats_empty(self, mock_db, vendor_id):
        """Test getting stats with no feedback."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        result = get_feedback_stats(vendor_id=vendor_id, db=mock_db, days_back=30)

        assert result.total_feedback_count == 0
        assert result.avg_rating is None
        assert result.accuracy_rate is None
        assert result.overstock_rate is None
        assert result.understock_rate is None
        assert result.avg_variance_percentage is None

    def test_get_feedback_stats_custom_period(self, mock_db, vendor_id):
        """Test stats with custom period."""
        feedback = MagicMock(spec=RecommendationFeedback)
        feedback.rating = 5
        feedback.was_accurate = True
        feedback.was_overstocked = False
        feedback.was_understocked = False
        feedback.variance_percentage = Decimal("5.0")

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [feedback]
        mock_db.query.return_value = mock_query

        with patch('src.routers.feedback.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value = datetime(2025, 1, 14, 12, 0, 0)

            result = get_feedback_stats(vendor_id=vendor_id, db=mock_db, days_back=7)

            assert result.total_feedback_count == 1


class TestGetFeedback:
    """Test get_feedback endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return MagicMock(spec=Session)

    @pytest.fixture
    def vendor_id(self):
        """Test vendor ID."""
        return uuid4()

    @pytest.fixture
    def feedback_id(self):
        """Test feedback ID."""
        return uuid4()

    @pytest.fixture
    def existing_feedback(self, feedback_id, vendor_id):
        """Existing feedback."""
        feedback = MagicMock(spec=RecommendationFeedback)
        feedback.id = feedback_id
        feedback.recommendation_id = uuid4()
        feedback.actual_quantity_brought = 50
        feedback.actual_quantity_sold = 48
        feedback.actual_revenue = Decimal("240.00")
        feedback.quantity_variance = Decimal("-2.0")
        feedback.variance_percentage = Decimal("-4.0")
        feedback.rating = 4
        feedback.comments = "Good"
        feedback.was_accurate = True
        feedback.was_overstocked = False
        feedback.was_understocked = False
        feedback.submitted_at = datetime(2025, 1, 15, 12, 0, 0)
        return feedback

    def test_get_feedback_success(self, mock_db, vendor_id, feedback_id, existing_feedback):
        """Test getting feedback by ID."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = existing_feedback
        mock_db.query.return_value = mock_query

        result = get_feedback(
            feedback_id=feedback_id,
            vendor_id=vendor_id,
            db=mock_db,
        )

        assert isinstance(result, FeedbackResponse)
        assert result.id == feedback_id
        assert result.actual_quantity_sold == 48
        assert result.rating == 4
        assert result.comments == "Good"

    def test_get_feedback_not_found(self, mock_db, vendor_id, feedback_id):
        """Test getting non-existent feedback."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            get_feedback(
                feedback_id=feedback_id,
                vendor_id=vendor_id,
                db=mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in exc_info.value.detail

    def test_get_feedback_wrong_vendor(self, mock_db, feedback_id):
        """Test getting feedback from wrong vendor."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            get_feedback(
                feedback_id=feedback_id,
                vendor_id=uuid4(),  # Different vendor
                db=mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
