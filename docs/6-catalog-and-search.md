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
task ──▶ catalog/_index.md          (~650 tokens, ~14 lines: one per category)
      ──▶ catalog/<category>.md     (~160–1,040 tokens: that category only)
      ──▶ ranked matches
         the other shards are never opened
```

Measured on a 45-skill / 10-category collection: **~1.2–1.7k tokens per
search**, against ~5k+ for a flat catalog read. Paid only when a search actually
happens. The session index line costs ~54 tokens standing.

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
2. **Stage 1** — read `_index.md` *only*. Pick **one** category, two at most.
   Counts overlap, so the pick does not have to land on *the* right bucket, only
   *a* right one.
3. **Stage 2** — read `catalog/<category>.md` *only*. Rank and return the top
   1–3 with id, description, path and tier. Near-identical results are presented
   side by side, deliberately — surfacing duplicates at decision time is a
   feature.
4. **Using a result:** `[enabled]` → invoke natively with the `Skill` tool.
   `[searchable]` → the skill is dormant: `Read` the SKILL.md at the listed path
   and follow it as plain instructions. On that path frontmatter `allowed-tools`
   enforcement and auto-triggering **do not apply** — an accepted trade for zero
   standing cost.
5. **Never hunt for SKILL.md files outside `catalog/`.** A skill absent from
   every shard is disabled by choice.
6. Serving from `uncategorized.md` → say so and suggest `/skill-atlas`.
7. **"No skill fits" is a first-class answer.** Never force a fit.

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
