import json
import os
import subprocess
import sys
import unittest

import helpers
import atlas_paths

CHECK_STALE = str(helpers.SCRIPTS / "check_stale.py")
MARK_DIRTY = str(helpers.SCRIPTS / "mark_dirty.py")


def _run(script, cwd, stdin_data=None):
    return subprocess.run(
        [sys.executable, script], cwd=cwd, input=stdin_data,
        env=os.environ.copy(), capture_output=True, text=True, timeout=30)


class TestCheckStale(unittest.TestCase):
    def test_builds_when_no_graph_exists(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            result = _run(CHECK_STALE, sandbox.project_dir)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertTrue(atlas_paths.graph_path().exists())

    def test_fresh_graph_not_rebuilt(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            _run(CHECK_STALE, sandbox.project_dir)
            before = atlas_paths.graph_path().stat().st_mtime_ns
            result = _run(CHECK_STALE, sandbox.project_dir)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(atlas_paths.graph_path().stat().st_mtime_ns, before)

    def test_settings_toggle_triggers_rebuild(self):
        # The M4 property: enabledPlugins changes touch no SKILL.md but must
        # rebuild on next session start, unprompted.
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            _run(CHECK_STALE, sandbox.project_dir)
            before = atlas_paths.graph_path().stat().st_mtime_ns
            settings = sandbox.claude / "settings.json"
            settings.write_text(settings.read_text().replace(
                '"alpha@fake-mp": true', '"alpha@fake-mp": false'))
            result = _run(CHECK_STALE, sandbox.project_dir)
            self.assertEqual(result.returncode, 0)
            self.assertGreater(atlas_paths.graph_path().stat().st_mtime_ns, before)
            graph = json.loads(atlas_paths.graph_path().read_text())
            alpha_one = next(n for n in graph["nodes"] if n["id"] == "alpha:one")
            self.assertFalse(alpha_one["enabled"])

    def test_dirty_flag_consumed(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            _run(CHECK_STALE, sandbox.project_dir)
            atlas_paths.dirty_path().touch()
            before = atlas_paths.graph_path().stat().st_mtime_ns
            _run(CHECK_STALE, sandbox.project_dir)
            self.assertFalse(atlas_paths.dirty_path().exists())
            self.assertGreater(atlas_paths.graph_path().stat().st_mtime_ns, before)

    def test_autobuild_off_does_nothing(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            os.environ["SKILL_ATLAS_AUTOBUILD"] = "0"
            result = _run(CHECK_STALE, sandbox.project_dir)
            self.assertEqual(result.returncode, 0)
            self.assertFalse(atlas_paths.graph_path().exists())

    def test_config_edit_alone_triggers_rebuild(self):
        # The M2 done-when: editing config.json touches no SKILL.md and no
        # manifest, but must rebuild on next session start.
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            _run(CHECK_STALE, sandbox.project_dir)
            before = atlas_paths.graph_path().stat().st_mtime_ns
            helpers.write_config(sandbox, helpers.searchable_config("beta"))
            result = _run(CHECK_STALE, sandbox.project_dir)
            self.assertEqual(result.returncode, 0)
            self.assertGreater(atlas_paths.graph_path().stat().st_mtime_ns, before)
            graph = json.loads(atlas_paths.graph_path().read_text())
            beta = next(n for n in graph["nodes"] if n["id"] == "beta:x")
            self.assertTrue(beta["searchable"])

    def test_invalid_categories_never_breaks_session(self):
        # Fail-loud is the explicit build's job; the hook swallows, keeps
        # the last-good graph, and the session proceeds.
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            _run(CHECK_STALE, sandbox.project_dir)
            atlas_paths.categories_path().write_text("{broken")
            result = _run(CHECK_STALE, sandbox.project_dir)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertTrue(atlas_paths.graph_path().exists())

    def test_broken_environment_still_exits_0_silently(self):
        with helpers.EnvSandbox() as sandbox:
            (sandbox.claude / "plugins").mkdir()
            (sandbox.claude / "plugins" / "installed_plugins.json").write_text("{broken")
            result = _run(CHECK_STALE, sandbox.tmp)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")


class TestCheckStaleProjectView(unittest.TestCase):
    def test_project_artifacts_built_on_session_start(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            result = _run(CHECK_STALE, sandbox.project_dir)
            self.assertEqual(result.returncode, 0)
            self.assertTrue(atlas_paths.graph_path().exists())
            project_graph = atlas_paths.project_graph_path(sandbox.project_dir)
            self.assertTrue(project_graph.exists())
            self.assertEqual(json.loads(project_graph.read_text())["view"], "project")

    def test_project_settings_edit_rebuilds_project_only(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            _run(CHECK_STALE, sandbox.project_dir)
            project_graph = atlas_paths.project_graph_path(sandbox.project_dir)
            global_before = atlas_paths.graph_path().stat().st_mtime_ns
            project_before = project_graph.stat().st_mtime_ns
            (sandbox.project_dir / ".claude" / "settings.local.json").write_text(
                json.dumps({"enabledPlugins": {"beta@fake-mp": True}}))
            _run(CHECK_STALE, sandbox.project_dir)
            # Project settings are outside the global fingerprint's scope.
            self.assertEqual(atlas_paths.graph_path().stat().st_mtime_ns, global_before)
            self.assertGreater(project_graph.stat().st_mtime_ns, project_before)
            rebuilt = json.loads(project_graph.read_text())
            beta = next(n for n in rebuilt["nodes"] if n["id"] == "beta:x")
            self.assertTrue(beta["enabled"])

    def test_non_project_cwd_gets_no_files(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            plain_dir = sandbox.tmp / "not-a-project"
            plain_dir.mkdir()
            result = _run(CHECK_STALE, plain_dir)
            self.assertEqual(result.returncode, 0)
            self.assertTrue(atlas_paths.graph_path().exists())
            self.assertFalse((plain_dir / ".claude").exists())


class TestIndexLine(unittest.TestCase):
    """M5: the one stdout line check_stale may emit — the documented
    SessionStart JSON contract, only when the dormant tier is nonempty.
    (The stdout == "" assertions elsewhere in this file are sandboxes with
    no config.json: dormant == 0, silent by design.)"""

    def test_line_present_with_dormant_tier(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            helpers.write_categories(sandbox, helpers.approved_categories())
            helpers.write_config(sandbox, helpers.searchable_config("beta"))
            result = _run(CHECK_STALE, sandbox.tmp)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stderr, "")
            payload = json.loads(result.stdout)
            self.assertEqual(payload["hookSpecificOutput"]["hookEventName"],
                             "SessionStart")
            line = payload["hookSpecificOutput"]["additionalContext"]
            self.assertIn("2 dormant skills", line)
            self.assertIn("eng(3)", line)
            self.assertIn("3 uncategorized", line)  # graphify, linked-skill, beta:y
            self.assertIn("Run /skill-atlas to categorize.", line)
            self.assertIn("skill-search", line)
            self.assertLessEqual(len(line), 240)  # ≈ the ~50-token target

    def test_no_nag_when_fully_categorized(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            assigned = dict(helpers.ASSIGNED)
            assigned.update({"graphify": ["docs"], "linked-skill": ["eng"],
                             "beta:y": ["eng"]})
            helpers.write_categories(
                sandbox, helpers.approved_categories(assigned=assigned))
            helpers.write_config(sandbox, helpers.searchable_config("beta"))
            result = _run(CHECK_STALE, sandbox.tmp)
            line = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
            self.assertNotIn("uncategorized", line)
            self.assertNotIn("/skill-atlas", line)

    def test_silent_when_nothing_dormant(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            helpers.write_categories(sandbox, helpers.approved_categories())
            # No config: categorized but nothing searchable → no line.
            result = _run(CHECK_STALE, sandbox.tmp)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")

    def test_autobuild_off_stays_silent(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            helpers.write_config(sandbox, helpers.searchable_config("beta"))
            os.environ["SKILL_ATLAS_AUTOBUILD"] = "0"
            result = _run(CHECK_STALE, sandbox.tmp)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")


class TestMarkDirty(unittest.TestCase):
    def _payload(self, path):
        return json.dumps({"tool_name": "Write", "tool_input": {"file_path": path}})

    def test_skill_edit_sets_marker(self):
        with helpers.EnvSandbox() as sandbox:
            result = _run(MARK_DIRTY, sandbox.tmp,
                          self._payload("/some/plugin/skills/tdd/SKILL.md"))
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertTrue(atlas_paths.dirty_path().exists())

    def test_manifest_edit_sets_marker(self):
        # §5.2: manifest paths are as load-bearing as skill paths.
        for path in ("/home/u/.claude/settings.json",
                     "/repo/.claude-plugin/plugin.json",
                     "/home/u/.claude/plugins/installed_plugins.json"):
            with helpers.EnvSandbox() as sandbox:
                _run(MARK_DIRTY, sandbox.tmp, self._payload(path))
                self.assertTrue(atlas_paths.dirty_path().exists(), path)

    def test_curated_state_edit_sets_marker(self):
        for path in ("/home/u/.claude/skill-atlas/categories.json",
                     "/home/u/.claude/skill-atlas/config.json"):
            with helpers.EnvSandbox() as sandbox:
                _run(MARK_DIRTY, sandbox.tmp, self._payload(path))
                self.assertTrue(atlas_paths.dirty_path().exists(), path)

    def test_unrelated_edit_ignored(self):
        with helpers.EnvSandbox() as sandbox:
            _run(MARK_DIRTY, sandbox.tmp, self._payload("/repo/src/main.py"))
            self.assertFalse(atlas_paths.dirty_path().exists())

    def test_garbage_stdin_exits_0(self):
        with helpers.EnvSandbox() as sandbox:
            result = _run(MARK_DIRTY, sandbox.tmp, "not json at all")
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
