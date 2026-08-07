import json
import re
import unittest

import helpers
import atlas_io
import atlas_paths
import build_graph
import render


def _render(sandbox):
    graph, _ = build_graph.build(cwd=sandbox.project_dir)
    atlas_io.atomic_write_json(atlas_paths.graph_path(), graph)
    out = render.render(cwd=sandbox.project_dir)
    return out.read_text(encoding="utf-8")


def _data_block(html):
    match = re.search(
        r'<script id="atlas-data" type="application/json">(.*?)</script>',
        html, re.S)
    return json.loads(match.group(1).replace("<\\/", "</"))


class TestRender(unittest.TestCase):
    def test_self_contained_no_external_references(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            html = _render(sandbox)
            self.assertNotIn("<script src=", html)
            self.assertNotIn("<link", html)
            self.assertNotIn("@import", html)
            self.assertNotIn("url(http", html)
            self.assertIn("d3js.org v7.9.0", html)  # vendored D3 is actually inlined

    def test_script_terminator_escaped_in_data(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            html = _render(sandbox)
            match = re.search(
                r'<script id="atlas-data" type="application/json">(.*?)</script>',
                html, re.S)
            self.assertNotIn("</", match.group(1))

    def test_data_round_trips(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            html = _render(sandbox)
            data = _data_block(html)
            self.assertEqual(data["graph"]["stats"]["skills"], 8)
            ids = {n["id"] for n in data["graph"]["nodes"]}
            self.assertIn("skill?:qa", ids)

    def test_deterministic_output(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            graph, _ = build_graph.build(cwd=sandbox.project_dir)
            atlas_io.atomic_write_json(atlas_paths.graph_path(), graph)
            first = render.render(cwd=sandbox.project_dir).read_bytes()
            second = render.render(cwd=sandbox.project_dir).read_bytes()
            self.assertEqual(first, second)

    def test_project_render_lands_in_project(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            build_graph.main(["--cwd", str(sandbox.project_dir), "--quiet"])
            out = render.render(cwd=sandbox.project_dir, project=True)
            self.assertEqual(out, atlas_paths.project_atlas_path(sandbox.project_dir))
            html = out.read_text(encoding="utf-8")
            self.assertIn("<title>skill-atlas · project</title>", html)
            meta = _data_block(html)["meta"]
            self.assertEqual(meta["view"], "project")
            self.assertEqual(meta["project_name"], "project")
            # Global render keeps its plain title and location.
            global_out = render.render(cwd=sandbox.project_dir)
            self.assertEqual(global_out, atlas_paths.atlas_home() / "atlas.html")
            self.assertIn("<title>skill-atlas</title>",
                          global_out.read_text(encoding="utf-8"))

    def test_category_view_data_and_markup(self):
        # M6: v3 fields round-trip into the page, and the category-view
        # machinery is present (force-layout behavior is validated live).
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            helpers.write_categories(
                sandbox, helpers.approved_categories(cwd=sandbox.project_dir))
            helpers.write_config(sandbox, helpers.searchable_config("beta"))
            html = _render(sandbox)
            nodes = {n["id"]: n for n in _data_block(html)["graph"]["nodes"]}
            self.assertEqual(nodes["alpha:two"]["categories"], ["eng", "docs"])
            self.assertFalse(nodes["alpha:two"]["category_stale"])
            self.assertTrue(nodes["beta:x"]["searchable"])
            taxonomy = _data_block(html)["graph"]["taxonomy"]
            self.assertEqual([t["name"] for t in taxonomy], ["eng", "docs"])
            # Static template assertions at the M6 seams.
            self.assertIn('id="t-category"', html)
            self.assertIn('"cat:"', html)          # hub synthesis marker
            self.assertIn("--tier-searchable", html)
            self.assertIn("category hub", html)     # legend row
            self.assertIn("searchable (dormant)", html)

    def test_stale_flag_when_skill_newer_than_graph(self):
        import os
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            graph, _ = build_graph.build(cwd=sandbox.project_dir)
            atlas_io.atomic_write_json(atlas_paths.graph_path(), graph)
            skill = sandbox.claude / "skills" / "plain-skill" / "SKILL.md"
            stat = os.stat(atlas_paths.graph_path())
            os.utime(skill, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000))
            out = render.render(cwd=sandbox.project_dir)  # no rebuild in between
            meta = _data_block(out.read_text())["meta"]
            self.assertTrue(meta["stale"])


if __name__ == "__main__":
    unittest.main()
