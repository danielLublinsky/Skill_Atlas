import unittest

import helpers
import atlas_discovery
import atlas_paths


class TestDiscovery(unittest.TestCase):
    def _discover(self, sandbox, **kwargs):
        atlas_paths.set_scope(sandbox.project_dir)
        return atlas_discovery.discover(**kwargs)

    def test_registered_set_exact(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            result = self._discover(sandbox)
            ids = sorted(s["id"] for s in result["skills"])
            self.assertEqual(ids, [
                "alpha:one", "alpha:two", "beta:x", "beta:y",
                "graphify@project", "graphify@user",
                "linked-skill", "plain-skill",
            ])

    def test_stale_versions_and_marketplace_excluded(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            result = self._discover(sandbox)
            all_paths = [s["path"] for s in result["skills"] + result["unregistered"]]
            self.assertFalse(any("/0.9.0/" in p for p in all_paths),
                             "stale cached version was walked")
            self.assertFalse(any("/marketplaces/" in p for p in all_paths),
                             "marketplace catalogue was walked")

    def test_symlinked_user_skill_found(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            result = self._discover(sandbox)
            linked = [s for s in result["skills"] if s["id"] == "linked-skill"]
            self.assertEqual(len(linked), 1)
            # Display path is the logical (symlink) location.
            self.assertIn("/skills/linked-skill/SKILL.md", linked[0]["path"])
            self.assertEqual(linked[0]["description"],
                             "Symlinked user skill; discovery must follow the link to find this.")

    def test_allowlist_and_flat_fallback(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            result = self._discover(sandbox)
            alpha = sorted(s["name"] for s in result["skills"] if s["plugin"] == "alpha")
            beta = sorted(s["name"] for s in result["skills"] if s["plugin"] == "beta")
            self.assertEqual(alpha, ["one", "two"])  # allowlist, not the on-disk tree
            self.assertEqual(beta, ["x", "y"])       # flat glob fallback

    def test_unregistered_indexed_not_registered(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            result = self._discover(sandbox)
            names = [s["name"] for s in result["unregistered"]]
            self.assertEqual(names, ["qa"])
            self.assertFalse(result["unregistered"][0]["registered"])

    def test_enabled_via_settings_local_override(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            result = self._discover(sandbox)
            by_id = {s["id"]: s for s in result["skills"]}
            # settings.json enables beta, settings.local.json disables it — local wins.
            self.assertFalse(by_id["beta:x"]["enabled"])
            self.assertFalse(by_id["beta:y"]["enabled"])
            self.assertTrue(by_id["alpha:one"]["enabled"])
            self.assertTrue(by_id["plain-skill"]["enabled"])  # user skills always enabled

    def test_duplicate_names_surfaced_not_merged(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            result = self._discover(sandbox)
            self.assertEqual(result["duplicate_names"], ["graphify"])
            dupes = sorted(s["id"] for s in result["skills"] if s.get("duplicate"))
            self.assertEqual(dupes, ["graphify@project", "graphify@user"])

    def test_install_records_surfaced(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            result = self._discover(sandbox)
            alpha_one = next(s for s in result["skills"] if s["id"] == "alpha:one")
            self.assertEqual(alpha_one["install_records"], 2)
            self.assertEqual(alpha_one["marketplace"], "fake-mp")
            beta_x = next(s for s in result["skills"] if s["id"] == "beta:x")
            self.assertEqual(beta_x["version"], "unknown")

    def test_light_mode_reads_nothing_but_agrees_on_paths(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            full = self._discover(sandbox)
            light = self._discover(sandbox, light=True)
            self.assertEqual([s["path"] for s in full["skills"]],
                             [s["path"] for s in light["skills"]])
            self.assertIsNone(light["skills"][0].get("description"))

    def test_naive_count_exceeds_registered(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            result = self._discover(sandbox)
            naive = atlas_discovery.naive_skillmd_count()
            # Fixture: 8 registered + qa + stale + phantom = 11 on disk, plus
            # the symlinked skill counted again through its link path = 12.
            self.assertGreater(naive, len(result["skills"]))
            self.assertEqual(naive, 12)


class TestBuiltins(unittest.TestCase):
    """The fourth discovery root (DESIGN-ISSUES issue 1): built-ins ship
    inside the Claude Code binary, so they come from the vendored manifest."""

    def _discover(self, sandbox, **kwargs):
        atlas_paths.set_scope(sandbox.project_dir)
        return atlas_discovery.discover(**kwargs)

    def test_absent_manifest_means_no_builtins(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            result = self._discover(sandbox)
            self.assertEqual([s for s in result["skills"]
                              if s["scope"] == "builtin"], [])

    def test_builtin_record_shape(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            helpers.write_builtins(
                sandbox,
                {"name": "code-review", "description": "Review the diff."},
                {"name": "dataviz", "description": "Chart guidance."})
            result = self._discover(sandbox)
            builtins = {s["id"]: s for s in result["skills"]
                        if s["scope"] == "builtin"}
            self.assertEqual(sorted(builtins), ["code-review", "dataviz"])
            record = builtins["code-review"]
            self.assertIsNone(record["path"])       # nothing on disk to read
            self.assertTrue(record["enabled"])      # always session-loaded
            self.assertTrue(record["registered"])
            self.assertIsNone(record["plugin"])
            self.assertEqual(record["description"], "Review the diff.")

    def test_name_collision_with_user_skill_surfaced(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            helpers.write_builtins(sandbox, {"name": "plain-skill",
                                             "description": "Shadowed."})
            result = self._discover(sandbox)
            self.assertIn("plain-skill", result["duplicate_names"])
            dupes = sorted(s["id"] for s in result["skills"]
                           if s.get("duplicate") and s["name"] == "plain-skill")
            self.assertEqual(dupes, ["plain-skill@builtin", "plain-skill@user"])

    def test_light_mode_agrees_and_fingerprint_paths_skip_builtins(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            helpers.write_builtins(sandbox, {"name": "loop",
                                             "description": "Recurring runs."})
            full = self._discover(sandbox)
            light = self._discover(sandbox, light=True)
            self.assertEqual([s["id"] for s in full["skills"]],
                             [s["id"] for s in light["skills"]])
            # No None paths in the fingerprint input; change detection for
            # built-ins rides on the manifest side instead.
            paths = atlas_discovery.skill_md_paths()
            self.assertTrue(all(str(p) for p in paths))
            self.assertNotIn(None, [str(p) for p in paths])
            self.assertIn(atlas_paths.builtins_path(),
                          atlas_paths.manifest_paths())

    def test_malformed_manifest_yields_no_builtins(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            baseline = len(self._discover(sandbox)["skills"])
            for raw in ("not json at all", '["a", "list"]',
                        '{"skills": "nope"}', '{"skills": [42, {"x": 1}]}'):
                helpers.write_builtins(sandbox, raw=raw)
                result = self._discover(sandbox)
                self.assertEqual(len(result["skills"]), baseline, raw)

    def test_shipped_manifest_is_valid(self):
        """The vendored file itself: parseable, unique names, descriptions."""
        import json
        shipped = helpers.SCRIPTS / "builtin_skills.json"
        data = json.loads(shipped.read_text(encoding="utf-8"))
        names = [s["name"] for s in data["skills"]]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(s.get("description") for s in data["skills"]))


class TestFrontmatter(unittest.TestCase):
    def test_plain_quoted_and_block_values(self):
        parse = atlas_discovery.parse_frontmatter
        self.assertEqual(parse("---\nname: tdd\ndescription: Simple.\n---\nbody"),
                         {"name": "tdd", "description": "Simple."})
        self.assertEqual(parse('---\nname: "quoted"\n---\n')["name"], "quoted")
        folded = parse("---\ndescription: >-\n  line one\n  line two\nname: x\n---\n")
        self.assertEqual(folded["description"], "line one line two")
        self.assertEqual(folded["name"], "x")
        self.assertEqual(parse("no frontmatter here"), {})


if __name__ == "__main__":
    unittest.main()
