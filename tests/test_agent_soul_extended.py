from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


from sediman.agent.soul import load_soul, save_soul, reset_soul, DEFAULT_SOUL


class TestLoadSoul:
    def test_returns_default_when_no_file(self, tmp_sediman_dir: Path):
        with patch("sediman.agent.soul.SOUL_FILE", tmp_sediman_dir / "SOUL.md"):
            content = load_soul()
            assert content == DEFAULT_SOUL

    def test_returns_file_content(self, tmp_sediman_dir: Path):
        soul_file = tmp_sediman_dir / "SOUL.md"
        soul_file.parent.mkdir(parents=True, exist_ok=True)
        soul_file.write_text("Custom soul content")
        with patch("sediman.agent.soul.SOUL_FILE", soul_file):
            content = load_soul()
            assert content == "Custom soul content"

    def test_default_soul_content(self):
        assert "Sediman" in DEFAULT_SOUL
        assert "self-improving" in DEFAULT_SOUL
        assert "browser automation" in DEFAULT_SOUL


class TestSaveSoul:
    def test_creates_file(self, tmp_sediman_dir: Path):
        soul_file = tmp_sediman_dir / "SOUL.md"
        with patch("sediman.agent.soul.SOUL_FILE", soul_file):
            save_soul("New soul content")
            assert soul_file.exists()
            assert soul_file.read_text() == "New soul content"

    def test_creates_parent_dir(self, tmp_path: Path):
        soul_file = tmp_path / "deep" / "nested" / "SOUL.md"
        with patch("sediman.agent.soul.SOUL_FILE", soul_file):
            save_soul("Content")
            assert soul_file.exists()

    def test_overwrites_existing(self, tmp_sediman_dir: Path):
        soul_file = tmp_sediman_dir / "SOUL.md"
        soul_file.parent.mkdir(parents=True, exist_ok=True)
        soul_file.write_text("Old")
        with patch("sediman.agent.soul.SOUL_FILE", soul_file):
            save_soul("Updated")
            assert soul_file.read_text() == "Updated"


class TestResetSoul:
    def test_removes_file(self, tmp_sediman_dir: Path):
        soul_file = tmp_sediman_dir / "SOUL.md"
        soul_file.parent.mkdir(parents=True, exist_ok=True)
        soul_file.write_text("Content")
        with patch("sediman.agent.soul.SOUL_FILE", soul_file):
            reset_soul()
            assert not soul_file.exists()

    def test_noop_when_no_file(self, tmp_sediman_dir: Path):
        soul_file = tmp_sediman_dir / "SOUL.md"
        with patch("sediman.agent.soul.SOUL_FILE", soul_file):
            reset_soul()
            assert not soul_file.exists()
