"""Project-local skill and MCP asset syncing for scan."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from desloppify.app.commands.scan.codebase_asset_detection import (
    detect_codebase_signals,
    select_mcp_servers,
    select_skills,
)
from desloppify.base.discovery.file_paths import safe_write_text

_SAFE_MCP_SERVERS = frozenset({"context7", "filesystem", "github", "obsidian"})
_SKILL_SOURCE_ENV = "DESLOPPIFY_SKILL_SOURCE_DIR"
_MCPORTER_CONFIG_ENV = "MCPORTER_CONFIG"
_MANIFEST_NAME = "scan-assets.json"


@dataclass(frozen=True)
class CodebaseAssetSyncResult:
    """Summarize the project-local skills and MCP config prepared for scan."""

    synced_skills: tuple[str, ...]
    mcp_servers: tuple[str, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)


def ensure_codebase_agent_assets(project_root: Path) -> CodebaseAssetSyncResult:
    """Sync project-local skills and MCP config based on codebase markers."""
    root = project_root.resolve()
    state_dir = root / ".desloppify"
    skills_dir = state_dir / "skills"
    mcporter_path = state_dir / "mcporter.json"
    manifest_path = state_dir / _MANIFEST_NAME

    warnings: list[str] = []
    signals = detect_codebase_signals(root, warnings=warnings)
    selected_skills = select_skills(signals)
    selected_servers = select_mcp_servers(signals)

    skill_source = _resolve_skill_source_dir()
    synced_skills = _sync_skills(
        source_dir=skill_source,
        target_dir=skills_dir,
        manifest_path=manifest_path,
        selected_skills=selected_skills,
        warnings=warnings,
    )
    synced_servers = _sync_mcporter_config(
        target_path=mcporter_path,
        selected_servers=selected_servers,
        warnings=warnings,
    )

    manifest = {
        "signals": sorted(signals),
        "managed_skills": list(synced_skills),
        "mcp_servers": list(synced_servers),
    }
    safe_write_text(manifest_path, json.dumps(manifest, indent=2) + "\n")

    return CodebaseAssetSyncResult(
        synced_skills=tuple(synced_skills),
        mcp_servers=tuple(synced_servers),
        warnings=tuple(warnings),
    )


def _resolve_skill_source_dir() -> Path | None:
    """Resolve the preferred local skill source directory."""
    candidates = [
        Path.home() / ".skillnet" / "migration-backups" / "remove-desloppify-skills" / "skills",
        Path.home() / ".skillnet" / "skills",
    ]
    if env_value := os.environ.get(_SKILL_SOURCE_ENV):
        candidates.insert(0, Path(env_value).expanduser())
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    return None


def _sync_skills(
    *,
    source_dir: Path | None,
    target_dir: Path,
    manifest_path: Path,
    selected_skills: list[str],
    warnings: list[str],
) -> list[str]:
    """Mirror selected managed skills into the project's `.desloppify/skills`."""
    target_dir.mkdir(parents=True, exist_ok=True)
    previous = set(_load_managed_skills(manifest_path))
    for stale_name in sorted(previous - set(selected_skills)):
        _remove_managed_skill_dir(target_dir, stale_name)

    if source_dir is None:
        warnings.append("No local SkillNet source directory found; skipped skill sync.")
        return []

    synced: list[str] = []
    for skill_name in selected_skills:
        if not _is_safe_skill_name(skill_name):
            warnings.append(f"Skipped unsafe skill name `{skill_name}`.")
            continue
        source_path = source_dir / skill_name
        if not source_path.is_dir():
            warnings.append(f"Skill source missing for `{skill_name}`; skipped.")
            continue
        destination = target_dir / skill_name
        _remove_path(destination)
        shutil.copytree(source_path, destination)
        synced.append(skill_name)
    return synced


def _sync_mcporter_config(
    *,
    target_path: Path,
    selected_servers: list[str],
    warnings: list[str],
) -> list[str]:
    """Write a project-local mcporter config using safe mirrored servers."""
    source_path = Path(
        os.environ.get(
            _MCPORTER_CONFIG_ENV,
            str(Path.home() / ".mcporter" / "mcporter.json"),
        )
    ).expanduser()
    payload: dict[str, Any] = {"mcpServers": {}, "imports": []}
    if not source_path.is_file():
        warnings.append("No mcporter config found; wrote an empty project MCP config.")
        safe_write_text(target_path, json.dumps(payload, indent=2) + "\n")
        return []

    try:
        source_payload = json.loads(source_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        warnings.append(f"Could not parse mcporter config `{source_path}`: {exc}")
        safe_write_text(target_path, json.dumps(payload, indent=2) + "\n")
        return []
    source_servers = source_payload.get("mcpServers", {})
    if not isinstance(source_servers, dict):
        warnings.append("mcporter config had no usable mcpServers map; wrote an empty project MCP config.")
        safe_write_text(target_path, json.dumps(payload, indent=2) + "\n")
        return []

    mirrored: list[str] = []
    for server_name in selected_servers:
        if server_name not in _SAFE_MCP_SERVERS:
            continue
        server_payload = source_servers.get(server_name)
        if server_payload is None:
            warnings.append(f"MCP server `{server_name}` was not available in mcporter config.")
            continue
        payload["mcpServers"][server_name] = server_payload
        mirrored.append(server_name)

    safe_write_text(target_path, json.dumps(payload, indent=2) + "\n")
    return mirrored


def _load_managed_skills(manifest_path: Path) -> list[str]:
    """Return previously managed skill names from the last sync manifest."""
    if not manifest_path.is_file():
        return []
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    managed = payload.get("managed_skills", [])
    return [
        name
        for name in managed
        if isinstance(name, str) and name.strip() and _is_safe_skill_name(name)
    ]


def _is_safe_skill_name(name: str) -> bool:
    """Return whether a skill name is safe to use as a single path segment."""
    candidate = Path(name.strip())
    return (
        bool(name.strip())
        and not candidate.is_absolute()
        and candidate.parts == (candidate.name,)
        and candidate.name not in {"", ".", ".."}
    )


def _remove_managed_skill_dir(target_dir: Path, skill_name: str) -> None:
    """Delete a managed skill directory while keeping removals inside target_dir."""
    if not _is_safe_skill_name(skill_name):
        return
    _remove_path(target_dir / skill_name)


def _remove_path(path: Path) -> None:
    """Delete an existing file, symlink, or directory."""
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    if path.is_dir():
        shutil.rmtree(path)


__all__ = ["CodebaseAssetSyncResult", "ensure_codebase_agent_assets"]
