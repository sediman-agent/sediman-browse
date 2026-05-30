from __future__ import annotations

from pathlib import Path

from sediman.agent.coding_agent.types import ProjectInfo


def discover_project(root_dir: str | Path | None = None) -> ProjectInfo:
    root = Path(root_dir).resolve() if root_dir else Path.cwd()
    info = ProjectInfo(root_dir=str(root))

    _detect_project_type(info, root)
    _find_config_files(info, root)
    _detect_commands(info, root)
    _detect_frameworks(info, root)
    _find_project_instructions(info, root)
    _detect_conventions(info, root)

    return info


def _detect_project_type(info: ProjectInfo, root: Path) -> None:
    if (root / "pyproject.toml").exists():
        info.project_type = "Python"
        info.language = "Python"
        info.package_manager = "uv/pip"
    elif (root / "setup.py").exists() or (root / "setup.cfg").exists():
        info.project_type = "Python"
        info.language = "Python"
        info.package_manager = "pip"

    if (root / "package.json").exists():
        if info.project_type:
            info.project_type += " + Node.js"
        else:
            info.project_type = "Node.js"
        info.language = _merge(info.language, "TypeScript/JavaScript")

        pkg_json = _try_read_json(root / "package.json")
        if pkg_json:
            if pkg_json.get("workspaces"):
                info.package_manager = _merge(info.package_manager, "npm workspaces")
            if (root / "bun.lockb").exists() or (root / "bun.lock").exists():
                info.package_manager = _merge(info.package_manager, "bun")
            elif (root / "yarn.lock").exists():
                info.package_manager = _merge(info.package_manager, "yarn")
            elif (root / "pnpm-lock.yaml").exists():
                info.package_manager = _merge(info.package_manager, "pnpm")
            elif (root / "package-lock.json").exists():
                info.package_manager = _merge(info.package_manager, "npm")

    if (root / "Cargo.toml").exists():
        if info.project_type:
            info.project_type += " + Rust"
        else:
            info.project_type = "Rust"
        info.language = _merge(info.language, "Rust")
        info.package_manager = _merge(info.package_manager, "cargo")

    if (root / "go.mod").exists():
        info.language = _merge(info.language, "Go")
        info.package_manager = _merge(info.package_manager, "go modules")
        if not info.project_type:
            info.project_type = "Go"

    if (root / "Makefile").exists():
        info.build_commands.append("make")

    if not info.project_type:
        info.project_type = "Unknown"


def _find_config_files(info: ProjectInfo, root: Path) -> None:
    config_patterns = [
        "pyproject.toml", "setup.py", "setup.cfg", "tox.ini",
        "package.json", "tsconfig.json", "tsconfig.base.json",
        "Cargo.toml", "Cargo.lock",
        "go.mod", "go.sum",
        "Makefile", "makefile",
        "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
        ".env.example", ".env",
        ".gitignore", ".gitmodules",
        ".pre-commit-config.yaml",
        "ruff.toml", ".ruff.toml", "pyproject.toml",
        ".eslintrc.js", ".eslintrc.json", ".eslintrc.yml", "eslint.config.js",
        ".prettierrc", ".prettierrc.json", ".prettierrc.js",
        "biome.json", "biome.jsonc",
        "tslint.json",
        ".editorconfig",
    ]
    for pattern in config_patterns:
        if (root / pattern).exists():
            info.config_files.append(pattern)


def _detect_commands(info: ProjectInfo, root: Path) -> None:
    # Python
    if (root / "pyproject.toml").exists():
        data = _try_read_toml(root / "pyproject.toml")
        if data:
            scripts = data.get("project", {}).get("scripts", {})
            if "lint" in scripts:
                info.lint_commands.append(f"uv run lint" if _has_uv(root) else "python -m lint")
            if "test" in scripts or "pytest" in str(scripts):
                info.test_commands.append(
                    "uv run pytest" if _has_uv(root) else "python -m pytest"
                )
            if "typecheck" in scripts or "mypy" in str(scripts):
                info.lint_commands.append(
                    "uv run mypy ." if _has_uv(root) else "python -m mypy ."
                )

            tool_ruff = data.get("tool", {}).get("ruff", {})
            if tool_ruff:
                info.lint_commands.append(
                    "uv run ruff check ." if _has_uv(root) else "ruff check ."
                )
                info.format_commands.append(
                    "uv run ruff format ." if _has_uv(root) else "ruff format ."
                )
    elif (root / "ruff.toml").exists() or (root / ".ruff.toml").exists():
        info.lint_commands.append(
            "uv run ruff check ." if _has_uv(root) else "ruff check ."
        )

    if (root / "Makefile").exists():
        content = _try_read_text(root / "Makefile")
        if content:
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("test"):
                    info.test_commands.append("make test")
                    break
            for line in content.splitlines():
                line = line.strip()
                if "lint" in line.lower() and not line.startswith("#"):
                    info.lint_commands.append("make lint")
                    break

    # Node.js
    if (root / "package.json").exists():
        data = _try_read_json(root / "package.json")
        if data:
            scripts = data.get("scripts", {})
            for name, cmd in scripts.items():
                cmd_lower = cmd.lower()
                if name in ("lint", "lint:check", "format:check") or (
                    "lint" in name and "eslint" in cmd_lower
                ):
                    info.lint_commands.append(f"npm run {name}")
                if name in ("format", "format:check", "prettier") or (
                    "format" in name and "prettier" in cmd_lower
                ):
                    info.format_commands.append(f"npm run {name}")
                if name in ("test", "test:ci", "spec") or (
                    "test" in name and ("jest" in cmd_lower or "vitest" in cmd_lower or "mocha" in cmd_lower)
                ):
                    info.test_commands.append(f"npm run {name}")
                if name == "typecheck" or ("typecheck" in name and "tsc" in cmd_lower):
                    info.lint_commands.append(f"npm run {name}")
                if name in ("build", "compile") or "build" in name:
                    info.build_commands.append(f"npm run {name}")

    # Rust
    if (root / "Cargo.toml").exists():
        info.test_commands.append("cargo test")
        info.lint_commands.append("cargo clippy -- -D warnings")
        info.format_commands.append("cargo fmt --check")
        info.build_commands.append("cargo build")

    # Go
    if (root / "go.mod").exists():
        info.test_commands.append("go test ./...")
        info.lint_commands.append("golangci-lint run")
        info.build_commands.append("go build ./...")

    # Lint tools by config presence
    if (root / ".pre-commit-config.yaml").exists():
        info.lint_commands.append("pre-commit run --all-files")
    if _has_eslint_config(root):
        if not any("eslint" in c.lower() for c in info.lint_commands):
            info.lint_commands.append("npx eslint .")


def _detect_frameworks(info: ProjectInfo, root: Path) -> None:
    if (root / "package.json").exists():
        data = _try_read_json(root / "package.json")
        if data:
            deps = {}
            deps.update(data.get("dependencies", {}))
            deps.update(data.get("devDependencies", {}))
            deps.update(data.get("peerDependencies", {}))

            framework_map = {
                "react": "React",
                "next": "Next.js",
                "vue": "Vue",
                "nuxt": "Nuxt",
                "svelte": "Svelte",
                "angular": "Angular",
                "express": "Express",
                "fastify": "Fastify",
                "koa": "Koa",
                "hono": "Hono",
                "elysia": "Elysia",
                "lit": "Lit",
                "solid-js": "SolidJS",
                "tailwindcss": "Tailwind CSS",
            }
            for pkg, name in framework_map.items():
                if pkg in deps and name not in info.frameworks:
                    info.frameworks.append(name)

    if (root / "pyproject.toml").exists():
        data = _try_read_toml(root / "pyproject.toml")
        if data:
            deps = list(data.get("project", {}).get("dependencies", []))
            deps_str = " ".join(deps).lower()
            framework_map = {
                "fastapi": "FastAPI",
                "flask": "Flask",
                "django": "Django",
                "litestar": "Litestar",
                "sanic": "Sanic",
                "bottle": "Bottle",
                "starlette": "Starlette",
            }
            for pkg, name in framework_map.items():
                if pkg in deps_str and name not in info.frameworks:
                    info.frameworks.append(name)

    if (root / "Cargo.toml").exists():
        data = _try_read_toml(root / "Cargo.toml")
        if data:
            deps = data.get("dependencies", {})
            framework_map = {
                "axum": "Axum",
                "actix-web": "Actix Web",
                "rocket": "Rocket",
                "warp": "Warp",
                "tauri": "Tauri",
                "leptos": "Leptos",
                "yew": "Yew",
                "dioxus": "Dioxus",
            }
            for pkg, name in framework_map.items():
                if pkg in deps and name not in info.frameworks:
                    info.frameworks.append(name)


def _find_project_instructions(info: ProjectInfo, root: Path) -> None:
    instruction_files = [
        "AGENTS.md",
        "CLAUDE.md",
        ".cursorrules",
        ".github/copilot-instructions.md",
        "CONTRIBUTING.md",
    ]
    for filename in instruction_files:
        path = root / filename
        if path.exists():
            content = _try_read_text(path)
            if content:
                info.project_instructions += f"\n### {filename}\n{content[:2000]}\n"
                if len(content) > 2000:
                    info.project_instructions += "... (truncated)\n"


def _detect_conventions(info: ProjectInfo, root: Path) -> None:
    if (root / "pyproject.toml").exists():
        data = _try_read_toml(root / "pyproject.toml")
        if data:
            line_length = (
                data.get("tool", {})
                .get("ruff", {})
                .get("line-length")
                or data.get("tool", {})
                .get("black", {})
                .get("line-length")
            )
            if line_length:
                info.conventions["line_length"] = str(line_length)

    if (root / ".editorconfig").exists():
        content = _try_read_text(root / ".editorconfig")
        if content:
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("indent_size"):
                    info.conventions["indent_size"] = line.split("=")[-1].strip()
                elif line.startswith("indent_style"):
                    info.conventions["indent_style"] = line.split("=")[-1].strip()

    if (root / "tsconfig.base.json").exists() or (root / "tsconfig.json").exists():
        info.conventions["typescript"] = "strict mode likely"


def _try_read_json(path: Path) -> dict | None:
    try:
        import json
        return json.loads(path.read_text())
    except Exception:
        return None


def _try_read_toml(path: Path) -> dict | None:
    try:
        import tomllib
        return tomllib.loads(path.read_text())
    except Exception:
        try:
            import tomli
            return tomli.loads(path.read_text())
        except Exception:
            return None


def _try_read_text(path: Path) -> str | None:
    try:
        return path.read_text()
    except Exception:
        return None


def _has_uv(root: Path) -> bool:
    return (root / "uv.lock").exists() or (root / ".venv").exists()


def _has_eslint_config(root: Path) -> bool:
    patterns = [
        ".eslintrc.js", ".eslintrc.json", ".eslintrc.yml", ".eslintrc.yaml",
        "eslint.config.js", "eslint.config.mjs", "eslint.config.cjs",
        ".eslintrc", "eslint.config.ts",
    ]
    return any((root / p).exists() for p in patterns)


def _merge(a: str, b: str) -> str:
    if not a:
        return b
    if b in a:
        return a
    return f"{a}, {b}"
