"""M1: schema validation, the validating writer, and the categorize.py CLI."""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

import helpers
import atlas_categories
import atlas_paths
import build_graph


def _build_global():
    neutral = str(Path(os.environ["SKILL_ATLAS_CLAUDE_DIR"]).parent)
    return build_graph.main(["--quiet", "--cwd", neutral])


def _cli(*args, stdin_text=None, cwd=None):
    # Explicit --cwd always: categorize.py follows the view from cwd, and
    # the test runner's own cwd (this repo) is itself a project. The
    # sandbox tmp dir is the neutral non-project → global view.
    neutral = str(Path(os.environ["SKILL_ATLAS_CLAUDE_DIR"]).parent)
    return subprocess.run(
        [sys.executable, str(helpers.SCRIPTS / "categorize.py"),
         "--cwd", cwd or neutral, *args],
        input=stdin_text, capture_output=True, text=True, env=os.environ.copy())


def _read_categories():
    return json.loads(atlas_paths.categories_path().read_text(encoding="utf-8"))


class TestValidation(unittest.TestCase):
    def test_round_trip(self):
        with helpers.EnvSandbox() as _:
            obj = {"version": 1, "taxonomy_approved_at": "2026-08-07",
                   "taxonomy": list(helpers.TAXONOMY),
                   "assignments": {"some:skill": {
                       "categories": ["eng"],
                       "desc_hash": atlas_categories.desc_hash("d"),
                       "assigned_at": "2026-08-07"}}}
            atlas_categories.write_categories(obj)
            self.assertEqual(atlas_categories.load_categories_strict(), obj)
            leftovers = [p for p in atlas_paths.atlas_home().iterdir()
                         if p.suffix == ".tmp"]
            self.assertEqual(leftovers, [])

    def test_rejection_classes(self):
        good_hash = atlas_categories.desc_hash("d")

        def errors_of(obj, known_ids=None):
            return atlas_categories.validate_categories(obj, known_ids=known_ids)

        base = lambda: {"version": 1, "taxonomy": list(helpers.TAXONOMY),
                        "assignments": {}}

        obj = base(); obj["version"] = 2
        self.assertTrue(any("version" in e for e in errors_of(obj)))

        obj = base(); obj["asignments"] = {}
        self.assertTrue(any("unknown key 'asignments'" in e for e in errors_of(obj)))

        obj = base(); obj["taxonomy"].append({"name": "eng", "description": "again"})
        self.assertTrue(any("duplicate category name" in e for e in errors_of(obj)))

        obj = base(); obj["taxonomy"].append({"name": "uncategorized", "description": "x"})
        self.assertTrue(any("reserved" in e for e in errors_of(obj)))

        obj = base(); obj["taxonomy"].append({"name": "Bad Slug", "description": "x"})
        self.assertTrue(any("name must match" in e for e in errors_of(obj)))

        obj = base()
        obj["assignments"]["a"] = {"categories": [], "desc_hash": good_hash,
                                   "assigned_at": "2026-08-07"}
        self.assertTrue(any("non-empty ordered list" in e for e in errors_of(obj)))

        obj = base()
        obj["assignments"]["a"] = {"categories": ["nope"], "desc_hash": good_hash,
                                   "assigned_at": "2026-08-07"}
        self.assertTrue(any("not in the taxonomy" in e for e in errors_of(obj)))

        obj = base()
        obj["assignments"]["a"] = {"categories": ["eng"], "desc_hash": "sha256:xyz",
                                   "assigned_at": "2026-08-07"}
        self.assertTrue(any("desc_hash must match" in e for e in errors_of(obj)))

        obj = base()
        obj["assignments"]["a"] = {"categories": ["eng"], "desc_hash": good_hash,
                                   "assigned_at": "2026-08-07", "extra": 1}
        self.assertTrue(any("unknown key 'extra'" in e for e in errors_of(obj)))

        obj = base()
        obj["assignments"]["ghost"] = {"categories": ["eng"], "desc_hash": good_hash,
                                       "assigned_at": "2026-08-07"}
        self.assertTrue(any("not a registered skill" in e
                            for e in errors_of(obj, known_ids={"real"})))
        # Same object, no known_ids: environmental drift is not a violation.
        self.assertEqual(errors_of(obj), [])

    def test_failed_write_leaves_file_untouched(self):
        with helpers.EnvSandbox() as _:
            good = {"version": 1, "taxonomy": list(helpers.TAXONOMY), "assignments": {}}
            atlas_categories.write_categories(good)
            before = atlas_paths.categories_path().read_bytes()
            bad = {"version": 99}
            with self.assertRaises(atlas_categories.CategoriesError):
                atlas_categories.write_categories(bad)
            self.assertEqual(atlas_paths.categories_path().read_bytes(), before)

    def test_strict_load_missing_and_invalid(self):
        with helpers.EnvSandbox() as _:
            self.assertEqual(atlas_categories.load_categories_strict(),
                             atlas_categories.empty_categories())
            self.assertEqual(atlas_categories.load_config_strict(),
                             atlas_categories.empty_config())

            atlas_paths.atlas_home().mkdir(parents=True, exist_ok=True)
            atlas_paths.categories_path().write_text("{broken-secret-content")
            with self.assertRaises(atlas_categories.CategoriesError):
                atlas_categories.load_categories_strict()

    def test_config_validation(self):
        errors = atlas_categories.validate_config(
            {"version": 1, "searchable_plugins": ["a", "a"]})
        self.assertTrue(any("duplicate" in e for e in errors))
        errors = atlas_categories.validate_config(
            {"version": 1, "searchable_plugins": "a"})
        self.assertTrue(any("expected a list" in e for e in errors))
        self.assertEqual(atlas_categories.validate_config(
            helpers.searchable_config("beta")), [])


class TestCLI(unittest.TestCase):
    def _bootstrap_payload(self, assigned=None):
        return json.dumps({"taxonomy": helpers.TAXONOMY,
                           "assignments": assigned if assigned is not None
                           else helpers.ASSIGNED_ALL})

    def test_status_requires_graph(self):
        with helpers.EnvSandbox(copy_fixtures=True):
            proc = _cli("status")
            self.assertEqual(proc.returncode, 2)
            self.assertIn("build_graph", proc.stderr)

    def test_bootstrap_lifecycle(self):
        with helpers.EnvSandbox(copy_fixtures=True):
            _build_global()
            status = json.loads(_cli("status").stdout)
            self.assertFalse(status["bootstrapped"])
            self.assertEqual(status["counts"]["skills"], 7)
            self.assertEqual(status["counts"]["uncategorized"], 7)

            proc = _cli("bootstrap", stdin_text=self._bootstrap_payload())
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("bootstrapped: 2 categories", proc.stdout)
            self.assertIn("design target is 8–12", proc.stderr)

            obj = _read_categories()
            self.assertTrue(obj["taxonomy_approved_at"])
            for entry in obj["assignments"].values():
                self.assertRegex(entry["desc_hash"], r"^sha256:[0-9a-f]{64}$")

            status = json.loads(_cli("status", "--full").stdout)
            self.assertTrue(status["bootstrapped"])
            self.assertEqual(status["counts"]["categorized"], 7)
            self.assertEqual(status["counts"]["uncategorized"], 0)
            self.assertEqual(status["counts"]["stale"], 0)
            self.assertEqual(len(status["skills"]), 7)

            # Freeze means freeze.
            proc = _cli("bootstrap", stdin_text=self._bootstrap_payload())
            self.assertEqual(proc.returncode, 3)
            self.assertIn("already bootstrapped", proc.stderr)

    def test_bootstrap_rejects_unknown_id(self):
        with helpers.EnvSandbox(copy_fixtures=True):
            _build_global()
            payload = self._bootstrap_payload({"no-such-skill": ["eng"]})
            proc = _cli("bootstrap", stdin_text=payload)
            self.assertEqual(proc.returncode, 3)
            self.assertIn("no-such-skill", proc.stderr)
            self.assertFalse(atlas_paths.categories_path().exists())

    def test_bootstrap_rejects_partial_coverage(self):
        # Every skill must be categorized — incomplete coverage is an error,
        # not a warning, and nothing is written.
        with helpers.EnvSandbox(copy_fixtures=True):
            _build_global()
            proc = _cli("bootstrap",
                        stdin_text=self._bootstrap_payload(helpers.ASSIGNED))
            self.assertEqual(proc.returncode, 3)
            self.assertIn("must cover every registered skill", proc.stderr)
            self.assertIn("graphify", proc.stderr)
            self.assertFalse(atlas_paths.categories_path().exists())

    def test_assign_flow(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            _build_global()
            proc = _cli("assign",
                        stdin_text=json.dumps({"assignments": {"beta:y": ["eng"]}}))
            self.assertEqual(proc.returncode, 3)
            self.assertIn("not bootstrapped", proc.stderr)

            helpers.write_categories(sandbox, helpers.approved_categories(sandbox))
            before = _read_categories()["assignments"]

            proc = _cli("assign",
                        stdin_text=json.dumps({"assignments": {"beta:y": ["nope"]}}))
            self.assertEqual(proc.returncode, 3)
            self.assertIn("'nope' is not in the taxonomy", proc.stderr)

            proc = _cli("assign",
                        stdin_text=json.dumps({"assignments": {"beta:y": ["eng"]}}))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            after = _read_categories()["assignments"]
            self.assertIn("beta:y", after)
            # No reshuffling: every pre-existing entry byte-identical.
            for skill_id, entry in before.items():
                self.assertEqual(json.dumps(after[skill_id], sort_keys=True),
                                 json.dumps(entry, sort_keys=True))

    def test_confirm_refreshes_stale(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            _build_global()
            obj = helpers.approved_categories(sandbox)
            obj["assignments"]["alpha:one"]["desc_hash"] = \
                atlas_categories.desc_hash("something else entirely")
            helpers.write_categories(sandbox, obj)

            status = json.loads(_cli("status").stdout)
            self.assertEqual([s["id"] for s in status["stale"]], ["alpha:one"])

            proc = _cli("confirm", "alpha:one")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            status = json.loads(_cli("status").stdout)
            self.assertEqual(status["stale"], [])
            self.assertEqual(_read_categories()["assignments"]["alpha:one"]["categories"],
                             ["eng"])

            proc = _cli("confirm", "never-assigned")
            self.assertEqual(proc.returncode, 3)

    def test_add_category_then_assign(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            _build_global()
            helpers.write_categories(sandbox, helpers.approved_categories(sandbox))
            proc = _cli("add-category", "misc", "everything else")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            proc = _cli("assign",
                        stdin_text=json.dumps({"assignments": {"beta:y": ["misc"]}}))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            obj = _read_categories()
            self.assertEqual(len(obj["taxonomy"]), 3)
            self.assertEqual(obj["assignments"]["beta:y"]["categories"], ["misc"])

            proc = _cli("add-category", "misc", "duplicate")
            self.assertEqual(proc.returncode, 3)

    def test_import(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            _build_global()
            helpers.write_categories(sandbox, helpers.approved_categories(sandbox))
            edited = _read_categories()
            edited["taxonomy"].append({"name": "extra", "description": "imported"})
            path = sandbox.tmp / "edited.json"
            path.write_text(json.dumps(edited))

            proc = _cli("import", str(path))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(len(_read_categories()["taxonomy"]), 3)

            before = atlas_paths.categories_path().read_bytes()
            bad = sandbox.tmp / "bad.json"
            bad.write_text(json.dumps({"version": 7}))
            proc = _cli("import", str(bad))
            self.assertEqual(proc.returncode, 3)
            self.assertEqual(atlas_paths.categories_path().read_bytes(), before)

    def test_config_lifecycle(self):
        with helpers.EnvSandbox(copy_fixtures=True):
            _build_global()
            proc = _cli("config", "--add-searchable", "no-such-plugin")
            self.assertEqual(proc.returncode, 3)
            proc = _cli("config", "--add-searchable", "no-such-plugin", "--force")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            proc = _cli("config", "--add-searchable", "beta")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            shown = json.loads(_cli("config", "--show").stdout)
            self.assertEqual(shown["searchable_plugins"], ["no-such-plugin", "beta"])
            proc = _cli("config", "--remove-searchable", "no-such-plugin")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            proc = _cli("config", "--remove-searchable", "no-such-plugin")
            self.assertEqual(proc.returncode, 3)


if __name__ == "__main__":
    unittest.main()
