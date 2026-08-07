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
            atlas_paths.atlas_home().mkdir(parents=True, exist_ok=True)
            atlas_paths.dirty_path().touch()
            code = build_graph.main(["--cwd", str(sandbox.project_dir), "--quiet"])
            self.assertEqual(code, 1)
            graph = json.loads(atlas_paths.graph_path().read_text())
            self.assertEqual(graph["version"], 2)
            self.assertFalse(atlas_paths.dirty_path().exists())
            leftovers = [p for p in atlas_paths.atlas_home().iterdir()
                         if p.suffix == ".tmp"]
            self.assertEqual(leftovers, [])

    def test_check_mode_writes_nothing(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            code = build_graph.main(["--cwd", str(sandbox.project_dir),
                                     "--check", "--quiet"])
            self.assertEqual(code, 1)
            self.assertFalse(atlas_paths.graph_path().exists())
            self.assertFalse(
                atlas_paths.project_graph_path(sandbox.project_dir).exists())


class TestDualViews(unittest.TestCase):
    def test_main_builds_both_views(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            code = build_graph.main(["--cwd", str(sandbox.project_dir), "--quiet"])
            self.assertEqual(code, 1)
            global_graph = json.loads(atlas_paths.graph_path().read_text())
            self.assertEqual(global_graph["view"], "global")
            self.assertIsNone(global_graph["project"])
            # Machine-level: 3 user + 2 alpha + 2 beta, no project skills,
            # hence no graphify collision either.
            self.assertEqual(global_graph["stats"]["skills"], 7)
            self.assertEqual(global_graph["stats"]["duplicate_names"], [])

            project_graph = json.loads(
                atlas_paths.project_graph_path(sandbox.project_dir).read_text())
            self.assertEqual(project_graph["view"], "project")
            self.assertEqual(project_graph["project"], "project")
            self.assertEqual(project_graph["stats"]["skills"], 8)
            self.assertEqual(project_graph["stats"]["duplicate_names"], ["graphify"])

    def test_project_settings_override_flips_enabled(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            (sandbox.project_dir / ".claude" / "settings.json").write_text(
                json.dumps({"enabledPlugins": {"beta@fake-mp": True}}))
            build_graph.main(["--cwd", str(sandbox.project_dir), "--quiet"])
            global_graph = json.loads(atlas_paths.graph_path().read_text())
            project_graph = json.loads(
                atlas_paths.project_graph_path(sandbox.project_dir).read_text())

            g_beta = next(n for n in global_graph["nodes"] if n["id"] == "beta:x")
            p_beta = next(n for n in project_graph["nodes"] if n["id"] == "beta:x")
            self.assertFalse(g_beta["enabled"])   # user settings.local: disabled
            self.assertTrue(p_beta["enabled"])    # project override: enabled

            # And classification follows: the mention of x is dangling
            # (disabled) globally but healthy in the project view.
            g_edge = next(e for e in global_graph["edges"]
                          if e["source"] == "alpha:two" and e["target"] == "beta:x")
            p_edge = next(e for e in project_graph["edges"]
                          if e["source"] == "alpha:two" and e["target"] == "beta:x")
            self.assertEqual(g_edge["kind"], "dangling")
            self.assertEqual(p_edge["kind"], "mentions")

    def test_view_flags(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            build_graph.main(["--cwd", str(sandbox.project_dir),
                              "--global-only", "--quiet"])
            self.assertTrue(atlas_paths.graph_path().exists())
            self.assertFalse(
                atlas_paths.project_graph_path(sandbox.project_dir).exists())

            build_graph.main(["--cwd", str(sandbox.project_dir),
                              "--project-only", "--quiet"])
            self.assertTrue(
                atlas_paths.project_graph_path(sandbox.project_dir).exists())

            code = build_graph.main(["--cwd", str(sandbox.tmp),
                                     "--project-only", "--quiet"])
            self.assertEqual(code, 2)  # not a project

    def test_non_project_cwd_builds_global_only(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            code = build_graph.main(["--cwd", str(sandbox.tmp), "--quiet"])
            self.assertEqual(code, 1)
            self.assertTrue(atlas_paths.graph_path().exists())
            self.assertFalse((sandbox.tmp / ".claude").exists())

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
