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
            # Artifacts always live in the .claude/skill-atlas of the scope
            # (the sandbox points the scope at its neutral tmp dir).
            self.assertEqual(atlas_paths.atlas_home(),
                             sandbox.tmp / ".claude" / "skill-atlas")
            atlas_paths.set_scope("/x/proj")
            self.assertEqual(atlas_paths.atlas_home(),
                             Path("/x/proj/.claude/skill-atlas"))
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

            atlas_paths.set_scope(project)
            merged = atlas_paths.merged_enabled_plugins()
            self.assertEqual(merged, {"a@mp": True, "b@mp": False, "c@mp": True})
            # A scope without its own .claude: project layers don't apply.
            atlas_paths.set_scope(sandbox.tmp)
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
            project = sandbox.tmp / "someproject"
            (project / ".claude").mkdir(parents=True)
            atlas_paths.set_scope(project)
            paths = atlas_paths.manifest_paths()
            self.assertIn(atlas_paths.installed_plugins_path(), paths)
            self.assertIn(sandbox.claude / "settings.json", paths)
            self.assertIn(sandbox.claude / "settings.local.json", paths)
            self.assertIn(project / ".claude" / "settings.json", paths)
            self.assertIn(Path("/x/alpha/1.0.0/.claude-plugin/plugin.json"), paths)
            # Phase 2 build inputs join the fingerprint (DESIGN-PHASE2 §3.3):
            # this scope's own curated categories.json + config.json.
            self.assertIn(project / ".claude" / "skill-atlas" / "categories.json",
                          paths)
            self.assertIn(project / ".claude" / "skill-atlas" / "config.json",
                          paths)


class TestScopePaths(unittest.TestCase):
    def test_has_local_skills_root(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            atlas_paths.set_scope(sandbox.project_dir)
            self.assertTrue(atlas_paths.has_local_skills_root())
            atlas_paths.set_scope(sandbox.tmp)   # no .claude/ of its own
            self.assertFalse(atlas_paths.has_local_skills_root())
            # A scope whose .claude IS the user-level dir (i.e. running from
            # ~) must not double-count user skills as project skills.
            fake_home = sandbox.tmp / "fake-home"
            fake_home.mkdir()
            (fake_home / ".claude").symlink_to(sandbox.claude, target_is_directory=True)
            atlas_paths.set_scope(fake_home)
            self.assertFalse(atlas_paths.has_local_skills_root())

    def test_artifact_paths_under_scope(self):
        with helpers.EnvSandbox():
            atlas_paths.set_scope("/x/proj")
            home = Path("/x/proj/.claude/skill-atlas")
            self.assertEqual(atlas_paths.atlas_home(), home)
            self.assertEqual(atlas_paths.graph_path(), home / "graph.json")
            self.assertEqual(atlas_paths.atlas_path(), home / "atlas.html")
            self.assertEqual(atlas_paths.categories_path(), home / "categories.json")
            self.assertEqual(atlas_paths.config_path(), home / "config.json")
            self.assertEqual(atlas_paths.catalog_dir(), home / "catalog")
            self.assertEqual(atlas_paths.catalog_index_path(),
                             home / "catalog" / "_index.md")


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
            atlas_paths.atlas_home().mkdir(parents=True)
            try:
                json.loads("CANARY_SECRET_XYZ this is parsed file content")
            except json.JSONDecodeError as exc:
                atlas_io.debug_log("test", "/some/file.jsonl", 7, exc)
            content = atlas_paths.debug_log_path().read_text()
            self.assertIn("JSONDecodeError", content)
            self.assertIn("/some/file.jsonl:7", content)
            self.assertNotIn("CANARY_SECRET_XYZ", content)

    def test_debug_log_never_initializes_a_scope(self):
        # A failed run in an untouched directory must not create the atlas
        # dir just to log into it — that would arm the SessionStart hook.
        with helpers.EnvSandbox():
            atlas_io.debug_log("test", "/some/file", 0, ValueError())
            self.assertFalse(atlas_paths.atlas_home().exists())


if __name__ == "__main__":
    unittest.main()
