import json
import pathlib
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


def _docs_block(html):
    match = re.search(
        r'<script id="atlas-docs" type="application/json">(.*?)</script>',
        html, re.S)
    return json.loads(match.group(1).replace("<\\/", "</"))


def _markup_only(html):
    """The page with its JSON payloads removed.

    Both payloads are inert text to the parser, and one of them is the verbatim
    contents of every SKILL.md in the library — markdown that can legitimately
    contain "<link", "@import" or "url(http" inside a fenced example. Scanning
    it for external references reports on what the docs talk about rather than
    on what the page loads.
    """
    return re.sub(
        r'<script id="atlas-(?:data|docs)" type="application/json">.*?</script>',
        "", html, flags=re.S)


class TestRender(unittest.TestCase):
    def test_self_contained_no_external_references(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            html = _render(sandbox)
            markup = _markup_only(html)
            self.assertNotIn("<script src=", markup)
            self.assertNotIn("@import", markup)
            self.assertNotIn("url(http", markup)
            # <link> is allowed only as a data: URI — that is the inlined
            # favicon, which costs no request. Anything else is a fetch.
            for tag in re.findall(r"<link\b[^>]*>", markup):
                self.assertRegex(tag, r'href=["\']data:',
                                 f"external <link> in atlas.html: {tag}")
            self.assertIn("d3js.org v7.9.0", html)  # vendored D3 is actually inlined

    def test_docs_embedded_for_files_on_disk(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            html = _render(sandbox)
            docs = _docs_block(html)
            data = _data_block(html)
            paths = {n["path"] for n in data["graph"]["nodes"] if n.get("path")}
            self.assertTrue(paths, "fixture graph has no node with a path")
            present = {p for p in paths if pathlib.Path(p).is_file()}
            self.assertTrue(present, "fixture graph has no readable file")
            for path in present:
                self.assertIn(path, docs)
                self.assertEqual(docs[path],
                                 pathlib.Path(path).read_text(encoding="utf-8"))
            # a node pointing at a file that isn't on disk embeds nothing — the
            # viewer says so rather than opening blank
            self.assertTrue(paths - present,
                            "fixture should include a broken reference")
            for path in paths - present:
                self.assertNotIn(path, docs)

    def test_no_embed_docs_leaves_map_empty(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            graph, _ = build_graph.build(cwd=sandbox.project_dir)
            atlas_io.atomic_write_json(atlas_paths.graph_path(), graph)
            out = render.render(cwd=sandbox.project_dir, embed_docs=False)
            self.assertEqual(_docs_block(out.read_text(encoding="utf-8")), {})

    def test_script_terminator_escaped_in_docs(self):
        """A doc containing "</script>" must not end the block it travels in."""
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            html = _render(sandbox)
            match = re.search(
                r'<script id="atlas-docs" type="application/json">(.*?)</script>',
                html, re.S)
            self.assertNotIn("</", match.group(1))

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

    def test_render_lands_in_scope(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            build_graph.main(["--cwd", str(sandbox.project_dir), "--quiet"])
            out = render.render(cwd=sandbox.project_dir)
            self.assertEqual(out,
                             helpers.atlas_dir(sandbox.project_dir) / "atlas.html")
            html = out.read_text(encoding="utf-8")
            self.assertIn("<title>skill-atlas · project</title>", html)
            meta = _data_block(html)["meta"]
            self.assertEqual(meta["view"], "local")
            self.assertEqual(meta["project_name"], "project")

    def test_category_view_data_and_markup(self):
        # M6: v3 fields round-trip into the page, and the category-view
        # machinery is present (force-layout behavior is validated live).
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            helpers.write_categories(
                sandbox,
                helpers.approved_categories(sandbox, cwd=sandbox.project_dir),
                cwd=sandbox.project_dir)
            helpers.write_config(sandbox, helpers.searchable_config("beta"),
                                 cwd=sandbox.project_dir)
            html = _render(sandbox)
            nodes = {n["id"]: n for n in _data_block(html)["graph"]["nodes"]}
            self.assertEqual(nodes["alpha:two"]["categories"], ["eng", "docs"])
            self.assertFalse(nodes["alpha:two"]["category_stale"])
            self.assertTrue(nodes["beta:x"]["searchable"])
            taxonomy = _data_block(html)["graph"]["taxonomy"]
            self.assertEqual([t["name"] for t in taxonomy], ["eng", "docs"])
            # Static template assertions at the M6 seams.
            self.assertIn('data-view="category"', html)   # view tab
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
