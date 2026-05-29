from __future__ import annotations

import re
from dataclasses import dataclass


# ── Exception Hierarchy ────────────────────────────────────────────


class SedimanError(Exception):
    """Base exception for all sediman-browse errors."""

    def __init__(self, message: str = "", *, code: str = "UNKNOWN") -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class ToolError(SedimanError):
    """Raised when a tool encounters an unrecoverable error."""

    def __init__(self, message: str = "", *, code: str = "TOOL_ERROR") -> None:
        super().__init__(message, code=code)


class TerminalError(ToolError):
    """Raised when terminal/shell command execution fails."""

    def __init__(self, message: str = "", command: str = "", *, code: str = "TERMINAL_ERROR") -> None:
        self.command = command
        super().__init__(message, code=code)


class BrowserError(SedimanError):
    """Raised when browser automation fails."""

    def __init__(self, message: str = "", *, code: str = "BROWSER_ERROR") -> None:
        super().__init__(message, code=code)


class LLMError(SedimanError):
    """Raised when LLM provider communication fails."""

    def __init__(self, message: str = "", *, code: str = "LLM_ERROR") -> None:
        super().__init__(message, code=code)


class AuthError(LLMError):
    """Raised for authentication/API key errors."""

    def __init__(self, message: str = "") -> None:
        super().__init__(message, code="AUTH_ERROR")


class RateLimitError(LLMError):
    """Raised when rate limited by the LLM provider."""

    def __init__(self, message: str = "") -> None:
        super().__init__(message, code="RATE_LIMIT")


class SkillError(SedimanError):
    """Raised when skill operations fail."""

    def __init__(self, message: str = "", *, code: str = "SKILL_ERROR") -> None:
        super().__init__(message, code=code)


class MemoryError(SedimanError):
    """Raised when memory operations fail."""

    def __init__(self, message: str = "", *, code: str = "MEMORY_ERROR") -> None:
        super().__init__(message, code=code)


class ConfigError(SedimanError):
    """Raised when configuration is invalid."""

    def __init__(self, message: str = "") -> None:
        super().__init__(message, code="CONFIG_ERROR")


# ── Existing ErrorInfo ─────────────────────────────────────────────


@dataclass
class ErrorInfo:
    code: str
    message: str
    suggestion: str | None = None


_ERROR_PATTERNS = re.compile(
    r"(?:error|failed|timeout|not found|exception|unreachable|refused|denied)",
    re.IGNORECASE,
)


def classify_error(exc: Exception) -> ErrorInfo:
    if isinstance(exc, AuthError):
        return ErrorInfo("AUTH_ERROR", exc.message or "Invalid or missing API key.", "Set your API key: export OPENAI_API_KEY=sk-...")

    if isinstance(exc, RateLimitError):
        return ErrorInfo("RATE_LIMIT", exc.message or "Rate limit exceeded.", "Wait a moment and try again.")

    if isinstance(exc, LLMError):
        return ErrorInfo("LLM_ERROR", exc.message or "LLM provider error.", "Check your provider configuration.")

    if isinstance(exc, TerminalError):
        return ErrorInfo("TERMINAL_ERROR", exc.message or "Command execution failed.", "Check the command and try again.")

    if isinstance(exc, BrowserError):
        return ErrorInfo("BROWSER_ERROR", exc.message or "Browser error.", "Check browser configuration.")

    if isinstance(exc, ToolError):
        return ErrorInfo("TOOL_ERROR", exc.message or "Tool execution failed.", "Try a different approach.")

    if isinstance(exc, SkillError):
        return ErrorInfo("SKILL_ERROR", exc.message or "Skill operation failed.", "Check skill configuration.")

    if isinstance(exc, MemoryError):
        return ErrorInfo("MEMORY_ERROR", exc.message or "Memory operation failed.", "")

    if isinstance(exc, ConfigError):
        return ErrorInfo("CONFIG_ERROR", exc.message or "Configuration error.", "Check your settings.")

    msg = str(exc)
    exc_type = type(exc).__name__
    msg_lower = msg.lower()

    if "api key" in msg_lower or "apikey" in msg_lower or "invalid key" in msg_lower or "incorrect api key" in msg_lower:
        return ErrorInfo("AUTH_ERROR", msg, "Set your API key: export OPENAI_API_KEY=sk-...")

    if "ConnectionError" in exc_type or "ConnectionRefused" in msg or "connect" in msg_lower:
        return ErrorInfo("CONNECTION_ERROR", "Cannot connect to the LLM provider.", "Check your network connection and API base URL.")

    if "timeout" in msg_lower or "timed out" in msg_lower or "TimeoutError" in exc_type:
        return ErrorInfo("TIMEOUT", "The request timed out.", "Try again, or use a simpler task.")

    if "rate limit" in msg_lower or "RateLimitError" in exc_type:
        return ErrorInfo("RATE_LIMIT", "Rate limit exceeded.", "Wait a moment and try again.")

    if "not found" in msg_lower and "browser" in msg_lower:
        return ErrorInfo("BROWSER_NOT_FOUND", "Browser not found.", "Install Chromium or run with a different browser.")

    if "ModuleNotFoundError" in exc_type:
        return ErrorInfo("MISSING_DEP", f"Missing dependency: {msg}", "Run: pip install sediman-browse")

    return ErrorInfo("INTERNAL_ERROR", msg[:300] if msg else exc_type, None)


def looks_like_error(text: str) -> bool:
    if not text:
        return True
    matches = _ERROR_PATTERNS.findall(text)
    if len(matches) >= 2:
        return True
    first_line = text.split("\n")[0].lower()
    return bool(re.match(r"^(error|failed|exception|traceback)", first_line))
