"""Edge extraction from SKILL.md bodies (DESIGN §3.1).

Two extractors, both classification-free — build_graph decides whether a
mention is healthy or dangling:

- references: markdown links plus bare references/|scripts/|assets/ paths,
  resolved against the skill directory, flagged broken when missing.
- mentions: STRICT by design. A word-boundary match on known names produced
  91 edges on a 41-skill collection, dominated by names that are ordinary
  English words. A mention counts only in an unambiguous form: backticked,
  slash-prefixed (skills/<name>), or a bare hyphenated/multi-word name.
  Fenced code blocks are stripped first (a mention inside a fence is
  documentation, not instruction); inline code spans are kept — backtick
  mentions ARE inline code.
"""

import re
from pathlib import Path

_MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
_BARE_PATH = re.compile(r"(?<![\w/(])((?:references|scripts|assets)/[A-Za-z0-9_.\-/]+)")
_BACKTICK = re.compile(r"`([^`\n]+)`")
_SLASH_FORM = re.compile(r"(?<![\w/])skills/([A-Za-z0-9_-]+)")
_NAMESPACED = re.compile(r"^[A-Za-z0-9_-]+:[A-Za-z0-9_-]+$")


def split_frontmatter_body(text: str) -> str:
    """Return the body only — a skill's own frontmatter naming itself must
    not create edges."""
    stripped = text.lstrip("﻿")
    if not stripped.startswith("---"):
        return stripped
    lines = stripped.splitlines(keepends=True)
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() in ("---", "..."):
            return "".join(lines[index + 1:])
    return stripped


def strip_fences(body: str) -> str:
    out = []
    fence = None
    for line in body.splitlines():
        marker = line.lstrip()[:3]
        if fence is None and marker in ("```", "~~~"):
            fence = marker
            continue
        if fence is not None:
            if marker == fence:
                fence = None
            continue
        out.append(line)
    return "\n".join(out)


def extract_references(body: str, skill_dir: Path) -> list:
    """Bundled-file references. Returns [{target, path, exists}] deduped,
    ordered by first appearance."""
    body = strip_fences(body)
    seen = {}
    candidates = []
    for match in _MD_LINK.finditer(body):
        candidates.append(match.group(1))
    for match in _BARE_PATH.finditer(body):
        candidates.append(match.group(1))
    for raw in candidates:
        target = raw.strip().rstrip(".,;:")
        if "://" in target or target.startswith(("mailto:", "#", "/")):
            continue
        target = target.split("#", 1)[0]
        if not target or target.endswith("/"):
            continue
        if target in seen:
            continue
        path = (skill_dir / target)
        seen[target] = {
            "target": target,
            "path": str(path),
            "exists": path.is_file(),
        }
    return list(seen.values())


def extract_mentions(body: str, universe, plugin_names, self_names=()) -> list:
    """Strict-form mention tokens, ordered by first appearance.

    universe: every resolvable skill name/id (registered + unregistered index).
    plugin_names: known plugin bare names — a backticked '<plugin>:<name>'
    token with a known prefix counts even when the target does not exist
    (that is exactly the 'absent' dangling case worth surfacing).
    self_names: the mentioning skill's own names, never edges.
    """
    universe = set(universe)
    plugin_names = set(plugin_names)
    self_names = set(self_names)
    body = strip_fences(body)
    found = []

    def add(token):
        if token and token not in self_names and token not in found:
            found.append(token)

    for match in _BACKTICK.finditer(body):
        token = match.group(1).strip()
        if token in universe:
            add(token)
        elif _NAMESPACED.match(token) and token.split(":", 1)[0] in plugin_names:
            add(token)

    for match in _SLASH_FORM.finditer(body):
        token = match.group(1)
        if token in universe:
            add(token)

    for name in universe:
        if "-" not in name and " " not in name:
            continue  # single common words only ever match in explicit forms
        if ":" in name:
            continue  # namespaced ids match via backtick form only
        if name in self_names or name in found:
            continue
        if re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", body):
            add(name)

    return found
