"""Single source of truth for paths, env vars and settings merging.

Fully project-local (DESIGN-PHASE2 §0 amendment 8): every artifact and
curated file lives in `<scope>/.claude/skill-atlas/`, where the SCOPE is
the directory skill-atlas runs in. There is no global artifact root and no
artifact-location env var. The first explicit run in a directory creates
its `.claude/skill-atlas/` (auto-init); the hooks stay inert anywhere that
was never initialized.

The scope is process-wide state set once by each entry point (defaulting
to the process cwd). SKILL_ATLAS_CLAUDE_DIR redirects only Claude Code's
own config root — the inputs — and remains the testability seam.
"""

import json
import os
from pathlib import Path

_scope = None


def set_scope(cwd=None) -> Path:
    """Fix the directory this process operates on. Entry points call this
    exactly once, before any path is resolved."""
    global _scope
    _scope = Path(cwd).expanduser() if cwd else Path.cwd()
    return _scope


def scope() -> Path:
    return _scope if _scope is not None else Path.cwd()


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else default


def claude_dir() -> Path:
    """Claude Code's own config root — inputs only, never written."""
    return _env_path("SKILL_ATLAS_CLAUDE_DIR", Path.home() / ".claude")


def autobuild_enabled() -> bool:
    return os.environ.get("SKILL_ATLAS_AUTOBUILD", "1") != "0"


def atlas_home() -> Path:
    """This scope's artifact root. Derived files (graph.json, atlas.html,
    catalog/) plus the curated categories.json and the config.json opt-in —
    all of it travels with the directory it describes."""
    return scope() / ".claude" / "skill-atlas"


def initialized() -> bool:
    """True once an explicit run has created this scope's atlas dir — the
    opt-in signal the hooks honour."""
    return atlas_home().is_dir()


def graph_path() -> Path:
    return atlas_home() / "graph.json"


def atlas_path() -> Path:
    return atlas_home() / "atlas.html"


def dirty_path() -> Path:
    return atlas_home() / "graph.dirty"


def debug_log_path() -> Path:
    return atlas_home() / "debug.log"


def categories_path() -> Path:
    """Curated category state for this scope (taxonomy + assignments) —
    never regenerated; commit it with the project."""
    return atlas_home() / "categories.json"


def config_path() -> Path:
    """This scope's searchable-tier opt-in (DESIGN-PHASE2 §3.2)."""
    return atlas_home() / "config.json"


def catalog_dir() -> Path:
    """Derived search shards (DESIGN-PHASE2 §5) — rebuild, never repair."""
    return atlas_home() / "catalog"


def catalog_index_path() -> Path:
    # "_" is outside the category slug alphabet, so no category shard can
    # ever collide with the index file.
    return catalog_dir() / "_index.md"


def user_skills_root() -> Path:
    return claude_dir() / "skills"


def has_local_skills_root() -> bool:
    """Whether this scope contributes its own project skills. Running from
    the home directory, `<scope>/.claude` IS the user config dir — its
    skills are already the user scope and must not double-count."""
    local = scope() / ".claude"
    try:
        if not local.is_dir():
            return False
        return local.resolve() != claude_dir().resolve()
    except OSError:
        return False


def local_skills_root() -> Path:
    return scope() / ".claude" / "skills"


def installed_plugins_path() -> Path:
    return claude_dir() / "plugins" / "installed_plugins.json"


def settings_paths() -> list:
    """All settings files that may carry enabledPlugins, lowest precedence
    first: user level, then this scope's own .claude (when distinct)."""
    paths = [claude_dir() / "settings.json", claude_dir() / "settings.local.json"]
    if has_local_skills_root():
        local = scope() / ".claude"
        paths += [local / "settings.json", local / "settings.local.json"]
    return paths


def merged_enabled_plugins() -> dict:
    """Merge enabledPlugins across settings files (scope local > scope >
    user local > user). Keys are composite '<name>@<marketplace>' strings —
    that is how both settings.json and installed_plugins.json key plugins."""
    merged = {}
    for path in settings_paths():
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


def manifest_paths() -> list:
    """Every non-SKILL.md file the graph depends on. These join the §5.1
    fingerprint: toggling enabledPlugins, installing a plugin, or editing
    this scope's curated categories.json / config.json must not leave the
    graph silently stale; absence hashes as "|missing", so a file's first
    appearance flips the fingerprint too."""
    paths = [installed_plugins_path(), categories_path(), config_path()] \
        + settings_paths()
    try:
        for record in installed_plugins():
            paths.append(record["install_path"] / ".claude-plugin" / "plugin.json")
    except (OSError, ValueError):
        pass
    return paths
