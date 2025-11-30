"""Unit tests for encryption service."""
import pytest
import base64
from cryptography.fernet import InvalidToken

from src.services.encryption import EncryptionService


class TestEncryptionServiceInit:
    """Test EncryptionService initialization."""

    def test_init_creates_cipher(self):
        """Test initialization creates Fernet cipher."""
        service = EncryptionService()

        assert service.cipher is not None
        assert hasattr(service.cipher, 'encrypt')
        assert hasattr(service.cipher, 'decrypt')


class TestEncrypt:
    """Test encryption functionality."""

    def test_encrypt_returns_base64_string(self):
        """Test encrypt returns base64-encoded string."""
        service = EncryptionService()

        plaintext = "sensitive_token_data"
        encrypted = service.encrypt(plaintext)

        # Should be a string
        assert isinstance(encrypted, str)

        # Should be valid base64
        try:
            base64.b64decode(encrypted)
        except Exception:
            pytest.fail("Encrypted data is not valid base64")

    def test_encrypt_different_inputs_produce_different_outputs(self):
        """Test different inputs produce different encrypted outputs."""
        service = EncryptionService()

        encrypted1 = service.encrypt("token1")
        encrypted2 = service.encrypt("token2")

        assert encrypted1 != encrypted2

    def test_encrypt_same_input_produces_different_outputs(self):
        """Test same input produces different outputs (due to nonce)."""
        service = EncryptionService()

        encrypted1 = service.encrypt("same_token")
        encrypted2 = service.encrypt("same_token")

        # Fernet includes a random nonce, so same plaintext encrypts differently
        assert encrypted1 != encrypted2

    def test_encrypt_empty_string(self):
        """Test encrypting empty string."""
        service = EncryptionService()

        encrypted = service.encrypt("")

        assert isinstance(encrypted, str)
        assert len(encrypted) > 0  # Encrypted form should have data


class TestDecrypt:
    """Test decryption functionality."""

    def test_decrypt_reverses_encrypt(self):
        """Test decrypt successfully reverses encryption."""
        service = EncryptionService()

        plaintext = "my_secret_token_12345"
        encrypted = service.encrypt(plaintext)
        decrypted = service.decrypt(encrypted)

        assert decrypted == plaintext

    def test_decrypt_multiple_values(self):
        """Test decrypting multiple different encrypted values."""
        service = EncryptionService()

        test_values = [
            "token1",
            "another_secret",
            "API_KEY_ABC123",
            "very_long_token_" * 10,
        ]

        for plaintext in test_values:
            encrypted = service.encrypt(plaintext)
            decrypted = service.decrypt(encrypted)
            assert decrypted == plaintext

    def test_decrypt_invalid_data_raises_error(self):
        """Test decrypting invalid data raises InvalidToken."""
        service = EncryptionService()

        invalid_encrypted = base64.b64encode(b"not_real_encrypted_data").decode('utf-8')

        with pytest.raises(InvalidToken):
            service.decrypt(invalid_encrypted)

    def test_decrypt_corrupted_base64_raises_error(self):
        """Test decrypting corrupted base64 raises error."""
        service = EncryptionService()

        # Invalid base64
        with pytest.raises(Exception):  # Could be InvalidToken or base64 decode error
            service.decrypt("not_valid_base64!@#$%")


class TestEncryptDecryptRoundTrip:
    """Test encrypt/decrypt round-trip scenarios."""

    def test_round_trip_unicode_characters(self):
        """Test round-trip with Unicode characters."""
        service = EncryptionService()

        plaintext = "Hello 世界 🌍 émojis"
        encrypted = service.encrypt(plaintext)
        decrypted = service.decrypt(encrypted)

        assert decrypted == plaintext

    def test_round_trip_special_characters(self):
        """Test round-trip with special characters."""
        service = EncryptionService()

        plaintext = "token!@#$%^&*()_+-=[]{}|;':\",./<>?"
        encrypted = service.encrypt(plaintext)
        decrypted = service.decrypt(encrypted)

        assert decrypted == plaintext

    def test_round_trip_empty_string(self):
        """Test round-trip with empty string."""
        service = EncryptionService()

        plaintext = ""
        encrypted = service.encrypt(plaintext)
        decrypted = service.decrypt(encrypted)

        assert decrypted == plaintext

    def test_encryption_is_deterministic_per_instance(self):
        """Test same instance can decrypt its own encrypted data."""
        service = EncryptionService()

        plaintext = "test_token"

        # Encrypt and decrypt multiple times with same instance
        for _ in range(5):
            encrypted = service.encrypt(plaintext)
            decrypted = service.decrypt(encrypted)
            assert decrypted == plaintext

    def test_different_instances_can_decrypt(self):
        """Test different EncryptionService instances can decrypt each other's data."""
        service1 = EncryptionService()
        service2 = EncryptionService()

        plaintext = "shared_secret"

        # Encrypt with service1
        encrypted = service1.encrypt(plaintext)

        # Decrypt with service2 (should work since they use same config key)
        decrypted = service2.decrypt(encrypted)

        assert decrypted == plaintext
