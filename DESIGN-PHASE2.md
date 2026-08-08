# skill-atlas — Phase 2 Design: Categorization + Search

**Status:** implemented 2026-08-07 (all six milestones; amendments in §0 below)
**Parent:** [DESIGN.md](DESIGN.md) — Phase 1's graph model (§3), discovery (§4.1) and freshness
machinery (§5) are assumed throughout and are not restated here.
**Naming note:** "Phase 2" previously named usage tracking, which was fully specified and then
dropped the same day this phase was designed (DESIGN.md §0.4, §6). This phase reuses the number;
it revives nothing from that design. Nothing here reads `~/.claude/projects`.

---

## 0. Implementation amendments — 2026-08-07

Decided with the user during implementation planning; the body text below is left as designed,
and these amendments override it where they conflict.

1. **Bootstrap is autonomous — the §4.1 approval step is removed for now.** `/skill-atlas`
   drafts the taxonomy AND writes the full categorization in one run, reporting the result
   informationally. The taxonomy still freezes at bootstrap — for search stability, not
   approval — and later runs assign into it. When nothing fits, the model adds a category via
   the explicit `add-category` CLI act and calls it out in the report: additions are always
   visible, never silent. Editing/curation workflows come later (amendment 3).
2. **Scope view stays the atlas default, and the category view is pure catalog.** §7.1's "new
   default view" is amended: the by-category view is a second tab, and Phase 1's scope
   clustering remains the opening picture. In category view the model contains ONLY category
   hubs, member skills and membership edges — no files, `references`, `mentions`, dangling
   targets or orphan gutter (the structural toggles grey out); §7.1's "existing toggle brings
   files back" is dropped. The structural picture belongs to the scope view. Additionally the
   orphan gutter is removed from the scope view too (amends DESIGN.md §7.2): orphans float as
   ordinary nodes and settle near their own cluster. The unregistered gutter goes the same way
   — unregistered skills carry their originating plugin and cluster with it, since "this
   plugin ships skills its manifest never registers" is the finding, and a lane off to the
   side severs it from the plugin it indicts. They obey the plugin filter for the same reason.
3. **Future editing direction: export/download from the HTML.** categories.json is hand-editable
   curated state, and the long-term plan is editing it in the atlas page (rename categories,
   drag skills) with a download of the resulting categories.json — a static file:// page cannot
   write to disk. `categorize.py import <path>` exists now as the validated landing pad; the
   File System Access API is a possible Chromium-only one-click-save enhancement later.
4. **Invalid hand-edits fail loud.** A present-but-invalid categories.json or config.json fails
   the build with exit 2 naming every violation (same class as an unparseable manifest) — no
   tolerate-and-degrade for curated state. Boundary: environmental drift is not an edit error.
   An assignment whose skill left the graph is reported as `orphan_assignments` and skipped;
   a stale `desc_hash` is the designed stale state. The SessionStart hook never breaks a
   session: it swallows the failure, keeps the last-good graph, and the explicit build is where
   the violations print.
5. **The frozen taxonomy rides in graph.json** (top-level `taxonomy` key, v3). The stage-1
   index needs the curated category descriptions; carrying them in the graph keeps shard
   emission and the category view single-source (graph.json only), as §5 intended.
6. **Full coverage is mandatory (2026-08-07, user decision).** Every registered skill must be
   categorized: `categorize.py bootstrap` rejects incomplete coverage (exit 3, missing ids
   named, nothing written), and a `/skill-atlas` run must end with zero uncategorized skills —
   when nothing fits, the taxonomy is missing a category and the model adds one. The
   uncategorized bucket, shard and index-line nag remain, but strictly as the *transitional*
   state for skills installed between runs (the model-free build cannot label them) and for
   degraded configurations — never as an acceptable end state of a run.
7. **Project skills are categorized too, and curated state is split per scope
   (2026-08-07/08, user decisions).** `categorize.py` is view-aware: run from a project
   directory it operates on that project's graph, so project-scope skills and
   collision-renamed ids (`name@user` / `name@project`) are covered like any other skill.
   Curated state lives in two files: the GLOBAL `~/.claude/skill-atlas/categories.json`
   (frozen taxonomy + user/plugin assignments) and a per-project
   `.claude/skill-atlas/categories.json` (`{"version", "assignments"}` only — a project file
   carrying a taxonomy is rejected; labels validate against the global taxonomy). The project
   file travels with the repo and is meant to be committed (gitignore the derived siblings,
   not it). Project views merge the two, project entries winning on id collisions; each file
   joins its view's fingerprint. Orphan reporting stays per-view (bare names shadowed by a
   collision rename are excluded), and coverage stays per-view: each view's uncategorized
   count nudges a `/skill-atlas` run from the place that can see those skills.
   Additionally the `SKILL_ATLAS_HOME` env var is REMOVED: artifacts always live in the
   `.claude/skill-atlas` of their scope; §3.4's "under SKILL_ATLAS_HOME" and §5's shard
   location now read `~/.claude/skill-atlas/`. Tests and dev/smoke_live.py isolate via
   `SKILL_ATLAS_CLAUDE_DIR` (smoke symlinks real inputs into a temp claude dir).
8. **Fully project-local — no global state at all (2026-08-08, user decision; supersedes the
   split in amendment 7).** Every artifact and curated file lives in
   `<scope>/.claude/skill-atlas/`, where the scope is the directory skill-atlas runs in:
   graph, atlas, catalog shards, a COMPLETE per-scope categories.json (its own taxonomy —
   scopes bootstrap independently and may diverge), config.json, dirty marker and debug log.
   Auto-init: an explicit build in any directory creates its atlas dir; the hooks operate only
   where that dir already exists and never initialize one (sessions in untouched directories
   stay untouched, and emit nothing). skill-search reads `./.claude/skill-atlas/catalog/` and
   never falls back to another directory. The dual-view machinery, the global/project curated
   split and the cross-view orphan rules are all deleted; `SKILL_ATLAS_HOME` stays removed and
   the previous global state was retired without migration (fresh start — each scope
   re-bootstraps autonomously on its next /skill-atlas run). Inputs are unchanged: discovery
   still reads the machine's plugins, user skills and settings from `~/.claude`.
9. **Measured token costs (M4, on the author's 45-skill / 10-category collection):**
   `_index.md` ≈ 650 tokens (above the §5 estimate — the derived token lists are what grew it),
   shards 160–1,040 tokens (largest: planning, 12 members). A search costs the index plus one
   shard ≈ 1.2–1.7k tokens, versus ~5k+ for a flat catalog read — the §5 arbitrage holds. The
   session index line measured 216 chars ≈ 54 tokens with all ten categories listed.

---

## 1. Purpose

Two facts about how Claude Code loads skills, both measured on the author's machine:

- An **enabled** skill costs ~48 tokens *every session*: its frontmatter description is injected
  into context at session start whether or not the skill is ever used. 27 enabled skills ≈ 1,200
  tokens per session (DESIGN.md §7.1).
- A **disabled** skill costs nothing and is completely invisible: the description is not
  injected, the Skill tool cannot invoke it, and the model does not know it exists. The
  `SKILL.md` is still on disk and still readable as a plain file.

Multi-plugin users sit on the wrong side of both facts at once. Plugins ship skills in bulk, so
a collection grows to 80–150 descriptions competing for context, several of which do essentially
the same thing — and the only native remedies are "pay for all of them every session" or "make
them cease to exist."

Phase 2 arbitrages the gap with a third tier between enabled and disabled: **searchable** —
skills that cost zero tokens per session but remain findable through a search skill and usable
by reading their `SKILL.md` directly. To make search work at that scale without re-injecting
every description at query time, the collection gets a **category catalog**: model-assigned
categories over skill descriptions, curated once by the user, then maintained incrementally.

**Honest scale note, in the spirit of DESIGN.md §6:** at the author's current scale (27 enabled,
~1,200 tokens) the savings are real but modest. The design pays for itself on collections of
80–150 skills, where injection cost reaches 4–7k tokens per session and near-duplicate skills
measurably confuse native selection. The justification is scale-dependent and this document says
so rather than implying otherwise.

### Non-goals

- No embeddings, no RAG over skill bodies. Search operates on descriptions and categories only.
- No editing of Claude Code's own config. skill-atlas never flips `enabledPlugins` — it observes
  `settings.json`; it does not write it.
- No model calls in hooks or in `build_graph.py` — the build stays offline, deterministic, free.
- No new hooks. The existing SessionStart / PostToolUse pair (DESIGN.md §5) is sufficient.
- No usage tracking. Still dead; see DESIGN.md §6.

---

## 2. The three-tier model

| Tier | In context? | Findable? | Invocable? | Cost / session |
| --- | --- | --- | --- | --- |
| **Enabled** | yes — description injected | natively | Skill tool | ~48 tokens each |
| **Searchable** | no | via the search skill | `Read` the SKILL.md, follow it | 0 |
| **Disabled** | no | **no** | no | 0 |

- **Enabled** is unchanged Claude Code behavior: the daily drivers, invoked natively with the
  full frontmatter machinery (allowed-tools, auto-triggering).
- **Searchable** is Phase 2's tier: plugins that are disabled in `settings.json` but opted in
  via skill-atlas's own config (§3.2). Search can serve them; the model uses them by reading the
  `SKILL.md` path and following it as plain instructions. This deliberately bypasses the plugin
  machinery and loses `allowed-tools` enforcement and auto-triggering — an accepted trade for
  zero standing cost.
- **Disabled and not opted in means disabled.** Search must never serve it. A plugin disabled
  because it is broken or unwanted does not come back through a side door.

Opt-in is **per-plugin** (§3.2). Note that standalone user/project skills have no disable toggle
in Claude Code — they are always loaded — so tier 2 is in practice a plugin-skill tier.

The tier is derived, never stored: `enabled` wins, then `searchable`, else off.

---

## 3. Data model

### 3.1 `categories.json` — curated state, not a cache

The first file in the system that is neither source nor derived artifact. DESIGN.md §2's rule —
*derived artifacts are rebuilt, never repaired* — explicitly does **not** apply here: a
regeneration would re-propose categories differently and would discard the user's one-time
approval and any hand-renames. Treat it like configuration you cannot cheaply recreate: back it
up, keep it in dotfiles if inclined.

```jsonc
{
  "version": 1,
  "taxonomy_approved_at": "2026-08-06",       // set once at bootstrap approval (§4.1); never cleared
  "taxonomy": [
    { "name": "planning",  "description": "breaking down, sequencing and estimating work" },
    { "name": "testing",   "description": "writing, running and structuring tests" }
    // ~8–12 entries; each description is one line — stage 1 of search reads these (§5)
  ],
  "assignments": {
    "mattpocock-skills:tdd": {
      "categories": ["testing", "engineering"],   // ordered — FIRST entry is the display home
      "desc_hash": "sha256:…",                    // hash of the skill description at assignment time
      "assigned_at": "2026-08-06"
    }
  }
}
```

Rules:

- **Assignments are keyed by node id** — the invocation string, including `@user`/`@project`
  disambiguation for name collisions (DESIGN.md §4.1).
- **`categories` is an ordered, non-empty list.** Multiple categories per skill are allowed and
  are a recall feature (§5); the first entry is the single place the renderer draws the node.
- **`desc_hash` makes staleness derivable.** The cache never stores a `stale` flag —
  `build_graph.py` compares the recorded hash against the current description at build time.
- **Written only through a validating helper** (schema check + atomic tmp-rename, same
  discipline as `atlas_io.py`). The model never free-hands this JSON.

### 3.2 `config.json` — the searchable opt-in

```jsonc
{
  "version": 1,
  "searchable_plugins": ["superpowers", "some-other-plugin"]
}
```

Per-plugin, nothing finer, on day one. A plugin listed here whose skills are disabled lands in
tier 2. Per-skill overrides are deferred until a real case demands them (§10).

### 3.3 `graph.json` additions — version 3

Per skill node:

| Field | Type | Meaning |
| --- | --- | --- |
| `categories` | `string[]` | ordered, from the cache; `[]` when no valid assignment exists — rendered and searched as the visible **uncategorized** bucket |
| `category_stale` | `bool` | assignment exists but `desc_hash` no longer matches; labels stay in effect (§4.3) |
| `searchable` | `bool` | plugin is in `searchable_plugins` (recorded even when `enabled` is also true; the tier derivation in §2 decides what it means) |

`stats` additions: `uncategorized`, `stale_categories`, `searchable`.

**Exit codes are untouched.** Uncategorized and stale are TODO states for the next
`/skill-atlas` run, not defects; exit 1 remains reserved for dangling references (DESIGN.md §4.2).

**The staleness fingerprint grows by two files.** DESIGN.md §5.1's argument for including
manifests applies verbatim: editing `categories.json` or `config.json` changes `graph.json`
while touching no `SKILL.md`, so both join the fingerprint and the §5.2 dirty-flag matchers.
Cost: two more `stat` calls.

### 3.4 File classes under `SKILL_ATLAS_HOME`

DESIGN.md §8 describes the artifact root as "derived files only." Phase 2 amends that — the
directory now holds three classes with three different loss semantics:

| File | Class | On corruption/loss |
| --- | --- | --- |
| `graph.json`, `atlas.html`, `catalog/` | derived | delete and rebuild — never repair |
| `categories.json` | **curated** | restore from backup; regeneration loses the approval |
| `config.json` | user config | user rewrites it; 5 lines |

---

## 4. Categorization — the single model moment

`build_graph.py` stays model-free forever, and is read-only toward `categories.json`. All
intelligence runs inside `/skill-atlas`, where a model is already present, already paid for,
and already reporting to the user. No API keys, no network in the build, no model calls in
hooks (a 10s hook timeout cannot fit one anyway).

`/skill-atlas` flow: run `build_graph.py` → read the uncategorized and stale lists from
`graph.json` → label them → write the cache through the validating helper → rebuild → report.

(A deterministic classifier that would auto-assign new skills at rebuild time was designed and
explicitly deferred — §10.6. First step keeps categorization in one place.)

### 4.1 Bootstrap — once

First run against an unapproved cache (`taxonomy_approved_at` absent): the model reads **all**
registered skill descriptions and proposes a taxonomy — target **8–12 categories**, each with a
one-line description — plus the full grouping, in the report. The user tweaks names and merges,
approves once; `taxonomy_approved_at` is set and the taxonomy is **frozen**. A model left
unsupervised will happily produce 20 categories for 41 skills; the approval step is where that
is caught, and the one-line category descriptions written here are load-bearing — they are what
search stage 1 reads (§5) and what keeps later incremental assignments consistent.

**Writing the category descriptions is the real work of bootstrap.** Each line does three jobs
at once: search stage 1 routes tasks by reading it, the model assigns every later skill by
matching against it, and the user approves the taxonomy by judging it. Rules of thumb,
mirroring §5.1's principles at the category level:

- describe the task shape in user-intent terms, not implementation terms;
- when two categories could be confused, let each description name its side of the boundary —
  "storing and querying data, *from any source*" is what lets a Slack-archiver skill land
  confidently in both `slack` and `databases` instead of guessing one;
- product-based categories are legitimate when a product dominates the collection (15 Slack
  skills earn a `slack` category); otherwise products share a capability bucket and product
  identity lives in the skill descriptions, where stage 2 can still see it;
- **concrete tokens beat abstractions** — tasks say "send a discord message", never "perform
  messaging", so the routing surface must contain the product words. But the curated sentence
  does *not* hand-enumerate them: a hand-written list rots the day a new Discord plugin joins
  the category. The sentence carries intent and boundary; the build derives the enumeration
  (§5).

### 4.2 Incremental — every run after

New skills are assigned **into the frozen taxonomy**. The model may propose a genuinely new
category only when nothing fits, and must flag it in the report for the user to accept or
reassign — silent taxonomy growth is how the category layout reshuffles under a search skill
that memorized last week's shape. Unchanged skills are never re-labeled.

Between runs, new skills sit visibly in the uncategorized bucket — and that bucket is not dead
air. **Search includes it** (§5): uncategorized skills remain findable, just via the expensive
flat path, and when search serves from that bucket the model's answer says so and suggests
running `/skill-atlas`. That in-the-moment suggestion, plus the index line's count (§6), is the
entire freshness mechanism — by choice, not omission.

### 4.3 Invalidation — stale, not dropped

When a description changes (an edit, a plugin update), the assignment's `desc_hash` stops
matching: `build_graph.py` marks the node `category_stale: true` **but the old labels stay in
effect**. Search keeps working on yesterday's categories; the next `/skill-atlas` run
re-confirms or moves the stale entries and reports what it did. The failure mode this buys:
a plugin update that rewords 15 descriptions changes nothing operationally, instead of dumping
15 skills out of the index until someone notices.

### 4.4 Freshness — why no new hooks

Skills arrive when a plugin is installed — a deliberate act, a few times a month, not a stream.
Structural freshness (a new skill appears in the graph as uncategorized) is already covered by
the existing Phase 1 hooks. Category freshness waits for the next explicit `/skill-atlas` run,
and the worst interim state is a skill sitting visibly in the uncategorized bucket — still
findable through search's uncategorized shard, with the suggestion to run `/skill-atlas`
delivered right where it's felt (§4.2). That is an acceptable staleness model for a monthly
event; it is not worth a resident model call anywhere.

### 4.5 Degradation — `/skill-atlas` is an optimizer, not a dependency

The governing rule: categorization improves search **economics**; its absence must never break
search **correctness**. The failure mode is "search got expensive," never "skills became
unfindable." Three scenarios:

- **Never run, nothing opted in.** Phase 2 is inert and the system *is* Phase 1: the existing
  hooks keep `graph.json` structurally fresh without a model, the atlas and dangling detection
  work unchanged, and nothing costs anything. Phase 2 is opt-in twice over (config **and** a
  categorization run); doing nothing is a supported state, not a broken one.
- **Opted in, never categorized** — the worst-value configuration, still functional. The long
  tail goes dark with no taxonomy behind it, so every skill sits in the uncategorized bucket
  and search degrades to browsing one flat shard: correct results at roughly the full-catalog
  token cost per search (~5k at 100 skills, versus ~700 with categories). The index line and
  every search answer that touches the bucket suggest the fix: the one-time bootstrap.
- **Run exactly once** — the gold state, decaying gracefully and *visibly*. Everything labeled
  at run #1 stays labeled forever: the taxonomy is frozen, and §4.3 keeps stale labels in effect
  indefinitely, so even description-rewording plugin updates change nothing operationally. Only
  skills installed *after* the run degrade, and only into the uncategorized bucket — findable,
  just expensively — accumulating at plugin-install pace. The index line's count and search's
  own suggestion tick the reminder until the next run.

Two commitments this forces on §5 and §6:

1. **`uncategorized` is a permanent, first-class bucket** — always present in the stage-1 index
   and always emitted as a shard, even when no taxonomy exists at all. Search must work against
   an empty `categories.json`.
2. **The index line carries the uncategorized count** — it is the one standing channel that
   makes decay visible and names the fix (`run /skill-atlas`) without a nag hook, a warning
   dialog, or any new machinery.

---

## 5. Search — second increment

A skill (always-enabled — the one fixed cost of the system) that finds the right skill for a
task across all three tiers, in two stages, without ever loading the full catalog:

1. **Pick a category.** Read the category index: taxonomy names, one-line descriptions, counts,
   and a **derived token list** per category — the member skills' plugin and skill names,
   appended automatically by the build so the concrete product words ("discord", "bigquery")
   are always present and always in sync with membership, with no curation (§4.1). ~10 lines,
   one per category:
   `messaging(14) — sending and reading messages across services — slack-tools, discord-kit, mail-helper`
   The model matches the task against these lines, not skill descriptions.
2. **Browse one shard.** Read `catalog/<category>.md` — that category's entries only (~10–15
   skills: id, description, path, tier). Rank matches; return the top few with their
   descriptions, paths and tiers.

The caller then invokes an enabled result natively, or `Read`s a searchable result's `SKILL.md`
and follows it. No match is a first-class answer: say so and proceed without a skill — never
force a fit.

- **Shards are derived artifacts**, emitted by the build from `graph.json` + `categories.json`
  into `SKILL_ATLAS_HOME/catalog/` — rebuild-never-repair class, deterministic, no model. A
  multi-category skill appears in every shard it belongs to; that overlap is the point.
- **`catalog/uncategorized.md` always exists** (§4.5), holding every skill with no valid
  assignment. It is the degraded-but-correct path when `/skill-atlas` has not (yet) run; it may
  be large, and search should say so when reading it rather than pretending it is cheap.
- **Multi-category is the recall mechanism.** Stage 1's pick doesn't have to be *the* right
  bucket, only *a* right one. Category counts consequently sum to more than the skill count —
  present them as overlapping, never as a partition.
- **Duplicates surface at decision time.** Near-identical skills share a category, so ranked
  multi-match results place them side by side exactly when one is about to be used. This is
  DESIGN.md §10.3's overlap detection, absorbed.
- **Token budget per search** (to be measured at M4): index ~150–300 tokens (the derived token
  lists are what grew it) + one shard ~500–800. Compare against the standing alternative — every searchable skill's description in
  every session — and the arbitrage holds as long as searches are occasional, which is the
  premise of the whole tier.

### 5.1 The search skill's own description

The searchable tier removes triggering from every skill inside it, so the system's entire
triggering burden funnels through this one frontmatter field — the most load-bearing 1,024
characters in the plugin. It is written to the trigger-optimization principles (imperative,
pushy about user intent, explicit about when it does **not** apply), and it is a starting
point, not a final answer: M4 validates it against a list of should-trigger and
shouldn't-trigger prompts and revises it on measurement, never on prose review.

```yaml
name: skill-search
description: >
  Find the best skill for the current task across the entire skill
  library, including the dormant majority whose descriptions are never
  loaded into context. Use this before starting any nontrivial task —
  coding, debugging, git operations, planning, reviewing, writing docs,
  building UI, handling data or config — even when no loaded skill seems
  relevant and even when the user does not name a tool or domain: the
  library usually holds a specialist that stays invisible until searched.
  Returns ranked matches with descriptions, paths and usage: invoke
  enabled matches with the Skill tool; for dormant matches, read the
  SKILL.md at the returned path and follow it. Skip only for trivial
  one-step requests, or when an already-loaded skill obviously covers
  the task.
```

Two deliberate choices. It names *generic* task shapes rather than the user's actual
categories — the description is static text in a SKILL.md, while the live category names and
counts travel in the index line (§6); the two are one triggering surface and are evaluated
together. And it spells out its own skip conditions — trivial one-step requests, tasks an
enabled skill already covers — because false triggers on the hot path are the cost side of
pushiness: a search that fires on "what's 2+2" burns more than it ever saves.

---

## 6. Session index line — third increment

With the long tail dark, nothing in context advertises that it exists — the failure mode that
silently degrades the system to "you have 12 skills" is the model simply never calling search.
Mitigation: the existing SessionStart hook additionally injects **one line**, ~40 tokens:

```text
Skill library: 87 dormant skills — planning(12), ui(9), cli(14), testing(11), …, 4 uncategorized. Call skill-search before nontrivial tasks.
```

When the uncategorized count is nonzero the line appends `— run /skill-atlas to categorize`.
It is a suggestion, never an instruction — the session is not asked to spend tokens on work
the user didn't request. Together with search's own in-answer suggestion (§4.2), this is the
sole nag channel for catalog decay — no nag hooks, no dialogs.

Built from `graph.json` stats — no model, no new hook, and it uses the documented SessionStart
stdout JSON contract that hook invariant 2 (DESIGN.md §5.4) already carves out. The line is the
visibility the searchable tier pays instead of ~48 tokens per skill.

Whether the model actually calls search when it should — the adoption question — is an open
measurement, not an assumption (§10).

---

## 7. Rendering

Phase 2 adds one real view and two channels:

### 7.1 The by-category view

A new default view of the atlas: **one hub node per category, with every member skill attached
to it as a connected node.**

- **Category hubs are synthesized at render time** from the skill nodes' `categories` field —
  they exist in the picture, never in `graph.json`. A hub is visually distinct from both skill
  and file nodes (larger, labelled `name (count)`), and an **`uncategorized` hub always
  renders** when its count is nonzero — same visible-state principle as everywhere else.
- **Membership is an edge.** Every skill links to *every* category it belongs to: the display
  home (`categories[0]`) with a solid edge, additional memberships with a lighter/dashed edge.
  A multi-category skill therefore hangs *between* its hubs — the force layout makes
  cross-category skills (`slack-db` between `slack` and `databases`) and same-bucket
  near-duplicates visually obvious with no extra machinery.
- **Skills only.** File nodes and `references` edges are hidden by default in this view (the
  existing toggle brings them back); the category view is about finding and comparing skills,
  not auditing their bundles.
- **Scope view survives as the first tab** — the Phase 1 clustering (user / project / plugin)
  remains for structural questions. The two views are tabs centred on the control bar, not a
  checkbox queued among the filters: swapping the whole picture is a different act from
  subtracting from it, and it only reads as the page's primary control if it sits apart from
  the filters — which have since moved behind a dropdown of their own.
- Hub-and-spoke also helps at scale: hubs anchor the layout, so the 200–600 node band
  (DESIGN.md §7.4) stays legible longer than free force-directed clustering does.

### 7.2 Channels

- **Uncategorized and stale are visible states** — the `uncategorized` hub collects the
  unlabeled; stale nodes get a marker.
- **Tier gets a channel** — enabled / searchable / off; searchable reuses the hollow-fill idea
  with a distinct stroke so it cannot be confused with plain disabled.

Beyond the view tabs, no new interaction machinery except a category filter in the existing
search box.

---

## 8. Build order and milestones

The user-chosen sequencing: **catalog first, search second, index line last.** Each milestone is
validated against the real collection, in the Phase 1 style — a milestone is done when the live
machine says so, not when the code compiles.

| # | Deliverable | Done when |
| --- | --- | --- |
| 1 | `categories.json` + `config.json` schemas, validating writer | Round-trips under the writer; malformed input is rejected, write is atomic |
| 2 | `build_graph.py` delta (merge, stats, fingerprint, v3) | Fixture skills carry categories; editing `config.json` alone triggers a rebuild on next session start; exit codes unchanged |
| 3 | `/skill-atlas` bootstrap + incremental categorization | Real collection fully labeled after one approved bootstrap; a subsequently added fixture skill is assigned into the frozen taxonomy with zero reshuffling of existing labels |
| 4 | Catalog shards + search skill (uncategorized shard included, with the run-`/skill-atlas` suggestion) | From a cold session, search finds a searchable-tier skill by task description and the model completes the task via `Read`; a search touching the uncategorized shard surfaces the suggestion; the §5.1 description holds up against a small should/shouldn't-trigger prompt list; per-search token cost measured and recorded here |
| 5 | Session index line | A fresh session's context contains the line at ≤ ~50 tokens with live counts |
| 6 | By-category view in `atlas.html` (§7.1) | Toggling to category view shows a hub per category with member skills attached; a multi-category fixture skill hangs between its hubs; the `uncategorized` hub appears when nonempty. Can land any time after M3 |

---

## 9. Deliberately not built

- **Auto-toggling `enabledPlugins`.** The obvious "one-click enable from the atlas" writes to
  Claude Code's config file; skill-atlas stays read-only toward `settings.json`. Recommend, never
  act.
- **Per-skill opt-in granularity** — per-plugin covers the install-shaped reality; revisit on a
  concrete case.
- **Embeddings or any content index.** Descriptions and categories carry the search; if they
  ever don't, the fix is better descriptions — which is a skill-authoring defect the atlas
  should *surface*, not paper over with retrieval.
- **A categorization hook.** No model runs outside `/skill-atlas`, ever.

---

## 10. Open questions

1. **Taxonomy governance after the freeze.** Renaming or merging categories is currently a
   hand-edit of curated state plus a re-run. Fine at 10 categories; a `/skill-atlas retag` flow
   is the likely shape if it ever isn't.
2. **Search adoption is unmeasured.** The index line is the mitigation for silent non-use, but
   whether the model reliably calls search before barehanded attempts needs observing once M4/M5
   land. If adoption is poor, the next lever is the search skill's own description, then a
   CLAUDE.md policy line — escalate only on evidence.
3. **Empty categories** after plugin removal: keep (stable taxonomy) or prune at the next
   `/skill-atlas` (tidy index)? Leaning keep — search stage 1 tolerates a zero count, and
   pruning reshuffles what the model memorized.
4. **Project views.** Phase 1 emits per-project graphs; Phase 2 should eventually facet the
   catalog the same way (a project's `enabledPlugins` overrides change tier derivation). Global
   catalog + global taxonomy first; project-faceted shards only after M4 proves the shape.
5. **Per-skill opt-out** inside an opted-in plugin ("all of X except Y") — deferred with §9's
   granularity decision.
6. **Deferred: a static classifier for new skills** (designed 2026-08-07, explicitly not
   first-step). After bootstrap the approved cache is labeled data, so a deterministic
   TF-IDF-style classifier inside `build_graph.py` could assign clearly-fitting new skills into
   the frozen taxonomy at rebuild time — confidence-gated, additive-only writes, marked
   provisional for `/skill-atlas` to confirm, with below-gate misfits escalating the index line
   to an in-session categorization instruction. Deferred until the first-step mechanism —
   uncategorized-included-in-search plus a suggestion to run `/skill-atlas` — proves annoying in
   practice; at plugin-install pace the bucket may never grow fast enough to justify it.

---

## 11. Privacy

Unchanged from Phase 1, and the standing rules (DESIGN.md §10.2) apply as written:
`~/.claude/projects` is never opened; `debug.log` gets path + line + exception type, never
content. New surfaces are benign — `categories.json` holds skill ids and category labels;
`catalog/` shards hold the same descriptions already present in `graph.json`. The §10.2 note
about real paths in shareable artifacts extends to shards.
