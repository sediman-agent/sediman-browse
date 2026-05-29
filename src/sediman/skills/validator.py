from __future__ import annotations

import re
from dataclasses import dataclass

from sediman.skills.format import SkillData


_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"<\s*script", re.IGNORECASE),
]

_EXFILTRATION_PATTERNS = [
    re.compile(r"(api[_-]?key|token|secret|password|credential)\s*[:=]", re.IGNORECASE),
    re.compile(r"(send|post|upload|exfil|fetch)\s+.*to\s+(https?://|ftp://)", re.IGNORECASE),
    re.compile(r"(curl|wget|http\.post|requests\.post)\s+", re.IGNORECASE),
]

_DESTRUCTIVE_PATTERNS = [
    re.compile(r"rm\s+-rf\s+/", re.IGNORECASE),
    re.compile(r"delete\s+all", re.IGNORECASE),
    re.compile(r"drop\s+table", re.IGNORECASE),
    re.compile(r"format\s+[a-z]:", re.IGNORECASE),
]


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]
    trust_level: str

    @property
    def ok(self) -> bool:
        return self.valid


def validate_skill(skill: SkillData) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    if not skill.name:
        errors.append("name is required")
    elif not _NAME_RE.match(skill.name):
        errors.append(
            f"name '{skill.name}' must be lowercase alphanumeric with hyphens, "
            "no leading/trailing/consecutive hyphens"
        )
    elif len(skill.name) > 64:
        errors.append("name must be 64 characters or less")

    if not skill.description:
        errors.append("description is required")
    elif len(skill.description) > 1024:
        errors.append("description must be 1024 characters or less")
    elif len(skill.description) < 10:
        warnings.append("description is very short — consider adding more detail")

    if not skill.steps:
        warnings.append("no steps defined — skill may not be actionable")

    all_text = f"{skill.name} {skill.description} {' '.join(skill.steps)}"

    for pattern in _INJECTION_PATTERNS:
        if pattern.search(all_text):
            errors.append("potential prompt injection detected")
            break

    for pattern in _EXFILTRATION_PATTERNS:
        if pattern.search(all_text):
            warnings.append("potential data exfiltration pattern detected")
            break

    for pattern in _DESTRUCTIVE_PATTERNS:
        if pattern.search(all_text):
            errors.append("destructive command pattern detected")
            break

    trust = _determine_trust(skill, errors, warnings)

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        trust_level=trust,
    )


def validate_name(name: str) -> list[str]:
    errors = []
    if not name:
        errors.append("name is required")
    elif not _NAME_RE.match(name):
        errors.append("name must be lowercase alphanumeric with hyphens only")
    elif len(name) > 64:
        errors.append("name must be 64 characters or less")
    return errors


def _determine_trust(skill: SkillData, errors: list[str], warnings: list[str]) -> str:
    if skill.source == "bundled":
        return "bundled"
    if errors:
        return "dangerous"
    if skill.source in ("official", "verified"):
        return "trusted"
    if warnings:
        return "caution"
    return "community"
