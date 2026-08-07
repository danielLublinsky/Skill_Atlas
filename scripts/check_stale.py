"""SessionStart hook — rebuild graph.json when it is stale (DESIGN §5.1)
and inject the skill-library index line (DESIGN-PHASE2 §6).

Hook invariants (§6.1): always exit 0, swallow every exception, never
block. A slow hook is worse than a stale graph — the fingerprint walk
aborts at 2 s and lets the session proceed. Stdout carries ONLY the
documented SessionStart JSON contract — one hookSpecificOutput line, and
only when the dormant (searchable) tier is nonempty; a Phase-2-inert
install stays byte-identical to Phase 1: empty stdout. (Deliberate
revision of the original "never write to stdout" invariant.)
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

FINGERPRINT_DEADLINE_SECONDS = 2.0
LINE_BUDGET_CHARS = 220


def index_line(graph):
    """The ~40-token advertisement for the dormant tier, from stats.catalog
    alone. None when there is nothing dormant — the searchable tier is what
    the line pays for, and silence keeps the inert state truly inert."""
    try:
        catalog = graph["stats"]["catalog"]
        dormant = catalog["dormant"]
    except (KeyError, TypeError):
        return None
    if not dormant:
        return None
    counts = sorted(((n, c) for n, c in catalog["categories"].items() if c),
                    key=lambda item: (-item[1], item[0]))
    uncategorized = catalog.get("uncategorized", 0)
    nag = " Run /skill-atlas to categorize." if uncategorized else ""

    def build(parts):
        segments = []
        if parts:
            segments.append(", ".join(parts))
        if uncategorized:
            segments.append(f"{uncategorized} uncategorized")
        middle = (" — " + ", ".join(segments)) if segments else ""
        return (f"Skill library: {dormant} dormant skills{middle}. "
                f"Call skill-search before nontrivial tasks.{nag}")

    kept = []
    for name, count in counts:
        trial = kept + [f"{name}({count})"]
        if len(build(trial)) > LINE_BUDGET_CHARS and kept:
            kept.append("…")
            break
        kept = trial
    return build(kept)


def run():
    """Rebuild stale views; return the freshest global graph dict (already
    in hand after a rebuild, lazily read otherwise) so main() can emit the
    index line — or None when unavailable."""
    import atlas_discovery
    import atlas_fingerprint
    import atlas_io
    import atlas_paths
    import atlas_shards
    import build_graph

    if not atlas_paths.autobuild_enabled():
        return None
    started = time.monotonic()
    deadline = started + FINGERPRINT_DEADLINE_SECONDS
    cwd = os.getcwd()
    dirty = atlas_paths.dirty_path().exists()

    def stored_fingerprint(graph_file):
        try:
            return json.loads(graph_file.read_text(encoding="utf-8")).get("source_fingerprint")
        except (OSError, ValueError):
            return None

    def stale_reason(graph_file, view_cwd):
        """None = fresh; otherwise why this view needs a rebuild."""
        if dirty:
            return "dirty-flag"
        stored = stored_fingerprint(graph_file)
        if stored is None:
            return "no-graph"
        current = atlas_fingerprint.compute(
            atlas_discovery.skill_md_paths(view_cwd),
            atlas_paths.manifest_paths(view_cwd), deadline=deadline)
        if current is None:
            return "deadline"
        return "fingerprint-mismatch" if current != stored else None

    # Two views, each judged against its own scope: global (machine-level,
    # cwd=None) and — when the cwd carries its own .claude/ — the project
    # view, whose fingerprint additionally covers project skills + settings.
    views = [("global", None, atlas_paths.graph_path())]
    if atlas_paths.is_project(cwd):
        views.append(("project", cwd, atlas_paths.project_graph_path(cwd)))

    rebuilt = []
    global_graph = None
    for name, view_cwd, graph_file in views:
        reason = stale_reason(graph_file, view_cwd)
        if reason == "deadline":
            atlas_io.debug_note("check_stale", f"{name} fingerprint-deadline-exceeded")
            return global_graph
        if reason is None:
            continue
        graph, _ = build_graph.build(cwd=view_cwd)
        atlas_io.atomic_write_json(graph_file, graph)
        if view_cwd is None:
            # A hook rebuild must not leave the search shards stale — a
            # handful of small atomic writes, well inside the 10s budget.
            atlas_shards.emit(graph)
            global_graph = graph
        rebuilt.append(f"{name}={reason}")

    if rebuilt:
        try:
            atlas_paths.dirty_path().unlink()
        except OSError:
            pass
    total_ms = int((time.monotonic() - started) * 1000)
    status = "rebuilt " + ",".join(rebuilt) if rebuilt else "fresh"
    atlas_io.debug_note("check_stale", f"{status} total_ms={total_ms}")

    if global_graph is None:
        try:
            global_graph = json.loads(
                atlas_paths.graph_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            global_graph = None
    return global_graph


def main() -> int:
    line = None
    try:
        graph = run()
        if graph is not None:
            line = index_line(graph)
    except BaseException as exc:  # a non-zero hook can interrupt the session
        try:
            import atlas_io
            atlas_io.debug_log("check_stale", "-", 0, exc)
        except BaseException:
            pass
    if line is not None:
        try:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": line}}))
        except BaseException:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
