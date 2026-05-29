from __future__ import annotations

import datetime


def format_conversation_context(
    messages: list[dict[str, str]],
    limit: int = 10,
    max_chars: int = 200,
) -> str:
    lines = []
    for msg in messages[-limit:]:
        role = "User" if msg["role"] == "user" else "Assistant"
        lines.append(f"{role}: {msg['content'][:max_chars]}")
    return "\n".join(lines)


def relative_time(timestamp: str, now: datetime.datetime | None = None) -> str:
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)
    try:
        if "T" in timestamp:
            ts = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        else:
            ts = datetime.datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=datetime.timezone.utc)
        delta = now - ts
        seconds = int(delta.total_seconds())
        if seconds < 60:
            return "just now"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h ago"
        days = hours // 24
        if days < 30:
            return f"{days}d ago"
        return timestamp[:10]
    except Exception:
        return timestamp


def extract_json_from_text(text: str) -> dict | list | None:
    if not text:
        return None
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    text = text.strip()
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        else:
            return None
    import json
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None
