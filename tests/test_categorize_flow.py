"""M3: the /skill-atlas categorization flow, end to end at the CLI level.

The conversational layer (commands/skill-atlas.md) is validated live; these
tests pin the CLI sequence it drives: bootstrap → rebuild → a new skill
arrives and is assigned into the frozen taxonomy with zero reshuffling →
a description edit goes stale and is confirmed."""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

import helpers
import atlas_paths
import build_graph


def _cli(*args, stdin_text=None, cwd=None):
    neutral = str(Path(os.environ["SKILL_ATLAS_HOME"]).parent)
    return subprocess.run(
        [sys.executable, str(helpers.SCRIPTS / "categorize.py"),
         "--cwd", cwd or neutral, *args],
        input=stdin_text, capture_output=True, text=True, env=os.environ.copy())


def _build():
    return build_graph.main(["--global-only", "--quiet", "--cwd", os.getcwd()])


def _graph():
    return json.loads(atlas_paths.graph_path().read_text(encoding="utf-8"))


def _categories():
    return json.loads(atlas_paths.categories_path().read_text(encoding="utf-8"))


FULL_ASSIGNMENTS = helpers.ASSIGNED_ALL


class TestCategorizationFlow(unittest.TestCase):
    def test_bootstrap_then_incremental_no_reshuffle(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            _build()
            status = json.loads(_cli("status").stdout)
            self.assertFalse(status["bootstrapped"])
            self.assertEqual(status["counts"]["uncategorized"], 7)

            proc = _cli("bootstrap", stdin_text=json.dumps(
                {"taxonomy": helpers.TAXONOMY, "assignments": FULL_ASSIGNMENTS}))
            self.assertEqual(proc.returncode, 0, proc.stderr)

            _build()
            graph = _graph()
            self.assertEqual(graph["stats"]["uncategorized"], 0)
            node = next(n for n in graph["nodes"] if n["id"] == "alpha:two")
            self.assertEqual(node["categories"], ["eng", "docs"])

            # A new skill arrives: visibly uncategorized, nothing reshuffled.
            snapshot = _categories()
            newbie = sandbox.claude / "skills" / "newbie"
            newbie.mkdir()
            (newbie / "SKILL.md").write_text(
                "---\nname: newbie\ndescription: freshly installed\n---\nbody\n")
            _build()
            status = json.loads(_cli("status").stdout)
            self.assertTrue(status["bootstrapped"])
            self.assertEqual([u["id"] for u in status["uncategorized"]], ["newbie"])

            proc = _cli("assign",
                        stdin_text=json.dumps({"assignments": {"newbie": ["eng"]}}))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            after = _categories()
            self.assertEqual(set(after["assignments"]) - set(snapshot["assignments"]),
                             {"newbie"})
            self.assertEqual(after["taxonomy"], snapshot["taxonomy"])
            self.assertEqual(after["taxonomy_approved_at"],
                             snapshot["taxonomy_approved_at"])
            for skill_id, entry in snapshot["assignments"].items():
                self.assertEqual(json.dumps(after["assignments"][skill_id],
                                            sort_keys=True),
                                 json.dumps(entry, sort_keys=True))

    def test_project_skills_categorized(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            build_graph.main(["--cwd", str(sandbox.project_dir), "--quiet"])
            proc = _cli("bootstrap", stdin_text=json.dumps(
                {"taxonomy": helpers.TAXONOMY, "assignments": FULL_ASSIGNMENTS}))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            build_graph.main(["--cwd", str(sandbox.project_dir), "--quiet"])

            # The project view renames the colliding graphify pair and adds
            # the project skill — both variants surface as uncategorized
            # there, and the shadowed bare-name assignment is NOT an orphan.
            status = json.loads(
                _cli("status", cwd=str(sandbox.project_dir)).stdout)
            self.assertEqual(status["view"], "project")
            self.assertEqual([u["id"] for u in status["uncategorized"]],
                             ["graphify@project", "graphify@user"])
            self.assertEqual(status["orphan_assignments"], [])

            proc = _cli("assign", cwd=str(sandbox.project_dir),
                        stdin_text=json.dumps({"assignments": {
                            "graphify@project": ["docs"],
                            "graphify@user": ["docs"]}}))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            obj = _categories()
            self.assertIs(obj["assignments"]["graphify@project"]["project"], True)
            self.assertIs(obj["assignments"]["graphify@user"]["project"], True)

            build_graph.main(["--cwd", str(sandbox.project_dir), "--quiet"])
            project_graph = json.loads(
                atlas_paths.project_graph_path(sandbox.project_dir).read_text())
            self.assertEqual(project_graph["stats"]["uncategorized"], 0)
            self.assertEqual(project_graph["stats"]["orphan_assignments"], [])
            node = next(n for n in project_graph["nodes"]
                        if n["id"] == "graphify@project")
            self.assertEqual(node["categories"], ["docs"])
            # View-local entries are not orphans in the global view either.
            global_graph = _graph()
            self.assertEqual(global_graph["stats"]["orphan_assignments"], [])
            self.assertEqual(global_graph["stats"]["uncategorized"], 0)

    def test_description_edit_goes_stale_then_confirmed(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            _build()
            proc = _cli("bootstrap", stdin_text=json.dumps(
                {"taxonomy": helpers.TAXONOMY, "assignments": FULL_ASSIGNMENTS}))
            self.assertEqual(proc.returncode, 0, proc.stderr)

            one = (sandbox.claude / "plugins" / "cache" / "fake-mp" / "alpha"
                   / "1.0.0" / "skills" / "eng" / "one" / "SKILL.md")
            one.write_text("---\nname: one\ndescription: totally reworded\n---\nbody\n")
            _build()

            graph = _graph()
            node = next(n for n in graph["nodes"] if n["id"] == "alpha:one")
            self.assertTrue(node["category_stale"])
            self.assertEqual(node["categories"], ["eng"])  # labels stay in effect
            status = json.loads(_cli("status").stdout)
            self.assertEqual([s["id"] for s in status["stale"]], ["alpha:one"])

            proc = _cli("confirm", "alpha:one")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            _build()
            node = next(n for n in _graph()["nodes"] if n["id"] == "alpha:one")
            self.assertFalse(node["category_stale"])
            self.assertEqual(node["categories"], ["eng"])


if __name__ == "__main__":
    unittest.main()
