"""categorize.py — the validating CLI the /skill-atlas model drives.

The model never free-hands curated state: every mutation flows through
this CLI, which validates against the schema and the current graph before
an atomic replace (DESIGN-PHASE2 §3.1, §4). Payload-taking subcommands read
JSON on stdin (heredoc-friendly under the command's Bash(python3:*) grant).

Curated state is split per scope: the GLOBAL file
(~/.claude/skill-atlas/categories.json) holds the frozen taxonomy plus
assignments for user and plugin skills; each project's
.claude/skill-atlas/categories.json holds only that project's view-local
assignments (project-scope skills and collision-renamed name@scope ids) —
committable with the repo, never carrying a taxonomy of its own. Run from
a project directory, this CLI operates on that project's view and routes
each write to the right file automatically.

Exit codes:
  0  success (warnings may appear on stderr)
  2  environment failure: no graph.json, or invalid curated state already
     on disk (violations on stderr — fix the file or `import` a good one)
  3  validation rejection of THIS payload — violations one per line on
     stderr; fix the payload and retry

Environmental drift is never an error here: assignments whose skill left
the graph are reported by `status` as orphans, and stale desc_hashes are
the designed stale state (`confirm` refreshes them).
"""

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import atlas_categories
import atlas_paths


class EnvError(Exception):
    """Environment (not payload) problem — mapped to exit 2."""


class PayloadError(Exception):
    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("payload rejected")


def _fail(errors, code=3) -> int:
    for line in errors:
        print(f"categorize: {line}", file=sys.stderr)
    return code


def _warn(lines) -> None:
    for line in lines:
        print(f"categorize: warning: {line}", file=sys.stderr)


def _today() -> str:
    return datetime.date.today().isoformat()


def _env_error_from(exc) -> EnvError:
    lines = [f"{exc.source}: {line}" for line in exc.errors]
    lines.append(f"{exc.source} is invalid on disk — fix it by hand, restore a backup, "
                 "or install a corrected file with: categorize.py import <path>")
    return EnvError("\n".join(lines))


def _load_graph(cwd) -> dict:
    path = (atlas_paths.project_graph_path(cwd) if atlas_paths.is_project(cwd)
            else atlas_paths.graph_path())
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise EnvError(f"no graph at {path} — run build_graph.py first")
    except (OSError, ValueError) as exc:
        raise EnvError(f"unreadable graph.json ({type(exc).__name__}) — rebuild it")


def _view(args) -> dict:
    """Everything a command needs about the current view: the graph, both
    curated files (project one only inside a project), and the merged
    assignment map the view actually sees."""
    cwd = args.cwd or os.getcwd()
    graph = _load_graph(cwd)
    try:
        categories = atlas_categories.load_categories_strict()
        config = atlas_categories.load_config_strict()
        names = atlas_categories.taxonomy_names(categories)
        project = (atlas_categories.load_project_categories_strict(cwd, names)
                   if atlas_paths.is_project(cwd) else None)
    except atlas_categories.CategoriesError as exc:
        raise _env_error_from(exc)
    merged = dict(categories["assignments"])
    if project is not None:
        merged.update(project["assignments"])
    return {"cwd": cwd, "graph": graph, "categories": categories,
            "config": config, "project": project, "merged": merged,
            "names": names}


def _registered(graph) -> list:
    return [n for n in graph.get("nodes", [])
            if n.get("type") == "skill" and n.get("registered")]


def _registered_map(graph) -> dict:
    return {n["id"]: n for n in _registered(graph)}


def _is_view_local(node) -> bool:
    """View-local skills live in the PROJECT curated file: project-scope
    skills, and collision-renamed ids that only exist in project views."""
    return node.get("scope") == "project" or bool(node.get("duplicate"))


def _make_entry(node, labels, today) -> dict:
    return {"categories": list(labels),
            "desc_hash": atlas_categories.desc_hash(node.get("description")),
            "assigned_at": today}


def _tier(node) -> str:
    if node.get("enabled"):
        return "enabled"
    if node.get("searchable"):
        return "searchable"
    return "off"


def _read_stdin_payload() -> dict:
    text = sys.stdin.read()
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise PayloadError([f"stdin: unparseable JSON: {exc}"])
    if not isinstance(payload, dict):
        raise PayloadError(["stdin: expected a JSON object"])
    return payload


def _payload_assignments(payload, taxonomy_labels, known_ids) -> dict:
    raw = payload.get("assignments")
    errors = []
    if not isinstance(raw, dict) or not raw:
        raise PayloadError(["assignments: expected a non-empty object of "
                            '{"<skill id>": ["<category>", ...]}'])
    for skill_id in sorted(raw):
        labels = raw[skill_id]
        if skill_id not in known_ids:
            errors.append(f"assignments[{skill_id!r}]: not a registered skill in graph.json")
        if not isinstance(labels, list) or not labels or \
                not all(isinstance(l, str) for l in labels):
            errors.append(f"assignments[{skill_id!r}]: expected a non-empty list of category names")
            continue
        for label in labels:
            if label not in taxonomy_labels:
                errors.append(f"assignments[{skill_id!r}]: {label!r} is not in the taxonomy")
    if errors:
        raise PayloadError(errors)
    return raw


def _write_split(view, updates) -> None:
    """Route each {id: entry} update to its home file and write whichever
    files were touched, global first (the taxonomy anchors validation)."""
    registered_by_id = _registered_map(view["graph"])
    touched_global = touched_project = False
    for skill_id, entry in updates.items():
        node = registered_by_id[skill_id]
        if _is_view_local(node):
            if view["project"] is None:
                raise PayloadError([f"{skill_id!r} is view-local but the current "
                                    "directory is not a project"])
            view["project"]["assignments"][skill_id] = entry
            touched_project = True
        else:
            view["categories"]["assignments"][skill_id] = entry
            touched_global = True
    if touched_global:
        atlas_categories.write_categories(view["categories"])
    if touched_project:
        atlas_categories.write_project_categories(
            view["cwd"], view["project"],
            atlas_categories.taxonomy_names(view["categories"]))


def _require_bootstrapped(categories) -> None:
    if not atlas_categories.is_bootstrapped(categories):
        raise PayloadError(["not bootstrapped yet — run the bootstrap flow first "
                            "(/skill-atlas), or categorize.py bootstrap"])


def cmd_status(args) -> int:
    view = _view(args)
    graph, merged = view["graph"], view["merged"]
    registered = _registered(graph)

    uncategorized, stale = [], []
    for node in sorted(registered, key=lambda n: n["id"]):
        entry = merged.get(node["id"])
        if entry is None:
            uncategorized.append({"id": node["id"], "description": node.get("description"),
                                  "plugin": node.get("plugin"), "tier": _tier(node)})
        elif entry["desc_hash"] != atlas_categories.desc_hash(node.get("description")):
            stale.append({"id": node["id"], "description": node.get("description"),
                          "categories": entry["categories"], "tier": _tier(node)})

    out = {
        "view": graph.get("view", "global"),
        "project": graph.get("project"),
        "bootstrapped": atlas_categories.is_bootstrapped(view["categories"]),
        "taxonomy_approved_at": view["categories"].get("taxonomy_approved_at"),
        "taxonomy": view["categories"]["taxonomy"],
        "counts": {
            "skills": len(registered),
            "categorized": sum(1 for n in registered if n["id"] in merged),
            "uncategorized": len(uncategorized),
            "stale": len(stale),
        },
        "uncategorized": uncategorized,
        "stale": stale,
        "orphan_assignments": atlas_categories.orphan_ids(
            merged, {n["id"] for n in registered},
            graph.get("stats", {}).get("duplicate_names", [])),
        "config": view["config"],
    }
    if args.full:
        out["skills"] = [{"id": n["id"], "description": n.get("description")}
                         for n in sorted(registered, key=lambda n: n["id"])]
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


def cmd_bootstrap(args) -> int:
    view = _view(args)
    if atlas_categories.is_bootstrapped(view["categories"]):
        return _fail([f"already bootstrapped ({view['categories']['taxonomy_approved_at']}) — "
                      "the taxonomy is frozen; assign into it, or delete "
                      f"{atlas_paths.categories_path()} deliberately to start over"])

    payload = _read_stdin_payload()
    taxonomy = payload.get("taxonomy")
    unknown_keys = sorted(set(payload) - {"taxonomy", "assignments"})
    if unknown_keys:
        return _fail([f"stdin: unknown key {key!r}" for key in unknown_keys])
    # Validate the taxonomy alone first, so a malformed taxonomy reports as
    # itself instead of as a cascade of "label not in taxonomy" errors.
    probe = {"version": 1, "taxonomy": taxonomy, "assignments": {}}
    taxonomy_errors = atlas_categories.validate_categories(probe)
    if taxonomy_errors:
        return _fail(taxonomy_errors)
    registered_by_id = _registered_map(view["graph"])
    raw = _payload_assignments(payload, atlas_categories.taxonomy_names(probe),
                               set(registered_by_id))
    # Full coverage is a hard requirement: every registered skill must be
    # categorized. If nothing fits, the taxonomy is missing a category —
    # add one; never leave a skill out.
    missing = sorted(set(registered_by_id) - set(raw))
    if missing:
        return _fail(["assignments must cover every registered skill; missing: "
                      + ", ".join(missing),
                      "every skill must be categorized — add a category if nothing fits"])

    today = _today()
    view["categories"]["taxonomy"] = taxonomy
    view["categories"]["taxonomy_approved_at"] = today
    updates = {skill_id: _make_entry(registered_by_id[skill_id], labels_for, today)
               for skill_id, labels_for in raw.items()}
    try:
        # Global file is written even if only project entries exist — the
        # taxonomy freeze lives there.
        atlas_categories.write_categories(view["categories"])
        _write_split(view, updates)
    except atlas_categories.CategoriesError as exc:
        return _fail(exc.errors)

    if not 8 <= len(taxonomy) <= 12:
        _warn([f"{len(taxonomy)} categories — the design target is 8–12"])
    counts = {entry["name"]: 0 for entry in taxonomy}
    for labels_for in raw.values():
        for label in labels_for:
            counts[label] += 1
    for name in sorted(counts):
        print(f"  {name}: {counts[name]}")
    print(f"bootstrapped: {len(taxonomy)} categories, "
          f"{len(raw)}/{len(registered_by_id)} skills assigned")
    return 0


def cmd_assign(args) -> int:
    view = _view(args)
    _require_bootstrapped(view["categories"])
    payload = _read_stdin_payload()
    registered_by_id = _registered_map(view["graph"])
    raw = _payload_assignments(payload, view["names"], set(registered_by_id))
    today = _today()
    updates = {skill_id: _make_entry(registered_by_id[skill_id], labels_for, today)
               for skill_id, labels_for in raw.items()}
    try:
        _write_split(view, updates)
    except atlas_categories.CategoriesError as exc:
        return _fail(exc.errors)
    print(f"assigned {len(raw)} skill(s)")
    return 0


def cmd_confirm(args) -> int:
    view = _view(args)
    _require_bootstrapped(view["categories"])
    registered_by_id = _registered_map(view["graph"])
    errors = []
    for skill_id in args.ids:
        if skill_id not in view["merged"]:
            errors.append(f"{skill_id!r}: no assignment to confirm")
        elif skill_id not in registered_by_id:
            errors.append(f"{skill_id!r}: no longer in the graph — cannot confirm")
    if errors:
        return _fail(errors)
    today = _today()
    updates = {}
    for skill_id in args.ids:
        entry = dict(view["merged"][skill_id])
        entry["desc_hash"] = atlas_categories.desc_hash(
            registered_by_id[skill_id].get("description"))
        entry["assigned_at"] = today
        updates[skill_id] = entry
    try:
        _write_split(view, updates)
    except atlas_categories.CategoriesError as exc:
        return _fail(exc.errors)
    print(f"confirmed {len(args.ids)} assignment(s)")
    return 0


def cmd_add_category(args) -> int:
    view = _view(args)
    _require_bootstrapped(view["categories"])
    view["categories"]["taxonomy"].append(
        {"name": args.name, "description": args.description})
    try:
        atlas_categories.write_categories(view["categories"])
    except atlas_categories.CategoriesError as exc:
        return _fail(exc.errors)
    print(f"added category {args.name!r}; taxonomy now has "
          f"{len(view['categories']['taxonomy'])} categories")
    return 0


def cmd_import(args) -> int:
    view = _view(args)
    try:
        text = Path(args.path).read_text(encoding="utf-8")
    except OSError as exc:
        raise EnvError(f"cannot read {args.path}: {type(exc).__name__}")
    try:
        obj = json.loads(text)
    except ValueError as exc:
        return _fail([f"{args.path}: unparseable JSON: {exc}"])

    project_mode = view["project"] is not None
    if project_mode:
        errors = atlas_categories.validate_project_categories(obj, view["names"])
    else:
        errors = atlas_categories.validate_categories(obj)
    if errors:
        return _fail([f"{args.path}: {line}" for line in errors])

    known = set(_registered_map(view["graph"]))
    orphans = sorted(set(obj.get("assignments", {})) - known)
    if orphans:
        # A user-edited full state may legitimately carry assignments for
        # skills that left the graph — surfaced, never rejected.
        _warn([f"{len(orphans)} assignment(s) for skills not in the graph: "
               + ", ".join(orphans)])
    if project_mode:
        merged_after = dict(view["categories"]["assignments"])
        merged_after.update(obj.get("assignments", {}))
    else:
        merged_after = dict(obj.get("assignments", {}))
    uncovered = sorted(known - set(merged_after))
    if uncovered:
        _warn([f"{len(uncovered)} registered skill(s) not covered: "
               + ", ".join(uncovered)
               + " — every skill must be categorized; run /skill-atlas"])

    if project_mode:
        atlas_categories.write_project_categories(view["cwd"], obj, view["names"])
        print(f"imported into project categories.json: "
              f"{len(obj['assignments'])} assignments")
    else:
        atlas_categories.write_categories(obj)
        print(f"imported: {len(obj['taxonomy'])} categories, "
              f"{len(obj['assignments'])} assignments")
    return 0


def cmd_config(args) -> int:
    view = _view(args)
    config = view["config"]
    if not (args.show or args.add or args.remove):
        return _fail(["one of --show / --add-searchable / --remove-searchable is required"])
    if args.show:
        print(json.dumps(config, indent=2, sort_keys=True))
        return 0
    if args.add:
        known = set()
        for node in view["graph"].get("nodes", []):
            if node.get("type") == "skill":
                known.add(node.get("plugin"))
                known.add(node.get("plugin_key"))
        known.discard(None)
        if args.add not in known and not args.force:
            return _fail([f"{args.add!r} is not an installed plugin in graph.json "
                          "(--force to add anyway)"])
        if args.add in config["searchable_plugins"]:
            print(f"{args.add!r} is already searchable")
            return 0
        config["searchable_plugins"].append(args.add)
    if args.remove:
        if args.remove not in config["searchable_plugins"]:
            return _fail([f"{args.remove!r} is not in searchable_plugins"])
        config["searchable_plugins"].remove(args.remove)
    try:
        atlas_categories.write_config(config)
    except atlas_categories.CategoriesError as exc:
        return _fail(exc.errors)
    print(f"searchable_plugins: {json.dumps(config['searchable_plugins'])}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Validating writer for skill-atlas categorization state.")
    parser.add_argument("--cwd", default=None,
                        help="view selector: a project directory categorizes that "
                             "project's view (default: current directory)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("status", help="machine-readable categorization state")
    p.add_argument("--full", action="store_true",
                   help="include every registered skill's id and description")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("bootstrap",
                       help='one-time: stdin {"taxonomy": [...], "assignments": {id: [labels]}}')
    p.set_defaults(func=cmd_bootstrap)

    p = sub.add_parser("assign", help='stdin {"assignments": {id: [labels]}}')
    p.set_defaults(func=cmd_assign)

    p = sub.add_parser("confirm", help="refresh desc_hash for stale ids, keeping labels")
    p.add_argument("ids", nargs="+")
    p.set_defaults(func=cmd_confirm)

    p = sub.add_parser("add-category", help="append one category to the frozen taxonomy")
    p.add_argument("name")
    p.add_argument("description")
    p.set_defaults(func=cmd_add_category)

    p = sub.add_parser("import",
                       help="validate and install a hand-edited/downloaded categories.json "
                            "(global schema outside a project, project schema inside one)")
    p.add_argument("path")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("config", help="searchable-plugins opt-in (always global)")
    p.add_argument("--show", action="store_true")
    p.add_argument("--add-searchable", dest="add", metavar="PLUGIN")
    p.add_argument("--remove-searchable", dest="remove", metavar="PLUGIN")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_config)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except PayloadError as exc:
        return _fail(exc.errors)
    except EnvError as exc:
        for line in str(exc).splitlines():
            print(f"categorize: {line}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
