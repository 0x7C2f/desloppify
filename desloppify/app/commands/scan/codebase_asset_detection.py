"""Codebase signal detection and asset selection for scan."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any, cast

_BASE_SKILLS = ("code-review", "plan", "update-codemaps", "update-docs", "verify")
_DEP_SPLIT_RE = re.compile(r"[\s<>=!~\[\];]")


def detect_codebase_signals(
    project_root: Path,
    *,
    warnings: list[str] | None = None,
) -> set[str]:
    """Infer coarse stack signals from common project manifests."""
    signals: set[str] = set()
    package_json = project_root / "package.json"
    composer_json = project_root / "composer.json"
    pyproject_toml = project_root / "pyproject.toml"

    if (project_root / ".obsidian").is_dir():
        signals.add("obsidian")
    if (project_root / "go.mod").is_file():
        signals.update({"backend", "go"})
    if (project_root / "Cargo.toml").is_file():
        signals.add("rust")

    package_deps = _json_dependency_names(
        package_json,
        ("dependencies", "devDependencies"),
        warnings=warnings,
    )
    if package_deps:
        signals.add("javascript")
    if package_deps & {"next", "react", "svelte", "vue"}:
        signals.add("frontend")
    if package_deps & {"express", "fastify", "koa", "nestjs"}:
        signals.add("backend")
    if package_deps & {"@modelcontextprotocol/sdk", "@modelcontextprotocol/server-filesystem"}:
        signals.add("mcp")

    composer_deps = _json_dependency_names(
        composer_json,
        ("require", "require-dev"),
        warnings=warnings,
    )
    if composer_deps:
        signals.add("php")
    if "laravel/framework" in composer_deps:
        signals.update({"backend", "laravel"})
    if "essa/api-tool-kit" in composer_deps:
        signals.add("laravel-tool-kit")

    python_deps = _python_dependency_names(pyproject_toml, warnings=warnings)
    if python_deps:
        signals.add("python")
    if python_deps & {"django", "fastapi", "flask", "gradio"}:
        signals.add("backend")
    if python_deps & {"mcp", "modelcontextprotocol"}:
        signals.add("mcp")

    if (project_root / "mcp.json").is_file() or (project_root / ".mcp.json").is_file():
        signals.add("mcp")
    return signals


def select_skills(signals: set[str]) -> list[str]:
    """Choose the local skills that fit the detected codebase."""
    selected: set[str] = set(_BASE_SKILLS)
    if "backend" in signals:
        selected.add("multi-backend")
    if "frontend" in signals:
        selected.update({"build-fix", "e2e", "multi-frontend"})
    if "python" in signals:
        selected.update({"python-review", "test-coverage"})
    if "go" in signals:
        selected.update({"go-build", "go-review", "go-test"})
    if "laravel" in signals:
        selected.add("laravel-api")
    if "laravel-tool-kit" in signals:
        selected.add("laravel-api-tool-kit")
    if "mcp" in signals:
        selected.add("mcp-development")
    if "obsidian" in signals:
        selected.add("obsidian")
    return sorted(selected)


def select_mcp_servers(signals: set[str]) -> list[str]:
    """Choose safe MCP servers to mirror into the project-local config."""
    selected = {"context7", "filesystem", "github"}
    if "obsidian" in signals:
        selected.add("obsidian")
    return sorted(selected)


def _json_dependency_names(
    path: Path,
    sections: tuple[str, ...],
    *,
    warnings: list[str] | None = None,
) -> set[str]:
    """Collect dependency keys from selected JSON manifest sections."""
    if not path.is_file():
        return set()
    try:
        payload = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError) as exc:
        if warnings is not None:
            warnings.append(f"Could not parse `{path.name}` for asset detection: {exc}")
        return set()
    names: set[str] = set()
    for section in sections:
        deps = cast(dict[str, Any], payload.get(section, {}))
        names.update(name.strip().lower() for name in deps)
    return names


def _python_dependency_names(
    path: Path,
    warnings: list[str] | None = None,
) -> set[str]:
    """Collect Python dependency names from pyproject metadata."""
    if not path.is_file():
        return set()
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as exc:
        if warnings is not None:
            warnings.append(f"Could not parse `{path.name}` for asset detection: {exc}")
        return set()
    names: set[str] = set()
    project = cast(dict[str, Any], payload.get("project", {}))
    dependencies = cast(list[Any], project.get("dependencies", []))
    for dependency in dependencies or []:
        if isinstance(dependency, str):
            names.add(_normalize_dependency_name(dependency))
    optionals = cast(dict[str, list[Any]], project.get("optional-dependencies", {}))
    for group in optionals.values():
        for dependency in group or []:
            if isinstance(dependency, str):
                names.add(_normalize_dependency_name(dependency))
    tool = payload.get("tool", {})
    poetry = cast(dict[str, Any], cast(dict[str, Any], tool).get("poetry", {})) if isinstance(tool, dict) else {}
    dependencies = cast(dict[str, Any], poetry.get("dependencies", {}))
    names.update(_normalize_dependency_name(name) for name in dependencies)
    groups = cast(dict[str, dict[str, Any]], poetry.get("group", {}))
    for group in groups.values():
        group_deps = cast(dict[str, Any], group.get("dependencies", {}))
        names.update(_normalize_dependency_name(name) for name in group_deps)
    return {name for name in names if name}


def _normalize_dependency_name(raw: str) -> str:
    """Strip version markers and extras from a dependency token."""
    return _DEP_SPLIT_RE.split(raw.strip().lower(), maxsplit=1)[0]


__all__ = ["detect_codebase_signals", "select_mcp_servers", "select_skills"]
