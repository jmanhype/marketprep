"""
Unit tests for Secrets Manager Module

Tests cryptographic functionality:
- String encryption and decryption with Fernet
- Password hashing and verification with bcrypt
- API key generation and hashing
- Secret token generation
- API key rotation utilities
- OAuth token encryption
- API credentials encryption/decryption
- Convenience wrapper functions
"""

import pytest
from datetime import datetime, timedelta
from freezegun import freeze_time
from unittest.mock import patch, MagicMock

from src.security.secrets_manager import (
    SecretsManager,
    APIKeyRotation,
    SecureDataHandler,
    generate_api_key,
    hash_api_key,
    encrypt_string,
    decrypt_string,
)


class TestSecretsManagerEncryption:
    """Test encryption and decryption functionality"""

    @pytest.fixture
    def manager(self):
        """Create SecretsManager instance"""
        return SecretsManager()

    def test_encrypt_string_returns_different_output(self, manager):
        """Test encryption produces different output than input"""
        plaintext = "sensitive_data_12345"

        encrypted = manager.encrypt_string(plaintext)

        assert encrypted != plaintext
        assert len(encrypted) > 0

    def test_encrypt_decrypt_roundtrip(self, manager):
        """Test encryption and decryption roundtrip"""
        plaintext = "test_secret_value"

        encrypted = manager.encrypt_string(plaintext)
        decrypted = manager.decrypt_string(encrypted)

        assert decrypted == plaintext

    def test_encrypt_unicode_string(self, manager):
        """Test encryption with unicode characters"""
        plaintext = "测试数据 🔐 Ñoño"

        encrypted = manager.encrypt_string(plaintext)
        decrypted = manager.decrypt_string(encrypted)

        assert decrypted == plaintext

    def test_encrypt_empty_string(self, manager):
        """Test encryption of empty string"""
        plaintext = ""

        encrypted = manager.encrypt_string(plaintext)
        decrypted = manager.decrypt_string(encrypted)

        assert decrypted == ""

    def test_encrypt_long_string(self, manager):
        """Test encryption of long strings"""
        plaintext = "a" * 10000

        encrypted = manager.encrypt_string(plaintext)
        decrypted = manager.decrypt_string(encrypted)

        assert decrypted == plaintext

    def test_decrypt_invalid_ciphertext_raises_error(self, manager):
        """Test decrypting invalid data raises exception"""
        invalid_ciphertext = "not_valid_encrypted_data"

        with pytest.raises(Exception):
            manager.decrypt_string(invalid_ciphertext)

    def test_same_plaintext_produces_different_ciphertext(self, manager):
        """Test that encryption is non-deterministic (uses IV)"""
        plaintext = "same_value"

        encrypted1 = manager.encrypt_string(plaintext)
        encrypted2 = manager.encrypt_string(plaintext)

        # Different ciphertexts due to IV
        assert encrypted1 != encrypted2

        # But both decrypt to same plaintext
        assert manager.decrypt_string(encrypted1) == plaintext
        assert manager.decrypt_string(encrypted2) == plaintext

    def test_encrypt_string_handles_encryption_failure(self, manager):
        """Test encryption failure is logged and re-raised (covers lines 70-72)."""
        plaintext = "test_data"

        # Mock fernet.encrypt to raise an exception
        with patch.object(manager.fernet, 'encrypt', side_effect=RuntimeError("Encryption hardware failure")):
            # The exception handler should log the error and re-raise
            with pytest.raises(RuntimeError, match="Encryption hardware failure"):
                manager.encrypt_string(plaintext)


class TestSecretsManagerPasswordHashing:
    """Test password hashing and verification"""

    @pytest.fixture
    def manager(self):
        """Create SecretsManager instance"""
        return SecretsManager()

    def test_hash_password_returns_different_output(self, manager):
        """Test password hashing produces different output"""
        password = "StrongPassword123!"

        hashed = manager.hash_password(password)

        assert hashed != password
        assert len(hashed) > 0
        assert hashed.startswith("$2b$")  # bcrypt format

    def test_verify_password_correct_password(self, manager):
        """Test verifying correct password"""
        password = "MySecretPass123"
        hashed = manager.hash_password(password)

        is_valid = manager.verify_password(password, hashed)

        assert is_valid is True

    def test_verify_password_incorrect_password(self, manager):
        """Test verifying incorrect password"""
        password = "CorrectPassword"
        wrong_password = "WrongPassword"
        hashed = manager.hash_password(password)

        is_valid = manager.verify_password(wrong_password, hashed)

        assert is_valid is False

    def test_hash_password_same_password_different_hashes(self, manager):
        """Test that same password produces different hashes (salt)"""
        password = "SamePassword123"

        hash1 = manager.hash_password(password)
        hash2 = manager.hash_password(password)

        # Different hashes due to salt
        assert hash1 != hash2

        # But both verify correctly
        assert manager.verify_password(password, hash1) is True
        assert manager.verify_password(password, hash2) is True

    def test_verify_password_case_sensitive(self, manager):
        """Test password verification is case-sensitive"""
        password = "CaseSensitive"
        hashed = manager.hash_password(password)

        assert manager.verify_password("casesensitive", hashed) is False
        assert manager.verify_password("CASESENSITIVE", hashed) is False
        assert manager.verify_password("CaseSensitive", hashed) is True


class TestSecretsManagerKeyGeneration:
    """Test API key and token generation"""

    def test_generate_api_key_default_params(self):
        """Test API key generation with default parameters"""
        api_key = SecretsManager.generate_api_key()

        assert api_key.startswith("mp_")
        assert len(api_key) == 3 + 64  # "mp_" + 32 bytes = 64 hex chars

    def test_generate_api_key_custom_prefix(self):
        """Test API key generation with custom prefix"""
        api_key = SecretsManager.generate_api_key(prefix="test", length=16)

        assert api_key.startswith("test_")
        assert len(api_key) == 5 + 32  # "test_" + 16 bytes = 32 hex chars

    def test_generate_api_key_randomness(self):
        """Test that generated keys are random"""
        key1 = SecretsManager.generate_api_key()
        key2 = SecretsManager.generate_api_key()

        assert key1 != key2

    def test_generate_secret_token_default_length(self):
        """Test secret token generation"""
        token = SecretsManager.generate_secret_token()

        assert len(token) > 0
        # URL-safe base64 encoding

    def test_generate_secret_token_custom_length(self):
        """Test secret token with custom length"""
        token = SecretsManager.generate_secret_token(length=64)

        assert len(token) > 0

    def test_generate_secret_token_randomness(self):
        """Test that tokens are random"""
        token1 = SecretsManager.generate_secret_token()
        token2 = SecretsManager.generate_secret_token()

        assert token1 != token2

    def test_hash_api_key_deterministic(self):
        """Test API key hashing is deterministic"""
        api_key = "mp_test_key_12345"

        hash1 = SecretsManager.hash_api_key(api_key)
        hash2 = SecretsManager.hash_api_key(api_key)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex digest

    def test_hash_api_key_different_keys_different_hashes(self):
        """Test different keys produce different hashes"""
        key1 = "mp_key1"
        key2 = "mp_key2"

        hash1 = SecretsManager.hash_api_key(key1)
        hash2 = SecretsManager.hash_api_key(key2)

        assert hash1 != hash2


class TestAPIKeyRotation:
    """Test API key rotation utilities"""

    @freeze_time("2025-06-01 12:00:00")
    def test_should_rotate_key_old_key(self):
        """Test that old keys should be rotated"""
        # Key created 91 days ago
        created_at = datetime.utcnow() - timedelta(days=91)

        should_rotate = APIKeyRotation.should_rotate_key(created_at, rotation_days=90)

        assert should_rotate is True

    @freeze_time("2025-06-01 12:00:00")
    def test_should_rotate_key_new_key(self):
        """Test that new keys should not be rotated"""
        # Key created 30 days ago
        created_at = datetime.utcnow() - timedelta(days=30)

        should_rotate = APIKeyRotation.should_rotate_key(created_at, rotation_days=90)

        assert should_rotate is False

    @freeze_time("2025-06-01 12:00:00")
    def test_should_rotate_key_exactly_90_days(self):
        """Test key exactly at rotation period"""
        # Key created exactly 90 days ago
        created_at = datetime.utcnow() - timedelta(days=90)

        should_rotate = APIKeyRotation.should_rotate_key(created_at, rotation_days=90)

        assert should_rotate is True

    @freeze_time("2025-06-01 12:00:00")
    def test_get_rotation_warning_expired_key(self):
        """Test warning for expired key"""
        # Key created 100 days ago
        created_at = datetime.utcnow() - timedelta(days=100)

        warning = APIKeyRotation.get_rotation_warning(created_at, rotation_days=90)

        assert warning == "API key has expired and should be rotated immediately"

    @freeze_time("2025-06-01 12:00:00")
    def test_get_rotation_warning_expiring_soon(self):
        """Test warning for key expiring soon"""
        # Key created 85 days ago (5 days remaining)
        created_at = datetime.utcnow() - timedelta(days=85)

        warning = APIKeyRotation.get_rotation_warning(created_at, rotation_days=90)

        assert warning == "API key expires in 5 days"

    @freeze_time("2025-06-01 12:00:00")
    def test_get_rotation_warning_no_warning_needed(self):
        """Test no warning for fresh key"""
        # Key created 30 days ago (60 days remaining)
        created_at = datetime.utcnow() - timedelta(days=30)

        warning = APIKeyRotation.get_rotation_warning(created_at, rotation_days=90)

        assert warning is None

    @freeze_time("2025-06-01 12:00:00")
    def test_get_rotation_warning_exactly_7_days(self):
        """Test warning at exactly 7 days remaining"""
        # Key created 83 days ago (7 days remaining)
        created_at = datetime.utcnow() - timedelta(days=83)

        warning = APIKeyRotation.get_rotation_warning(created_at, rotation_days=90)

        assert warning == "API key expires in 7 days"

    @freeze_time("2025-06-01 12:00:00")
    def test_generate_key_pair(self):
        """Test generating API key pair"""
        api_key, api_key_hash, created_at = APIKeyRotation.generate_key_pair()

        # Verify key format
        assert api_key.startswith("mp_")
        assert len(api_key) == 3 + 64

        # Verify hash matches key
        expected_hash = SecretsManager.hash_api_key(api_key)
        assert api_key_hash == expected_hash

        # Verify timestamp is current
        assert created_at == datetime.utcnow()


class TestSecureDataHandler:
    """Test secure data handler for vendor data"""

    @pytest.fixture
    def handler(self):
        """Create SecureDataHandler instance"""
        return SecureDataHandler()

    def test_encrypt_oauth_token(self, handler):
        """Test OAuth token encryption"""
        token = "oauth_access_token_12345"

        encrypted = handler.encrypt_oauth_token(token)

        assert encrypted != token
        assert len(encrypted) > 0

    def test_decrypt_oauth_token(self, handler):
        """Test OAuth token decryption"""
        token = "oauth_access_token_12345"

        encrypted = handler.encrypt_oauth_token(token)
        decrypted = handler.decrypt_oauth_token(encrypted)

        assert decrypted == token

    def test_encrypt_api_credentials_all_strings(self, handler):
        """Test encrypting credentials dictionary with all strings"""
        credentials = {
            "api_key": "secret_key_123",
            "api_secret": "secret_value_456",
            "username": "vendor_user",
        }

        encrypted = handler.encrypt_api_credentials(credentials)

        # All values should be encrypted (different from originals)
        assert encrypted["api_key"] != credentials["api_key"]
        assert encrypted["api_secret"] != credentials["api_secret"]
        assert encrypted["username"] != credentials["username"]

    def test_encrypt_api_credentials_mixed_types(self, handler):
        """Test encrypting credentials with mixed types"""
        credentials = {
            "api_key": "secret_key_123",
            "timeout": 30,  # integer
            "enabled": True,  # boolean
            "config": None,  # None
        }

        encrypted = handler.encrypt_api_credentials(credentials)

        # Only strings should be encrypted
        assert encrypted["api_key"] != credentials["api_key"]
        assert encrypted["timeout"] == 30
        assert encrypted["enabled"] is True
        assert encrypted["config"] is None

    def test_encrypt_api_credentials_empty_strings(self, handler):
        """Test encrypting credentials with empty strings"""
        credentials = {
            "api_key": "secret_key",
            "optional_field": "",  # empty string
        }

        encrypted = handler.encrypt_api_credentials(credentials)

        # Non-empty strings encrypted, empty strings passed through
        assert encrypted["api_key"] != credentials["api_key"]
        assert encrypted["optional_field"] == ""

    def test_decrypt_api_credentials(self, handler):
        """Test decrypting credentials dictionary"""
        credentials = {
            "api_key": "secret_key_123",
            "api_secret": "secret_value_456",
        }

        encrypted = handler.encrypt_api_credentials(credentials)
        decrypted = handler.decrypt_api_credentials(encrypted)

        assert decrypted == credentials

    def test_decrypt_api_credentials_mixed_types(self, handler):
        """Test decrypting credentials with mixed types"""
        credentials = {
            "api_key": "secret_key",
            "timeout": 30,
            "enabled": True,
        }

        encrypted = handler.encrypt_api_credentials(credentials)
        decrypted = handler.decrypt_api_credentials(encrypted)

        assert decrypted == credentials

    def test_decrypt_api_credentials_invalid_data_graceful(self, handler):
        """Test graceful handling of invalid encrypted data"""
        # Mix of encrypted and plain text (simulating partial encryption)
        mixed_credentials = {
            "valid_encrypted": handler.secrets_manager.encrypt_string("secret"),
            "plain_text": "not_encrypted_value",  # Will fail to decrypt
            "number": 123,
        }

        decrypted = handler.decrypt_api_credentials(mixed_credentials)

        # Valid encrypted data should decrypt
        assert decrypted["valid_encrypted"] == "secret"
        # Invalid data should pass through unchanged
        assert decrypted["plain_text"] == "not_encrypted_value"
        assert decrypted["number"] == 123


class TestConvenienceFunctions:
    """Test convenience wrapper functions"""

    def test_generate_api_key_wrapper(self):
        """Test generate_api_key convenience function"""
        api_key = generate_api_key(prefix="test", length=16)

        assert api_key.startswith("test_")
        assert len(api_key) == 5 + 32

    def test_hash_api_key_wrapper(self):
        """Test hash_api_key convenience function"""
        api_key = "mp_test_key"

        hashed = hash_api_key(api_key)

        assert len(hashed) == 64
        # Should match direct call
        assert hashed == SecretsManager.hash_api_key(api_key)

    def test_encrypt_string_wrapper(self):
        """Test encrypt_string convenience function"""
        plaintext = "test_secret"

        encrypted = encrypt_string(plaintext)

        assert encrypted != plaintext
        assert len(encrypted) > 0

    def test_decrypt_string_wrapper(self):
        """Test decrypt_string convenience function"""
        plaintext = "test_secret"

        encrypted = encrypt_string(plaintext)
        decrypted = decrypt_string(encrypted)

        assert decrypted == plaintext

    def test_encrypt_decrypt_roundtrip_wrappers(self):
        """Test full roundtrip with convenience wrappers"""
        original = "sensitive_data_12345"

        encrypted = encrypt_string(original)
        decrypted = decrypt_string(encrypted)

        assert decrypted == original
