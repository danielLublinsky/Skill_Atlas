"""build_graph.py — manifests + skill roots → graph.json (DESIGN §4).

Exit codes (§4.2):
  0  graph built, nothing dangling
  1  graph built, ≥1 broken reference or dangling mention (CI gate)
  2  build failed (unreadable root, unparseable manifest, write error)

Exit 1 covers all three dangling kinds: a references edge to a missing file,
a mention of an unregistered skill, and a mention of a disabled skill — all
mean a skill points somewhere the reader cannot follow.
"""

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import atlas_annotate
import atlas_categories
import atlas_discovery
import atlas_extract
import atlas_fingerprint
import atlas_io
import atlas_paths
import atlas_shards


def _classify_mention(source, token, registered_by_id, by_name, unreg_lookup,
                      plugin_names):
    """Resolve a mention token to an edge dict, or None for no edge.
    Ambiguous bare names (duplicates) get no edge — mentions are
    attributed to neither collision partner."""
    target = registered_by_id.get(token)
    if target is None:
        candidates = by_name.get(token, [])
        if len(candidates) == 1:
            target = candidates[0]
        elif len(candidates) > 1:
            return None
    if target is not None:
        if target["id"] == source["id"]:
            return None
        if target["enabled"]:
            return {"source": source["id"], "target": target["id"], "kind": "mentions"}
        return {"source": source["id"], "target": target["id"],
                "kind": "dangling", "reason": "disabled"}

    unreg = unreg_lookup.get(token)
    if unreg:
        return {"source": source["id"], "target": f"skill?:{token}",
                "kind": "dangling", "reason": "unregistered"}
    return {"source": source["id"], "target": f"skill?:{token}",
            "kind": "dangling", "reason": "absent"}


def build(cwd=None, naive_count=False) -> tuple:
    """Build the one local view of this scope: the machine collection plus
    the scope's own skills, with the scope's settings overrides. Returns
    (graph, exit_code). Raises on unbuildable environments — main() maps
    that to exit 2."""
    atlas_paths.set_scope(cwd)
    discovery = atlas_discovery.discover()
    skills = discovery["skills"]
    unregistered = discovery["unregistered"]
    plugin_names = {p["name"] for p in discovery["plugins"]}

    # Phase 2 annotation (DESIGN-PHASE2 §3.3): categories, staleness and the
    # searchable tier ride every skill record from here on, so node assembly,
    # stats and the renderer see them for free. Curated-state schema
    # violations raise CategoriesError — fail loud, exit 2 via main().
    categories = atlas_categories.load_categories_strict()
    config = atlas_categories.load_config_strict()
    atlas_annotate.annotate_skills(skills, categories, config)

    registered_by_id = {s["id"]: s for s in skills}
    by_name = {}
    for skill in skills:
        by_name.setdefault(skill["name"], []).append(skill)
    unreg_lookup = {}
    for record in unregistered:
        unreg_lookup.setdefault(record["name"], []).append(record)
        if record["plugin"]:
            unreg_lookup.setdefault(f"{record['plugin']}:{record['name']}", []).append(record)

    universe = set(by_name) | set(registered_by_id) | set(unreg_lookup)

    edges = []
    file_nodes = {}
    dangling_nodes = {}
    broken_refs = 0

    for skill in skills:
        if skill.get("missing") or not skill.get("path"):
            continue
        try:
            text = Path(skill["path"]).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        body = atlas_extract.split_frontmatter_body(text)
        skill_dir = Path(skill["path"]).parent

        for ref in atlas_extract.extract_references(body, skill_dir):
            file_id = f"file:{ref['path']}"
            if file_id not in file_nodes:
                node = {"id": file_id, "type": "file",
                        "name": Path(ref["path"]).name,
                        "path": ref["path"], "exists": ref["exists"]}
                if ref["exists"]:
                    try:
                        node["bytes"] = Path(ref["path"]).stat().st_size
                    except OSError:
                        pass
                file_nodes[file_id] = node
            broken = not ref["exists"]
            if broken:
                broken_refs += 1
            edges.append({"source": skill["id"], "target": file_id,
                          "kind": "references", "broken": broken})

        self_names = {skill["name"], skill["id"]}
        seen_targets = set()
        for token in atlas_extract.extract_mentions(body, universe, plugin_names, self_names):
            edge = _classify_mention(skill, token, registered_by_id, by_name,
                                     unreg_lookup, plugin_names)
            if edge is None:
                continue
            # Two token forms (backticked namespaced + bare hyphenated) can
            # resolve to the same target — one edge, not two.
            key = (edge["target"], edge["kind"])
            if key in seen_targets:
                continue
            seen_targets.add(key)
            edges.append(edge)
            if edge["kind"] == "dangling" and edge["target"].startswith("skill?:"):
                records = unreg_lookup.get(token, [])
                dangling_nodes[edge["target"]] = {
                    "id": edge["target"], "type": "skill", "name": token,
                    "path": records[0]["path"] if records else None,
                    "scope": records[0]["scope"] if records else None,
                    "registered": False, "enabled": False, "dangling": True,
                }

    linked = set()
    for edge in edges:
        linked.add(edge["source"])
        linked.add(edge["target"])
    orphans = [s["id"] for s in skills if s["id"] not in linked]

    dangling_edges = [e for e in edges if e["kind"] == "dangling"]

    skill_paths = [s["path"] for s in skills + unregistered if s.get("path")]
    fingerprint = atlas_fingerprint.compute(skill_paths,
                                            atlas_paths.manifest_paths())

    nodes = ([{k: v for k, v in s.items() if k != "plugin_key" or v} for s in skills]
             + [dangling_nodes[k] for k in sorted(dangling_nodes)]
             + [file_nodes[k] for k in sorted(file_nodes)])

    stats = {
        "skills": len(skills),
        "enabled": sum(1 for s in skills if s["enabled"]),
        "unregistered": len(unregistered),
        "files": len(file_nodes),
        "edges": len(edges),
        "broken_refs": broken_refs,
        "dangling": len(dangling_edges),
        "orphans": len(orphans),
        "orphan_ids": sorted(orphans),
        "duplicate_names": discovery["duplicate_names"],
        # TODO states for the next /skill-atlas run — never defects, so
        # never part of the exit code (DESIGN-PHASE2 §3.3).
        **atlas_annotate.phase2_stats(skills, categories,
                                      discovery["duplicate_names"]),
    }
    if naive_count:
        # Diagnostic only — a machine-wide rglob, so opt-in (--naive-count).
        stats["skillmd_on_disk"] = atlas_discovery.naive_skillmd_count()

    graph = {
        "version": 3,
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
                        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "view": "local",
        "scope": str(atlas_paths.scope().resolve()),
        "project": atlas_paths.scope().resolve().name,
        "roots": discovery["roots"],
        "source_fingerprint": fingerprint,
        # The frozen taxonomy rides along so shards and the category view
        # derive from graph.json alone — one source of truth.
        "taxonomy": categories["taxonomy"],
        "nodes": nodes,
        "edges": edges,
        # Indexed, not drawn (§4.1) — the visualization's "show unregistered"
        # toggle synthesizes nodes from this client-side.
        "unregistered_index": [
            {"name": u["name"], "path": u["path"], "plugin": u["plugin"],
             "scope": u["scope"]}
            for u in unregistered
        ],
        "stats": stats,
    }
    exit_code = 1 if (broken_refs or dangling_edges) else 0
    return graph, exit_code


def report(graph, stream=sys.stdout):
    stats = graph["stats"]
    label = graph.get("project") or "local"
    todo = []
    if stats["uncategorized"]:
        todo.append(f"{stats['uncategorized']} uncategorized")
    if stats["stale_categories"]:
        todo.append(f"{stats['stale_categories']} stale categories")
    todo_text = (", " + ", ".join(todo)) if todo else ""
    naive = (f" [naive on-disk count: {stats['skillmd_on_disk']}]"
             if "skillmd_on_disk" in stats else "")
    print(f"skill-atlas [{label}]: {stats['skills']} skills ({stats['enabled']} enabled), "
          f"{stats['files']} files, {stats['edges']} edges{todo_text}{naive}",
          file=stream)
    if stats["duplicate_names"]:
        print(f"  duplicate names: {', '.join(stats['duplicate_names'])}", file=stream)
    for edge in graph["edges"]:
        if edge["kind"] == "dangling":
            target = edge["target"].replace("skill?:", "")
            print(f"  dangling: {edge['source']} -> {target} ({edge['reason']})",
                  file=stream)
        elif edge.get("broken"):
            print(f"  broken reference: {edge['source']} -> {edge['target']}",
                  file=stream)


# Dropped into the atlas dir the first time a build creates it, so the
# derived caches never show up as repo noise. Not self-ignoring: commit it
# alongside categories.json so clones inherit it. Deleting it is a user
# choice that sticks — it is never recreated.
_SCOPE_GITIGNORE = """\
# derived by skill-atlas — these are caches, safe to delete.
# Commit categories.json (curated) and config.json (per-scope opt-in).
graph.json
atlas.html
catalog/
graph.dirty
debug.log
"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build graph.json from skill manifests.")
    parser.add_argument("--check", action="store_true",
                        help="build and report without writing graph.json")
    parser.add_argument("--cwd", default=None,
                        help="scope directory (default: cwd); its "
                             ".claude/skill-atlas is created on first write")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--naive-count", action="store_true",
                        help="also report what a naive machine-wide SKILL.md "
                             "walk would find (diagnostic, slow)")
    args = parser.parse_args(argv)
    cwd = args.cwd or os.getcwd()

    try:
        atlas_paths.set_scope(cwd)
        newly_init = not args.check and not atlas_paths.initialized()
        graph, worst = build(cwd=cwd, naive_count=args.naive_count)
        if not args.check:
            # Auto-init: the atomic writes create .claude/skill-atlas here.
            atlas_io.atomic_write_json(atlas_paths.graph_path(), graph)
            atlas_shards.emit(graph)
            if newly_init:
                atlas_io.atomic_write_text(
                    atlas_paths.atlas_home() / ".gitignore", _SCOPE_GITIGNORE)
            try:
                atlas_paths.dirty_path().unlink()
            except OSError:
                pass
        if not args.quiet:
            report(graph)
    except atlas_categories.CategoriesError as exc:
        # Decision: invalid CURATED state fails loud, naming every violation
        # (the file is the user's own — this is not the debug.log privacy
        # boundary, which still records the type only).
        atlas_io.debug_log("build_graph", cwd, 0, exc)
        for line in exc.errors:
            print(f"skill-atlas: {exc.source}: {line}", file=sys.stderr)
        print(f"skill-atlas: build failed: invalid {exc.source} — fix it by hand, "
              "restore a backup, or install a corrected file with "
              "categorize.py import", file=sys.stderr)
        return 2
    except Exception as exc:
        atlas_io.debug_log("build_graph", cwd, 0, exc)
        print(f"skill-atlas: build failed: {type(exc).__name__}", file=sys.stderr)
        return 2
    return worst


if __name__ == "__main__":
    sys.exit(main())
