# 6 — Catalog and search

**Files:** [atlas_shards.py](../scripts/atlas_shards.py) (emitter),
[skills/skill-search/SKILL.md](../skills/skill-search/SKILL.md) (the query
protocol), [check_stale.py:30](../scripts/check_stale.py#L30) (the session index
line). **Tests:** [test_shards.py](../tests/test_shards.py).

This is the component the whole three-tier idea exists for: making dormant
skills findable without paying for them.

## The arbitrage

Loading every dormant description into every session is the thing being avoided.
Loading the whole catalog at query time would just move that cost to the query.
So the catalog is **sharded**, and a search reads exactly two files:

```text
task ──▶ catalog/_index.md          (one line per category)
      ──▶ catalog/<category>.md     (that category only)
      ──▶ one named match, then the task continues
         the other shards are never opened
```

Measured on a 70-skill / 13-category collection (2026-08-14):

| | tokens |
| --- | --- |
| `skill-search` SKILL.md body | 417 |
| `_index.md` | 1,591 — category descriptions 944, token lists 438, names 87 |
| one category shard | 361–1,623 (median ~600) |
| **one search** | **~2,400**, paid only when a search happens |
| session index line | ~54, standing |

**Be honest about the baseline.** The alternative worth comparing against is not
a flat read of all 13 shards (~12.5k) — nobody would do that. It is *loading
every catalog description into context at startup*, which is ~4,300 tokens
**once**. Against that, the arbitrage breaks even at roughly **two searches per
session**. It improves as the library grows and the index stays bounded; it is
thin at this size, and the honest reason to keep it is that the standing cost is
paid in *every* session including the ones that never search.

Two known levers were measured and deliberately left alone (2026-08-14):

- **Category descriptions, 944 tokens** — the single largest line item, ~290
  chars each where ~140 would route as well. Cutting them means regenerating
  `categories.json`, which is model-owned and frozen. Deferred, not dismissed.
- **`_token_list` truncation** — four index lines hit `TOKEN_BUDGET_CHARS` and
  end in `…`, hiding real skill names (`update-config` among them), because
  plugin names are emitted first and `mattpocock-skills` alone occupies a slot
  on 10 of 12 lines. Every variant tested (drop plugins, raise the cap, keep
  only single-category plugins) landed within ~100 tokens of the others, so the
  change was judged not worth the churn. Search compensates in the prompt
  instead: a token-list *miss* is defined as evidence of nothing.

## Emission

[`emit(graph)`](../scripts/atlas_shards.py#L76) is called by every writer of
`graph.json` — the full build, the SessionStart rebuild, and `categorize.py`'s
refresh. It derives **everything from `graph.json` alone** (v3 nodes carry
categories, tier and staleness, and the graph carries the frozen taxonomy), so
there is one source of truth and no second read of `categories.json`.

Properties to preserve:

- **Deterministic** — entries sorted by id, no timestamps. Re-emitting identical
  inputs produces byte-identical files.
- **Fully derived** — which licenses deleting shards whose category no longer
  exists ([atlas_shards.py:121](../scripts/atlas_shards.py#L121)).
- **Tier rule: tier-off skills are excluded at emit time**
  ([`_catalog_skills`](../scripts/atlas_shards.py#L34)). If an entry is in a
  shard, search will eventually serve it — so a disabled-and-not-opted-in plugin
  must never appear. This is the side door that stays shut.
- **`uncategorized.md` is always emitted**, even against an empty taxonomy.
  Search degrades to a flat shard; it never breaks.
- A multi-category skill appears in **every** shard it belongs to. That overlap
  is the point, not redundancy.

### `_index.md`

```text
# skill catalog index
<!-- derived by skill-atlas; do not edit. Counts overlap … -->

testing-and-verification(3) — proving behaviour is correct … — superpowers, tdd, …
uncategorized(2) — skills not yet categorized; run /skill-atlas to file them
```

Each line is `name(count) — curated description — derived token list`. The
**token list** ([`_token_list`](../scripts/atlas_shards.py#L46)) is member plugin
names then skill names, capped at `TOKEN_BUDGET_CHARS = 200` with an ellipsis.
It is derived, never curated — tasks say "send a discord message", never
"perform messaging", so the routing surface must contain the product words, and
deriving them keeps them in sync with membership forever.

### `<category>.md`

```text
## <node id> [enabled|searchable] (stale)
<description>
- path: /abs/path/to/SKILL.md
- also in: other-category, third-category
```

`- also in:` lists the skill's *other* categories — the cross-reference that
makes near-duplicates visible.

## The search protocol

[skill-search](../skills/skill-search/SKILL.md) is the one always-enabled cost of
the system. Its contract:

1. **Locate** `./.claude/skill-atlas/catalog/` — project-local, relative to the
   cwd. No `_index.md` here means this directory has no atlas: say search is
   unavailable, suggest `/skill-atlas`, and proceed without a skill. **Never
   fall back to another directory's catalog.**
2. **Stage 1** — read `_index.md` *only*. The category description decides, and
   its `…; see <other>` carve-out is the strongest routing signal in the file.
   The token list only corroborates: because it truncates, a hit favours a
   category and a **miss proves nothing** — no category may be ruled out on it.
   Counts overlap, so the pick does not have to land on *the* right bucket, only
   *a* right one.
3. **Stage 2** — read `catalog/<category>.md`. One shard is the norm. A second
   is opened *only* when the winning entry's `also in:` names a category not yet
   read, or when nothing rose above weak — never a third. Prefer specific over
   broad; near-identical entries are resolved silently (`[enabled]` first, then
   the sharper description) rather than presented for the user to arbitrate.
4. **Say the name, then work** — the search emits exactly one line,
   `Using <id>.` or `No skill fits — proceeding without one.`, and the task
   continues in the same turn. No narration of the search, no category or shard
   names, no runners-up, no echoed paths, no permission request, no summary.
   Search is a lookup inside the task, not a deliverable.
5. **Using a result:** `[enabled]` → invoke natively with the `Skill` tool.
   `[searchable]` → the skill is dormant: `Read` the SKILL.md at the listed path
   and follow it as plain instructions. On that path frontmatter `allowed-tools`
   enforcement and auto-triggering **do not apply** — an accepted trade for zero
   standing cost.
6. **Never hunt for SKILL.md files outside `catalog/`.** A skill absent from
   every shard is disabled by choice.
7. Serving from `uncategorized.md` → say so and suggest `/skill-atlas`. It
   counts against the shard budget.
8. **"No skill fits" is a first-class answer.** Never force a fit.

### The description is the whole triggering surface

The searchable tier removes triggering from every skill inside it, so the
system's entire triggering burden funnels through `skill-search`'s frontmatter
description — the most load-bearing text in the plugin. It deliberately names
*generic* task shapes rather than the user's actual category names (those live
in the index line, which is live; the description is static), and it spells out
its own **skip** conditions, because a search that fires on "what's 2+2" burns
more than it ever saves.

`test_skill_search_frontmatter` guards that this description stays within the
1,024-character frontmatter limit and keeps its shape.

## The session index line

With the long tail dark, nothing in context would advertise that it exists. The
SessionStart hook injects one line built from `stats.catalog` alone
([`index_line`](../scripts/check_stale.py#L30)):

```text
Skill library: 48 dormant skills — tooling-and-environment-setup(8), …, 2 uncategorized. Call skill-search before nontrivial tasks. Run /skill-atlas to categorize.
```

- **Silent when nothing is dormant.** The line pays for the searchable tier; an
  inert scope stays byte-identical to Phase 1 — empty stdout.
- Categories are sorted by count (descending, then name) and truncated with `…`
  at `LINE_BUDGET_CHARS = 220`.
- The `Run /skill-atlas to categorize` nag appears only when the uncategorized
  count is nonzero. It is a **suggestion, never an instruction** — the session is
  not asked to spend tokens on work the user did not request.

Together with search's own in-answer suggestion, this is the *sole* nag channel
for catalog decay. No nag hooks, no dialogs.

## Degradation ladder

The governing rule: categorization improves search **economics**; its absence
must never break search **correctness**. The failure mode is "search got
expensive", never "skills became unfindable".

| State | Behaviour |
| --- | --- |
| never run, nothing opted in | Phase 2 inert; the system *is* Phase 1. Supported, not broken. |
| opted in, never categorized | every skill sits in `uncategorized.md`; correct results at roughly full-catalog cost. The index line names the fix. |
| run exactly once | the gold state, decaying visibly: everything labeled stays labeled (frozen taxonomy + stale-keeps-labels); only skills installed *since* degrade, into the uncategorized bucket. |
