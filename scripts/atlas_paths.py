"""Single source of truth for paths, env vars and settings merging.

Every other module resolves locations through here. SKILL_ATLAS_CLAUDE_DIR is
the testability seam: pointing it at a fixture tree redirects the entire
system without monkeypatching.
"""

import json
import os
from pathlib import Path


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else default


def claude_dir() -> Path:
    return _env_path("SKILL_ATLAS_CLAUDE_DIR", Path.home() / ".claude")


def atlas_home() -> Path:
    """Artifact root — derived files only."""
    return _env_path("SKILL_ATLAS_HOME", claude_dir() / "skill-atlas")


def autobuild_enabled() -> bool:
    return os.environ.get("SKILL_ATLAS_AUTOBUILD", "1") != "0"


def graph_path() -> Path:
    return atlas_home() / "graph.json"


def dirty_path() -> Path:
    return atlas_home() / "graph.dirty"


def debug_log_path() -> Path:
    return atlas_home() / "debug.log"


def user_skills_root() -> Path:
    return claude_dir() / "skills"


def is_project(cwd) -> bool:
    """A directory is a project iff it carries its own .claude/ — and that
    .claude is not the user-level one (running from ~ must not double-count
    user skills as project skills)."""
    if not cwd:
        return False
    project_claude = Path(cwd) / ".claude"
    try:
        if not project_claude.is_dir():
            return False
        return project_claude.resolve() != claude_dir().resolve()
    except OSError:
        return False


def project_home(cwd) -> Path:
    """Per-project artifact root, inside the project folder (user decision:
    project atlases live with the project, not under ~/.claude)."""
    return Path(cwd) / ".claude" / "skill-atlas"


def project_graph_path(cwd) -> Path:
    return project_home(cwd) / "graph.json"


def project_atlas_path(cwd) -> Path:
    return project_home(cwd) / "atlas.html"


def installed_plugins_path() -> Path:
    return claude_dir() / "plugins" / "installed_plugins.json"


def settings_paths(cwd=None) -> list:
    """All settings files that may carry enabledPlugins, lowest precedence first."""
    paths = [claude_dir() / "settings.json", claude_dir() / "settings.local.json"]
    if cwd:
        project = Path(cwd) / ".claude"
        paths += [project / "settings.json", project / "settings.local.json"]
    return paths


def merged_enabled_plugins(cwd=None) -> dict:
    """Merge enabledPlugins across settings files (project local > project >
    user local > user). Keys are composite '<name>@<marketplace>' strings —
    that is how both settings.json and installed_plugins.json key plugins."""
    merged = {}
    for path in settings_paths(cwd):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        enabled = data.get("enabledPlugins")
        if isinstance(enabled, dict):
            merged.update({key: bool(value) for key, value in enabled.items()})
    return merged


def installed_plugins() -> list:
    """Parse installed_plugins.json. Per-plugin values are ARRAYS of install
    records; installPath is the only ground truth for what is installed
    (.in_use markers are unreliable, stale cache versions coexist on disk).

    One record is chosen per plugin key — project scope preferred, else the
    first — and the total record count is surfaced rather than hidden.
    Raises OSError/ValueError on an unreadable or unparseable manifest;
    build_graph maps that to exit 2.
    """
    data = json.loads(installed_plugins_path().read_text(encoding="utf-8"))
    plugins = data.get("plugins", {})
    out = []
    for key, records in plugins.items():
        if isinstance(records, dict):  # tolerate a single-record shape
            records = [records]
        if not isinstance(records, list):
            continue
        records = [r for r in records if isinstance(r, dict) and r.get("installPath")]
        if not records:
            continue
        chosen = next((r for r in records if r.get("scope") == "project"), records[0])
        name, _, marketplace = key.partition("@")
        out.append({
            "key": key,
            "name": name,
            "marketplace": marketplace or None,
            "install_path": Path(chosen["installPath"]).expanduser(),
            "version": chosen.get("version"),  # opaque — may be "unknown"
            "scope": chosen.get("scope"),
            "install_records": len(records),
        })
    return out


def manifest_paths(cwd=None) -> list:
    """Every non-SKILL.md file the graph depends on. These join the §5.1
    fingerprint: toggling enabledPlugins or installing a plugin must not
    leave the graph silently stale."""
    paths = [installed_plugins_path()] + settings_paths(cwd)
    try:
        for record in installed_plugins():
            paths.append(record["install_path"] / ".claude-plugin" / "plugin.json")
    except (OSError, ValueError):
        pass
    return paths
