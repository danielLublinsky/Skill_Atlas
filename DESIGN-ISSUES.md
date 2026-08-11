# Design issues

Open defects found by a 10-agent read-only probe of `skill-search` (one agent
per catalog category). Routing was 10/10 correct — every agent picked the right
category on the first try. Both issues below are in **what discovery collects**,
not in how search reads it.

---

## Issue 1 — Built-in skills never enter the catalog

**What happens.** Skills that ship with Claude Code itself are absent from every
shard. Verified missing: `simplify`, `security-review`, `dataviz`,
`artifact-design`, `update-config`, `keybindings-help`, `loop`, `schedule`,
`claude-api`. Across all ten probes the catalog served exactly one `[enabled]`
skill (`graphify`); everything else was `[searchable]`.

**Why it happens.** `scripts/atlas_discovery.py:109` walks three roots — the user
skills root, the project skills root, and installed plugins. Built-in skills live
in none of them, so they are never discovered.

**Why it matters — this is worse than an omission.** A built-in and a plugin
skill can share a bare name. The code-review probe was asked to review a diff and
was handed `mattpocock-skills:code-review`, while the built-in `code-review` —
same name, better fit, `--comment` and `--fix` flags — sat invisible. The catalog
does not merely miss the better skill, it **shadows** it: `skill-search` tells
the agent never to look outside `catalog/`, so the better skill cannot be
recovered through any other path.

**Shape of the fix.** Add a fourth discovery root for built-ins. Needs a decision
on how to locate them (they are not on disk under `~/.claude/`) and on how the
tier should read — they are enabled, but not via a plugin manifest.

---

## Issue 2 — `frontend-design` is stranded with a colliding id

**What happens.** `catalog/uncategorized.md` holds two entries, and they are the
same skill twice:

```
## frontend-design@plugin [searchable]
- path: .../claude-plugins-official/frontend-design/unknown/skills/frontend-design/SKILL.md

## frontend-design@plugin [searchable]
- path: .../claude-code-plugins/frontend-design/1.1.0/skills/frontend-design/SKILL.md
```

Two problems visible here: **identical ids** on two distinct rows, and a version
segment of literally `unknown` on the first path.

**Why it happens.** `_assign_ids` (`scripts/atlas_discovery.py:189`) disambiguates
a name collision by rewriting the id to `<name>@<scope>`. That works for the case
it was written for — a project skill shadowing a user skill, where the scopes
differ. Here both copies come from two different marketplaces, so both have scope
`plugin`, and `<name>@<scope>` produces the *same* id for both. The
disambiguation step re-collides instead of separating them.

**Why it matters.** `frontend-design` is the only general (non-platform-specific)
UI skill in the library. Stuck in `uncategorized`, it never reached the UI probe,
which fell through to Shopify-only skills instead. The colliding id also makes
the two rows indistinguishable to anything downstream that keys on id.

**Shape of the fix.** Disambiguate plugin-scope collisions by something that
actually differs — marketplace, or plugin install path. Separately, decide what
a `unknown` version segment means: a stale or half-installed plugin cache may be
worth reporting rather than cataloguing.
