"""Schema validation and the validating writer for Phase 2's curated state.

categories.json is CURATED (DESIGN-PHASE2 §3.1): never regenerated, never
repaired. Every write flows through validate-then-atomic-replace here, and
the build reads it through the strict loaders, which fail loud on a
hand-edit that breaks the schema — build_graph maps CategoriesError to
exit 2 with the violations on stderr. config.json (§3.2) gets the same
treatment.

The one thing that is never a schema violation: environmental drift. An
assignment for a skill that no longer exists in the graph is the build's
business (stats.orphan_assignments), and a stale desc_hash is the designed
stale state — neither is fatal. known_ids checking is opt-in, used by the
CLI to catch model-hallucinated ids at write time.
"""

import hashlib
import json
import re

import atlas_io
import atlas_paths

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
RESERVED_NAMES = ("uncategorized",)

_CATEGORIES_KEYS = {"version", "taxonomy", "taxonomy_approved_at", "assignments"}
_ASSIGNMENT_KEYS = {"categories", "desc_hash", "assigned_at"}
# Per-project curated file: assignments only — the taxonomy lives solely in
# the global file, so project state can travel with the repo without ever
# forking the frozen taxonomy.
_PROJECT_KEYS = {"version", "assignments"}
_CONFIG_KEYS = {"version", "searchable_plugins"}


class CategoriesError(ValueError):
    """Schema violations, all of them at once — callers print the list so a
    bad payload is fixed in one round trip, not one error per attempt."""

    def __init__(self, source, errors):
        self.source = source
        self.errors = list(errors)
        super().__init__(f"{source}: {len(self.errors)} schema violation(s)")


def desc_hash(description) -> str:
    """Hash of a skill description as recorded at assignment time. The one
    definition shared by writer and build, so staleness detection can never
    drift from what was written."""
    text = description if isinstance(description, str) else ""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def empty_categories() -> dict:
    return {"version": 1, "taxonomy": [], "assignments": {}}


def empty_project_categories() -> dict:
    return {"version": 1, "assignments": {}}


def empty_config() -> dict:
    return {"version": 1, "searchable_plugins": []}


def is_bootstrapped(obj) -> bool:
    return bool(obj.get("taxonomy_approved_at"))


def taxonomy_names(obj) -> set:
    return {entry.get("name") for entry in obj.get("taxonomy", [])
            if isinstance(entry, dict)}


def validate_categories(obj, known_ids=None) -> list:
    """Return every violation as a human-readable string; empty means valid.
    Unknown keys are violations too — a typo like "asignments" must fail
    loud, not silently empty the catalog."""
    if not isinstance(obj, dict):
        return ["top level: expected an object"]
    errors = []
    for key in sorted(set(obj) - _CATEGORIES_KEYS):
        errors.append(f"unknown key {key!r}")
    if obj.get("version") != 1:
        errors.append(f"version: expected 1, got {obj.get('version')!r}")
    approved = obj.get("taxonomy_approved_at")
    if approved is not None and (not isinstance(approved, str) or not approved.strip()):
        errors.append("taxonomy_approved_at: expected a non-empty string")

    names = set()
    taxonomy = obj.get("taxonomy")
    if not isinstance(taxonomy, list):
        errors.append("taxonomy: expected a list")
        taxonomy = []
    for index, entry in enumerate(taxonomy):
        where = f"taxonomy[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{where}: expected an object")
            continue
        for key in sorted(set(entry) - {"name", "description"}):
            errors.append(f"{where}: unknown key {key!r}")
        name = entry.get("name")
        if not isinstance(name, str) or not SLUG_RE.match(name):
            errors.append(f"{where}: name must match {SLUG_RE.pattern}")
        elif name in RESERVED_NAMES:
            errors.append(f"{where}: {name!r} is a reserved name")
        elif name in names:
            errors.append(f"{where}: duplicate category name {name!r}")
        else:
            names.add(name)
        desc = entry.get("description")
        if not isinstance(desc, str) or not desc.strip() or "\n" in desc:
            errors.append(f"{where}: description must be a non-empty single line")

    _validate_assignments(obj.get("assignments"), names, known_ids, errors)
    return errors


def _validate_assignments(assignments, valid_names, known_ids, errors) -> None:
    if not isinstance(assignments, dict):
        errors.append("assignments: expected an object")
        return
    for skill_id in sorted(assignments):
        entry = assignments[skill_id]
        where = f"assignments[{skill_id!r}]"
        if not isinstance(skill_id, str) or not skill_id.strip():
            errors.append(f"{where}: empty skill id")
        elif known_ids is not None and skill_id not in known_ids:
            errors.append(f"{where}: not a registered skill in graph.json")
        if not isinstance(entry, dict):
            errors.append(f"{where}: expected an object")
            continue
        for key in sorted(_ASSIGNMENT_KEYS - set(entry)):
            errors.append(f"{where}: missing key {key!r}")
        for key in sorted(set(entry) - _ASSIGNMENT_KEYS):
            errors.append(f"{where}: unknown key {key!r}")
        labels = entry.get("categories")
        if not isinstance(labels, list) or not labels:
            errors.append(f"{where}: categories must be a non-empty ordered list")
        else:
            seen = set()
            for label in labels:
                if not isinstance(label, str):
                    errors.append(f"{where}: labels must be strings")
                    continue
                if label not in valid_names:
                    errors.append(f"{where}: {label!r} is not in the taxonomy")
                if label in seen:
                    errors.append(f"{where}: duplicate label {label!r}")
                seen.add(label)
        hash_value = entry.get("desc_hash")
        if "desc_hash" in entry and (not isinstance(hash_value, str)
                                     or not HASH_RE.match(hash_value)):
            errors.append(f"{where}: desc_hash must match {HASH_RE.pattern}")
        assigned_at = entry.get("assigned_at")
        if "assigned_at" in entry and (not isinstance(assigned_at, str)
                                       or not assigned_at.strip()):
            errors.append(f"{where}: assigned_at must be a non-empty string")


def validate_project_categories(obj, taxonomy_names, known_ids=None) -> list:
    """Per-project curated file: `{"version": 1, "assignments": {...}}`.
    Labels are validated against the GLOBAL taxonomy — a project file that
    tries to carry its own taxonomy is rejected with a pointer."""
    if not isinstance(obj, dict):
        return ["top level: expected an object"]
    errors = []
    for key in sorted(set(obj) - _PROJECT_KEYS):
        hint = (" — the taxonomy lives only in the global categories.json"
                if key in ("taxonomy", "taxonomy_approved_at") else "")
        errors.append(f"unknown key {key!r}{hint}")
    if obj.get("version") != 1:
        errors.append(f"version: expected 1, got {obj.get('version')!r}")
    _validate_assignments(obj.get("assignments"), set(taxonomy_names),
                          known_ids, errors)
    return errors


def orphan_ids(assignments, view_ids, duplicate_names=()) -> list:
    """Assignments this view cannot resolve AND should worry about — a bare
    name shadowed by a collision rename in this view is not gone, so it is
    not environmental drift."""
    dupes = set(duplicate_names)
    return sorted(skill_id for skill_id in assignments
                  if skill_id not in view_ids and skill_id not in dupes)


def validate_config(obj) -> list:
    if not isinstance(obj, dict):
        return ["top level: expected an object"]
    errors = []
    for key in sorted(set(obj) - _CONFIG_KEYS):
        errors.append(f"unknown key {key!r}")
    if obj.get("version") != 1:
        errors.append(f"version: expected 1, got {obj.get('version')!r}")
    plugins = obj.get("searchable_plugins")
    if not isinstance(plugins, list):
        errors.append("searchable_plugins: expected a list")
        return errors
    seen = set()
    for index, name in enumerate(plugins):
        where = f"searchable_plugins[{index}]"
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{where}: expected a non-empty string")
        elif name in seen:
            errors.append(f"{where}: duplicate entry {name!r}")
        else:
            seen.add(name)
    return errors


def _load_strict(path, validate, empty, label):
    """Missing file → empty skeleton (a supported state). Present but
    unreadable/unparseable/invalid → CategoriesError, which the build maps
    to exit 2: curated state fails loud, never tolerate-and-degrade."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return empty()
    except OSError as exc:
        raise CategoriesError(label, [f"unreadable: {type(exc).__name__}"]) from exc
    try:
        obj = json.loads(text)
    except ValueError as exc:
        # JSONDecodeError's message carries position only, never content.
        raise CategoriesError(label, [f"unparseable JSON: {exc}"]) from exc
    errors = validate(obj)
    if errors:
        raise CategoriesError(label, errors)
    return obj


def load_categories_strict() -> dict:
    return _load_strict(atlas_paths.categories_path(), validate_categories,
                        empty_categories, "categories.json")


def load_project_categories_strict(cwd, taxonomy_names) -> dict:
    return _load_strict(
        atlas_paths.project_categories_path(cwd),
        lambda obj: validate_project_categories(obj, taxonomy_names),
        empty_project_categories, "project categories.json")


def load_config_strict() -> dict:
    return _load_strict(atlas_paths.config_path(), validate_config,
                        empty_config, "config.json")


def write_categories(obj, known_ids=None) -> None:
    """Validate, then atomic replace. On rejection the file on disk is
    untouched — validation runs before the temp file exists."""
    errors = validate_categories(obj, known_ids=known_ids)
    if errors:
        raise CategoriesError("categories.json", errors)
    atlas_io.atomic_write_json(atlas_paths.categories_path(), obj)


def write_project_categories(cwd, obj, taxonomy_names, known_ids=None) -> None:
    errors = validate_project_categories(obj, taxonomy_names, known_ids=known_ids)
    if errors:
        raise CategoriesError("project categories.json", errors)
    atlas_io.atomic_write_json(atlas_paths.project_categories_path(cwd), obj)


def write_config(obj) -> None:
    errors = validate_config(obj)
    if errors:
        raise CategoriesError("config.json", errors)
    atlas_io.atomic_write_json(atlas_paths.config_path(), obj)
