"""SessionStart hook — rebuild graph.json when it is stale (DESIGN §5.1).

Hook invariants (§6.1, non-negotiable): always exit 0, never write to
stdout, swallow every exception, never block. A slow hook is worse than a
stale graph — the fingerprint walk aborts at 2 s and lets the session
proceed.
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

FINGERPRINT_DEADLINE_SECONDS = 2.0


def run() -> None:
    import json

    import atlas_discovery
    import atlas_fingerprint
    import atlas_io
    import atlas_paths
    import build_graph

    if not atlas_paths.autobuild_enabled():
        return
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
    for name, view_cwd, graph_file in views:
        reason = stale_reason(graph_file, view_cwd)
        if reason == "deadline":
            atlas_io.debug_note("check_stale", f"{name} fingerprint-deadline-exceeded")
            return
        if reason is None:
            continue
        graph, _ = build_graph.build(cwd=view_cwd)
        atlas_io.atomic_write_json(graph_file, graph)
        rebuilt.append(f"{name}={reason}")

    if rebuilt:
        try:
            atlas_paths.dirty_path().unlink()
        except OSError:
            pass
    total_ms = int((time.monotonic() - started) * 1000)
    status = "rebuilt " + ",".join(rebuilt) if rebuilt else "fresh"
    atlas_io.debug_note("check_stale", f"{status} total_ms={total_ms}")


def main() -> int:
    try:
        run()
    except BaseException as exc:  # a non-zero hook can interrupt the session
        try:
            import atlas_io
            atlas_io.debug_log("check_stale", "-", 0, exc)
        except BaseException:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
