#!/usr/bin/env python3
"""Read-only structural assertions against the real machine (DESIGN §9).

Never hard-codes counts — the doc's numbers drifted within days of being
written. Every comparison recomputes both sides at runtime. Isolation:
inputs (skills, plugins, settings) come through a temp claude dir of
symlinks to the real ~/.claude, and artifacts land in a throwaway scope
directory — the real machine is only ever read.

Covers: M1 (manifest-driven counts), M2 (dangling detection incl. the known
setup-matt-pocock-skills → qa defect when that plugin is installed),
M5 (self-contained offline HTML), §11.1 partial (disabled plugins surfaced),
§11.3 (registered ≪ on-disk). M4 needs a manual session — reported as SKIP.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

failures = []


def check(label, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def independent_registered_count(claude_dir: Path, cwd: Path) -> int:
    """Recount registered skills with deliberately separate, minimal logic."""
    count = 0
    for root in (claude_dir / "skills", cwd / ".claude" / "skills"):
        if root.is_dir():
            for child in sorted(root.iterdir()):
                if child.is_dir() and (child / "SKILL.md").is_file():
                    count += 1
    manifest = json.loads((claude_dir / "plugins" / "installed_plugins.json")
                          .read_text(encoding="utf-8"))
    for records in manifest.get("plugins", {}).values():
        if isinstance(records, dict):
            records = [records]
        seen = set()
        for record in records:
            install = record.get("installPath")
            if not install or install in seen:
                continue
            seen.add(install)
            plugin_json = Path(install) / ".claude-plugin" / "plugin.json"
            try:
                plugin = json.loads(plugin_json.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                plugin = {}
            entries = plugin.get("skills")
            if isinstance(entries, list):
                count += len([e for e in entries if isinstance(e, str)])
            else:
                skills_dir = Path(install) / "skills"
                if skills_dir.is_dir():
                    count += len([d for d in skills_dir.iterdir()
                                  if d.is_dir() and (d / "SKILL.md").is_file()])
            break  # one record per plugin key, matching discovery
    return count


def main() -> int:
    real = Path(os.environ.get("SKILL_ATLAS_CLAUDE_DIR",
                               "~/.claude")).expanduser()
    tmp = Path(tempfile.mkdtemp(prefix="skill-atlas-smoke-"))
    fake = tmp / "claude"
    fake.mkdir()
    for name in ("skills", "plugins", "settings.json", "settings.local.json"):
        src = real / name
        if src.exists():
            (fake / name).symlink_to(src)
    os.environ["SKILL_ATLAS_CLAUDE_DIR"] = str(fake)
    scope_dir = tmp / "scope"   # a neutral throwaway scope for artifacts
    scope_dir.mkdir()

    import atlas_paths
    import build_graph
    import render

    claude_dir = atlas_paths.claude_dir()
    cwd = scope_dir
    print(f"smoke: inputs={real} artifacts={scope_dir / '.claude' / 'skill-atlas'}\n")

    print("M1 — manifest-driven discovery")
    graph, exit_code = build_graph.build(cwd=cwd)
    stats = graph["stats"]
    expected = independent_registered_count(claude_dir, cwd)
    check("registered count matches independent recount",
          stats["skills"] == expected, f"{stats['skills']} vs {expected}")
    # The naive count is opt-in on builds (--naive-count) and would be
    # computed against the symlinked temp claude dir anyway, where rglob
    # does not descend — recount independently against the real one.
    naive_on_disk = sum(1 for _ in real.rglob("SKILL.md"))
    check("registered well below naive on-disk count",
          stats["skills"] < naive_on_disk,
          f"{stats['skills']} registered / {naive_on_disk} on disk")
    check("no node from the marketplace catalogue",
          not any("/marketplaces/" in (n.get("path") or "") for n in graph["nodes"]))
    enabled_map = atlas_paths.merged_enabled_plugins()
    disabled_plugins = sorted(k for k, v in enabled_map.items() if not v)
    for key in disabled_plugins:
        name = key.split("@", 1)[0]
        nodes = [n for n in graph["nodes"]
                 if n.get("plugin") == name and n.get("registered")]
        if nodes:
            check(f"§11.1: every {name} node carries enabled=false",
                  all(not n["enabled"] for n in nodes), f"{len(nodes)} nodes")
    user_skill_dirs = [d.name for d in (claude_dir / "skills").iterdir()
                       if d.is_dir() and (d / "SKILL.md").is_file()]
    node_paths = {n.get("path") or "" for n in graph["nodes"]}
    for name in user_skill_dirs:
        check(f"user skill '{name}' discovered (symlinks followed)",
              any(f"/skills/{name}/SKILL.md" in p for p in node_paths))

    print("\nM2 — dangling detection")
    dangling = [e for e in graph["edges"] if e["kind"] == "dangling"]
    broken = [e for e in graph["edges"] if e.get("broken")]
    check("exit code matches findings",
          exit_code == (1 if (dangling or broken) else 0),
          f"exit {exit_code}, {len(dangling)} dangling, {len(broken)} broken")
    qa_edges = [e for e in dangling
                if e["source"].endswith("setup-matt-pocock-skills")
                and e["target"] == "skill?:qa"]
    setup_nodes = [n for n in graph["nodes"]
                   if n["id"].endswith("setup-matt-pocock-skills")]
    if not setup_nodes:
        print("  [SKIP] mattpocock-skills not installed — qa defect n/a")
    elif "`qa`" not in Path(setup_nodes[0]["path"]).read_text(encoding="utf-8"):
        # The defect this tool found (§11.2) was fixed upstream in 1.2.2 —
        # the fixture twin still validates the mechanism.
        print("  [SKIP] qa defect fixed upstream — installed version has no `qa` mention")
    else:
        check("the known qa defect is named",
              len(qa_edges) == 1 and qa_edges[0]["reason"] == "unregistered")

    print("\n§11.3 — most SKILL.md files are not skills")
    check("on-disk count at least 2x registered",
          naive_on_disk >= 2 * stats["skills"],
          f"{naive_on_disk} vs {stats['skills']}")

    print("\nM5 — self-contained HTML")
    import atlas_io
    atlas_io.atomic_write_json(atlas_paths.graph_path(), graph)
    out = render.render(cwd=cwd)
    html = out.read_text(encoding="utf-8")
    check("atlas.html written", out.is_file(), f"{out.stat().st_size} bytes")
    check("no external scripts or stylesheets",
          "<script src=" not in html and "<link" not in html)

    print("\n[SKIP] M4 (auto-update) — manual procedure: make m4-check")

    print(f"\n{'FAILED: ' + ', '.join(failures) if failures else 'all live checks passed'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
