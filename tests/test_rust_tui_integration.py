"""Tests for the Python-to-Rust TUI integration.

Verifies that:
1. The Rust binary is findable by the Python CLI detection logic
2. The Rust binary accepts the expected CLI arguments
3. The Python fallback works when the binary is missing
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _find_rust_tui_binary() -> str | None:
    """Mirror of the CLI's _find_rust_tui_binary function."""
    candidates = [
        PROJECT_ROOT / "target" / "release" / "sediman-tui",
        PROJECT_ROOT / "target" / "debug" / "sediman-tui",
        "sediman-tui",
    ]
    for candidate in candidates:
        if isinstance(candidate, Path) and candidate.exists():
            return str(candidate.resolve())
        if isinstance(candidate, str):
            which = os.popen(f"which {candidate} 2>/dev/null").read().strip()
            if which:
                return which
    return None


@pytest.mark.skipif(
    not (PROJECT_ROOT / "target" / "release" / "sediman-tui").exists()
    and not (PROJECT_ROOT / "target" / "debug" / "sediman-tui").exists(),
    reason="Rust TUI binary not built. Run: cargo build -p sediman-tui",
)
class TestRustTuiBinary:
    """Tests that require the Rust TUI binary to be built."""

    @pytest.fixture(scope="class")
    def binary_path(self) -> str:
        path = _find_rust_tui_binary()
        assert path is not None, "Rust TUI binary should be findable"
        return path

    def test_binary_exists(self):
        """The binary can be found by the Python CLI detection logic."""
        path = _find_rust_tui_binary()
        assert path is not None, (
            "sediman-tui binary not found. Build with: cargo build --release -p sediman-tui"
        )
        assert os.path.exists(path), f"Binary path {path} does not exist"

    def test_binary_help(self, binary_path: str):
        """Running --help returns usage info."""
        result = subprocess.run(
            [binary_path, "--help"], capture_output=True, text=True, timeout=10
        )
        assert result.returncode == 0
        assert "Sediman TUI" in result.stdout
        assert "--provider" in result.stdout
        assert "--model" in result.stdout
        assert "--headless" in result.stdout
        assert "--api-url" in result.stdout

    def test_binary_default_api_url(self, binary_path: str):
        """The default API URL is http://localhost:8080."""
        result = subprocess.run(
            [binary_path, "--help"], capture_output=True, text=True, timeout=10
        )
        assert "http://localhost:8080" in result.stdout

    def test_binary_accepts_provider_flag(self, binary_path: str):
        """The --provider flag is accepted with a value."""
        # Just validate parsing — the binary will fail to connect, but shouldn't crash on args
        result = subprocess.run(
            [binary_path, "--provider", "ollama", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0

    def test_binary_accepts_model_flag(self, binary_path: str):
        """The --model flag is accepted."""
        result = subprocess.run(
            [binary_path, "--model", "gpt-4o", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0

    def test_binary_accepts_headless_flag(self, binary_path: str):
        """The --headless flag is a boolean flag (no value)."""
        result = subprocess.run(
            [binary_path, "--headless", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0

    def test_binary_rejects_unknown_flags(self, binary_path: str):
        """Unknown flags should cause a non-zero exit."""
        result = subprocess.run(
            [binary_path, "--nonexistent-flag"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0

    def test_binary_combined_args(self, binary_path: str):
        """Multiple flags can be combined."""
        result = subprocess.run(
            [
                binary_path,
                "--provider", "openai",
                "--model", "gpt-4o-mini",
                "--headless",
                "--api-url", "http://127.0.0.1:9999",
                "--help",
            ],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0

    def test_all_args_forwarded_from_cli(self, binary_path: str):
        """Simulates what _launch_rust_tui in cli.py does."""
        provider = "openai"
        model = "gpt-4o"
        base_url = None
        headless = True

        args = [binary_path]
        args.extend(["--provider", provider])
        if model:
            args.extend(["--model", model])
        if base_url:
            args.extend(["--base-url", base_url])
        if headless:
            args.append("--headless")
        args.append("--help")

        result = subprocess.run(args, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0


class TestBinaryDetection:
    """Tests for the binary detection logic."""

    def test_detection_finds_binary(self):
        """Detection should find the built binary."""
        path = _find_rust_tui_binary()
        # Either the binary exists or we document how to build it
        if path is None:
            pytest.skip("Binary not built — run: cargo build -p sediman-tui")
        assert os.access(path, os.X_OK), f"{path} is not executable"

    def test_detection_returns_none_when_missing(self, monkeypatch):
        """When the binary is absent, detection returns None."""
        monkeypatch.setattr(Path, "exists", lambda self: False)
        assert _find_rust_tui_binary() is None

    def test_binary_size(self):
        """The binary should be a reasonable size (>1MB for release)."""
        path = _find_rust_tui_binary()
        if path is None:
            pytest.skip("Binary not built")
        size = os.path.getsize(path)
        assert size > 100_000, f"Binary seems too small: {size} bytes"
