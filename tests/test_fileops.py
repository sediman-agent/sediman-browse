from __future__ import annotations

import pytest
import pytest_asyncio

from sediman.agent.tools.fileops import (
    _fuzzy_match_hunk,
    _handle_list_files,
    _handle_patch,
    _handle_read_file,
    _handle_search_files,
    _handle_write_file,
    _token_overlap,
)


@pytest.fixture
def sample_file(tmp_path):
    p = tmp_path / "sample.txt"
    p.write_text("line one\nline two\nline three\nline four\nline five\n", encoding="utf-8")
    return p


@pytest.fixture
def large_file(tmp_path):
    p = tmp_path / "large.txt"
    content = "\n".join(f"line {i}" for i in range(2000))
    p.write_text(content, encoding="utf-8")
    return p


class TestTokenOverlap:
    def test_identical_strings(self):
        assert _token_overlap("hello world", "hello world") == 1.0

    def test_no_overlap(self):
        assert _token_overlap("aaa bbb", "ccc ddd") == 0.0

    def test_partial_overlap(self):
        score = _token_overlap("hello world foo", "hello bar world")
        assert 0.0 < score < 1.0

    def test_both_empty(self):
        assert _token_overlap("", "") == 1.0

    def test_one_empty(self):
        assert _token_overlap("hello", "") == 0.0

    def test_single_token_identical(self):
        assert _token_overlap("hello", "hello") == 1.0


class TestFuzzyMatchHunk:
    def test_exact_match_at_start(self):
        lines = ["alpha", "beta", "gamma", "delta"]
        old = ["alpha", "beta"]
        assert _fuzzy_match_hunk(lines, old, 0) == 0

    def test_no_match(self):
        lines = ["aaa", "bbb", "ccc"]
        old = ["xxx", "yyy", "zzz"]
        assert _fuzzy_match_hunk(lines, old, 0) is None

    def test_match_with_whitespace_diff(self):
        lines = ["  hello  ", "  world  "]
        old = ["hello", "world"]
        assert _fuzzy_match_hunk(lines, old, 0) == 0

    def test_match_near_start_position(self):
        lines = ["x", "y", "alpha", "beta", "gamma"]
        old = ["alpha", "beta"]
        assert _fuzzy_match_hunk(lines, old, 2) == 2


@pytest.mark.asyncio
class TestReadFile:
    async def test_missing_path(self):
        r = await _handle_read_file(path=None)
        assert r.success is False
        assert "required" in r.output

    async def test_file_not_found(self, tmp_path):
        r = await _handle_read_file(path=str(tmp_path / "nonexistent.txt"))
        assert r.success is False
        assert "not found" in r.output.lower()

    async def test_not_a_file(self, tmp_path):
        r = await _handle_read_file(path=str(tmp_path))
        assert r.success is False
        assert "not a file" in r.output.lower()

    async def test_read_success(self, sample_file):
        r = await _handle_read_file(path=str(sample_file))
        assert r.success is True
        assert "line one" in r.output
        assert "1:" in r.output

    async def test_read_with_offset(self, sample_file):
        r = await _handle_read_file(path=str(sample_file), offset=3)
        assert r.success is True
        assert "3: line three" in r.output
        assert "line one" not in r.output

    async def test_read_with_limit(self, sample_file):
        r = await _handle_read_file(path=str(sample_file), limit=2)
        assert r.success is True
        assert "1: line one" in r.output
        assert "2: line two" in r.output
        assert "line three" not in r.output

    async def test_read_offset_and_limit(self, sample_file):
        r = await _handle_read_file(path=str(sample_file), offset=2, limit=2)
        assert r.success is True
        assert "2: line two" in r.output
        assert "3: line three" in r.output
        assert "line one" not in r.output
        assert "line four" not in r.output

    async def test_file_too_large(self, tmp_path):
        p = tmp_path / "big.txt"
        p.write_bytes(b"x" * 600_000)
        r = await _handle_read_file(path=str(p))
        assert r.success is False
        assert "too large" in r.output.lower()

    async def test_truncation(self, tmp_path):
        p = tmp_path / "long.txt"
        p.write_text("\n".join(f"{'x' * 50} line {i}" for i in range(2000)), encoding="utf-8")
        r = await _handle_read_file(path=str(p))
        assert r.success is True
        if len(r.output) > 50000:
            assert "truncated" in r.output

    async def test_data_fields(self, sample_file):
        r = await _handle_read_file(path=str(sample_file))
        assert r.data is not None
        assert r.data["total_lines"] == 5


@pytest.mark.asyncio
class TestWriteFile:
    async def test_missing_path(self):
        r = await _handle_write_file(content="hi")
        assert r.success is False
        assert "required" in r.output

    async def test_missing_content(self, tmp_path):
        r = await _handle_write_file(path=str(tmp_path / "f.txt"))
        assert r.success is False
        assert "required" in r.output

    async def test_create_new_file(self, tmp_path):
        p = tmp_path / "new.txt"
        r = await _handle_write_file(path=str(p), content="hello world")
        assert r.success is True
        assert "Created" in r.output
        assert p.read_text() == "hello world"

    async def test_overwrite_existing(self, tmp_path):
        p = tmp_path / "exist.txt"
        p.write_text("old", encoding="utf-8")
        r = await _handle_write_file(path=str(p), content="new")
        assert r.success is True
        assert "Updated" in r.output
        assert p.read_text() == "new"

    async def test_auto_mkdir(self, tmp_path):
        p = tmp_path / "sub" / "dir" / "file.txt"
        r = await _handle_write_file(path=str(p), content="deep")
        assert r.success is True
        assert p.read_text() == "deep"

    async def test_data_existed_flag(self, tmp_path):
        p = tmp_path / "f.txt"
        p.write_text("old", encoding="utf-8")
        r = await _handle_write_file(path=str(p), content="new")
        assert r.data["existed"] is True


@pytest.mark.asyncio
class TestPatch:
    async def test_missing_path(self):
        r = await _handle_patch(old="a", new="b")
        assert r.success is False

    async def test_missing_old_new(self, tmp_path):
        p = tmp_path / "f.txt"
        p.write_text("hello", encoding="utf-8")
        r = await _handle_patch(path=str(p))
        assert r.success is False
        assert "required" in r.output

    async def test_file_not_found(self, tmp_path):
        r = await _handle_patch(path=str(tmp_path / "nope.txt"), old="a", new="b")
        assert r.success is False
        assert "not found" in r.output.lower()

    async def test_exact_single_match(self, tmp_path):
        p = tmp_path / "f.txt"
        p.write_text("aaa\nbbb\nccc\n", encoding="utf-8")
        r = await _handle_patch(path=str(p), old="bbb", new="BBB")
        assert r.success is True
        assert "exact match" in r.output
        assert p.read_text() == "aaa\nBBB\nccc\n"

    async def test_multiple_matches_rejected(self, tmp_path):
        p = tmp_path / "f.txt"
        p.write_text("aaa\nbbb\nbbb\naaa\n", encoding="utf-8")
        r = await _handle_patch(path=str(p), old="bbb", new="BBB")
        assert r.success is False
        assert "2 matches" in r.output

    async def test_fuzzy_match(self, tmp_path):
        p = tmp_path / "f.txt"
        p.write_text("  hello  \n  world  \nfoo\n", encoding="utf-8")
        r = await _handle_patch(path=str(p), old="hello\nworld", new="HELLO\nWORLD")
        assert r.success is True
        assert "fuzzy" in r.output

    async def test_no_match_at_all(self, tmp_path):
        p = tmp_path / "f.txt"
        p.write_text("aaa\nbbb\n", encoding="utf-8")
        r = await _handle_patch(path=str(p), old="xyz\n123", new="nope")
        assert r.success is False
        assert "Could not find" in r.output


@pytest.mark.asyncio
class TestListFiles:
    async def test_dir_not_found(self, tmp_path):
        r = await _handle_list_files(path=str(tmp_path / "nope"))
        assert r.success is False
        assert "not found" in r.output.lower()

    async def test_not_a_directory(self, sample_file):
        r = await _handle_list_files(path=str(sample_file))
        assert r.success is False
        assert "not a directory" in r.output.lower()

    async def test_list_all(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("bb")
        r = await _handle_list_files(path=str(tmp_path))
        assert r.success is True
        assert "a.txt" in r.output
        assert "b.txt" in r.output
        assert len(r.data["files"]) == 2

    async def test_list_with_pattern(self, tmp_path):
        (tmp_path / "hello.py").write_text("")
        (tmp_path / "hello.js").write_text("")
        r = await _handle_list_files(path=str(tmp_path), pattern="*.py")
        assert r.success is True
        assert "hello.py" in r.output
        assert "hello.js" not in r.output

    async def test_list_empty(self, tmp_path):
        r = await _handle_list_files(path=str(tmp_path), pattern="*.xyz")
        assert r.success is True
        assert "No files" in r.output

    async def test_list_shows_directories(self, tmp_path):
        (tmp_path / "subdir").mkdir()
        r = await _handle_list_files(path=str(tmp_path))
        assert r.success is True
        assert "subdir/" in r.output


@pytest.mark.asyncio
class TestSearchFiles:
    async def test_missing_query(self):
        r = await _handle_search_files(query=None)
        assert r.success is False
        assert "required" in r.output

    async def test_dir_not_found(self, tmp_path):
        r = await _handle_search_files(query="test", path=str(tmp_path / "nope"))
        assert r.success is False
        assert "not found" in r.output.lower()

    async def test_no_matches(self, tmp_path):
        (tmp_path / "f.txt").write_text("hello world", encoding="utf-8")
        r = await _handle_search_files(query="zzz_nonexistent_pattern_xyz", path=str(tmp_path))
        assert r.success is True
        assert "no matches" in r.output.lower()

    async def test_finds_match(self, tmp_path):
        (tmp_path / "f.txt").write_text("findme is here\n", encoding="utf-8")
        r = await _handle_search_files(query="findme", path=str(tmp_path))
        assert r.success is True
        assert "findme" in r.output

    async def test_with_file_pattern(self, tmp_path):
        (tmp_path / "a.py").write_text("unicorn_pattern_42\n", encoding="utf-8")
        (tmp_path / "b.js").write_text("unicorn_pattern_42\n", encoding="utf-8")
        r = await _handle_search_files(query="unicorn_pattern_42", path=str(tmp_path), file_pattern="*.py")
        assert r.success is True
        assert "a.py" in r.output
