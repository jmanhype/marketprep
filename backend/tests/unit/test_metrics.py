"""
Unit tests for Prometheus Metrics

Tests metric collection functionality:
- API call tracking decorator
- Database query tracking decorator
- ML prediction tracking decorator
- Business metrics collection (MetricsCollector)
- Cache metrics
- System metrics
- Prometheus response generation
"""

import pytest
import time
from unittest.mock import patch, MagicMock
from prometheus_client import REGISTRY

from src.monitoring.metrics import (
    track_api_call,
    track_db_query,
    track_ml_prediction,
    MetricsCollector,
    metrics_response,
    initialize_metrics,
    # Import metrics to check values
    external_api_calls_total,
    external_api_duration_seconds,
    external_api_errors_total,
    db_queries_total,
    db_query_duration_seconds,
    db_errors_total,
    ml_predictions_total,
    ml_prediction_duration_seconds,
    ml_prediction_confidence,
    recommendations_generated_total,
    recommendations_accepted_total,
    feedback_submitted_total,
    feedback_accuracy_rate,
    square_products_synced_total,
    square_sync_duration_seconds,
    cache_hits_total,
    cache_misses_total,
    cache_errors_total,
    system_memory_usage_bytes,
    system_cpu_usage_percent,
)


class TestTrackApiCallDecorator:
    """Test track_api_call decorator"""

    @pytest.mark.asyncio
    async def test_tracks_successful_api_call(self):
        """Test decorator tracks successful API calls"""

        @track_api_call('square', 'list_locations')
        async def mock_api_call():
            await asyncio.sleep(0.01)
            return {"locations": []}

        # Get initial counter value
        initial_count = external_api_calls_total.labels(
            service='square',
            endpoint='list_locations',
            status='success'
        )._value.get()

        result = await mock_api_call()

        # Check result
        assert result == {"locations": []}

        # Check counter incremented
        final_count = external_api_calls_total.labels(
            service='square',
            endpoint='list_locations',
            status='success'
        )._value.get()
        assert final_count == initial_count + 1

    @pytest.mark.asyncio
    async def test_tracks_failed_api_call(self):
        """Test decorator tracks API call failures"""

        @track_api_call('weather', 'get_forecast')
        async def mock_failing_call():
            raise ValueError("API error")

        # Get initial error counter
        initial_errors = external_api_errors_total.labels(
            service='weather',
            error_type='ValueError'
        )._value.get()

        # Should raise the exception
        with pytest.raises(ValueError, match="API error"):
            await mock_failing_call()

        # Check error counter incremented
        final_errors = external_api_errors_total.labels(
            service='weather',
            error_type='ValueError'
        )._value.get()
        assert final_errors == initial_errors + 1

        # Check status is error
        error_count = external_api_calls_total.labels(
            service='weather',
            endpoint='get_forecast',
            status='error'
        )._value.get()
        assert error_count > 0

    @pytest.mark.asyncio
    async def test_tracks_api_call_duration(self):
        """Test decorator tracks API call duration"""

        @track_api_call('events', 'search_events')
        async def mock_slow_call():
            await asyncio.sleep(0.05)  # 50ms delay
            return {"events": []}

        await mock_slow_call()

        # Duration should be recorded (can't easily check exact value)
        # Just verify the metric exists with correct labels
        metric_samples = list(external_api_duration_seconds.collect())[0].samples
        found = any(
            s.labels.get('service') == 'events' and
            s.labels.get('endpoint') == 'search_events'
            for s in metric_samples
        )
        assert found


class TestTrackDbQueryDecorator:
    """Test track_db_query decorator"""

    @pytest.mark.asyncio
    async def test_tracks_successful_db_query(self):
        """Test decorator tracks successful database queries"""

        @track_db_query('SELECT')
        async def mock_select_query():
            await asyncio.sleep(0.01)
            return [{"id": 1, "name": "Product"}]

        initial_count = db_queries_total.labels(operation='SELECT')._value.get()

        result = await mock_select_query()

        assert result == [{"id": 1, "name": "Product"}]

        final_count = db_queries_total.labels(operation='SELECT')._value.get()
        assert final_count == initial_count + 1

    @pytest.mark.asyncio
    async def test_tracks_failed_db_query(self):
        """Test decorator tracks database query failures"""

        @track_db_query('INSERT')
        async def mock_failing_query():
            raise RuntimeError("Database error")

        initial_errors = db_errors_total.labels(error_type='RuntimeError')._value.get()

        with pytest.raises(RuntimeError, match="Database error"):
            await mock_failing_query()

        final_errors = db_errors_total.labels(error_type='RuntimeError')._value.get()
        assert final_errors == initial_errors + 1

    @pytest.mark.asyncio
    async def test_tracks_db_query_duration(self):
        """Test decorator tracks query duration"""

        @track_db_query('UPDATE')
        async def mock_update_query():
            await asyncio.sleep(0.02)
            return True

        await mock_update_query()

        # Verify duration metric exists
        metric_samples = list(db_query_duration_seconds.collect())[0].samples
        found = any(
            s.labels.get('operation') == 'UPDATE'
            for s in metric_samples
        )
        assert found


class TestTrackMlPredictionDecorator:
    """Test track_ml_prediction decorator"""

    def test_tracks_ml_prediction(self):
        """Test decorator tracks ML predictions"""

        @track_ml_prediction('ml_model')
        def mock_prediction():
            time.sleep(0.01)
            return {"quantity": 100, "confidence_score": 0.85}

        initial_count = ml_predictions_total.labels(model_type='ml_model')._value.get()

        result = mock_prediction()

        assert result["quantity"] == 100

        final_count = ml_predictions_total.labels(model_type='ml_model')._value.get()
        assert final_count == initial_count + 1

    def test_tracks_fallback_prediction(self):
        """Test decorator tracks fallback heuristic predictions"""

        @track_ml_prediction('fallback_heuristic')
        def mock_fallback():
            return {"quantity": 50}

        initial_count = ml_predictions_total.labels(
            model_type='fallback_heuristic'
        )._value.get()

        result = mock_fallback()

        assert result["quantity"] == 50

        final_count = ml_predictions_total.labels(
            model_type='fallback_heuristic'
        )._value.get()
        assert final_count == initial_count + 1

    def test_tracks_prediction_confidence(self):
        """Test decorator tracks prediction confidence scores"""

        @track_ml_prediction('ml_model')
        def mock_confident_prediction():
            return {"quantity": 75, "confidence_score": 0.92}

        mock_confident_prediction()

        # Verify confidence metric recorded
        metric_samples = list(ml_prediction_confidence.collect())[0].samples
        found = any(
            s.labels.get('model_type') == 'ml_model'
            for s in metric_samples
        )
        assert found

    def test_tracks_prediction_without_confidence(self):
        """Test decorator handles predictions without confidence scores"""

        @track_ml_prediction('ml_model')
        def mock_no_confidence():
            return {"quantity": 60}  # No confidence_score

        # Should not raise error
        result = mock_no_confidence()
        assert result["quantity"] == 60


class TestMetricsCollector:
    """Test MetricsCollector business metrics"""

    def test_record_recommendation_generated(self):
        """Test recording recommendation generation"""
        vendor_id = "vendor-123"

        initial_count = recommendations_generated_total.labels(
            vendor_id=vendor_id
        )._value.get()

        MetricsCollector.record_recommendation_generated(vendor_id)

        final_count = recommendations_generated_total.labels(
            vendor_id=vendor_id
        )._value.get()
        assert final_count == initial_count + 1

    def test_record_recommendation_accepted(self):
        """Test recording recommendation acceptance"""
        vendor_id = "vendor-456"

        initial_count = recommendations_accepted_total.labels(
            vendor_id=vendor_id
        )._value.get()

        MetricsCollector.record_recommendation_accepted(vendor_id)

        final_count = recommendations_accepted_total.labels(
            vendor_id=vendor_id
        )._value.get()
        assert final_count == initial_count + 1

    def test_record_feedback_submitted(self):
        """Test recording feedback submission"""
        rating = 5

        initial_count = feedback_submitted_total.labels(
            rating=str(rating)
        )._value.get()

        MetricsCollector.record_feedback_submitted(rating)

        final_count = feedback_submitted_total.labels(
            rating=str(rating)
        )._value.get()
        assert final_count == initial_count + 1

    def test_record_feedback_multiple_ratings(self):
        """Test recording feedback with different ratings"""
        for rating in [1, 2, 3, 4, 5]:
            initial = feedback_submitted_total.labels(rating=str(rating))._value.get()
            MetricsCollector.record_feedback_submitted(rating)
            final = feedback_submitted_total.labels(rating=str(rating))._value.get()
            assert final == initial + 1

    def test_update_feedback_accuracy_rate(self):
        """Test updating feedback accuracy rate"""
        accuracy = 0.87

        MetricsCollector.update_feedback_accuracy_rate(accuracy)

        current_value = feedback_accuracy_rate._value.get()
        assert current_value == accuracy

    def test_update_feedback_accuracy_rate_multiple_times(self):
        """Test updating accuracy rate replaces previous value"""
        MetricsCollector.update_feedback_accuracy_rate(0.75)
        assert feedback_accuracy_rate._value.get() == 0.75

        MetricsCollector.update_feedback_accuracy_rate(0.82)
        assert feedback_accuracy_rate._value.get() == 0.82

    def test_record_square_sync(self):
        """Test recording Square product sync"""
        vendor_id = "vendor-789"
        duration = 5.5
        product_count = 25

        initial_products = square_products_synced_total.labels(
            vendor_id=vendor_id
        )._value.get()

        MetricsCollector.record_square_sync(vendor_id, duration, product_count)

        # Check product count incremented by product_count
        final_products = square_products_synced_total.labels(
            vendor_id=vendor_id
        )._value.get()
        assert final_products == initial_products + product_count

        # Duration should be recorded
        metric_samples = list(square_sync_duration_seconds.collect())[0].samples
        assert len([s for s in metric_samples if s.name.endswith('_count')]) > 0

    def test_record_cache_hit(self):
        """Test recording cache hits"""
        cache_key_prefix = "recommendations"

        initial_hits = cache_hits_total.labels(
            cache_key_prefix=cache_key_prefix
        )._value.get()

        MetricsCollector.record_cache_hit(cache_key_prefix)

        final_hits = cache_hits_total.labels(
            cache_key_prefix=cache_key_prefix
        )._value.get()
        assert final_hits == initial_hits + 1

    def test_record_cache_miss(self):
        """Test recording cache misses"""
        cache_key_prefix = "weather"

        initial_misses = cache_misses_total.labels(
            cache_key_prefix=cache_key_prefix
        )._value.get()

        MetricsCollector.record_cache_miss(cache_key_prefix)

        final_misses = cache_misses_total.labels(
            cache_key_prefix=cache_key_prefix
        )._value.get()
        assert final_misses == initial_misses + 1

    def test_record_cache_error(self):
        """Test recording cache errors"""
        operation = "get"

        initial_errors = cache_errors_total.labels(
            operation=operation
        )._value.get()

        MetricsCollector.record_cache_error(operation)

        final_errors = cache_errors_total.labels(
            operation=operation
        )._value.get()
        assert final_errors == initial_errors + 1

    def test_record_cache_error_different_operations(self):
        """Test recording errors for different cache operations"""
        for operation in ["get", "set", "delete"]:
            initial = cache_errors_total.labels(operation=operation)._value.get()
            MetricsCollector.record_cache_error(operation)
            final = cache_errors_total.labels(operation=operation)._value.get()
            assert final == initial + 1

    def test_update_system_metrics(self):
        """Test updating system resource metrics"""
        memory_bytes = 8589934592  # 8 GB
        cpu_percent = 45.7

        MetricsCollector.update_system_metrics(memory_bytes, cpu_percent)

        assert system_memory_usage_bytes._value.get() == memory_bytes
        assert system_cpu_usage_percent._value.get() == cpu_percent

    def test_update_system_metrics_multiple_times(self):
        """Test system metrics are updated (not accumulated)"""
        MetricsCollector.update_system_metrics(1000000, 50.0)
        assert system_memory_usage_bytes._value.get() == 1000000
        assert system_cpu_usage_percent._value.get() == 50.0

        # Update again - should replace, not add
        MetricsCollector.update_system_metrics(2000000, 60.0)
        assert system_memory_usage_bytes._value.get() == 2000000
        assert system_cpu_usage_percent._value.get() == 60.0


class TestMetricsResponse:
    """Test Prometheus metrics response generation"""

    def test_metrics_response_returns_response(self):
        """Test metrics_response returns a Response object"""
        response = metrics_response()

        from starlette.responses import Response
        assert isinstance(response, Response)

    def test_metrics_response_content_type(self):
        """Test metrics response has correct content type"""
        response = metrics_response()

        # Prometheus metrics should be text/plain
        assert "text/plain" in response.media_type

    def test_metrics_response_contains_metrics(self):
        """Test metrics response contains Prometheus format data"""
        # Record some metrics
        MetricsCollector.record_recommendation_generated("test-vendor")

        response = metrics_response()

        # Response should contain metric data
        content = response.body.decode('utf-8')
        assert len(content) > 0

        # Should contain TYPE declarations (Prometheus format)
        assert "# TYPE" in content or "marketprep" in content

    def test_metrics_response_includes_custom_metrics(self):
        """Test response includes MarketPrep-specific metrics"""
        MetricsCollector.record_feedback_submitted(5)

        response = metrics_response()
        content = response.body.decode('utf-8')

        # Should contain our custom metric names
        assert "marketprep" in content


class TestInitializeMetrics:
    """Test metrics initialization"""

    @patch('src.monitoring.metrics.logger')
    def test_initialize_metrics_logs_startup(self, mock_logger):
        """Test initialize_metrics logs startup information"""
        initialize_metrics()

        # Should log initialization messages
        assert mock_logger.info.called

        # Check for expected log messages
        call_args_list = [str(call) for call in mock_logger.info.call_args_list]
        log_output = " ".join(call_args_list)

        assert "Prometheus" in log_output or "metrics" in log_output.lower()

    @patch('src.monitoring.metrics.logger')
    def test_initialize_metrics_logs_version_and_environment(self, mock_logger):
        """Test initialization logs application version and environment"""
        initialize_metrics()

        call_args_list = [str(call) for call in mock_logger.info.call_args_list]
        log_output = " ".join(call_args_list)

        # Should mention version and environment
        assert "version" in log_output.lower() or "environment" in log_output.lower()


# Import asyncio for async tests
import asyncio
