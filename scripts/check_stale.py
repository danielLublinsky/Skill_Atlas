"""SessionStart hook — rebuild this scope's graph when it is stale
(DESIGN §5.1) and inject the skill-library index line (DESIGN §14.3).

Fully scope-local: the hook operates on `<cwd>/.claude/skill-atlas/` and
ONLY where that directory already exists — a directory becomes a scope the
first time an explicit run (build_graph.py or /skill-atlas) creates it;
the hook never initializes anything, so sessions in untouched directories
stay untouched.

Hook invariants (DESIGN §5.4): always exit 0, swallow every exception, never
block. A slow hook is worse than a stale graph — the fingerprint walk
aborts at 2 s and lets the session proceed. Stdout carries ONLY the
documented SessionStart JSON contract — one hookSpecificOutput line, and
only when the dormant (searchable) tier is nonempty; an uninitialized or
Phase-2-inert scope stays byte-identical to Phase 1: empty stdout.
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
    """Rebuild this scope's graph if stale; return the freshest graph dict
    (for the index line) — or None when the scope is uninitialized,
    autobuild is off, or the deadline hit."""
    import atlas_discovery
    import atlas_fingerprint
    import atlas_io
    import atlas_paths
    import atlas_shards
    import build_graph

    if not atlas_paths.autobuild_enabled():
        return None
    cwd = os.getcwd()
    atlas_paths.set_scope(cwd)
    if not atlas_paths.initialized():
        return None   # never-initialized directory: the hook stays inert

    started = time.monotonic()
    deadline = started + FINGERPRINT_DEADLINE_SECONDS
    graph_file = atlas_paths.graph_path()

    def stored_fingerprint():
        try:
            return json.loads(graph_file.read_text(encoding="utf-8")).get("source_fingerprint")
        except (OSError, ValueError):
            return None

    reason = None
    if atlas_paths.dirty_path().exists():
        reason = "dirty-flag"
    else:
        stored = stored_fingerprint()
        if stored is None:
            reason = "no-graph"
        else:
            current = atlas_fingerprint.compute(
                atlas_discovery.skill_md_paths(),
                atlas_paths.manifest_paths(), deadline=deadline)
            if current is None:
                atlas_io.debug_note("check_stale", "fingerprint-deadline-exceeded")
                return None
            if current != stored:
                reason = "fingerprint-mismatch"

    if reason:
        graph, _ = build_graph.build(cwd=cwd)
        atlas_io.atomic_write_json(graph_file, graph)
        atlas_shards.emit(graph)
        try:
            atlas_paths.dirty_path().unlink()
        except OSError:
            pass
    else:
        try:
            graph = json.loads(graph_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            graph = None

    total_ms = int((time.monotonic() - started) * 1000)
    status = f"rebuilt {reason}" if reason else "fresh"
    atlas_io.debug_note("check_stale", f"{status} total_ms={total_ms}")
    return graph


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
