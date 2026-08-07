import json
import os
import unittest
from pathlib import Path

import helpers  # noqa: F401  (sys.path setup)
import atlas_io
import atlas_paths


class TestEnvAndDefaults(unittest.TestCase):
    def test_env_overrides_and_defaults(self):
        with helpers.EnvSandbox() as sandbox:
            self.assertEqual(atlas_paths.claude_dir(), sandbox.claude)
            self.assertEqual(atlas_paths.atlas_home(), sandbox.tmp / "atlas-home")
            # Defaults derive from claude_dir when the env vars are unset.
            os.environ.pop("SKILL_ATLAS_HOME")
            self.assertEqual(atlas_paths.atlas_home(), sandbox.claude / "skill-atlas")
            self.assertTrue(atlas_paths.autobuild_enabled())
            os.environ["SKILL_ATLAS_AUTOBUILD"] = "0"
            self.assertFalse(atlas_paths.autobuild_enabled())


class TestSettingsMerge(unittest.TestCase):
    def test_precedence_project_local_wins(self):
        with helpers.EnvSandbox() as sandbox:
            project = sandbox.tmp / "someproject"
            (project / ".claude").mkdir(parents=True)
            write = lambda p, ep: p.write_text(json.dumps({"enabledPlugins": ep}))
            write(sandbox.claude / "settings.json", {"a@mp": True, "b@mp": True})
            write(sandbox.claude / "settings.local.json", {"b@mp": False})
            write(project / ".claude" / "settings.json", {"c@mp": False})
            write(project / ".claude" / "settings.local.json", {"c@mp": True})

            merged = atlas_paths.merged_enabled_plugins(cwd=project)
            self.assertEqual(merged, {"a@mp": True, "b@mp": False, "c@mp": True})
            # Without cwd, project layers don't apply.
            merged_user = atlas_paths.merged_enabled_plugins()
            self.assertEqual(merged_user, {"a@mp": True, "b@mp": False})

    def test_missing_and_malformed_files_skipped(self):
        with helpers.EnvSandbox() as sandbox:
            (sandbox.claude / "settings.json").write_text("{not json")
            self.assertEqual(atlas_paths.merged_enabled_plugins(), {})


class TestInstalledPlugins(unittest.TestCase):
    def _write_manifest(self, sandbox, plugins):
        path = sandbox.claude / "plugins" / "installed_plugins.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": 2, "plugins": plugins}))

    def test_array_records_and_scope_preference(self):
        with helpers.EnvSandbox() as sandbox:
            self._write_manifest(sandbox, {
                "alpha@fake-mp": [
                    {"scope": "user", "installPath": "/x/alpha/1.0.0", "version": "1.0.0"},
                    {"scope": "project", "installPath": "/y/alpha/1.1.0", "version": "1.1.0"},
                ],
                "beta@fake-mp": [
                    {"scope": "user", "installPath": "/x/beta/unknown", "version": "unknown"},
                ],
                # A hypothetical single-record (dict) shape must be tolerated.
                "gamma@fake-mp": {"scope": "user", "installPath": "/x/gamma/2.0"},
                # Records without installPath are unusable and skipped.
                "broken@fake-mp": [{"scope": "user"}],
            })
            records = {r["key"]: r for r in atlas_paths.installed_plugins()}
            self.assertEqual(set(records), {"alpha@fake-mp", "beta@fake-mp", "gamma@fake-mp"})
            alpha = records["alpha@fake-mp"]
            self.assertEqual(alpha["install_path"], Path("/y/alpha/1.1.0"))  # project preferred
            self.assertEqual(alpha["install_records"], 2)
            self.assertEqual(alpha["name"], "alpha")
            self.assertEqual(alpha["marketplace"], "fake-mp")
            self.assertEqual(records["beta@fake-mp"]["version"], "unknown")  # opaque, unparsed

    def test_manifest_paths_include_settings_and_plugin_manifests(self):
        with helpers.EnvSandbox() as sandbox:
            self._write_manifest(sandbox, {
                "alpha@fake-mp": [{"scope": "user", "installPath": "/x/alpha/1.0.0"}],
            })
            paths = atlas_paths.manifest_paths(cwd="/some/project")
            self.assertIn(atlas_paths.installed_plugins_path(), paths)
            self.assertIn(sandbox.claude / "settings.json", paths)
            self.assertIn(sandbox.claude / "settings.local.json", paths)
            self.assertIn(Path("/some/project/.claude/settings.json"), paths)
            self.assertIn(Path("/x/alpha/1.0.0/.claude-plugin/plugin.json"), paths)


class TestProjectPaths(unittest.TestCase):
    def test_is_project(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            self.assertTrue(atlas_paths.is_project(sandbox.project_dir))
            self.assertFalse(atlas_paths.is_project(sandbox.tmp))  # no .claude/
            self.assertFalse(atlas_paths.is_project(None))
            # A cwd whose .claude IS the user-level dir (i.e. running from ~)
            # must not count as a project — it would double-count user skills.
            fake_home = sandbox.tmp / "fake-home"
            fake_home.mkdir()
            (fake_home / ".claude").symlink_to(sandbox.claude, target_is_directory=True)
            self.assertFalse(atlas_paths.is_project(fake_home))

    def test_project_artifact_paths(self):
        home = atlas_paths.project_home("/x/proj")
        self.assertEqual(home, Path("/x/proj/.claude/skill-atlas"))
        self.assertEqual(atlas_paths.project_graph_path("/x/proj"),
                         home / "graph.json")
        self.assertEqual(atlas_paths.project_atlas_path("/x/proj"),
                         home / "atlas.html")


class TestAtomicIO(unittest.TestCase):
    def test_atomic_write_json_no_leftovers(self):
        with helpers.EnvSandbox():
            target = atlas_paths.atlas_home() / "graph.json"
            atlas_io.atomic_write_json(target, {"b": 1, "a": [1, 2]})
            data = json.loads(target.read_text())
            self.assertEqual(data, {"b": 1, "a": [1, 2]})
            leftovers = [p for p in target.parent.iterdir() if p.suffix == ".tmp"]
            self.assertEqual(leftovers, [])

    def test_debug_log_records_type_name_only(self):
        with helpers.EnvSandbox():
            try:
                json.loads("CANARY_SECRET_XYZ this is parsed file content")
            except json.JSONDecodeError as exc:
                atlas_io.debug_log("test", "/some/file.jsonl", 7, exc)
            content = atlas_paths.debug_log_path().read_text()
            self.assertIn("JSONDecodeError", content)
            self.assertIn("/some/file.jsonl:7", content)
            self.assertNotIn("CANARY_SECRET_XYZ", content)


if __name__ == "__main__":
    unittest.main()
