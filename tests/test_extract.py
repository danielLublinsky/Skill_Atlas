import unittest
from pathlib import Path

import helpers  # noqa: F401
import atlas_extract

UNIVERSE = {"tdd", "qa", "plain-skill", "resolving-merge-conflicts", "implement",
            "alpha:one", "two", "x"}
PLUGINS = {"alpha", "beta"}


def mentions(body, self_names=()):
    return atlas_extract.extract_mentions(body, UNIVERSE, PLUGINS, self_names)


class TestMentions(unittest.TestCase):
    def test_backtick_form(self):
        self.assertEqual(mentions("Use `tdd` here."), ["tdd"])
        self.assertEqual(mentions("Skills like `qa` write to it."), ["qa"])

    def test_slash_form(self):
        self.assertEqual(mentions("see skills/tdd for details"), ["tdd"])
        self.assertEqual(mentions("see skills/unknown-name for details"), [])

    def test_hyphenated_bare_form(self):
        self.assertEqual(mentions("try resolving-merge-conflicts first"),
                         ["resolving-merge-conflicts"])

    def test_bare_common_word_rejected(self):
        # 'implement' is in the universe but appears as an ordinary verb.
        self.assertEqual(mentions("you should implement this now"), [])
        # Backticked, the same name counts.
        self.assertEqual(mentions("run `implement` now"), ["implement"])

    def test_namespaced_with_known_prefix(self):
        self.assertEqual(mentions("Use `alpha:ghost` when it lands."), ["alpha:ghost"])
        self.assertEqual(mentions("Use `zeta:ghost` when it lands."), [])

    def test_fenced_code_ignored_inline_kept(self):
        body = "Use `tdd`.\n```example\nthis `qa` is documentation\n```\ndone"
        self.assertEqual(mentions(body), ["tdd"])

    def test_self_mention_excluded(self):
        self.assertEqual(mentions("`tdd` is this skill", self_names={"tdd"}), [])

    def test_frontmatter_never_reaches_extraction(self):
        text = "---\nname: tdd\ndescription: mentions `qa` in metadata\n---\nBody only.\n"
        body = atlas_extract.split_frontmatter_body(text)
        self.assertNotIn("metadata", body.split("Body")[0] if "---" in body else "")
        self.assertEqual(mentions(body), [])


class TestReferences(unittest.TestCase):
    def test_links_and_bare_paths(self):
        with helpers.EnvSandbox() as sandbox:
            skill_dir = sandbox.tmp / "skill"
            (skill_dir / "references").mkdir(parents=True)
            (skill_dir / "references" / "red.md").write_text("x")
            body = ("Read [notes](references/red.md) then references/missing.md "
                    "and [ext](https://example.com/a.md) and [anchor](#section).")
            refs = atlas_extract.extract_references(body, skill_dir)
            by_target = {r["target"]: r for r in refs}
            self.assertEqual(set(by_target), {"references/red.md", "references/missing.md"})
            self.assertTrue(by_target["references/red.md"]["exists"])
            self.assertFalse(by_target["references/missing.md"]["exists"])

    def test_dedup_and_fence_stripping(self):
        with helpers.EnvSandbox() as sandbox:
            skill_dir = sandbox.tmp / "skill"
            skill_dir.mkdir()
            body = ("scripts/run.sh twice: scripts/run.sh\n"
                    "```\nassets/inside-fence.png\n```\n")
            refs = atlas_extract.extract_references(body, skill_dir)
            self.assertEqual([r["target"] for r in refs], ["scripts/run.sh"])


if __name__ == "__main__":
    unittest.main()
