from __future__ import annotations


from sediman.errors import classify_error, looks_like_error, ErrorInfo


class TestErrorInfo:
    def test_defaults(self):
        info = ErrorInfo(code="ERR", message="something went wrong")
        assert info.suggestion is None

    def test_with_suggestion(self):
        info = ErrorInfo(code="ERR", message="msg", suggestion="try again")
        assert info.suggestion == "try again"


class TestClassifyError:
    def test_auth_error_by_type(self):
        class AuthenticationError(Exception):
            pass
        exc = AuthenticationError("invalid key")
        info = classify_error(exc)
        assert info.code == "AUTH_ERROR"

    def test_auth_error_by_message(self):
        exc = Exception("Invalid API key provided")
        info = classify_error(exc)
        assert info.code == "AUTH_ERROR"

    def test_auth_error_api_key_message(self):
        exc = Exception("Incorrect API key")
        info = classify_error(exc)
        assert info.code == "AUTH_ERROR"

    def test_auth_error_suggestion(self):
        exc = Exception("invalid api key")
        info = classify_error(exc)
        assert "OPENAI_API_KEY" in info.suggestion

    def test_connection_error_by_type(self):
        class ConnectionError(Exception):
            pass
        exc = ConnectionError("failed")
        info = classify_error(exc)
        assert info.code == "CONNECTION_ERROR"

    def test_connection_error_by_refused(self):
        exc = Exception("Connection refused")
        info = classify_error(exc)
        assert info.code == "CONNECTION_ERROR"

    def test_connection_error_by_connect(self):
        exc = Exception("could not connect to host")
        info = classify_error(exc)
        assert info.code == "CONNECTION_ERROR"

    def test_timeout_error_by_type(self):
        class TimeoutError(Exception):
            pass
        exc = TimeoutError("timed out")
        info = classify_error(exc)
        assert info.code == "TIMEOUT"

    def test_timeout_error_by_message(self):
        exc = Exception("Request timed out after 30s")
        info = classify_error(exc)
        assert info.code == "TIMEOUT"

    def test_rate_limit_by_type(self):
        class RateLimitError(Exception):
            pass
        exc = RateLimitError("too fast")
        info = classify_error(exc)
        assert info.code == "RATE_LIMIT"

    def test_rate_limit_by_message(self):
        exc = Exception("rate limit exceeded")
        info = classify_error(exc)
        assert info.code == "RATE_LIMIT"

    def test_browser_not_found(self):
        exc = Exception("browser not found")
        info = classify_error(exc)
        assert info.code == "BROWSER_NOT_FOUND"

    def test_browser_not_found_with_chromium(self):
        exc = Exception("Chrome browser not found in PATH")
        info = classify_error(exc)
        assert info.code == "BROWSER_NOT_FOUND"

    def test_missing_dep(self):
        class ModuleNotFoundError(Exception):
            pass
        exc = ModuleNotFoundError("No module named 'something'")
        info = classify_error(exc)
        assert info.code == "MISSING_DEP"

    def test_internal_error_fallback(self):
        exc = Exception("Something unexpected happened")
        info = classify_error(exc)
        assert info.code == "INTERNAL_ERROR"
        assert info.message == "Something unexpected happened"

    def test_internal_error_truncates_long_message(self):
        exc = Exception("x" * 500)
        info = classify_error(exc)
        assert len(info.message) <= 300

    def test_internal_error_empty_message(self):
        exc = Exception()
        info = classify_error(exc)
        assert info.code == "INTERNAL_ERROR"
        assert info.message == "Exception"


class TestLooksLikeError:
    def test_empty_text_is_error(self):
        assert looks_like_error("") is True

    def test_none_text_returns_true(self):
        assert looks_like_error(None) is True

    def test_two_error_keywords(self):
        assert looks_like_error("Error: connection error occurred") is True

    def test_two_error_keywords_different(self):
        assert looks_like_error("error: request timeout") is True

    def test_single_keyword_not_error(self):
        assert looks_like_error("this is not an error") is False

    def test_starts_with_error(self):
        assert looks_like_error("Error: something broke") is True

    def test_starts_with_failed(self):
        assert looks_like_error("Failed to load page") is True

    def test_starts_with_exception(self):
        assert looks_like_error("Exception in thread") is True

    def test_starts_with_traceback(self):
        assert looks_like_error("Traceback (most recent)") is True

    def test_normal_text(self):
        assert looks_like_error("Task completed successfully") is False

    def test_success_text(self):
        assert looks_like_error("All good, operation done") is False

    def test_timeout_and_error_together(self):
        assert looks_like_error("Timeout error occurred") is True

    def test_case_insensitive(self):
        assert looks_like_error("ERROR: FAILED") is True

    def test_mixed_case_error_keywords(self):
        assert looks_like_error("Error: Not Found") is True

    def test_single_keyword_at_start(self):
        assert looks_like_error("error but only one keyword") is True

    def test_multiline(self):
        assert looks_like_error("normal line\nError: failed\n") is True
