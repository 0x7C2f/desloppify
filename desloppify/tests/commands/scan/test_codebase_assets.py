"""Tests for scan-time project asset syncing."""

from __future__ import annotations

import json

from desloppify.app.commands.scan.codebase_assets import ensure_codebase_agent_assets


def _write_skill_source(root, names: list[str]) -> None:
    for name in names:
        skill_dir = root / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")


def test_python_backend_syncs_project_skills_and_mcps(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text(
        "[project]\ndependencies = ['fastapi>=0.1']\n",
        encoding="utf-8",
    )

    skill_source = tmp_path / "skills"
    _write_skill_source(
        skill_source,
        [
            "code-review",
            "multi-backend",
            "plan",
            "python-review",
            "test-coverage",
            "update-codemaps",
            "update-docs",
            "verify",
        ],
    )
    mcporter_config = tmp_path / "mcporter.json"
    mcporter_config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "context7": {"baseUrl": "https://example.test/context7"},
                    "filesystem": {"command": ["npx", "filesystem"]},
                    "github": {"command": ["npx", "github"]},
                    "obsidian": {"command": ["npx", "obsidian"]},
                },
                "imports": [],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("DESLOPPIFY_SKILL_SOURCE_DIR", str(skill_source))
    monkeypatch.setenv("MCPORTER_CONFIG", str(mcporter_config))

    result = ensure_codebase_agent_assets(project_root)

    assert result.synced_skills == (
        "code-review",
        "multi-backend",
        "plan",
        "python-review",
        "test-coverage",
        "update-codemaps",
        "update-docs",
        "verify",
    )
    assert result.mcp_servers == ("context7", "filesystem", "github")
    assert not result.warnings
    assert (project_root / ".desloppify" / "skills" / "python-review" / "SKILL.md").is_file()

    mcporter_payload = json.loads(
        (project_root / ".desloppify" / "mcporter.json").read_text(encoding="utf-8")
    )
    assert sorted(mcporter_payload["mcpServers"]) == ["context7", "filesystem", "github"]


def test_obsidian_vault_adds_obsidian_skill_and_mcp(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "vault"
    project_root.mkdir()
    (project_root / ".obsidian").mkdir()

    skill_source = tmp_path / "skills"
    _write_skill_source(
        skill_source,
        [
            "code-review",
            "obsidian",
            "plan",
            "update-codemaps",
            "update-docs",
            "verify",
        ],
    )
    mcporter_config = tmp_path / "mcporter.json"
    mcporter_config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "context7": {"baseUrl": "https://example.test/context7"},
                    "filesystem": {"command": ["npx", "filesystem"]},
                    "github": {"command": ["npx", "github"]},
                    "obsidian": {"command": ["npx", "obsidian"]},
                },
                "imports": [],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("DESLOPPIFY_SKILL_SOURCE_DIR", str(skill_source))
    monkeypatch.setenv("MCPORTER_CONFIG", str(mcporter_config))

    result = ensure_codebase_agent_assets(project_root)

    assert "obsidian" in result.synced_skills
    assert "obsidian" in result.mcp_servers
    assert (project_root / ".desloppify" / "skills" / "obsidian" / "SKILL.md").is_file()


def test_sync_prunes_old_managed_skills_but_keeps_unmanaged_dirs(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / ".obsidian").mkdir()

    skill_source = tmp_path / "skills"
    _write_skill_source(
        skill_source,
        [
            "code-review",
            "multi-backend",
            "obsidian",
            "plan",
            "python-review",
            "test-coverage",
            "update-codemaps",
            "update-docs",
            "verify",
        ],
    )
    mcporter_config = tmp_path / "mcporter.json"
    mcporter_config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "context7": {"baseUrl": "https://example.test/context7"},
                    "filesystem": {"command": ["npx", "filesystem"]},
                    "github": {"command": ["npx", "github"]},
                    "obsidian": {"command": ["npx", "obsidian"]},
                },
                "imports": [],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("DESLOPPIFY_SKILL_SOURCE_DIR", str(skill_source))
    monkeypatch.setenv("MCPORTER_CONFIG", str(mcporter_config))

    ensure_codebase_agent_assets(project_root)
    unmanaged = project_root / ".desloppify" / "skills" / "custom-user-skill"
    unmanaged.mkdir(parents=True)
    (unmanaged / "SKILL.md").write_text("# custom\n", encoding="utf-8")

    (project_root / ".obsidian").rmdir()
    (project_root / "pyproject.toml").write_text(
        "[project]\ndependencies = ['fastapi>=0.1']\n",
        encoding="utf-8",
    )

    result = ensure_codebase_agent_assets(project_root)

    assert "obsidian" not in result.synced_skills
    assert not (project_root / ".desloppify" / "skills" / "obsidian").exists()
    assert unmanaged.is_dir()


def test_malformed_manifests_warn_but_do_not_abort_sync(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "package.json").write_text("{not json", encoding="utf-8")
    (project_root / "pyproject.toml").write_text("[project", encoding="utf-8")

    skill_source = tmp_path / "skills"
    _write_skill_source(
        skill_source,
        ["code-review", "plan", "update-codemaps", "update-docs", "verify"],
    )
    mcporter_config = tmp_path / "mcporter.json"
    mcporter_config.write_text("{not json", encoding="utf-8")

    monkeypatch.setenv("DESLOPPIFY_SKILL_SOURCE_DIR", str(skill_source))
    monkeypatch.setenv("MCPORTER_CONFIG", str(mcporter_config))

    result = ensure_codebase_agent_assets(project_root)

    assert result.synced_skills == (
        "code-review",
        "plan",
        "update-codemaps",
        "update-docs",
        "verify",
    )
    assert result.mcp_servers == ()
    assert any("package.json" in warning for warning in result.warnings)
    assert any("pyproject.toml" in warning for warning in result.warnings)
    assert any("mcporter config" in warning for warning in result.warnings)
