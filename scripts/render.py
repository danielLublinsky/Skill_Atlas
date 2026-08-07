"""render.py — graph.json → self-contained atlas.html.

The output opens from file:// with zero network access: D3 is inlined from
the committed vendor file, data is embedded as JSON. The staleness banner is
computed here at render time — JS under file:// cannot stat files.

Deliberately deterministic: rendering the same inputs twice produces
byte-identical output (no render timestamp), so visual diffing works.
"""

import json
import os
import sys
from html import escape as html_escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import atlas_discovery
import atlas_io
import atlas_paths

VENDOR_D3 = Path(__file__).resolve().parent.parent / "vendor" / "d3.v7.min.js"
TEMPLATE = Path(__file__).resolve().parent / "template" / "atlas_template.html"


def _graph_is_stale(graph_file, cwd) -> bool:
    """True when the graph file is older than the newest SKILL.md or manifest
    in its own scope."""
    try:
        graph_mtime = graph_file.stat().st_mtime_ns
    except OSError:
        return True
    paths = [str(p) for p in atlas_discovery.skill_md_paths(cwd)]
    paths += [str(p) for p in atlas_paths.manifest_paths(cwd)]
    for path in paths:
        try:
            if os.stat(path).st_mtime_ns > graph_mtime:
                return True
        except OSError:
            continue
    return False


def build_meta(graph, stale: bool) -> dict:
    return {
        "generated_at": graph.get("generated_at"),
        "view": graph.get("view", "global"),
        "project_name": graph.get("project"),
        "stale": stale,
    }


def render(cwd=None, project=False) -> Path:
    if project:
        graph_file = atlas_paths.project_graph_path(cwd)
        out = atlas_paths.project_atlas_path(cwd)
        scope_cwd = cwd
    else:
        graph_file = atlas_paths.graph_path()
        out = atlas_paths.atlas_home() / "atlas.html"
        scope_cwd = None
    graph = json.loads(graph_file.read_text(encoding="utf-8"))

    meta = build_meta(graph, _graph_is_stale(graph_file, scope_cwd))
    payload = {"graph": graph, "meta": meta}
    # "</" must not terminate the surrounding <script> block.
    data_json = json.dumps(payload, sort_keys=True).replace("</", "<\\/")

    title = "skill-atlas"
    if meta.get("view") == "project" and meta.get("project_name"):
        title += " · " + meta["project_name"]

    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("__TITLE__", html_escape(title))
    html = html.replace("/*__D3__*/", VENDOR_D3.read_text(encoding="utf-8"))
    html = html.replace("__DATA_JSON__", data_json)

    atlas_io.atomic_write_text(out, html)
    return out


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Render atlas.html from graph.json.")
    parser.add_argument("--project-only", action="store_true",
                        help="render only the current project's atlas")
    parser.add_argument("--global-only", action="store_true",
                        help="render only the machine-level atlas")
    args = parser.parse_args(argv)
    cwd = os.getcwd()

    project_ready = (atlas_paths.is_project(cwd)
                     and atlas_paths.project_graph_path(cwd).is_file())
    if args.project_only and not project_ready:
        print("skill-atlas: no project graph here — run build_graph.py first",
              file=sys.stderr)
        return 2
    jobs = []
    if not args.project_only:
        jobs.append({"project": False})
    if not args.global_only and project_ready:
        jobs.append({"cwd": cwd, "project": True})

    exit_code = 0
    for job in jobs:
        try:
            out = render(**job)
            print(f"skill-atlas: wrote {out}")
        except FileNotFoundError as exc:
            print("skill-atlas: no graph.json — run build_graph.py first "
                  f"({type(exc).__name__})", file=sys.stderr)
            exit_code = 2
        except Exception as exc:
            atlas_io.debug_log("render", "-", 0, exc)
            print(f"skill-atlas: render failed: {type(exc).__name__}", file=sys.stderr)
            exit_code = 2
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
