from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class StepData:
    description: str = ""
    action_type: str = ""
    url: str | None = None
    selector: str | None = None
    text: str | None = None
    expected_outcome: str | None = None
    index: int | None = None
    duration_ms: int | None = None
    wait_for: str | None = None
    condition: str | None = None
    on_error: str | None = None
    screenshot_verify: str | None = None

    def to_string(self) -> str:
        if self.action_type == "navigate" and self.url:
            return f"Navigate to {self.url}"
        if self.action_type == "click":
            parts = ["Click"]
            if self.index is not None:
                parts.append(f"element {self.index}")
            if self.text:
                parts.append(f'"{self.text}"')
            if self.selector:
                parts.append(f"({self.selector})")
            return " ".join(parts)
        if self.action_type == "input":
            parts = ["Type"]
            if self.text:
                parts.append(f'"{self.text[:50]}"')
            if self.selector:
                parts.append(f"in {self.selector}")
            return " ".join(parts)
        if self.action_type == "extract":
            return "Extract data from page"
        if self.action_type == "scroll":
            return "Scroll page"
        if self.action_type == "search":
            return f"Search: {self.text}" if self.text else "Search"
        if self.url:
            return f"{self.description} {self.url}" if self.description else self.url
        return self.description

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {"description": self.description}
        if self.action_type:
            d["action_type"] = self.action_type
        if self.url:
            d["url"] = self.url
        if self.selector:
            d["selector"] = self.selector
        if self.text:
            d["text"] = self.text
        if self.expected_outcome:
            d["expected_outcome"] = self.expected_outcome
        if self.index is not None:
            d["index"] = self.index
        if self.wait_for:
            d["wait_for"] = self.wait_for
        if self.condition:
            d["condition"] = self.condition
        if self.on_error:
            d["on_error"] = self.on_error
        if self.screenshot_verify:
            d["screenshot_verify"] = self.screenshot_verify
        return d

    @classmethod
    def from_json(cls, data: str | dict[str, Any]) -> StepData:
        if isinstance(data, str):
            return cls(description=data)
        return cls(
            description=data.get("description", ""),
            action_type=data.get("action_type", ""),
            url=data.get("url"),
            selector=data.get("selector"),
            text=data.get("text"),
            expected_outcome=data.get("expected_outcome"),
            index=data.get("index"),
            duration_ms=data.get("duration_ms"),
            wait_for=data.get("wait_for"),
            condition=data.get("condition"),
            on_error=data.get("on_error"),
            screenshot_verify=data.get("screenshot_verify"),
        )

    @classmethod
    def from_browser_action(cls, action: dict[str, Any]) -> StepData:
        action_type = action.get("action", action.get("type", ""))
        args = action.get("arguments", action)
        interacted = action.get("interacted_element", {})
        description = cls._build_description(action_type, {**args, **interacted})
        return cls(
            description=description,
            action_type=action_type,
            url=args.get("url") or interacted.get("url"),
            selector=args.get("selector") or interacted.get("selector"),
            text=args.get("text") or interacted.get("text"),
            index=args.get("index") or interacted.get("index"),
            expected_outcome=args.get("expected_outcome"),
        )

    @staticmethod
    def _build_description(action_type: str, args: dict[str, Any]) -> str:
        if action_type == "navigate":
            return f"Navigate to {args.get('url', 'the page')}"
        if action_type == "click":
            idx = args.get("index", "")
            text = args.get("text", args.get("label", ""))
            parts = ["Click"]
            if idx:
                parts.append(f"element {idx}")
            if text:
                parts.append(f'"{text}"')
            return " ".join(parts)
        if action_type == "input":
            text = args.get("text", "")
            field = args.get("selector", args.get("label", ""))
            parts = ["Type"]
            if text:
                parts.append(f'"{text[:50]}"')
            if field:
                parts.append(f"in {field}")
            return " ".join(parts)
        if action_type == "extract":
            return "Extract data from page"
        if action_type == "scroll":
            return "Scroll the page"
        if action_type == "search":
            return f"Search for {args.get('query', 'the query')}"
        return args.get("text", str(args)[:100])


@dataclass
class SkillData:
    name: str
    description: str
    steps: list[str] = field(default_factory=list)
    structured_steps: list[dict[str, Any]] = field(default_factory=list)
    category: str = "general"
    version: int = 1
    variables: list[str] = field(default_factory=list)
    schedule: str | None = None
    author: str | None = None
    license: str | None = None
    compatibility: str | None = None
    source: str = "local"
    created_at: str | None = None
    updated_at: str | None = None
    body: str = ""
    when_to_use: str | None = None
    pitfalls: list[str] = field(default_factory=list)
    use_count: int = 0
    last_used_at: str | None = None
    verification: str | None = None
    disable_model_invocation: bool = False
    allowed_tools: dict[str, str] | None = None
    context: str = ""
    paths: list[str] | None = None
    inputs: list[dict[str, str]] | None = None
    outputs: list[dict[str, str]] | None = None
    dependencies: list[str] | None = None
    retry_policy: str | None = None
    timeout_seconds: int | None = None
    examples: list[str] | None = None
    success_rate: float | None = None
    last_error: str | None = None
    execution_count: int = 0
    avg_duration_ms: int | None = None

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "steps": self.steps,
            "category": self.category,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.structured_steps:
            d["structured_steps"] = self.structured_steps
        if self.variables:
            d["variables"] = self.variables
        if self.schedule:
            d["schedule"] = self.schedule
        if self.author:
            d["author"] = self.author
        if self.source != "local":
            d["source"] = self.source
        if self.when_to_use:
            d["when_to_use"] = self.when_to_use
        if self.pitfalls:
            d["pitfalls"] = self.pitfalls
        if self.use_count > 0:
            d["use_count"] = self.use_count
        if self.last_used_at:
            d["last_used_at"] = self.last_used_at
        if self.verification:
            d["verification"] = self.verification
        if self.disable_model_invocation:
            d["disable_model_invocation"] = True
        if self.allowed_tools:
            d["allowed_tools"] = self.allowed_tools
        if self.context:
            d["context"] = self.context
        if self.paths:
            d["paths"] = self.paths
        if self.inputs:
            d["inputs"] = self.inputs
        if self.outputs:
            d["outputs"] = self.outputs
        if self.dependencies:
            d["dependencies"] = self.dependencies
        if self.retry_policy:
            d["retry_policy"] = self.retry_policy
        if self.timeout_seconds is not None:
            d["timeout_seconds"] = self.timeout_seconds
        if self.examples:
            d["examples"] = self.examples
        if self.success_rate is not None:
            d["success_rate"] = self.success_rate
        if self.last_error:
            d["last_error"] = self.last_error
        if self.execution_count > 0:
            d["execution_count"] = self.execution_count
        if self.avg_duration_ms is not None:
            d["avg_duration_ms"] = self.avg_duration_ms
        return d

    def to_skill_md(self) -> str:
        lines = ["---"]
        lines.append(f"name: {self.name}")
        lines.append(f"description: \"{self.description}\"")
        if self.license:
            lines.append(f"license: {self.license}")
        if self.compatibility:
            lines.append(f"compatibility: {self.compatibility}")
        meta_parts = []
        if self.category != "general":
            meta_parts.append(f"  category: {self.category}")
        if self.author:
            meta_parts.append(f"  author: {self.author}")
        if self.version != 1:
            meta_parts.append(f"  version: \"{self.version}\"")
        if self.variables:
            meta_parts.append(f"  variables: {json.dumps(self.variables)}")
        if self.schedule:
            meta_parts.append(f"  schedule: \"{self.schedule}\"")
        if self.source != "local":
            meta_parts.append(f"  source: {self.source}")
        if self.disable_model_invocation:
            meta_parts.append(f"  disable_model_invocation: true")
        if self.allowed_tools:
            meta_parts.append(f"  allowed_tools: {json.dumps(self.allowed_tools)}")
        if self.context:
            meta_parts.append(f"  context: {self.context}")
        if self.paths:
            meta_parts.append(f"  paths: {json.dumps(self.paths)}")
        if self.inputs:
            meta_parts.append(f"  inputs: {json.dumps(self.inputs)}")
        if self.outputs:
            meta_parts.append(f"  outputs: {json.dumps(self.outputs)}")
        if self.dependencies:
            meta_parts.append(f"  dependencies: {json.dumps(self.dependencies)}")
        if self.retry_policy:
            meta_parts.append(f"  retry_policy: {self.retry_policy}")
        if self.timeout_seconds is not None:
            meta_parts.append(f"  timeout_seconds: {self.timeout_seconds}")
        if meta_parts:
            lines.append("metadata:")
            lines.extend(meta_parts)
        lines.append("---")
        lines.append("")
        lines.append(f"# {self.name}")
        lines.append("")
        lines.append(self.description)
        if self.steps:
            lines.append("")
            lines.append("## Steps")
            for i, step in enumerate(self.steps, 1):
                lines.append(f"{i}. {step}")
        if self.structured_steps:
            lines.append("")
            lines.append("## Structured Steps")
            for i, step in enumerate(self.structured_steps):
                action = step.get("action_type", "action")
                desc = step.get("description", "")
                url = step.get("url", "")
                sel = step.get("selector", "")
                expected = step.get("expected_outcome", "")
                wait = step.get("wait_for", "")
                parts = [f"- **{action}**: {desc}"]
                if url:
                    parts.append(f"  - URL: `{url}`")
                if sel:
                    parts.append(f"  - Selector: `{sel}`")
                if expected:
                    parts.append(f"  - Expected: {expected}")
                if wait:
                    parts.append(f"  - Wait for: {wait}")
                lines.append("\n".join(parts))
        if self.variables:
            lines.append("")
            lines.append("## Variables")
            for var in self.variables:
                lines.append(f"- `{var}`")
        if self.inputs:
            lines.append("")
            lines.append("## Inputs")
            for inp in self.inputs:
                name = inp.get("name", "")
                desc = inp.get("description", "")
                req = inp.get("required", "false")
                lines.append(f"- `{name}` ({req}): {desc}")
        if self.outputs:
            lines.append("")
            lines.append("## Outputs")
            for out in self.outputs:
                name = out.get("name", "")
                desc = out.get("description", "")
                lines.append(f"- `{name}`: {desc}")
        if self.schedule:
            lines.append("")
            lines.append("## Schedule")
            lines.append(f"Recommended: `{self.schedule}`")
        if self.when_to_use:
            lines.append("")
            lines.append("## When to Use")
            lines.append(self.when_to_use)
        if self.pitfalls:
            lines.append("")
            lines.append("## Pitfalls")
            for pitfall in self.pitfalls:
                lines.append(f"- {pitfall}")
        if self.verification:
            lines.append("")
            lines.append("## Verification")
            lines.append(self.verification)
        if self.examples:
            lines.append("")
            lines.append("## Examples")
            for ex in self.examples:
                lines.append(f"- {ex}")
        if self.dependencies:
            lines.append("")
            lines.append("## Dependencies")
            for dep in self.dependencies:
                lines.append(f"- {dep}")
        return "\n".join(lines) + "\n"


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)", re.DOTALL)


def parse_skill_md(content: str) -> SkillData | None:
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return None

    frontmatter_text = m.group(1)
    body = m.group(2).strip()

    try:
        import yaml
        meta = yaml.safe_load(frontmatter_text)
    except ImportError:
        meta = _parse_simple_yaml(frontmatter_text)

    if not isinstance(meta, dict) or "name" not in meta or "description" not in meta:
        return None

    metadata = meta.get("metadata", {}) or {}

    category = meta.get("category") or metadata.get("category", "general")
    version = meta.get("version") or metadata.get("version", 1)
    variables = meta.get("variables") or metadata.get("variables", [])
    if isinstance(variables, str):
        try:
            variables = json.loads(variables)
        except json.JSONDecodeError:
            variables = [v.strip() for v in variables.split(",")]
    schedule = meta.get("schedule") or metadata.get("schedule")
    author = meta.get("author") or metadata.get("author")
    source = meta.get("source") or metadata.get("source", "local")
    disable_model = meta.get("disable_model_invocation") or metadata.get("disable_model_invocation", False)
    allowed_tools = meta.get("allowed_tools") or metadata.get("allowed_tools")
    context = meta.get("context") or metadata.get("context", "")
    paths = meta.get("paths") or metadata.get("paths")
    inputs = meta.get("inputs") or metadata.get("inputs")
    outputs = meta.get("outputs") or metadata.get("outputs")
    dependencies = meta.get("dependencies") or metadata.get("dependencies")
    retry_policy = meta.get("retry_policy") or metadata.get("retry_policy")
    timeout_seconds = meta.get("timeout_seconds") or metadata.get("timeout_seconds")
    examples = _extract_examples_from_body(body)

    return SkillData(
        name=meta["name"],
        description=meta["description"],
        steps=_extract_steps_from_body(body),
        category=category,
        version=int(version) if version else 1,
        variables=variables or [],
        schedule=str(schedule) if schedule else None,
        author=author,
        license=meta.get("license"),
        compatibility=meta.get("compatibility"),
        source=source,
        body=body,
        disable_model_invocation=bool(disable_model),
        allowed_tools=allowed_tools,
        context=str(context) if context else "",
        paths=paths if isinstance(paths, list) else None,
        inputs=inputs if isinstance(inputs, list) else None,
        outputs=outputs if isinstance(outputs, list) else None,
        dependencies=dependencies if isinstance(dependencies, list) else None,
        retry_policy=str(retry_policy) if retry_policy else None,
        timeout_seconds=int(timeout_seconds) if timeout_seconds else None,
        examples=examples,
    )


def parse_skill_json(content: str) -> SkillData | None:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict) or "name" not in data or "description" not in data:
        return None

    return SkillData(
        name=data["name"],
        description=data["description"],
        steps=data.get("steps", []),
        structured_steps=data.get("structured_steps", []),
        category=data.get("category", "general"),
        version=data.get("version", 1),
        variables=data.get("variables", []),
        schedule=data.get("schedule"),
        author=data.get("author"),
        source=data.get("source", "local"),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
        when_to_use=data.get("when_to_use"),
        pitfalls=data.get("pitfalls", []),
        use_count=data.get("use_count", 0),
        last_used_at=data.get("last_used_at"),
        verification=data.get("verification"),
        disable_model_invocation=data.get("disable_model_invocation", False),
        allowed_tools=data.get("allowed_tools"),
        context=data.get("context", ""),
        paths=data.get("paths"),
        inputs=data.get("inputs"),
        outputs=data.get("outputs"),
        dependencies=data.get("dependencies"),
        retry_policy=data.get("retry_policy"),
        timeout_seconds=data.get("timeout_seconds"),
        examples=data.get("examples"),
        success_rate=data.get("success_rate"),
        last_error=data.get("last_error"),
        execution_count=data.get("execution_count", 0),
        avg_duration_ms=data.get("avg_duration_ms"),
    )


def load_skill(skill_dir: Path) -> SkillData | None:
    skill_json = skill_dir / "skill.json"
    if skill_json.exists():
        parsed = parse_skill_json(skill_json.read_text())
        if parsed:
            if not parsed.created_at:
                stat = skill_json.stat()
                from datetime import datetime, timezone
                parsed.created_at = datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat()
            return parsed

    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        parsed = parse_skill_md(skill_md.read_text())
        if parsed:
            if not parsed.created_at:
                stat = skill_md.stat()
                from datetime import datetime, timezone
                parsed.created_at = datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat()
            return parsed

    return None


def _extract_steps_from_body(body: str) -> list[str]:
    steps = []
    for line in body.split("\n"):
        stripped = line.strip()
        m = re.match(r"^\d+\.\s+(.+)", stripped)
        if m:
            steps.append(m.group(1))
    return steps


def _extract_examples_from_body(body: str) -> list[str] | None:
    in_examples = False
    examples = []
    for line in body.split("\n"):
        stripped = line.strip()
        if stripped.lower().startswith("## examples"):
            in_examples = True
            continue
        if in_examples and stripped.startswith("## "):
            break
        if in_examples and stripped.startswith("- "):
            examples.append(stripped[2:])
    return examples if examples else None


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    current_key: str | None = None

    for line in text.split("\n"):
        stripped = line.rstrip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip())

        if indent == 0 and ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            if val:
                result[key] = _yaml_value(val)
            else:
                result[key] = {}
                current_key = key
        elif current_key and indent > 0:
            stripped_inner = stripped.lstrip()
            if ":" in stripped_inner and not stripped_inner.startswith("-"):
                key, _, val = stripped_inner.partition(":")
                key = key.strip()
                val = val.strip()
                if isinstance(result.get(current_key), dict):
                    result[current_key][key] = _yaml_value(val)

    return result


def _yaml_value(val: str) -> Any:
    if val.startswith('"') and val.endswith('"'):
        return val[1:-1]
    if val.startswith("'") and val.endswith("'"):
        return val[1:-1]
    if val.startswith("["):
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            return val
    if val.lower() == "true":
        return True
    if val.lower() == "false":
        return False
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    return val
