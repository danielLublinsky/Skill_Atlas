"""Ship-integrity checks over the repo's own manifests and cross-references.

These guard the failure class that only bites *after* publishing: a manifest
that parses but points at nothing, two version numbers that drift apart, or a
docstring citing a design section that no longer exists. Everything here reads
the repo itself — no fixtures, no sandbox, no network.
"""

import json
import re
import unittest

import helpers

REPO = helpers.REPO
PLUGIN_JSON = REPO / ".claude-plugin" / "plugin.json"
MARKETPLACE_JSON = REPO / ".claude-plugin" / "marketplace.json"

# Files whose text may carry "DESIGN §x" citations.
CITING_SUFFIXES = {".py", ".md", ".sh"}
SKIP_DIRS = {".git", ".pytest_cache", "__pycache__", "vendor", "fixtures",
             ".claude"}


def _repo_files():
    for path in REPO.rglob("*"):
        if not path.is_file() or path.suffix not in CITING_SUFFIXES:
            continue
        if SKIP_DIRS & set(path.relative_to(REPO).parts):
            continue
        yield path


class TestManifests(unittest.TestCase):
    def test_manifests_are_valid_json(self):
        for path in (PLUGIN_JSON, MARKETPLACE_JSON,
                     REPO / "scripts" / "builtin_skills.json",
                     REPO / "hooks" / "hooks.json"):
            with self.subTest(manifest=path.name):
                json.loads(path.read_text(encoding="utf-8"))

    def test_plugin_and_marketplace_versions_agree(self):
        """A marketplace entry advertising a stale version installs the right
        code under the wrong number — invisible until someone reports it."""
        plugin = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))
        entries = json.loads(MARKETPLACE_JSON.read_text(encoding="utf-8"))["plugins"]
        entry = next(e for e in entries if e["name"] == plugin["name"])
        self.assertEqual(entry["version"], plugin["version"])

    def test_declared_skills_exist(self):
        plugin = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))
        for rel in plugin["skills"]:
            with self.subTest(skill=rel):
                self.assertTrue((REPO / rel / "SKILL.md").is_file(),
                                f"{rel}/SKILL.md declared but absent")

    def test_hook_commands_reference_real_scripts(self):
        text = (REPO / "hooks" / "hooks.json").read_text(encoding="utf-8")
        refs = re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w./-]+)", text)
        self.assertTrue(refs, "no hook commands found — did the schema change?")
        for rel in refs:
            with self.subTest(script=rel):
                self.assertTrue((REPO / rel).is_file(), f"{rel} is missing")

    def test_marketplace_homepage_is_set(self):
        entries = json.loads(MARKETPLACE_JSON.read_text(encoding="utf-8"))["plugins"]
        for entry in entries:
            with self.subTest(plugin=entry["name"]):
                self.assertTrue(entry.get("homepage", "").startswith("http"))

    def test_vendored_d3_carries_its_license(self):
        """D3 is ISC and gets inlined into every atlas.html; the license file
        has to ship beside it."""
        self.assertTrue((REPO / "vendor" / "LICENSE-d3").is_file())


class TestDesignCitations(unittest.TestCase):
    """Every `DESIGN §x` in the tree must resolve to a heading in DESIGN.md.

    The two specs were merged on 2026-08-14 and the citations renumbered; this
    is what keeps them from rotting again.
    """

    def test_every_citation_resolves(self):
        design = (REPO / "DESIGN.md").read_text(encoding="utf-8")
        headings = set(re.findall(r"^#{2,3} (\d+(?:\.\d+)?)\.?\s", design, re.M))
        self.assertTrue(headings, "no numbered headings parsed from DESIGN.md")

        dangling = []
        for path in _repo_files():
            if path.name == "DESIGN.md":
                continue
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(
                    r"DESIGN §(\d+(?:\.\d+)?)((?:,? §\d+(?:\.\d+)?)*)", text):
                cited = [match.group(1)]
                cited += re.findall(r"\d+(?:\.\d+)?", match.group(2))
                for section in cited:
                    if section not in headings:
                        rel = path.relative_to(REPO)
                        dangling.append(f"{rel}: DESIGN §{section}")
        self.assertEqual(dangling, [], "citations point at missing sections")

    def test_no_citations_into_the_merged_away_spec(self):
        """Naming the old file in prose is fine; *citing a section of it* is a
        pointer at a file that no longer exists."""
        stale = "DESIGN-PHASE2 " + chr(0xA7)
        for path in _repo_files():
            if path.name in {"DESIGN.md", "test_manifests.py"}:
                continue
            with self.subTest(file=str(path.relative_to(REPO))):
                self.assertNotIn(stale, path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
