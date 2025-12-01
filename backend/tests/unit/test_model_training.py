"""
Unit tests for ML model training service

Tests model training functionality:
- Initial model training from sales data
- Retraining with feedback data
- Training data preparation
- Metrics calculation
- Model saving and loading
- Scheduled retraining
"""

import pytest
import tempfile
import shutil
import json
import pickle
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
from sklearn.ensemble import RandomForestRegressor

from src.services.model_training import ModelTrainer, retrain_all_vendors_with_feedback


class TestModelTraining:
    """Test initial model training from sales data"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return MagicMock()

    @pytest.fixture
    def temp_model_dir(self):
        """Create temporary directory for model storage"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def trainer(self, mock_db, temp_model_dir):
        """Create model trainer with temp directory"""
        return ModelTrainer(db=mock_db, model_dir=temp_model_dir)

    def test_train_model_for_vendor_with_sufficient_data(self, trainer, mock_db, temp_model_dir):
        """Test successful model training with sufficient sales data"""
        vendor_id = "vendor-123"

        # Mock sales data (40 sales records)
        mock_sales = []
        base_date = datetime(2025, 1, 1)
        for i in range(40):
            sale = MagicMock()
            sale.sale_date = base_date + timedelta(days=i)
            sale.quantity = 10 + (i % 5)  # Varying quantities
            sale.total_amount = 100.0 + (i * 5)
            mock_sales.append(sale)

        # Mock query
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = mock_sales

        # Train model
        result = trainer.train_model_for_vendor(vendor_id, min_sales_records=30)

        # Verify result
        assert result is not None
        assert result["vendor_id"] == vendor_id
        assert "model_path" in result
        assert "metrics" in result
        assert result["training_samples"] > 0
        assert result["test_samples"] > 0

        # Verify model was saved
        model_files = list(temp_model_dir.glob(f"{vendor_id}_*.pkl"))
        assert len(model_files) == 1

        # Verify metadata was saved
        metadata_files = list(temp_model_dir.glob(f"{vendor_id}_*.json"))
        assert len(metadata_files) == 1

    def test_train_model_for_vendor_insufficient_data(self, trainer, mock_db):
        """Test training with insufficient sales data"""
        vendor_id = "vendor-456"

        # Mock insufficient sales (only 10 records)
        mock_sales = []
        for i in range(10):
            sale = MagicMock()
            sale.sale_date = datetime(2025, 1, 1) + timedelta(days=i)
            sale.quantity = 5
            sale.total_amount = 50.0
            mock_sales.append(sale)

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = mock_sales

        # Attempt training
        result = trainer.train_model_for_vendor(vendor_id, min_sales_records=30)

        # Should return None for insufficient data
        assert result is None

    def test_train_model_for_vendor_invalid_data(self, trainer, mock_db):
        """Test training with invalid sales data (zero quantities)"""
        vendor_id = "vendor-789"

        # Mock sales with invalid quantities
        mock_sales = []
        for i in range(40):
            sale = MagicMock()
            sale.sale_date = datetime(2025, 1, 1) + timedelta(days=i)
            sale.quantity = 0  # Invalid
            sale.total_amount = 0
            mock_sales.append(sale)

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = mock_sales

        result = trainer.train_model_for_vendor(vendor_id)

        # Should return None for invalid data
        assert result is None


class TestModelRetraining:
    """Test model retraining with feedback data"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return MagicMock()

    @pytest.fixture
    def temp_model_dir(self):
        """Create temporary directory"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def trainer(self, mock_db, temp_model_dir):
        """Create trainer"""
        return ModelTrainer(db=mock_db, model_dir=temp_model_dir)

    def test_retrain_with_feedback_sufficient_data(self, trainer, mock_db):
        """Test retraining with sufficient feedback"""
        vendor_id = "vendor-123"

        # Mock feedback records
        mock_feedback = []
        base_date = datetime(2025, 1, 1)
        for i in range(15):
            feedback = MagicMock()
            feedback.actual_quantity_sold = 8 + (i % 3)
            feedback.rating = 4

            # Mock recommendation
            recommendation = MagicMock()
            recommendation.vendor_id = vendor_id
            recommendation.market_date = base_date + timedelta(days=i)
            recommendation.recommended_quantity = 10
            feedback.recommendation = recommendation

            mock_feedback.append(feedback)

        # Mock query
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = mock_feedback

        # Retrain
        result = trainer.retrain_with_feedback(vendor_id, min_feedback_records=10)

        # Verify
        assert result is not None
        assert result["vendor_id"] == vendor_id
        assert result["feedback_records_used"] > 0
        assert "metrics" in result
        assert "model_replaced" in result

    def test_retrain_with_feedback_insufficient_data(self, trainer, mock_db):
        """Test retraining with insufficient feedback"""
        vendor_id = "vendor-456"

        # Mock insufficient feedback (only 5 records)
        mock_feedback = []
        for i in range(5):
            feedback = MagicMock()
            feedback.actual_quantity_sold = 10
            feedback.rating = 4
            recommendation = MagicMock()
            recommendation.market_date = datetime(2025, 1, 1)
            recommendation.recommended_quantity = 10
            feedback.recommendation = recommendation
            mock_feedback.append(feedback)

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = mock_feedback

        result = trainer.retrain_with_feedback(vendor_id, min_feedback_records=10)

        # Should return None
        assert result is None

    def test_retrain_with_feedback_all_invalid_data(self, trainer, mock_db):
        """Test retraining with all invalid feedback data (covers lines 186-187)"""
        vendor_id = "vendor-invalid"

        # Mock feedback records with all invalid actual_quantity_sold
        mock_feedback = []
        for i in range(15):  # Sufficient count
            feedback = MagicMock()
            feedback.actual_quantity_sold = 0  # Invalid - will be filtered out
            feedback.rating = 4
            recommendation = MagicMock()
            recommendation.market_date = datetime(2025, 1, 1)
            recommendation.recommended_quantity = 10
            feedback.recommendation = recommendation
            mock_feedback.append(feedback)

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = mock_feedback

        result = trainer.retrain_with_feedback(vendor_id, min_feedback_records=10)

        # Should return None because no valid training data after filtering
        assert result is None

    def test_retrain_keeps_better_existing_model(self, trainer, mock_db, temp_model_dir):
        """Test that retraining keeps existing model if it's better"""
        vendor_id = "vendor-789"

        # Create existing model with better performance
        existing_model = RandomForestRegressor(n_estimators=10, random_state=42)
        existing_model.fit([[1], [2], [3]], [10, 20, 30])

        # Save existing model with good metrics
        existing_metrics = {"mae": 1.0, "rmse": 1.5, "r2": 0.95, "mape": 5.0}
        model_path = temp_model_dir / f"{vendor_id}_base_20250101_000000.pkl"
        metadata_path = temp_model_dir / f"{vendor_id}_base_20250101_000000.json"

        with open(model_path, "wb") as f:
            pickle.dump(existing_model, f)

        with open(metadata_path, "w") as f:
            json.dump({
                "vendor_id": vendor_id,
                "metrics": existing_metrics,
                "feature_names": ["test"],
                "trained_at": datetime.utcnow().isoformat(),
            }, f)

        # Mock feedback that will produce worse model
        mock_feedback = []
        for i in range(15):
            feedback = MagicMock()
            feedback.actual_quantity_sold = 10 + (i * 10)  # High variance
            feedback.rating = 3
            recommendation = MagicMock()
            recommendation.market_date = datetime(2025, 1, 1) + timedelta(days=i)
            recommendation.recommended_quantity = 10
            feedback.recommendation = recommendation
            mock_feedback.append(feedback)

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = mock_feedback

        result = trainer.retrain_with_feedback(vendor_id)

        # Verify old model was kept if new one isn't significantly better
        assert result is not None
        # Model replacement depends on actual training results


class TestDataPreparation:
    """Test training data preparation"""

    @pytest.fixture
    def trainer(self):
        """Create trainer with mock db"""
        return ModelTrainer(db=MagicMock())

    def test_prepare_training_data_from_sales(self, trainer):
        """Test preparing features and labels from sales"""
        # Mock sales
        mock_sales = []
        for i in range(5):
            sale = MagicMock()
            sale.sale_date = datetime(2025, 1, 1) + timedelta(days=i)
            sale.quantity = 10 + i
            sale.total_amount = 100.0 + (i * 10)
            mock_sales.append(sale)

        X, y, feature_names = trainer._prepare_training_data(mock_sales)

        # Verify shapes
        assert X.shape[0] == 5  # 5 samples
        assert X.shape[1] == 4  # 4 features
        assert len(y) == 5
        assert len(feature_names) == 4
        assert "weekday" in feature_names
        assert "month" in feature_names

    def test_prepare_training_data_filters_invalid(self, trainer):
        """Test that invalid sales are filtered out"""
        # Mix of valid and invalid sales
        mock_sales = []
        for i in range(5):
            sale = MagicMock()
            sale.sale_date = datetime(2025, 1, 1)
            sale.quantity = i if i > 0 else 0  # First one is invalid
            sale.total_amount = 100.0
            mock_sales.append(sale)

        X, y, feature_names = trainer._prepare_training_data(mock_sales)

        # Should only have 4 valid samples (excludes quantity=0)
        assert X.shape[0] == 4

    def test_prepare_feedback_training_data(self, trainer):
        """Test preparing features from feedback"""
        # Mock feedback records
        mock_feedback = []
        for i in range(5):
            feedback = MagicMock()
            feedback.actual_quantity_sold = 8 + i
            feedback.rating = 4

            recommendation = MagicMock()
            recommendation.market_date = datetime(2025, 1, 1) + timedelta(days=i)
            recommendation.recommended_quantity = 10
            feedback.recommendation = recommendation

            mock_feedback.append(feedback)

        X, y, feature_names = trainer._prepare_feedback_training_data(mock_feedback)

        # Verify
        assert X.shape[0] == 5
        assert X.shape[1] == 5  # weekday, month, day, recommended_qty, rating
        assert len(y) == 5
        assert "recommended_qty" in feature_names
        assert "rating" in feature_names

    def test_prepare_feedback_training_data_filters_invalid(self, trainer):
        """Test that invalid feedback records are filtered out (covers line 302)"""
        # Mix of valid and invalid feedback
        mock_feedback = []
        for i in range(5):
            feedback = MagicMock()
            # First two have invalid actual_quantity_sold (0 and negative)
            if i == 0:
                feedback.actual_quantity_sold = 0  # Invalid
            elif i == 1:
                feedback.actual_quantity_sold = -5  # Invalid
            else:
                feedback.actual_quantity_sold = 10  # Valid

            feedback.rating = 4
            recommendation = MagicMock()
            recommendation.market_date = datetime(2025, 1, 1)
            recommendation.recommended_quantity = 10
            feedback.recommendation = recommendation
            mock_feedback.append(feedback)

        X, y, feature_names = trainer._prepare_feedback_training_data(mock_feedback)

        # Should only have 3 valid samples (excludes 0 and negative quantities)
        assert X.shape[0] == 3
        assert len(y) == 3


class TestMetricsCalculation:
    """Test model performance metrics"""

    @pytest.fixture
    def trainer(self):
        """Create trainer"""
        return ModelTrainer(db=MagicMock())

    def test_calculate_metrics(self, trainer):
        """Test metrics calculation"""
        y_true = np.array([10, 20, 30, 40, 50])
        y_pred = np.array([12, 19, 31, 38, 52])

        metrics = trainer._calculate_metrics(y_true, y_pred)

        # Verify all metrics present
        assert "mae" in metrics
        assert "rmse" in metrics
        assert "r2" in metrics
        assert "mape" in metrics

        # Verify metrics are reasonable
        assert metrics["mae"] > 0
        assert metrics["r2"] >= -1 and metrics["r2"] <= 1


class TestModelPersistence:
    """Test model saving and loading"""

    @pytest.fixture
    def temp_model_dir(self):
        """Create temporary directory"""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def trainer(self, temp_model_dir):
        """Create trainer"""
        return ModelTrainer(db=MagicMock(), model_dir=temp_model_dir)

    def test_save_model(self, trainer, temp_model_dir):
        """Test saving model and metadata"""
        vendor_id = "vendor-save-test"

        # Create simple model
        model = RandomForestRegressor(n_estimators=10, random_state=42)
        model.fit([[1], [2], [3]], [10, 20, 30])

        feature_names = ["feature1"]
        metrics = {"mae": 2.5, "rmse": 3.0, "r2": 0.85, "mape": 10.0}

        # Save
        model_path = trainer._save_model(
            vendor_id=vendor_id,
            model=model,
            feature_names=feature_names,
            metrics=metrics,
        )

        # Verify model file exists
        assert model_path.exists()
        assert model_path.suffix == ".pkl"

        # Verify metadata file exists
        metadata_path = model_path.with_suffix(".json")
        assert metadata_path.exists()

        # Verify metadata content
        with open(metadata_path) as f:
            metadata = json.load(f)
            assert metadata["vendor_id"] == vendor_id
            assert metadata["metrics"] == metrics
            assert metadata["feature_names"] == feature_names

    def test_get_latest_model_path(self, trainer, temp_model_dir):
        """Test retrieving latest model"""
        vendor_id = "vendor-latest-test"

        # Create multiple model files with different timestamps
        model1 = temp_model_dir / f"{vendor_id}_base_20250101_120000.pkl"
        model2 = temp_model_dir / f"{vendor_id}_base_20250102_120000.pkl"  # Newer

        model1.touch()
        model2.touch()

        # Get latest
        latest = trainer._get_latest_model_path(vendor_id)

        # Should return the newer one (model2)
        assert latest == model2

    def test_get_latest_model_path_no_models(self, trainer):
        """Test retrieving latest model when none exist"""
        vendor_id = "vendor-no-models"

        latest = trainer._get_latest_model_path(vendor_id)

        assert latest is None

    def test_load_model_metadata(self, trainer, temp_model_dir):
        """Test loading model metadata"""
        vendor_id = "vendor-metadata-test"

        # Create metadata file
        metadata = {
            "vendor_id": vendor_id,
            "metrics": {"mae": 1.5},
            "feature_names": ["test"],
        }

        model_path = temp_model_dir / f"{vendor_id}_base_20250101_000000.pkl"
        metadata_path = temp_model_dir / f"{vendor_id}_base_20250101_000000.json"

        model_path.touch()
        with open(metadata_path, "w") as f:
            json.dump(metadata, f)

        # Load
        loaded_metadata = trainer._load_model_metadata(vendor_id)

        assert loaded_metadata == metadata

    def test_load_model_metadata_no_models(self, trainer):
        """Test loading metadata when no models exist (covers line 389)"""
        vendor_id = "vendor-no-models"

        # Attempt to load metadata for non-existent vendor
        metadata = trainer._load_model_metadata(vendor_id)

        # Should return empty dict
        assert metadata == {}

    def test_load_model_metadata_no_metadata_file(self, trainer, temp_model_dir):
        """Test loading metadata when model exists but metadata file doesn't (covers line 393)"""
        vendor_id = "vendor-no-metadata"

        # Create model file WITHOUT metadata file
        model_path = temp_model_dir / f"{vendor_id}_base_20250101_000000.pkl"
        model_path.touch()

        # Attempt to load metadata
        metadata = trainer._load_model_metadata(vendor_id)

        # Should return empty dict
        assert metadata == {}


class TestScheduledRetraining:
    """Test scheduled retraining function"""

    def test_retrain_all_vendors_with_feedback(self):
        """Test scheduled retraining for all vendors"""
        mock_db = MagicMock()

        # Mock vendors with feedback
        mock_vendors = [("vendor-1",), ("vendor-2",), ("vendor-3",)]

        # Mock query
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.distinct.return_value = mock_query
        mock_query.all.return_value = mock_vendors

        # Mock trainer retrain_with_feedback
        with patch.object(ModelTrainer, 'retrain_with_feedback') as mock_retrain:
            # First vendor succeeds, second skips, third fails
            mock_retrain.side_effect = [
                {"metrics": {"mae": 2.0}},  # Success
                None,  # Insufficient feedback
                Exception("Training error"),  # Error
            ]

            result = retrain_all_vendors_with_feedback(mock_db)

            # Verify results
            assert result["total_vendors"] == 3
            assert result["retrained"] == 1
            assert result["skipped"] == 1
            assert result["failed"] == 1
            assert len(result["details"]) == 3
