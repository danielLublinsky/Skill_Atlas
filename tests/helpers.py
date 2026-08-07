"""Shared test plumbing: sys.path for scripts/, and an env sandbox that
points the whole system at a throwaway copy of the fixture tree. No test
ever touches the real ~/.claude."""

import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "fakehome"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

ENV_VARS = [
    "SKILL_ATLAS_CLAUDE_DIR",
    "SKILL_ATLAS_AUTOBUILD",
]

# Fixture manifests use this placeholder for absolute install paths; the
# sandbox rewrites it to the copied tree's real location.
PLACEHOLDER = "__CLAUDE_DIR__"


class EnvSandbox:
    def __init__(self, copy_fixtures: bool = False):
        self.copy_fixtures = copy_fixtures
        self.tmp = None
        self.claude = None
        self._saved = {}

    def __enter__(self):
        self._saved = {name: os.environ.get(name) for name in ENV_VARS}
        self.tmp = Path(tempfile.mkdtemp(prefix="skill-atlas-test-"))
        self.claude = self.tmp / "claude"
        if self.copy_fixtures:
            shutil.copytree(FIXTURES, self.claude, symlinks=True)
            self._rewrite_placeholders()
            self._ensure_symlink()
        else:
            self.claude.mkdir()
        os.environ["SKILL_ATLAS_CLAUDE_DIR"] = str(self.claude)
        os.environ.pop("SKILL_ATLAS_AUTOBUILD", None)
        return self

    def __exit__(self, *exc_info):
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False

    def _rewrite_placeholders(self):
        manifest = self.claude / "plugins" / "installed_plugins.json"
        if manifest.exists():
            text = manifest.read_text(encoding="utf-8")
            manifest.write_text(text.replace(PLACEHOLDER, str(self.claude)), encoding="utf-8")

    def _ensure_symlink(self):
        """Recreate the symlinked user skill if the checkout/copy lost it."""
        link = self.claude / "skills" / "linked-skill"
        if not link.exists() and not link.is_symlink():
            link.symlink_to("../linktarget", target_is_directory=True)

    @property
    def project_dir(self) -> Path:
        return self.claude / "project"


# --- Phase 2 fixtures -------------------------------------------------------
# SKILL_ATLAS_HOME is created per-sandbox at runtime, so curated-state
# fixtures live here as builders, not as files under fakehome/.

TAXONOMY = [
    {"name": "eng", "description": "building and changing code"},
    {"name": "docs", "description": "writing and maintaining documentation"},
]

# Which fixture skills an approved cache labels. alpha:two is the
# multi-category member (M4/M6 exercise it); graphify, linked-skill and
# beta:y stay uncategorized — graphify also dodges the id-vs-view question,
# since its id differs between the global and project views.
ASSIGNED = {
    "alpha:one": ["eng"],
    "alpha:two": ["eng", "docs"],
    "plain-skill": ["docs"],
    "beta:x": ["eng"],
}

# Full coverage of the global-view fixture collection (7 skills, bare
# user-skill ids). Bootstrap REQUIRES full coverage; the partial ASSIGNED
# above stays for direct-write build tests, where uncategorized is the
# legitimate transitional state.
ASSIGNED_ALL = dict(ASSIGNED)
ASSIGNED_ALL.update({"graphify": ["docs"], "beta:y": ["eng"],
                     "linked-skill": ["eng"]})


def approved_categories(cwd=None, assigned=None, taxonomy=None) -> dict:
    """A valid, bootstrapped categories.json for the fixture tree, with
    desc_hashes computed from the live sandbox descriptions (call inside an
    EnvSandbox). cwd chooses the view the ids come from."""
    import atlas_categories
    import atlas_discovery

    descriptions = {s["id"]: s.get("description")
                    for s in atlas_discovery.discover(cwd=cwd)["skills"]}
    assignments = {}
    for skill_id, labels in (assigned if assigned is not None else ASSIGNED).items():
        assignments[skill_id] = {
            "categories": list(labels),
            "desc_hash": atlas_categories.desc_hash(descriptions.get(skill_id)),
            "assigned_at": "2026-08-07",
        }
    return {
        "version": 1,
        "taxonomy_approved_at": "2026-08-07",
        "taxonomy": [dict(entry) for entry in (taxonomy or TAXONOMY)],
        "assignments": assignments,
    }


def write_categories(sandbox, obj) -> None:
    """Direct (non-validating) write — deliberately bypasses the validating
    writer so tests can plant hand-edited and broken states."""
    import atlas_io
    import atlas_paths
    atlas_io.atomic_write_json(atlas_paths.categories_path(), obj)


def write_config(sandbox, obj) -> None:
    import atlas_io
    import atlas_paths
    atlas_io.atomic_write_json(atlas_paths.config_path(), obj)


def write_project_categories(sandbox, obj) -> None:
    import atlas_io
    import atlas_paths
    atlas_io.atomic_write_json(
        atlas_paths.project_categories_path(sandbox.project_dir), obj)


def searchable_config(*plugins) -> dict:
    return {"version": 1, "searchable_plugins": list(plugins)}
