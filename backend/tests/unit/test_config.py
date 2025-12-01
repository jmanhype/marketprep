"""
Unit tests for Configuration

Tests application configuration and validation.
"""

import pytest
from pydantic import ValidationError

from src.config import Settings


class TestSettings:
    """Test Settings configuration"""

    def test_encryption_key_validation_too_short(self):
        """Test encryption key validation fails for short keys"""
        with pytest.raises(ValidationError) as exc_info:
            Settings(encryption_key="short")  # Less than 32 bytes

        assert "Encryption key must be at least 32 bytes" in str(exc_info.value)

    def test_encryption_key_validation_exactly_32_bytes(self):
        """Test encryption key validation passes for exactly 32 bytes"""
        # 32 character string = 32 bytes
        key = "a" * 32

        settings = Settings(encryption_key=key)

        assert settings.encryption_key == key

    def test_encryption_key_validation_longer_than_32_bytes(self):
        """Test encryption key validation passes for >32 bytes"""
        key = "a" * 64

        settings = Settings(encryption_key=key)

        assert settings.encryption_key == key
