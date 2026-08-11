# Design issues

Defects found by read-only probe fleets over `skill-search`: a 10-agent run (one
agent per catalog category — routing was 10/10 correct, every agent picked the
right category on the first try) and a later 8-agent boundary run. Issues 1 and
2 were in **what discovery collects**, not in how search reads it; issue 3 is in
the categorization instructions. A resolved issue keeps its original report
below the resolution.

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

### Original report — issue 1

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

## Issue 2 — `frontend-design` is stranded with a colliding id — **RESOLVED 2026-08-12**

**Resolution.** `_assign_ids` now escalates: the colliding invocation string
plus whichever record field actually separates the group — scope, then
marketplace, then version, then all three (`_disambiguate`) — and
`_enforce_unique_ids` backstops records that differ in nothing discovery can
read. The id is the join key for graph.json, the shards and `categories.json`,
so uniqueness is an invariant now rather than a hoped-for property. Verified on
the reporting machine: `frontend-design:frontend-design@claude-plugins-official`
and `frontend-design:frontend-design@claude-code-plugins`, 87/87 ids unique,
`orphan_ids` no longer lists one string twice. `duplicate_names` deliberately
keeps recording the *pre-rename* id (`frontend-design:frontend-design`) — that
is the ambiguous invocation string, `orphan_ids()` depends on the pre-rename
form to suppress false orphan warnings, and it is now a prefix of every id it
covers. Details: docs/3-discovery.md §"Node ids are invocation strings".

Two corrections to the original report:

- **The `unknown` version is not a broken install.** That plugin's
  `plugin.json` carries no `version` field at all — legal, since the key is
  optional — and `installed_plugins.json` records `"unknown"` faithfully.
  Nothing to report; at most a display choice ("unversioned").
- **The two files are byte-identical** (`md5 31c6336…`): one Anthropic skill
  published through two marketplaces. So "same name, same content, delete one"
  and "same name, different skill" are different problems for the user, and the
  atlas still cannot tell them apart. A content hash on duplicate-named nodes
  would — filed as its own enhancement, not part of this fix.

Cost, as predicted: the old `frontend-design@plugin` assignment key stops
resolving and is reported as an `orphan_assignment`; both new ids arrive in
`categorize.py status` as uncategorized (tier `off`) for the next
`/skill-atlas` run to file.

### Original report — issue 2

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

---

## Issue 3 — Overlap is missing exactly where categories are confusable — **INSTRUCTIONS FIXED 2026-08-11, data pending**

Found by an 8-agent boundary probe (one deliberately ambiguous task per
confusable category pair, Opus, read-only). Score: 8/8 found the right skill —
but 6/8 needed the full index-plus-two-shards budget, and one probe reported
outright that a one-shard read would have missed the best skill.

**What happens.** The catalog's stated defense against a wrong stage-1 pick is
overlap ("the pick doesn't have to land on *the* right bucket, only *a* right
one"). Measured on this scope: 63/87 assignments are single-category, and the
confusable pairs share almost nothing — `debugging` ∩
`testing-and-verification` = 0 skills, `discovery` ∩ `design` = 2, `discovery`
∩ `planning` = 1. The only heavy overlap (`implementation` +
`media-generation`, 7 pairings) belongs to an uninstalled plugin's orphaned
assignments. Probes survived on two crutches instead: the boundary carve-outs
in category descriptions, and spending the optional second shard defensively.
Probe 4 ("restructure how our backend modules talk") matched the discovery
description almost verbatim; the best skill,
`improve-codebase-architecture`, is single-homed in design — it was found
only via the second shard.

**Why it happens.** The bootstrap instructions spend four rules on
*description* quality but said only "assign EVERY skill to one or more
categories" about assignment — multi-homing was permitted, never instructed,
so the categorizing model minimized it.

**Why it matters.** This is the wrong-answer failure class: an agent that
opens the twin shard finds a plausible generic skill, is satisfied, and never
learns the better skill exists — search forbids looking outside the catalog,
so the miss is silent.

**Shape of the fix.** Taken (2026-08-11): assignment rules added to
`commands/skill-atlas.md`, `skills/skill-atlas/SKILL.md` and
`docs/5-categorization.md` (the command was merged into the skill on
2026-08-12, so those rules now live in the SKILL.md alone) — multi-home
across confusable boundaries (the
boundary clauses mark the pairs to sweep), second home requires a realistic
task phrasing, platform-locked skills stay out of generic categories. Applies
to fresh bootstraps and future incremental assigns. Existing scopes keep
their under-homed assignments until the planned category-control command
lands (the taxonomy/assignment data is model-generated and frozen by design —
no hand-repair path).

Related probe findings, same run, not fixed here: index token lists lead with
plugin names and truncate real skill names past `TOKEN_BUDGET_CHARS`
(`update-config` invisible in the `tooling-and-environment-setup` line);
generically-named vendor-locked `ui-theme-designer` tokens bait a wasted
shard read; near-duplicate skills surface with no tiebreaker between their
one-line descriptions.
