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

# A single doc past this is a data blob, not something anyone reads in a
# popup. Skipping it keeps one pathological file from doubling atlas.html;
# the viewer says so rather than opening empty.
MAX_DOC_BYTES = 256 * 1024


def collect_docs(graph) -> dict:
    """Every SKILL.md and bundled file the graph points at, keyed by path.

    Embedded at render time rather than fetched at runtime because atlas.html
    opens from file://, where browsers refuse fetch() against local files. A
    viewer that read on demand would work when served over http and fail the
    moment the file was opened by double-clicking it — the normal way.

    Keyed by path, not node id: a skill node and a file node can name the same
    file, and paths dedupe them.
    """
    docs = {}
    for node in graph.get("nodes", []):
        path = node.get("path")
        if not path or path in docs:
            continue          # built-ins and dangling targets have no file
        try:
            if os.path.getsize(path) > MAX_DOC_BYTES:
                continue
            docs[path] = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue          # unreadable or gone since the build; viewer says so
    return docs


def _graph_is_stale(graph_file) -> bool:
    """True when the graph file is older than the newest SKILL.md or manifest
    in its scope."""
    try:
        graph_mtime = graph_file.stat().st_mtime_ns
    except OSError:
        return True
    paths = [str(p) for p in atlas_discovery.skill_md_paths()]
    paths += [str(p) for p in atlas_paths.manifest_paths()]
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


def render(cwd=None, embed_docs=True) -> Path:
    atlas_paths.set_scope(cwd)
    graph_file = atlas_paths.graph_path()
    out = atlas_paths.atlas_path()
    graph = json.loads(graph_file.read_text(encoding="utf-8"))

    meta = build_meta(graph, _graph_is_stale(graph_file))
    payload = {"graph": graph, "meta": meta}
    # "</" must not terminate the surrounding <script> block.
    data_json = json.dumps(payload, sort_keys=True).replace("</", "<\\/")
    docs = collect_docs(graph) if embed_docs else {}
    docs_json = json.dumps(docs, sort_keys=True).replace("</", "<\\/")

    title = "skill-atlas"
    if meta.get("project_name"):
        title += " · " + meta["project_name"]

    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("__TITLE__", html_escape(title))
    html = html.replace("/*__D3__*/", VENDOR_D3.read_text(encoding="utf-8"))
    html = html.replace("__DATA_JSON__", data_json)
    html = html.replace("__DOCS_JSON__", docs_json)

    atlas_io.atomic_write_text(out, html)
    return out


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Render atlas.html from graph.json.")
    parser.add_argument("--cwd", default=None,
                        help="scope directory (default: cwd)")
    parser.add_argument("--no-embed-docs", action="store_true",
                        help="skip embedding SKILL.md/bundled file text; the "
                             "markdown viewer reports them unavailable")
    args = parser.parse_args(argv)

    try:
        out = render(cwd=args.cwd or os.getcwd(),
                     embed_docs=not args.no_embed_docs)
        print(f"skill-atlas: wrote {out}")
        return 0
    except FileNotFoundError as exc:
        print("skill-atlas: no graph.json — run build_graph.py first "
              f"({type(exc).__name__})", file=sys.stderr)
        return 2
    except Exception as exc:
        atlas_io.debug_log("render", "-", 0, exc)
        print(f"skill-atlas: render failed: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
