from __future__ import annotations

import datetime


from sediman.utils import format_conversation_context, relative_time


class TestFormatConversationContext:
    def test_empty_messages(self):
        assert format_conversation_context([]) == ""

    def test_single_user_message(self):
        result = format_conversation_context([{"role": "user", "content": "hello"}])
        assert "User: hello" in result

    def test_single_assistant_message(self):
        result = format_conversation_context([{"role": "assistant", "content": "hi there"}])
        assert "Assistant: hi there" in result

    def test_multiple_messages(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        result = format_conversation_context(messages)
        assert "User: hello" in result
        assert "Assistant: hi" in result

    def test_limit_truncates_old_messages(self):
        messages = [{"role": "user", "content": f"msg {i}"} for i in range(20)]
        result = format_conversation_context(messages, limit=5)
        lines = result.split("\n")
        assert len(lines) == 5
        assert "msg 15" in lines[0]

    def test_max_chars_truncates_long_messages(self):
        messages = [{"role": "user", "content": "x" * 500}]
        result = format_conversation_context(messages, max_chars=10)
        assert len(result.split(": ")[1]) <= 10

    def test_newlines_in_output(self):
        messages = [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
        ]
        result = format_conversation_context(messages)
        assert result.count("\n") == 1

    def test_unknown_role_label(self):
        messages = [{"role": "system", "content": "you are a bot"}]
        result = format_conversation_context(messages)
        assert "Assistant" in result

    def test_custom_limit_default(self):
        messages = [{"role": "user", "content": "a"}]
        result = format_conversation_context(messages, limit=10)
        assert "User: a" in result


class TestRelativeTime:
    def test_just_now(self):
        now = datetime.datetime(2024, 1, 15, 12, 0, 0, tzinfo=datetime.timezone.utc)
        ts = "2024-01-15T12:00:00+00:00"
        assert relative_time(ts, now) == "just now"

    def test_just_now_within_seconds(self):
        now = datetime.datetime(2024, 1, 15, 12, 0, 5, tzinfo=datetime.timezone.utc)
        ts = "2024-01-15T12:00:00+00:00"
        assert relative_time(ts, now) == "just now"

    def test_minutes_ago(self):
        now = datetime.datetime(2024, 1, 15, 12, 5, 0, tzinfo=datetime.timezone.utc)
        ts = "2024-01-15T12:00:00+00:00"
        assert relative_time(ts, now) == "5m ago"

    def test_hours_ago(self):
        now = datetime.datetime(2024, 1, 15, 15, 0, 0, tzinfo=datetime.timezone.utc)
        ts = "2024-01-15T12:00:00+00:00"
        assert relative_time(ts, now) == "3h ago"

    def test_days_ago(self):
        now = datetime.datetime(2024, 1, 18, 12, 0, 0, tzinfo=datetime.timezone.utc)
        ts = "2024-01-15T12:00:00+00:00"
        assert relative_time(ts, now) == "3d ago"

    def test_more_than_30_days_shows_date(self):
        now = datetime.datetime(2024, 3, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
        ts = "2024-01-15T12:00:00+00:00"
        result = relative_time(ts, now)
        assert "2024-01-15" == result

    def test_non_iso_format(self):
        now = datetime.datetime(2024, 1, 15, 12, 5, 0, tzinfo=datetime.timezone.utc)
        ts = "2024-01-15 12:00:00"
        assert relative_time(ts, now) == "5m ago"

    def test_z_suffix_in_timestamp(self):
        now = datetime.datetime(2024, 1, 15, 12, 5, 0, tzinfo=datetime.timezone.utc)
        ts = "2024-01-15T12:00:00Z"
        assert relative_time(ts, now) == "5m ago"

    def test_future_timestamp(self):
        now = datetime.datetime(2024, 1, 15, 12, 0, 0, tzinfo=datetime.timezone.utc)
        ts = "2024-01-15T13:00:00+00:00"
        result = relative_time(ts, now)
        assert "just now" in result

    def test_invalid_timestamp_returns_raw(self):
        result = relative_time("not a timestamp")
        assert result == "not a timestamp"

    def test_empty_string_returns_raw(self):
        assert relative_time("") == ""

    def test_default_now_used_when_not_provided(self):
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        result = relative_time(ts)
        assert result in ("just now", "0m ago")

    def test_different_timezone(self):
        now = datetime.datetime(2024, 1, 15, 17, 0, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=5)))
        ts = "2024-01-15T12:00:00+00:00"
        assert relative_time(ts, now) == "just now"
