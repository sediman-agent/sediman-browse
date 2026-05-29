from __future__ import annotations

import re
from typing import Any

import structlog

logger = structlog.get_logger()

_HIGH_IMPORTANCE_PATTERNS = [
    r"\b(always|never|must|important|critical|essential)\b",
    r"\b(preference|prefer|favorite|default)\b",
    r"\b(password|api.?key|token|secret|credential)\b",
    r"\b(error|failed|bug|fix|workaround)\b",
    r"\b(rule|policy|constraint|requirement)\b",
]

_LOW_IMPORTANCE_PATTERNS = [
    r"\b(okay|ok|sure|fine|whatever)\b",
    r"\b(test|testing|tmp|temp)\b",
    r"\b(maybe|perhaps|might|could)\b",
]

_FACT_PATTERN = re.compile(
    r"^(the|this|that|it|there|our|my|user|system|sediman)\b",
    re.IGNORECASE,
)

_PROCEDURE_PATTERN = re.compile(
    r"\b(step|first|then|next|after|before|click|navigate|type|scroll|search|open)\b",
    re.IGNORECASE,
)


def score_importance(content: str) -> float:
    if not content:
        return 0.0

    score = 0.5

    lower = content.lower()

    for pattern in _HIGH_IMPORTANCE_PATTERNS:
        if re.search(pattern, lower):
            score += 0.15

    for pattern in _LOW_IMPORTANCE_PATTERNS:
        if re.search(pattern, lower):
            score -= 0.1

    if len(content) < 20:
        score -= 0.1
    elif len(content) > 200:
        score += 0.1

    if content.count("\n") > 3:
        score += 0.05

    return max(0.1, min(1.0, score))


def classify_channel(content: str) -> str:
    lower = content.lower()
    proc_matches = len(_PROCEDURE_PATTERN.findall(lower))
    fact_matches = len(_FACT_PATTERN.findall(lower))

    if proc_matches > fact_matches + 1:
        return "procedural"
    return "declarative"


async def score_with_llm(content: str, llm: Any) -> float:
    prompt = (
        "Rate the importance of this memory entry for a browser automation agent.\n"
        "Consider: Is this a preference? A fact about the user? A procedure? Error knowledge?\n\n"
        f"Entry: {content[:500]}\n\n"
        "Respond with ONLY a number 1-5 where:\n"
        "1 = Trivial/temporary\n"
        "2 = Low importance\n"
        "3 = Moderately useful\n"
        "4 = Important preference or fact\n"
        "5 = Critical rule or preference"
    )

    try:
        response = await llm.chat(
            messages=[{"role": "user", "content": prompt}],
            tools=[],
        )
        text = (response.text or "").strip()
        for char in text:
            if char in "12345":
                return int(char) / 5.0
        return 0.5
    except Exception:
        return 0.5
