"""
Unit tests for Input Validation Security Module

Tests security validation functionality:
- HTML sanitization to prevent XSS attacks
- SQL injection pattern detection
- XSS pattern detection
- Path traversal prevention
- Alphanumeric validation
- Email format validation
- UUID format validation
- Filename sanitization
- Safe path validation within base directory
- Search query sanitization
- JSON key validation against allowed lists
- Convenience wrapper functions
"""

import pytest
from pathlib import Path
import tempfile
import os

from src.security.input_validation import (
    InputValidator,
    sanitize_html,
    validate_email,
    sanitize_filename,
)


class TestHTMLSanitization:
    """Test HTML sanitization to prevent XSS"""

    def test_sanitize_html_with_script_tag(self):
        """Test sanitizing script tags"""
        malicious = "<script>alert('xss')</script>"

        sanitized = InputValidator.sanitize_html(malicious)

        assert "&lt;script&gt;" in sanitized
        assert "&lt;/script&gt;" in sanitized
        assert "<script>" not in sanitized

    def test_sanitize_html_with_quotes(self):
        """Test sanitizing quotes"""
        text = 'Hello "world" and \'friends\''

        sanitized = InputValidator.sanitize_html(text)

        assert "&quot;" in sanitized or "&#x27;" in sanitized

    def test_sanitize_html_empty_string(self):
        """Test sanitizing empty string returns empty"""
        assert InputValidator.sanitize_html("") == ""
        assert InputValidator.sanitize_html(None) == ""

    def test_sanitize_html_with_max_length(self):
        """Test sanitizing with length limit"""
        long_text = "a" * 1000

        sanitized = InputValidator.sanitize_html(long_text, max_length=100)

        assert len(sanitized) == 100

    def test_sanitize_html_preserves_safe_text(self):
        """Test safe text is preserved"""
        safe_text = "Hello world! This is safe."

        sanitized = InputValidator.sanitize_html(safe_text)

        assert "Hello world" in sanitized


class TestSQLInjectionValidation:
    """Test SQL injection detection"""

    def test_validate_no_sql_injection_safe_text(self):
        """Test safe text passes validation"""
        safe_text = "John Smith"

        assert InputValidator.validate_no_sql_injection(safe_text) is True

    def test_validate_no_sql_injection_select_statement(self):
        """Test SELECT statement is detected"""
        malicious = "admin' OR '1'='1'; SELECT * FROM users--"

        assert InputValidator.validate_no_sql_injection(malicious) is False

    def test_validate_no_sql_injection_drop_table(self):
        """Test DROP TABLE is detected"""
        malicious = "test'; DROP TABLE users--"

        assert InputValidator.validate_no_sql_injection(malicious) is False

    def test_validate_no_sql_injection_insert(self):
        """Test INSERT is detected"""
        malicious = "'; INSERT INTO users VALUES ('hacker')--"

        assert InputValidator.validate_no_sql_injection(malicious) is False

    def test_validate_no_sql_injection_union(self):
        """Test UNION is detected"""
        malicious = "' UNION SELECT password FROM users--"

        assert InputValidator.validate_no_sql_injection(malicious) is False

    def test_validate_no_sql_injection_empty_string(self):
        """Test empty string is safe"""
        assert InputValidator.validate_no_sql_injection("") is True
        assert InputValidator.validate_no_sql_injection(None) is True

    def test_validate_no_sql_injection_case_insensitive(self):
        """Test detection is case-insensitive"""
        assert InputValidator.validate_no_sql_injection("SeLeCt * FrOm users") is False


class TestXSSValidation:
    """Test XSS pattern detection"""

    def test_validate_no_xss_safe_text(self):
        """Test safe text passes"""
        safe_text = "Hello world"

        assert InputValidator.validate_no_xss(safe_text) is True

    def test_validate_no_xss_script_tag(self):
        """Test <script> tag is detected"""
        malicious = "<script>alert('xss')</script>"

        assert InputValidator.validate_no_xss(malicious) is False

    def test_validate_no_xss_javascript_protocol(self):
        """Test javascript: protocol is detected"""
        malicious = "<a href='javascript:alert(1)'>click</a>"

        assert InputValidator.validate_no_xss(malicious) is False

    def test_validate_no_xss_onerror_handler(self):
        """Test onerror handler is detected"""
        malicious = "<img src=x onerror=alert(1)>"

        assert InputValidator.validate_no_xss(malicious) is False

    def test_validate_no_xss_onload_handler(self):
        """Test onload handler is detected"""
        malicious = "<body onload=alert(1)>"

        assert InputValidator.validate_no_xss(malicious) is False

    def test_validate_no_xss_iframe(self):
        """Test <iframe> tag is detected"""
        malicious = "<iframe src='evil.com'></iframe>"

        assert InputValidator.validate_no_xss(malicious) is False

    def test_validate_no_xss_empty_string(self):
        """Test empty string is safe"""
        assert InputValidator.validate_no_xss("") is True
        assert InputValidator.validate_no_xss(None) is True


class TestPathTraversalValidation:
    """Test path traversal detection"""

    def test_validate_no_path_traversal_safe_path(self):
        """Test safe path passes"""
        safe_path = "uploads/file.txt"

        assert InputValidator.validate_no_path_traversal(safe_path) is True

    def test_validate_no_path_traversal_dotdot_unix(self):
        """Test ../ is detected"""
        malicious = "../../../etc/passwd"

        assert InputValidator.validate_no_path_traversal(malicious) is False

    def test_validate_no_path_traversal_dotdot_windows(self):
        """Test ..\ is detected"""
        malicious = "..\\..\\..\\windows\\system32"

        assert InputValidator.validate_no_path_traversal(malicious) is False

    def test_validate_no_path_traversal_empty_string(self):
        """Test empty string is safe"""
        assert InputValidator.validate_no_path_traversal("") is True
        assert InputValidator.validate_no_path_traversal(None) is True


class TestAlphanumericValidation:
    """Test alphanumeric validation"""

    def test_validate_alphanumeric_safe_text(self):
        """Test alphanumeric with dashes passes"""
        assert InputValidator.validate_alphanumeric("user-123_test") is True

    def test_validate_alphanumeric_no_dash(self):
        """Test alphanumeric without dash option"""
        assert InputValidator.validate_alphanumeric("user123", allow_dash=False) is True
        assert InputValidator.validate_alphanumeric("user-123", allow_dash=False) is False

    def test_validate_alphanumeric_special_chars(self):
        """Test special characters are rejected"""
        assert InputValidator.validate_alphanumeric("user@example") is False
        assert InputValidator.validate_alphanumeric("user.name") is False

    def test_validate_alphanumeric_empty_string(self):
        """Test empty string is invalid"""
        assert InputValidator.validate_alphanumeric("") is False
        assert InputValidator.validate_alphanumeric(None) is False


class TestEmailValidation:
    """Test email validation"""

    def test_validate_email_valid_addresses(self):
        """Test valid email addresses"""
        valid_emails = [
            "user@example.com",
            "john.smith@company.co.uk",
            "test+tag@domain.org",
            "user123@test-domain.com",
        ]

        for email in valid_emails:
            assert InputValidator.validate_email(email) is True

    def test_validate_email_invalid_addresses(self):
        """Test invalid email addresses"""
        invalid_emails = [
            "notanemail",
            "@example.com",
            "user@",
            "user@.com",
            "user..double@example.com",
            "",
            None,
        ]

        for email in invalid_emails:
            result = InputValidator.validate_email(email)
            assert result is False, f"Email '{email}' should be invalid but returned {result}"

    def test_validate_email_too_long(self):
        """Test email exceeding RFC 5321 length limits"""
        # Email too long (> 254 chars)
        long_email = "a" * 250 + "@example.com"
        assert InputValidator.validate_email(long_email) is False

    def test_validate_email_local_part_too_long(self):
        """Test local part exceeding 64 chars"""
        long_local = "a" * 65 + "@example.com"
        assert InputValidator.validate_email(long_local) is False


class TestUUIDValidation:
    """Test UUID validation"""

    def test_validate_uuid_valid_uuids(self):
        """Test valid UUID formats"""
        valid_uuids = [
            "123e4567-e89b-12d3-a456-426614174000",
            "550e8400-e29b-41d4-a716-446655440000",
            "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
        ]

        for uuid_str in valid_uuids:
            assert InputValidator.validate_uuid(uuid_str) is True

    def test_validate_uuid_invalid_uuids(self):
        """Test invalid UUID formats"""
        invalid_uuids = [
            "not-a-uuid",
            "123e4567-e89b-12d3-a456",  # Too short
            "123e4567-e89b-12d3-a456-426614174000-extra",  # Too long
            "123e4567e89b12d3a456426614174000",  # No dashes
            "",
            None,
        ]

        for uuid_str in invalid_uuids:
            assert InputValidator.validate_uuid(uuid_str) is False

    def test_validate_uuid_case_insensitive(self):
        """Test UUID validation is case-insensitive"""
        uuid_lower = "123e4567-e89b-12d3-a456-426614174000"
        uuid_upper = "123E4567-E89B-12D3-A456-426614174000"

        assert InputValidator.validate_uuid(uuid_lower) is True
        assert InputValidator.validate_uuid(uuid_upper) is True


class TestFilenameSanitization:
    """Test filename sanitization"""

    def test_sanitize_filename_safe_name(self):
        """Test safe filename is preserved"""
        safe_name = "document.pdf"

        sanitized = InputValidator.sanitize_filename(safe_name)

        assert sanitized == "document.pdf"

    def test_sanitize_filename_removes_path_separators(self):
        """Test path separators are removed"""
        malicious = "../../../etc/passwd"

        sanitized = InputValidator.sanitize_filename(malicious)

        assert "/" not in sanitized
        assert "\\" not in sanitized

    def test_sanitize_filename_removes_null_bytes(self):
        """Test null bytes are removed"""
        malicious = "file\x00.txt"

        sanitized = InputValidator.sanitize_filename(malicious)

        assert "\x00" not in sanitized

    def test_sanitize_filename_removes_special_chars(self):
        """Test special characters are replaced"""
        malicious = 'file<name>with:special|chars?.txt'

        sanitized = InputValidator.sanitize_filename(malicious)

        assert "<" not in sanitized
        assert ">" not in sanitized
        assert ":" not in sanitized
        assert "|" not in sanitized
        assert "?" not in sanitized

    def test_sanitize_filename_limits_length(self):
        """Test filename length is limited to 255"""
        long_name = "a" * 300 + ".txt"

        sanitized = InputValidator.sanitize_filename(long_name)

        assert len(sanitized) <= 255
        assert sanitized.endswith(".txt")

    def test_sanitize_filename_handles_empty(self):
        """Test empty filename returns 'unnamed'"""
        assert InputValidator.sanitize_filename("") == "unnamed"
        assert InputValidator.sanitize_filename(None) == "unnamed"

    def test_sanitize_filename_strips_dots_and_spaces(self):
        """Test leading/trailing dots and spaces are stripped"""
        assert InputValidator.sanitize_filename("  file.txt  ") == "file.txt"
        assert InputValidator.sanitize_filename("...file.txt") == "file.txt"


class TestSafePathValidation:
    """Test safe path validation within base directory"""

    @pytest.fixture
    def temp_base_dir(self):
        """Create temporary base directory"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        # Cleanup happens automatically with temp directory

    def test_validate_safe_path_within_base(self, temp_base_dir):
        """Test path within base directory is valid"""
        safe_path = os.path.join(temp_base_dir, "subdir", "file.txt")

        is_safe = InputValidator.validate_safe_path(safe_path, temp_base_dir)

        assert is_safe is True

    def test_validate_safe_path_traversal_attack(self, temp_base_dir):
        """Test path traversal is detected"""
        malicious_path = os.path.join(temp_base_dir, "..", "..", "etc", "passwd")

        is_safe = InputValidator.validate_safe_path(malicious_path, temp_base_dir)

        assert is_safe is False

    def test_validate_safe_path_exact_base(self, temp_base_dir):
        """Test exact base directory is valid"""
        is_safe = InputValidator.validate_safe_path(temp_base_dir, temp_base_dir)

        assert is_safe is True

    def test_validate_safe_path_handles_exception(self):
        """Test exception handling returns False"""
        # Invalid paths that cause exceptions
        is_safe = InputValidator.validate_safe_path("/nonexistent/\x00/path", "/tmp")

        assert is_safe is False


class TestSearchQuerySanitization:
    """Test search query sanitization"""

    def test_sanitize_search_query_normal_text(self):
        """Test normal search text is preserved"""
        query = "product search term"

        sanitized = InputValidator.sanitize_search_query(query)

        assert sanitized == "product search term"

    def test_sanitize_search_query_max_length(self):
        """Test query is truncated to max length"""
        long_query = "a" * 500

        sanitized = InputValidator.sanitize_search_query(long_query, max_length=200)

        assert len(sanitized) == 200

    def test_sanitize_search_query_removes_control_chars(self):
        """Test control characters are removed"""
        query_with_control = "search\x00\x01\x02term"

        sanitized = InputValidator.sanitize_search_query(query_with_control)

        assert "\x00" not in sanitized
        assert "\x01" not in sanitized

    def test_sanitize_search_query_preserves_newlines(self):
        """Test newlines and tabs are preserved"""
        query = "line1\nline2\ttab"

        sanitized = InputValidator.sanitize_search_query(query)

        assert "\n" in sanitized
        assert "\t" in sanitized

    def test_sanitize_search_query_strips_whitespace(self):
        """Test leading/trailing whitespace is stripped"""
        query = "  search query  "

        sanitized = InputValidator.sanitize_search_query(query)

        assert sanitized == "search query"

    def test_sanitize_search_query_empty(self):
        """Test empty query returns empty string"""
        assert InputValidator.sanitize_search_query("") == ""
        assert InputValidator.sanitize_search_query(None) == ""


class TestJSONKeyValidation:
    """Test JSON key validation"""

    def test_validate_json_keys_all_allowed(self):
        """Test all allowed keys pass validation"""
        data = {"name": "John", "age": 30, "email": "john@example.com"}
        allowed = ["name", "age", "email"]

        is_valid = InputValidator.validate_json_keys(data, allowed)

        assert is_valid is True

    def test_validate_json_keys_unexpected_key(self):
        """Test unexpected key fails validation"""
        data = {"name": "John", "age": 30, "malicious_field": "hack"}
        allowed = ["name", "age"]

        is_valid = InputValidator.validate_json_keys(data, allowed)

        assert is_valid is False

    def test_validate_json_keys_subset_allowed(self):
        """Test subset of allowed keys is valid"""
        data = {"name": "John"}
        allowed = ["name", "age", "email"]

        is_valid = InputValidator.validate_json_keys(data, allowed)

        assert is_valid is True

    def test_validate_json_keys_not_dict(self):
        """Test non-dict input fails validation"""
        is_valid = InputValidator.validate_json_keys("not a dict", ["key"])

        assert is_valid is False

    def test_validate_json_keys_empty_dict(self):
        """Test empty dict is valid"""
        is_valid = InputValidator.validate_json_keys({}, ["name", "age"])

        assert is_valid is True


class TestConvenienceFunctions:
    """Test convenience wrapper functions"""

    def test_sanitize_html_wrapper(self):
        """Test sanitize_html convenience function"""
        malicious = "<script>alert('xss')</script>"

        sanitized = sanitize_html(malicious)

        assert "&lt;script&gt;" in sanitized

    def test_validate_email_wrapper(self):
        """Test validate_email convenience function"""
        assert validate_email("user@example.com") is True
        assert validate_email("invalid") is False

    def test_sanitize_filename_wrapper(self):
        """Test sanitize_filename convenience function"""
        malicious = "../../../etc/passwd"

        sanitized = sanitize_filename(malicious)

        assert "/" not in sanitized
