import os
import time
import unittest

import helpers
import atlas_discovery
import atlas_fingerprint
import atlas_paths


def _fingerprint(sandbox):
    paths = atlas_discovery.skill_md_paths(cwd=sandbox.project_dir)
    return atlas_fingerprint.compute(paths, atlas_paths.manifest_paths(sandbox.project_dir))


def _bump_mtime(path):
    stat = os.stat(path)
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))


class TestFingerprint(unittest.TestCase):
    def test_stable_when_nothing_changes(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            self.assertEqual(_fingerprint(sandbox), _fingerprint(sandbox))

    def test_changes_on_skill_edit(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            before = _fingerprint(sandbox)
            _bump_mtime(sandbox.claude / "skills" / "plain-skill" / "SKILL.md")
            self.assertNotEqual(before, _fingerprint(sandbox))

    def test_changes_on_settings_change(self):
        # The §5.1 requirement: toggling enabledPlugins touches no SKILL.md
        # but must still flip the fingerprint.
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            before = _fingerprint(sandbox)
            settings = sandbox.claude / "settings.json"
            settings.write_text(settings.read_text().replace(
                '"beta@fake-mp": true', '"beta@fake-mp": false'))
            self.assertNotEqual(before, _fingerprint(sandbox))

    def test_changes_on_plugin_manifest_change(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            before = _fingerprint(sandbox)
            manifest = (sandbox.claude / "plugins" / "cache" / "fake-mp" / "alpha"
                        / "1.0.0" / ".claude-plugin" / "plugin.json")
            _bump_mtime(manifest)
            self.assertNotEqual(before, _fingerprint(sandbox))

    def test_changes_when_missing_settings_local_appears(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            local = sandbox.claude / "settings.local.json"
            local.unlink()
            before = _fingerprint(sandbox)
            local.write_text("{}")
            self.assertNotEqual(before, _fingerprint(sandbox))

    def test_deadline_abort_returns_none(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            paths = atlas_discovery.skill_md_paths(cwd=sandbox.project_dir)
            result = atlas_fingerprint.compute(
                paths, atlas_paths.manifest_paths(sandbox.project_dir),
                deadline=time.monotonic() - 1)
            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
