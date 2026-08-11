# Design issues

Open defects found by a 10-agent read-only probe of `skill-search` (one agent
per catalog category). Routing was 10/10 correct — every agent picked the right
category on the first try. Both issues below are in **what discovery collects**,
not in how search reads it.

---

## Issue 1 — Built-in skills never enter the catalog — **RESOLVED 2026-08-11**

**Resolution.** Discovery gained a fourth root: a vendored manifest,
`scripts/builtin_skills.json`, listing the skills that ship inside the Claude
Code binary (15 entries as of Claude Code 2.1.227). The two open decisions
were taken as follows:

- **How to locate them:** they cannot be located — verified: not under
  `~/.claude/`, not in `installed_plugins.json`, not materialized in any
  cache, no CLI that lists them, and not extractable from the (compiled ELF)
  binary. So the list is *curated data* shipped with skill-atlas, updated
  with releases. A missing/malformed manifest degrades to "no built-ins",
  never an error. `SKILL_ATLAS_BUILTINS` overrides the path (test seam);
  the file joins `manifest_paths()` so updating it flips the staleness
  fingerprint. The known cost: the list can drift from the user's Claude
  Code version until skill-atlas ships an update — accepted, since every
  alternative (transcript mining is dead per DESIGN §6; binary scraping is
  coupling to an opaque format) was worse.
- **How the tier reads:** `[enabled]`. Built-ins are always session-loaded
  and natively invocable via the Skill tool, which is exactly what
  `[enabled]` instructs. They get `scope: "builtin"`, `path: null`; shards
  print `- built-in: ships with Claude Code, no file on disk` instead of a
  path line. They are never `searchable` — that tier exists to bypass plugin
  machinery built-ins don't use.

Verified after rebuild: the code-review shard now serves the built-in
`code-review [enabled]` beside `mattpocock-skills:code-review [searchable]` —
the shadowing case below. Details: docs/3-discovery.md §"Built-ins".

### Original report

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

```text
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
