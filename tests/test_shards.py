"""M4: catalog shards + stage-1 index + skill-search packaging."""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

import helpers
import atlas_discovery
import atlas_paths
import atlas_shards
import build_graph


def _build():
    neutral = str(Path(os.environ["SKILL_ATLAS_CLAUDE_DIR"]).parent)
    return build_graph.main(["--quiet", "--cwd", neutral])


def _index():
    return atlas_paths.catalog_index_path().read_text(encoding="utf-8")


def _shard(name):
    return (atlas_paths.catalog_dir() / f"{name}.md").read_text(encoding="utf-8")


class TestShards(unittest.TestCase):
    def test_index_and_shards_shape(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            helpers.write_categories(sandbox, helpers.approved_categories(sandbox))
            _build()
            index = _index()
            # name(count) — description — tokens; counts are catalog counts
            # (enabled only here: beta is not opted in).
            self.assertRegex(index, r"eng\(2\) — building and changing code — alpha")
            self.assertRegex(index, r"docs\(2\) — .* — alpha, plain-skill")
            self.assertIn("uncategorized(2) — skills not yet categorized; "
                          "run /skill-atlas to file them", index)

            eng = _shard("eng")
            self.assertIn("## alpha:one [enabled]", eng)
            self.assertIn("## alpha:two [enabled]", eng)
            self.assertNotIn("beta:x", eng)  # tier-off: excluded entirely
            self.assertIn("- also in: docs", eng)
            docs = _shard("docs")
            self.assertIn("## alpha:two [enabled]", docs)
            self.assertIn("- also in: eng", docs)

            uncat = _shard("uncategorized")
            self.assertIn("## journal [enabled]", uncat)
            self.assertIn("## linked-skill [enabled]", uncat)
            self.assertIn("/skill-atlas", uncat)

    def test_searchable_tier_included_when_opted_in(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            helpers.write_categories(sandbox, helpers.approved_categories(sandbox))
            helpers.write_config(sandbox, helpers.searchable_config("beta"))
            _build()
            self.assertIn("## beta:x [searchable]", _shard("eng"))
            self.assertIn("## beta:y [searchable]", _shard("uncategorized"))
            self.assertRegex(_index(), r"eng\(3\)")
            self.assertRegex(_index(), r"uncategorized\(3\)")

    def test_builtin_renders_enabled_without_path_line(self):
        # DESIGN-ISSUES issue 1: built-ins enter the catalog as [enabled]
        # (natively invocable) with no path — there is no SKILL.md to Read.
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            helpers.write_builtins(sandbox, {"name": "loop",
                                             "description": "Recurring runs."})
            _build()
            uncat = _shard("uncategorized")
            self.assertIn("## loop [enabled]", uncat)
            self.assertIn("- built-in: ships with Claude Code, no file on disk",
                          uncat)
            self.assertNotIn("path: None", uncat)

    def test_empty_categories_still_searchable(self):
        # DESIGN §13.7 commitment: search works against an empty categories.json —
        # everything lands in the always-present uncategorized shard.
        with helpers.EnvSandbox(copy_fixtures=True):
            _build()
            self.assertTrue(atlas_paths.catalog_index_path().exists())
            self.assertRegex(_index(), r"uncategorized\(5\)")
            uncat = _shard("uncategorized")
            for skill_id in ("journal", "plain-skill", "alpha:one"):
                self.assertIn(f"## {skill_id} [enabled]", uncat)

    def test_stale_marker_renders(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            obj = helpers.approved_categories(sandbox)
            obj["assignments"]["alpha:one"]["desc_hash"] = "sha256:" + "0" * 64
            helpers.write_categories(sandbox, obj)
            _build()
            self.assertIn("## alpha:one [enabled] (stale)", _shard("eng"))

    def test_deterministic_and_removes_stale_shards(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            helpers.write_categories(sandbox, helpers.approved_categories(sandbox))
            _build()
            first = {p.name: p.read_bytes()
                     for p in atlas_paths.catalog_dir().glob("*.md")}
            _build()
            second = {p.name: p.read_bytes()
                      for p in atlas_paths.catalog_dir().glob("*.md")}
            self.assertEqual(first, second)

            # Rename a category (taxonomy AND assignments): old shard goes.
            renamed = helpers.approved_categories(sandbox)
            renamed["taxonomy"][0]["name"] = "engineering"
            for entry in renamed["assignments"].values():
                entry["categories"] = ["engineering" if c == "eng" else c
                                       for c in entry["categories"]]
            helpers.write_categories(sandbox, renamed)
            _build()
            names = {p.name for p in atlas_paths.catalog_dir().glob("*.md")}
            self.assertIn("engineering.md", names)
            self.assertNotIn("eng.md", names)

    def test_check_mode_writes_no_shards(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            helpers.write_categories(sandbox, helpers.approved_categories(sandbox))
            build_graph.main(["--quiet", "--check",
                              "--cwd", str(sandbox.tmp)])
            self.assertFalse(atlas_paths.catalog_dir().exists())

    def test_hook_rebuild_refreshes_shards(self):
        with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
            helpers.write_categories(sandbox, helpers.approved_categories(sandbox))
            result = subprocess.run(
                [sys.executable, str(helpers.SCRIPTS / "check_stale.py")],
                cwd=sandbox.tmp, env=os.environ.copy(),
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0)
            self.assertTrue(atlas_paths.catalog_index_path().exists())
            self.assertIn("## alpha:one [enabled]", _shard("eng"))


class TestSkillSearchPackaging(unittest.TestCase):
    def test_plugin_registers_both_skills(self):
        manifest = json.loads(
            (helpers.REPO / ".claude-plugin" / "plugin.json").read_text())
        self.assertEqual(manifest["skills"],
                         ["./skills/skill-atlas", "./skills/skill-search"])

    def test_no_duplicate_component_names(self):
        """A command and a skill sharing a name register two components under
        one address: the loser is unreachable while both still cost session
        tokens. `skill-atlas` was both until the command merged into the
        skill."""
        names = [atlas_discovery.parse_frontmatter(p.read_text())["name"]
                 for p in sorted((helpers.REPO / "skills").glob("*/SKILL.md"))]
        names += [p.stem
                  for p in sorted((helpers.REPO / "commands").glob("*.md"))]
        self.assertEqual(sorted(names), sorted(set(names)),
                         f"name claimed by two components: {names}")

    def test_skill_search_frontmatter(self):
        text = (helpers.REPO / "skills" / "skill-search" / "SKILL.md").read_text()
        fields = atlas_discovery.parse_frontmatter(text)
        self.assertEqual(fields["name"], "skill-search")
        self.assertLessEqual(len(fields["description"]), 1024)
        self.assertIn("dormant", fields["description"])


if __name__ == "__main__":
    unittest.main()
