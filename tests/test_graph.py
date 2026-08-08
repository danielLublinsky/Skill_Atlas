import contextlib
import io
import json
import unittest

import helpers
import atlas_io
import atlas_paths
import build_graph


def _build(sandbox):
    return build_graph.build(cwd=sandbox.project_dir)


def _edges(graph, kind=None):
    return [e for e in graph["edges"] if kind is None or e["kind"] == kind]


class TestGraphBuild(unittest.TestCase):
    def test_exit_1_and_expected_edges(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            graph, code = _build(sandbox)
            self.assertEqual(code, 1)
            triples = {(e["source"], e["target"], e["kind"]) for e in graph["edges"]}

            # The fixture twin of the live defect: registered skill mentions
            # a deprecated, unregistered one.
            self.assertIn(("alpha:one", "skill?:qa", "dangling"), triples)
            qa_edge = next(e for e in graph["edges"] if e["target"] == "skill?:qa")
            self.assertEqual(qa_edge["reason"], "unregistered")

            # Mention of a skill in a disabled plugin.
            x_edge = next(e for e in graph["edges"]
                          if e["source"] == "alpha:two" and e["target"] == "beta:x")
            self.assertEqual((x_edge["kind"], x_edge["reason"]), ("dangling", "disabled"))

            # Namespaced mention of a skill that exists nowhere.
            ghost = next(e for e in graph["edges"] if e["target"] == "skill?:alpha:ghost")
            self.assertEqual(ghost["reason"], "absent")

            # Healthy mentions: backticked registered, bare hyphenated, slash form.
            self.assertIn(("alpha:one", "alpha:two", "mentions"), triples)
            self.assertIn(("alpha:one", "plain-skill", "mentions"), triples)
            self.assertIn(("beta:y", "plain-skill", "mentions"), triples)

            # Fenced mention must not edge.
            self.assertNotIn(("alpha:two", "plain-skill", "mentions"), triples)

            # References: one healthy, one broken.
            ref_edges = _edges(graph, "references")
            healthy = [e for e in ref_edges if e["source"] == "alpha:one"]
            self.assertEqual(len(healthy), 1)
            self.assertFalse(healthy[0]["broken"])
            broken = [e for e in ref_edges if e["source"] == "beta:x"]
            self.assertEqual(len(broken), 1)
            self.assertTrue(broken[0]["broken"])

    def test_nodes_and_stats(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            graph, _ = _build(sandbox)
            stats = graph["stats"]
            self.assertEqual(stats["skills"], 8)
            self.assertEqual(stats["enabled"], 6)      # beta's two are disabled
            self.assertEqual(stats["unregistered"], 1)  # qa
            self.assertEqual(stats["broken_refs"], 1)
            self.assertEqual(stats["dangling"], 3)
            self.assertEqual(stats["duplicate_names"], ["graphify"])
            self.assertEqual(sorted(stats["orphan_ids"]),
                             ["graphify@project", "graphify@user", "linked-skill"])
            self.assertGreater(stats["skillmd_on_disk"], stats["skills"])

            by_id = {n["id"]: n for n in graph["nodes"]}
            qa_node = by_id["skill?:qa"]
            self.assertTrue(qa_node["dangling"])
            self.assertIn("deprecated/qa/SKILL.md", qa_node["path"])
            self.assertIsNone(by_id["skill?:alpha:ghost"]["path"])
            self.assertTrue(graph["source_fingerprint"].startswith("sha256:"))

    def test_clean_collection_exits_0(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            alpha = (sandbox.claude / "plugins" / "cache" / "fake-mp" / "alpha"
                     / "1.0.0" / "skills" / "eng")
            (alpha / "one" / "SKILL.md").write_text(
                "---\nname: one\ndescription: d\n---\n\nRead "
                "[notes](references/red.md). Skills like `two` help.\n")
            (alpha / "two" / "SKILL.md").write_text(
                "---\nname: two\ndescription: d\n---\n\nNothing dangling here.\n")
            beta = (sandbox.claude / "plugins" / "cache" / "fake-mp" / "beta"
                    / "unknown" / "skills")
            (beta / "x" / "SKILL.md").write_text(
                "---\nname: x\ndescription: d\n---\n\nSelf-contained.\n")
            graph, code = _build(sandbox)
            self.assertEqual(code, 0)
            self.assertEqual(graph["stats"]["dangling"], 0)
            self.assertEqual(graph["stats"]["broken_refs"], 0)

    def test_unparseable_manifest_exits_2(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            (sandbox.claude / "plugins" / "installed_plugins.json").write_text("{broken")
            code = build_graph.main(["--cwd", str(sandbox.project_dir)])
            self.assertEqual(code, 2)

    def test_main_writes_graph_and_clears_dirty(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            home = helpers.atlas_dir(sandbox.project_dir)
            home.mkdir(parents=True, exist_ok=True)
            (home / "graph.dirty").touch()
            code = build_graph.main(["--cwd", str(sandbox.project_dir), "--quiet"])
            self.assertEqual(code, 1)
            graph = json.loads((home / "graph.json").read_text())
            self.assertEqual(graph["version"], 3)
            self.assertFalse((home / "graph.dirty").exists())
            leftovers = [p for p in home.iterdir() if p.suffix == ".tmp"]
            self.assertEqual(leftovers, [])

    def test_check_mode_writes_nothing(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            code = build_graph.main(["--cwd", str(sandbox.project_dir),
                                     "--check", "--quiet"])
            self.assertEqual(code, 1)
            self.assertFalse(helpers.atlas_dir(sandbox.project_dir).exists())


class TestScopes(unittest.TestCase):
    def test_each_directory_is_its_own_scope(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            neutral = sandbox.tmp / "neutral"
            neutral.mkdir()
            code = build_graph.main(["--cwd", str(neutral), "--quiet"])
            self.assertEqual(code, 1)
            neutral_graph = json.loads(
                (helpers.atlas_dir(neutral) / "graph.json").read_text())
            self.assertEqual(neutral_graph["view"], "local")
            self.assertEqual(neutral_graph["project"], "neutral")
            # No .claude of its own: machine collection only, no collision.
            self.assertEqual(neutral_graph["stats"]["skills"], 7)
            self.assertEqual(neutral_graph["stats"]["duplicate_names"], [])

            build_graph.main(["--cwd", str(sandbox.project_dir), "--quiet"])
            project_graph = json.loads(
                (helpers.atlas_dir(sandbox.project_dir) / "graph.json").read_text())
            self.assertEqual(project_graph["stats"]["skills"], 8)
            self.assertEqual(project_graph["stats"]["duplicate_names"], ["graphify"])

    def test_scope_settings_override_flips_enabled(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            (sandbox.project_dir / ".claude" / "settings.json").write_text(
                json.dumps({"enabledPlugins": {"beta@fake-mp": True}}))
            neutral = sandbox.tmp / "neutral"
            neutral.mkdir()
            build_graph.main(["--cwd", str(neutral), "--quiet"])
            build_graph.main(["--cwd", str(sandbox.project_dir), "--quiet"])
            neutral_graph = json.loads(
                (helpers.atlas_dir(neutral) / "graph.json").read_text())
            project_graph = json.loads(
                (helpers.atlas_dir(sandbox.project_dir) / "graph.json").read_text())

            n_beta = next(n for n in neutral_graph["nodes"] if n["id"] == "beta:x")
            p_beta = next(n for n in project_graph["nodes"] if n["id"] == "beta:x")
            self.assertFalse(n_beta["enabled"])   # user settings.local: disabled
            self.assertTrue(p_beta["enabled"])    # this scope's override: enabled

            # And classification follows per scope: the mention of x is
            # dangling where beta is disabled, healthy where it is enabled.
            n_edge = next(e for e in neutral_graph["edges"]
                          if e["source"] == "alpha:two" and e["target"] == "beta:x")
            p_edge = next(e for e in project_graph["edges"]
                          if e["source"] == "alpha:two" and e["target"] == "beta:x")
            self.assertEqual(n_edge["kind"], "dangling")
            self.assertEqual(p_edge["kind"], "mentions")

    def test_any_directory_becomes_a_scope(self):
        # Auto-init: an explicit build in a plain directory creates its
        # .claude/skill-atlas and produces a full atlas there.
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            plain = sandbox.tmp / "plain"
            plain.mkdir()
            code = build_graph.main(["--cwd", str(plain), "--quiet"])
            self.assertEqual(code, 1)
            self.assertTrue((helpers.atlas_dir(plain) / "graph.json").is_file())
            self.assertTrue(atlas_paths.catalog_index_path().is_file())


class TestCategoryMerge(unittest.TestCase):
    def test_category_merge_and_stats(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            helpers.write_categories(
                sandbox,
                helpers.approved_categories(sandbox, cwd=sandbox.project_dir),
                cwd=sandbox.project_dir)
            graph, code = _build(sandbox)
            self.assertEqual(code, 1)  # fixture defects unchanged by Phase 2
            by_id = {n["id"]: n for n in graph["nodes"]}
            self.assertEqual(by_id["alpha:two"]["categories"], ["eng", "docs"])
            self.assertFalse(by_id["alpha:two"]["category_stale"])
            self.assertEqual(by_id["graphify@user"]["categories"], [])
            stats = graph["stats"]
            self.assertEqual(stats["uncategorized"], 4)  # 8 skills, 4 assigned
            self.assertEqual(stats["stale_categories"], 0)
            # Catalog covers tiers 1+2 only: beta is disabled and not opted
            # in, so its assigned beta:x contributes nothing.
            self.assertEqual(stats["catalog"]["dormant"], 0)
            self.assertEqual(stats["catalog"]["categories"], {"eng": 2, "docs": 2})

    def test_no_phase2_files_all_defaults(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            graph, code = _build(sandbox)
            self.assertEqual(code, 1)
            for node in graph["nodes"]:
                if node.get("type") == "skill" and node.get("registered"):
                    self.assertEqual(node["categories"], [])
                    self.assertFalse(node["searchable"])
            stats = graph["stats"]
            self.assertEqual(stats["catalog"],
                             {"dormant": 0, "categories": {},
                              "uncategorized": stats["enabled"]})

    def test_stale_hash_keeps_labels(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            obj = helpers.approved_categories(sandbox, cwd=sandbox.project_dir)
            obj["assignments"]["alpha:one"]["desc_hash"] = \
                "sha256:" + "0" * 64
            helpers.write_categories(sandbox, obj, cwd=sandbox.project_dir)
            graph, _ = _build(sandbox)
            node = next(n for n in graph["nodes"] if n["id"] == "alpha:one")
            self.assertTrue(node["category_stale"])
            self.assertEqual(node["categories"], ["eng"])  # labels stay live
            self.assertEqual(graph["stats"]["stale_categories"], 1)

    def test_orphaned_label_fails_build_loud(self):
        # A hand-rename that leaves assignments pointing at a category that
        # no longer exists is a curated-state defect: exit 2, named.
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            obj = helpers.approved_categories(sandbox, cwd=sandbox.project_dir)
            obj["taxonomy"][0]["name"] = "engineering"  # orphans "eng" labels
            helpers.write_categories(sandbox, obj, cwd=sandbox.project_dir)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = build_graph.main(["--cwd", str(sandbox.project_dir),
                                         "--quiet"])
            self.assertEqual(code, 2)
            self.assertIn("'eng' is not in the taxonomy", stderr.getvalue())

    def test_unknown_assignment_id_is_environmental(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            obj = helpers.approved_categories(sandbox, cwd=sandbox.project_dir)
            obj["assignments"]["ghost:skill"] = {
                "categories": ["eng"], "desc_hash": "sha256:" + "0" * 64,
                "assigned_at": "2026-08-07"}
            helpers.write_categories(sandbox, obj, cwd=sandbox.project_dir)
            graph, code = _build(sandbox)
            self.assertEqual(code, 1)  # never fatal
            self.assertEqual(graph["stats"]["orphan_assignments"], ["ghost:skill"])

    def test_searchable_tier_from_config(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            helpers.write_categories(
                sandbox,
                helpers.approved_categories(sandbox, cwd=sandbox.project_dir),
                cwd=sandbox.project_dir)
            helpers.write_config(sandbox, helpers.searchable_config("beta", "alpha"),
                                 cwd=sandbox.project_dir)
            graph, _ = _build(sandbox)
            by_id = {n["id"]: n for n in graph["nodes"]}
            self.assertTrue(by_id["beta:x"]["searchable"])
            self.assertFalse(by_id["beta:x"]["enabled"])
            # Recorded even when enabled is also true; tier derivation is
            # the reader's job (enabled wins).
            self.assertTrue(by_id["alpha:one"]["searchable"])
            self.assertFalse(by_id["plain-skill"]["searchable"])  # user scope
            stats = graph["stats"]
            self.assertEqual(stats["searchable"], 4)
            self.assertEqual(stats["catalog"]["dormant"], 2)  # beta:x, beta:y
            self.assertEqual(stats["catalog"]["categories"], {"eng": 3, "docs": 2})

    def test_malformed_categories_exits_2(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            home = helpers.atlas_dir(sandbox.project_dir)
            home.mkdir(parents=True, exist_ok=True)
            (home / "categories.json").write_text("{broken")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = build_graph.main(["--cwd", str(sandbox.project_dir),
                                         "--quiet"])
            self.assertEqual(code, 2)
            self.assertIn("categories.json", stderr.getvalue())


class TestMentionDedup(unittest.TestCase):
    def test_same_target_via_two_forms_is_one_edge(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            one = (sandbox.claude / "plugins" / "cache" / "fake-mp" / "alpha"
                   / "1.0.0" / "skills" / "eng" / "one" / "SKILL.md")
            one.write_text(
                "---\nname: one\ndescription: d\n---\n\n"
                "Use `alpha:two` and also see skills/two, i.e. `two`.\n")
            graph, _ = _build(sandbox)
            two_edges = [e for e in graph["edges"]
                         if e["source"] == "alpha:one" and e["target"] == "alpha:two"]
            self.assertEqual(len(two_edges), 1)

if __name__ == "__main__":
    unittest.main()
