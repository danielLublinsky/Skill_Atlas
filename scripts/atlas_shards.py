"""Derived search catalog: catalog/_index.md + one shard per category +
catalog/uncategorized.md (DESIGN §14.1).

Everything derives from graph.json alone — v3 nodes carry categories, tier
and staleness, and the graph carries the frozen taxonomy — so there is one
source of truth and no second read of categories.json. Deterministic:
sorted entries, no timestamps. The catalog dir is fully derived
(rebuild-never-repair), which licenses deleting shards that no longer
correspond to a category.

Tier rule (DESIGN §12): tier-off skills are excluded at emit time — if an entry is
in a shard, search will eventually serve it, and a disabled-and-not-opted-in
plugin must never come back through a side door. The uncategorized shard is
always emitted, even against an empty taxonomy: search degrades to the flat
shard, it never breaks (DESIGN §13.7).
"""

import atlas_io
import atlas_paths

TOKEN_BUDGET_CHARS = 200

_INDEX_NOTE = ("<!-- derived by skill-atlas; do not edit. Counts overlap - "
               "a skill may appear under several categories. -->")
_SHARD_NOTE = ("<!-- derived by skill-atlas; do not edit. [enabled]: invoke "
               "with the Skill tool. [searchable]: Read the SKILL.md at the "
               "path and follow it as instructions. -->")
_UNCAT_NOTE = ("<!-- derived by skill-atlas; do not edit. These skills are "
               "not yet categorized and this shard may be large. After "
               "serving a result from it, say so and suggest running "
               "/skill-atlas. -->")


def _catalog_skills(graph) -> list:
    """Tiers 1+2 only, sorted by id for deterministic output."""
    return sorted((n for n in graph.get("nodes", [])
                   if n.get("type") == "skill" and n.get("registered")
                   and (n.get("enabled") or n.get("searchable"))),
                  key=lambda n: n["id"])


def _tier(node) -> str:
    return "enabled" if node.get("enabled") else "searchable"


def _token_list(members) -> str:
    """Concrete product/tool words for stage-1 routing: member plugin names
    first, then skill names, within a fixed budget. Derived, never curated —
    always in sync with membership (DESIGN §14.2)."""
    plugins = sorted({n["plugin"] for n in members if n.get("plugin")})
    names = sorted({n["name"] for n in members})
    tokens, used = [], 0
    for token in plugins + [n for n in names if n not in plugins]:
        used += len(token) + 2
        if used > TOKEN_BUDGET_CHARS:
            tokens.append("…")
            break
        tokens.append(token)
    return ", ".join(tokens)


def _shard_text(title, note, members, home_category=None) -> str:
    lines = [f"# {title}", note, ""]
    for node in members:
        stale = " (stale)" if node.get("category_stale") else ""
        lines.append(f"## {node['id']} [{_tier(node)}]{stale}")
        lines.append((node.get("description") or "(no description)").strip())
        if node.get("path"):
            lines.append(f"- path: {node.get('path')}")
        else:
            # Built-ins ship inside the Claude Code binary — nothing to Read;
            # [enabled] already tells the reader to invoke via the Skill tool.
            lines.append("- built-in: ships with Claude Code, no file on disk")
        others = [c for c in node.get("categories") or [] if c != home_category]
        if others:
            lines.append(f"- also in: {', '.join(others)}")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def emit(graph) -> list:
    """Write _index.md + every category shard + uncategorized.md; remove
    shards for categories that no longer exist. Returns written paths."""
    taxonomy = graph.get("taxonomy", [])
    skills = _catalog_skills(graph)
    by_category = {entry["name"]: [] for entry in taxonomy}
    uncategorized = []
    for node in skills:
        labels = node.get("categories") or []
        if not labels:
            uncategorized.append(node)
        for label in labels:
            by_category.setdefault(label, []).append(node)

    catalog = atlas_paths.catalog_dir()
    written = []

    index_lines = ["# skill catalog index", _INDEX_NOTE, ""]
    for entry in taxonomy:
        members = by_category[entry["name"]]
        line = f"{entry['name']}({len(members)}) — {entry['description']}"
        tokens = _token_list(members)
        if tokens:
            line += f" — {tokens}"
        index_lines.append(line)
    index_lines.append(f"uncategorized({len(uncategorized)}) — skills not yet "
                       "categorized; run /skill-atlas to file them")
    index_path = atlas_paths.catalog_index_path()
    atlas_io.atomic_write_text(index_path, "\n".join(index_lines) + "\n")
    written.append(index_path)

    for entry in taxonomy:
        path = catalog / f"{entry['name']}.md"
        atlas_io.atomic_write_text(
            path, _shard_text(f"{entry['name']} — {entry['description']}",
                              _SHARD_NOTE, by_category[entry["name"]],
                              home_category=entry["name"]))
        written.append(path)

    uncat_path = catalog / "uncategorized.md"
    atlas_io.atomic_write_text(
        uncat_path, _shard_text("uncategorized — skills not yet categorized",
                                _UNCAT_NOTE, uncategorized))
    written.append(uncat_path)

    keep = {path.name for path in written}
    for path in catalog.glob("*.md"):
        if path.name not in keep:
            path.unlink()
    return written
