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


def _init(base):
    """Simulate a prior explicit run: the hooks only operate where
    .claude/skill-atlas already exists."""
    helpers.atlas_dir(base).mkdir(parents=True, exist_ok=True)


def _graph_file(base):
    return helpers.atlas_dir(base) / "graph.json"


class TestCheckStale(unittest.TestCase):
    def test_uninitialized_dir_stays_inert(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            result = _run(CHECK_STALE, sandbox.project_dir)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertFalse(helpers.atlas_dir(sandbox.project_dir).exists())

    def test_builds_when_initialized_but_no_graph(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            _init(sandbox.project_dir)
            result = _run(CHECK_STALE, sandbox.project_dir)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertTrue(_graph_file(sandbox.project_dir).exists())

    def test_fresh_graph_not_rebuilt(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            _init(sandbox.project_dir)
            _run(CHECK_STALE, sandbox.project_dir)
            before = _graph_file(sandbox.project_dir).stat().st_mtime_ns
            result = _run(CHECK_STALE, sandbox.project_dir)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(_graph_file(sandbox.project_dir).stat().st_mtime_ns,
                             before)

    def test_settings_toggle_triggers_rebuild(self):
        # enabledPlugins changes touch no SKILL.md but must rebuild on next
        # session start, unprompted.
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            _init(sandbox.project_dir)
            _run(CHECK_STALE, sandbox.project_dir)
            before = _graph_file(sandbox.project_dir).stat().st_mtime_ns
            settings = sandbox.claude / "settings.json"
            settings.write_text(settings.read_text().replace(
                '"alpha@fake-mp": true', '"alpha@fake-mp": false'))
            result = _run(CHECK_STALE, sandbox.project_dir)
            self.assertEqual(result.returncode, 0)
            self.assertGreater(_graph_file(sandbox.project_dir).stat().st_mtime_ns,
                               before)
            graph = json.loads(_graph_file(sandbox.project_dir).read_text())
            alpha_one = next(n for n in graph["nodes"] if n["id"] == "alpha:one")
            self.assertFalse(alpha_one["enabled"])

    def test_config_edit_alone_triggers_rebuild(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            _init(sandbox.project_dir)
            _run(CHECK_STALE, sandbox.project_dir)
            before = _graph_file(sandbox.project_dir).stat().st_mtime_ns
            helpers.write_config(sandbox, helpers.searchable_config("beta"),
                                 cwd=sandbox.project_dir)
            result = _run(CHECK_STALE, sandbox.project_dir)
            self.assertEqual(result.returncode, 0)
            self.assertGreater(_graph_file(sandbox.project_dir).stat().st_mtime_ns,
                               before)
            graph = json.loads(_graph_file(sandbox.project_dir).read_text())
            beta = next(n for n in graph["nodes"] if n["id"] == "beta:x")
            self.assertTrue(beta["searchable"])

    def test_scopes_are_independent(self):
        # A rebuild in one directory never touches another's artifacts.
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            neutral = sandbox.tmp / "neutral"
            neutral.mkdir()
            _init(neutral)
            _init(sandbox.project_dir)
            _run(CHECK_STALE, neutral)
            _run(CHECK_STALE, sandbox.project_dir)
            neutral_before = _graph_file(neutral).stat().st_mtime_ns
            (sandbox.project_dir / ".claude" / "settings.local.json").write_text(
                json.dumps({"enabledPlugins": {"beta@fake-mp": True}}))
            _run(CHECK_STALE, sandbox.project_dir)
            _run(CHECK_STALE, neutral)
            # The project scope rebuilt; the neutral scope (whose fingerprint
            # never covered the project's settings) did not.
            rebuilt = json.loads(_graph_file(sandbox.project_dir).read_text())
            beta = next(n for n in rebuilt["nodes"] if n["id"] == "beta:x")
            self.assertTrue(beta["enabled"])
            self.assertEqual(_graph_file(neutral).stat().st_mtime_ns,
                             neutral_before)

    def test_dirty_flag_consumed(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            _init(sandbox.project_dir)
            _run(CHECK_STALE, sandbox.project_dir)
            marker = helpers.atlas_dir(sandbox.project_dir) / "graph.dirty"
            marker.touch()
            before = _graph_file(sandbox.project_dir).stat().st_mtime_ns
            _run(CHECK_STALE, sandbox.project_dir)
            self.assertFalse(marker.exists())
            self.assertGreater(_graph_file(sandbox.project_dir).stat().st_mtime_ns,
                               before)

    def test_autobuild_off_does_nothing(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            _init(sandbox.project_dir)
            os.environ["SKILL_ATLAS_AUTOBUILD"] = "0"
            result = _run(CHECK_STALE, sandbox.project_dir)
            self.assertEqual(result.returncode, 0)
            self.assertFalse(_graph_file(sandbox.project_dir).exists())

    def test_broken_environment_still_exits_0_silently(self):
        with helpers.EnvSandbox() as sandbox:
            (sandbox.claude / "plugins").mkdir()
            (sandbox.claude / "plugins" / "installed_plugins.json").write_text("{broken")
            _init(sandbox.tmp)
            result = _run(CHECK_STALE, sandbox.tmp)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")

    def test_invalid_categories_never_breaks_session(self):
        # Fail-loud is the explicit build's job; the hook swallows, keeps
        # the last-good graph, and the session proceeds.
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            _init(sandbox.project_dir)
            _run(CHECK_STALE, sandbox.project_dir)
            (helpers.atlas_dir(sandbox.project_dir) / "categories.json").write_text("{broken")
            result = _run(CHECK_STALE, sandbox.project_dir)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertTrue(_graph_file(sandbox.project_dir).exists())


class TestIndexLine(unittest.TestCase):
    """M5: the one stdout line check_stale may emit — the documented
    SessionStart JSON contract, only when the dormant tier is nonempty."""

    def test_line_present_with_dormant_tier(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            helpers.write_categories(
                sandbox, helpers.approved_categories(sandbox, cwd=sandbox.project_dir),
                cwd=sandbox.project_dir)
            helpers.write_config(sandbox, helpers.searchable_config("beta"),
                                 cwd=sandbox.project_dir)
            result = _run(CHECK_STALE, sandbox.project_dir)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stderr, "")
            payload = json.loads(result.stdout)
            self.assertEqual(payload["hookSpecificOutput"]["hookEventName"],
                             "SessionStart")
            line = payload["hookSpecificOutput"]["additionalContext"]
            self.assertIn("2 dormant skills", line)
            self.assertIn("eng(3)", line)
            self.assertIn("uncategorized", line)
            self.assertIn("Run /skill-atlas to categorize.", line)
            self.assertIn("skill-search", line)
            self.assertLessEqual(len(line), 240)  # ≈ the ~50-token target

    def test_no_nag_when_fully_categorized(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            assigned = dict(helpers.ASSIGNED)
            assigned.update({"graphify@user": ["docs"], "graphify@project": ["docs"],
                             "linked-skill": ["eng"], "beta:y": ["eng"]})
            helpers.write_categories(
                sandbox,
                helpers.approved_categories(sandbox, cwd=sandbox.project_dir,
                                            assigned=assigned),
                cwd=sandbox.project_dir)
            helpers.write_config(sandbox, helpers.searchable_config("beta"),
                                 cwd=sandbox.project_dir)
            result = _run(CHECK_STALE, sandbox.project_dir)
            line = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
            self.assertNotIn("uncategorized", line)
            self.assertNotIn("/skill-atlas", line)

    def test_silent_when_nothing_dormant(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            helpers.write_categories(
                sandbox, helpers.approved_categories(sandbox, cwd=sandbox.project_dir),
                cwd=sandbox.project_dir)
            # No config: categorized but nothing searchable → no line.
            result = _run(CHECK_STALE, sandbox.project_dir)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")

    def test_autobuild_off_stays_silent(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            helpers.write_config(sandbox, helpers.searchable_config("beta"),
                                 cwd=sandbox.project_dir)
            os.environ["SKILL_ATLAS_AUTOBUILD"] = "0"
            result = _run(CHECK_STALE, sandbox.project_dir)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")


class TestMarkDirty(unittest.TestCase):
    def _payload(self, path):
        return json.dumps({"tool_name": "Write", "tool_input": {"file_path": path}})

    def test_skill_edit_sets_marker(self):
        with helpers.EnvSandbox() as sandbox:
            _init(sandbox.tmp)
            result = _run(MARK_DIRTY, sandbox.tmp,
                          self._payload("/some/plugin/skills/tdd/SKILL.md"))
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertTrue((helpers.atlas_dir(sandbox.tmp) / "graph.dirty").exists())

    def test_manifest_edit_sets_marker(self):
        # §5.2: manifest paths are as load-bearing as skill paths.
        for path in ("/home/u/.claude/settings.json",
                     "/repo/.claude-plugin/plugin.json",
                     "/home/u/.claude/plugins/installed_plugins.json"):
            with helpers.EnvSandbox() as sandbox:
                _init(sandbox.tmp)
                _run(MARK_DIRTY, sandbox.tmp, self._payload(path))
                self.assertTrue(
                    (helpers.atlas_dir(sandbox.tmp) / "graph.dirty").exists(), path)

    def test_curated_state_edit_sets_marker(self):
        for path in ("/home/u/.claude/skill-atlas/categories.json",
                     "/some/proj/.claude/skill-atlas/config.json"):
            with helpers.EnvSandbox() as sandbox:
                _init(sandbox.tmp)
                _run(MARK_DIRTY, sandbox.tmp, self._payload(path))
                self.assertTrue(
                    (helpers.atlas_dir(sandbox.tmp) / "graph.dirty").exists(), path)

    def test_uninitialized_scope_gets_no_marker(self):
        with helpers.EnvSandbox() as sandbox:
            result = _run(MARK_DIRTY, sandbox.tmp,
                          self._payload("/some/plugin/skills/tdd/SKILL.md"))
            self.assertEqual(result.returncode, 0)
            self.assertFalse(helpers.atlas_dir(sandbox.tmp).exists())

    def test_unrelated_edit_ignored(self):
        with helpers.EnvSandbox() as sandbox:
            _init(sandbox.tmp)
            _run(MARK_DIRTY, sandbox.tmp, self._payload("/repo/src/main.py"))
            self.assertFalse((helpers.atlas_dir(sandbox.tmp) / "graph.dirty").exists())

    def test_garbage_stdin_exits_0(self):
        with helpers.EnvSandbox() as sandbox:
            _init(sandbox.tmp)
            result = _run(MARK_DIRTY, sandbox.tmp, "not json at all")
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
