"""
Unit tests for Database Connection Management

Tests database session management:
- Database session dependency (get_db)
- Session creation and cleanup
- Database initialization (init_db)
"""

import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session

from src.database import get_db, init_db, SessionLocal, engine, Base


class TestGetDb:
    """Test get_db dependency"""

    def test_get_db_yields_session(self):
        """Test dependency yields database session"""
        gen = get_db()
        db = next(gen)

        assert isinstance(db, Session)

        # Close generator
        try:
            next(gen)
        except StopIteration:
            pass  # Expected

    def test_get_db_closes_session(self):
        """Test dependency closes session on completion"""
        with patch('src.database.SessionLocal') as mock_session_class:
            mock_session = MagicMock(spec=Session)
            mock_session_class.return_value = mock_session

            gen = get_db()
            db = next(gen)

            # Close generator
            try:
                next(gen)
            except StopIteration:
                pass

            # Session should be closed
            mock_session.close.assert_called_once()

    def test_get_db_closes_session_on_exception(self):
        """Test dependency closes session even if exception occurs"""
        with patch('src.database.SessionLocal') as mock_session_class:
            mock_session = MagicMock(spec=Session)
            mock_session_class.return_value = mock_session

            gen = get_db()
            db = next(gen)

            # Simulate exception in finally block
            try:
                gen.throw(Exception("Test exception"))
            except Exception:
                pass

            # Session should still be closed
            mock_session.close.assert_called_once()


class TestInitDb:
    """Test init_db function"""

    @patch.object(Base.metadata, 'create_all')
    def test_init_db_creates_tables(self, mock_create_all):
        """Test init_db creates all database tables"""
        init_db()

        mock_create_all.assert_called_once_with(bind=engine)


class TestDatabaseConfiguration:
    """Test database configuration"""

    def test_engine_exists(self):
        """Test database engine is created"""
        assert engine is not None

    def test_session_local_exists(self):
        """Test SessionLocal factory is created"""
        assert SessionLocal is not None
