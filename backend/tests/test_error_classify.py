"""Tests for the error classification module."""

from app.services.extraction.error_classify import classify_error


class TestClassifyError:
    def test_none_error_returns_none(self):
        assert classify_error(None) is None

    def test_empty_string_returns_none(self):
        assert classify_error("") is None

    def test_needs_review_status(self):
        assert classify_error(None, status="needs_review") == "validation"

    def test_completed_status_no_error(self):
        assert classify_error(None, status="completed") is None

    def test_auth_api_key(self):
        assert classify_error("API key is invalid") == "auth"

    def test_auth_missing_key(self):
        assert classify_error("missing_api_key: openai") == "auth"

    def test_auth_not_configured(self):
        assert classify_error("Provider not configured") == "auth"

    def test_rate_limit(self):
        assert classify_error("Rate limit exceeded") == "rate_limit"

    def test_rate_limit_429(self):
        assert classify_error("HTTP 429 Too Many Requests") == "rate_limit"

    def test_rate_limit_quota(self):
        assert classify_error("Billing quota exceeded") == "rate_limit"

    def test_timeout(self):
        assert classify_error("Request timed out after 300s") == "timeout"

    def test_timeout_deadline(self):
        assert classify_error("Deadline exceeded") == "timeout"

    def test_parse_error_json(self):
        assert classify_error("Could not extract a JSON block") == "parse_error"

    def test_parse_error_unparseable(self):
        assert classify_error("Unparseable LLM output") == "parse_error"

    def test_file_error_not_found(self):
        assert classify_error("File not found: /uploads/abc.pdf") == "file_error"

    def test_file_error_does_not_exist(self):
        assert classify_error("Document does not exist") == "file_error"

    def test_provider_error_500(self):
        assert classify_error("HTTP 500 Internal Server Error") == "provider_error"

    def test_provider_error_service_unavailable(self):
        assert classify_error("Service unavailable, try later") == "provider_error"

    def test_unknown_error(self):
        assert classify_error("Something went wrong") == "unknown"

    def test_error_with_status(self):
        # Error message takes priority over status
        assert classify_error("API key is invalid", status="failed") == "auth"
