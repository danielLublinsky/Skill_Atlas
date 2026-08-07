"""Manifest-driven skill discovery (DESIGN §4.1).

"Any directory containing SKILL.md" over-counts by ~60% on a real machine, so
discovery starts from manifests: installed_plugins.json → each plugin.json's
skills[] allowlist (flat glob fallback when the key is absent) → the user and
project skill roots. The marketplace catalogue and stale cached plugin
versions are never walked; installPath is the only ground truth.

Enabled state is an attribute, not a filter — a disabled skill still enters
the graph (the author's most-invoked plugin was disabled when this was
designed; filtering would have hidden exactly the thing worth shouting about).
"""

import datetime
import json
import re
from pathlib import Path

import atlas_paths

_FM_KEY = re.compile(r"^([A-Za-z0-9_-]+)\s*:\s*(.*)$")


def parse_frontmatter(text: str) -> dict:
    """Hand-rolled name:/description: extraction (stdlib-only, no YAML lib).
    Handles quoted values and folded/literal block scalars conservatively."""
    text = text.lstrip("﻿")
    if not text.startswith("---"):
        return {}
    fields = {}
    block_key = None
    block_lines = []

    def flush():
        nonlocal block_key, block_lines
        if block_key is not None:
            fields[block_key] = " ".join(line for line in block_lines if line).strip()
        block_key, block_lines = None, []

    for line in text.splitlines()[1:]:
        if line.strip() in ("---", "..."):
            break
        if block_key is not None:
            if line.startswith((" ", "\t")) or not line.strip():
                block_lines.append(line.strip())
                continue
            flush()
        match = _FM_KEY.match(line)
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip()
        if value in (">", ">-", ">+", "|", "|-", "|+"):
            block_key, block_lines = key, []
        else:
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            fields[key] = value
    flush()
    return fields


def _skill_record(skill_md: Path, scope: str, plugin=None, registered=True,
                  enabled=True, light=False) -> dict:
    record = {
        "id": None,  # assigned after collision resolution
        "type": "skill",
        "name": skill_md.parent.name,
        "description": None,
        "path": str(skill_md),
        "scope": scope,
        "plugin": plugin["name"] if plugin else None,
        "plugin_key": plugin["key"] if plugin else None,
        "marketplace": plugin["marketplace"] if plugin else None,
        "version": plugin["version"] if plugin else None,
        "registered": registered,
        "enabled": enabled,
    }
    if plugin and plugin.get("install_records", 1) > 1:
        record["install_records"] = plugin["install_records"]
    if light:
        return record
    try:
        stat = skill_md.stat()  # follows symlinks — the target is what matters
        record["bytes"] = stat.st_size
        record["mtime"] = datetime.datetime.fromtimestamp(
            stat.st_mtime, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        text = skill_md.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(text)
        record["name"] = frontmatter.get("name") or skill_md.parent.name
        record["description"] = frontmatter.get("description")
    except OSError:
        pass
    return record


def _root_skill_dirs(root: Path):
    """Immediate children of a skill root holding SKILL.md. Follows symlinks
    (a live user skill is a symlinked directory)."""
    try:
        children = sorted(root.iterdir(), key=lambda p: p.name)
    except OSError:
        return
    for child in children:
        if child.is_dir() and (child / "SKILL.md").is_file():
            yield child / "SKILL.md"


def discover(cwd=None, light=False) -> dict:
    """Walk order: user root → project root → installed plugins (allowlist or
    flat glob). Returns registered skills, the unregistered index, collision
    info and the plugin records. light=True skips all file reads (stat/paths
    only) — the fingerprint uses it, so enumeration logic cannot drift
    between staleness checking and building."""
    enabled_map = atlas_paths.merged_enabled_plugins(cwd)
    skills = []
    unregistered = []
    registered_paths = set()

    user_root = atlas_paths.user_skills_root()
    for skill_md in _root_skill_dirs(user_root):
        skills.append(_skill_record(skill_md, "user", light=light))
        registered_paths.add(str(skill_md.resolve()))

    project_root = Path(cwd) / ".claude" / "skills" if cwd else None
    if project_root:
        for skill_md in _root_skill_dirs(project_root):
            skills.append(_skill_record(skill_md, "project", light=light))
            registered_paths.add(str(skill_md.resolve()))

    # May raise OSError/ValueError on a broken manifest → build exit 2.
    plugins = atlas_paths.installed_plugins()

    for plugin in plugins:
        install = plugin["install_path"]
        enabled = enabled_map.get(plugin["key"], True)
        manifest_path = install / ".claude-plugin" / "plugin.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            manifest = {}

        entries = manifest.get("skills")
        if isinstance(entries, list):
            skill_mds = []
            for entry in entries:
                if not isinstance(entry, str):
                    continue
                entry_path = (install / entry.lstrip("./")).resolve()
                skill_md = entry_path if entry_path.name == "SKILL.md" else entry_path / "SKILL.md"
                skill_mds.append(skill_md)
        else:
            # No skills key: flat glob fallback — load-bearing, not defensive
            # (superpowers registers all 14 of its skills this way).
            skill_mds = list(_root_skill_dirs(install / "skills"))

        for skill_md in skill_mds:
            record = _skill_record(skill_md, "plugin", plugin=plugin,
                                   enabled=enabled, light=light)
            if not skill_md.is_file():
                record["missing"] = True
            skills.append(record)
            registered_paths.add(str(skill_md.resolve()))

        # Index every other SKILL.md under the installed path: deprecated/,
        # in-progress/ trees. Indexed, not drawn — unless a registered skill
        # mentions one, which becomes a dangling node.
        try:
            for skill_md in sorted(install.rglob("SKILL.md")):
                if str(skill_md.resolve()) in registered_paths:
                    continue
                record = _skill_record(skill_md, "plugin", plugin=plugin,
                                       registered=False, enabled=False, light=light)
                unregistered.append(record)
        except OSError:
            pass

    duplicate_names = _assign_ids(skills)
    return {
        "skills": skills,
        "unregistered": unregistered,
        "duplicate_names": duplicate_names,
        "plugins": plugins,
        "roots": [str(user_root)] + ([str(project_root)] if project_root else []),
    }


def _assign_ids(skills) -> list:
    """Node id = the invocation string: '<plugin>:<name>' for plugin skills,
    bare '<name>' for user/project. Bare-name collisions (project shadowing
    user) get disambiguated ids like 'graphify@user' and are reported —
    a duplicate name is a defect worth surfacing, not an edge case to merge."""
    for skill in skills:
        if skill["scope"] == "plugin":
            skill["id"] = f"{skill['plugin']}:{skill['name']}"
        else:
            skill["id"] = skill["name"]
    by_id = {}
    for skill in skills:
        by_id.setdefault(skill["id"], []).append(skill)
    duplicates = []
    for node_id, group in sorted(by_id.items()):
        if len(group) > 1:
            duplicates.append(node_id)
            for skill in group:
                skill["duplicate"] = True
                skill["id"] = f"{skill['name']}@{skill['scope']}"
    return duplicates


def skill_md_paths(cwd=None) -> list:
    """Every SKILL.md the graph depends on (registered + unregistered index),
    with no file reads — the §5.1 fingerprint input."""
    result = discover(cwd=cwd, light=True)
    return [Path(s["path"]) for s in result["skills"] + result["unregistered"]]


def naive_skillmd_count(cwd=None) -> int:
    """What 'any directory containing SKILL.md' would have found: everything
    under the claude dir (cache incl. stale versions, marketplaces) plus the
    roots. Diagnostic only — the number the manifest-driven walk avoids."""
    count = 0
    seen = set()
    roots = [atlas_paths.claude_dir()]
    if cwd:
        roots.append(Path(cwd) / ".claude" / "skills")
    for root in roots:
        try:
            for skill_md in root.rglob("SKILL.md"):
                key = str(skill_md)
                if key not in seen:
                    seen.add(key)
                    count += 1
        except OSError:
            continue
    # rglob does not follow directory symlinks; count linked user skills too.
    for skill_md in _root_skill_dirs(atlas_paths.user_skills_root()):
        if str(skill_md) not in seen:
            seen.add(str(skill_md))
            count += 1
    return count
