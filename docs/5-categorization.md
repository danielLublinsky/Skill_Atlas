# 5 — Categorization

**Files:** [atlas_categories.py](../scripts/atlas_categories.py) (schema +
validating writer), [categorize.py](../scripts/categorize.py) (the CLI),
[atlas_annotate.py](../scripts/atlas_annotate.py) (shared derivation).
**Agent-facing:** [skills/skill-atlas/SKILL.md](../skills/skill-atlas/SKILL.md).
**Tests:** [test_categories.py](../tests/test_categories.py),
[test_categorize_flow.py](../tests/test_categorize_flow.py).

## The one model moment

`build_graph.py` is **model-free forever** and read-only toward
`categories.json`. All intelligence runs inside `/skill-atlas`, where a model is
already present and already reporting to the user. No API keys, no network in
the build, no model calls in hooks (a 10 s hook timeout could not fit one
anyway).

The model **never free-hands the JSON**. Every mutation goes through
`categorize.py`, which validates against both the schema and the current graph
before an atomic replace.

## `categories.json` — curated state

The one file in the system that is neither source nor derived artifact.
*Rebuild-never-repair does not apply to it.* Regeneration would re-propose
categories differently and discard the frozen taxonomy plus every assignment.
Each scope carries its own complete file; commit it with the repo.

```jsonc
{
  "version": 1,
  "taxonomy_approved_at": "2026-08-07",     // set once at bootstrap; never cleared
  "taxonomy": [
    { "name": "testing", "description": "writing, running and structuring tests" }
  ],
  "assignments": {
    "mattpocock-skills:tdd": {
      "categories": ["testing", "engineering"],  // ordered — FIRST is the display home
      "desc_hash": "sha256:…",                   // of the description at assignment time
      "assigned_at": "2026-08-07"
    }
  }
}
```

Rules enforced by [`validate_categories`](../scripts/atlas_categories.py#L69):

- keyed by **node id**, disambiguated forms (`name@user`) included;
- `categories` is an ordered, **non-empty** list; every label must exist in the
  taxonomy; no duplicates within an entry;
- category names match `^[a-z0-9][a-z0-9-]*$`, are unique, and `uncategorized`
  is **reserved** (it is the always-present derived bucket);
- each category description is a **non-empty single line**;
- **unknown keys are violations** — a typo like `"asignments"` must fail loud,
  not silently empty the catalog.

`config.json` gets the same treatment
([`validate_config`](../scripts/atlas_categories.py#L166)):

```jsonc
{ "version": 1, "searchable_plugins": ["superpowers", "mattpocock-skills"] }
```

Opt-in is **per-plugin**, not per-skill. A name here may be either the bare
plugin name or its composite `<name>@<marketplace>` key
([atlas_annotate.py:28](../scripts/atlas_annotate.py#L28)).

## Loud vs. tolerated

The boundary matters and is easy to get backwards:

| Situation | Handling |
| --- | --- |
| schema violation in a curated file | **exit 2**, every violation named, file untouched |
| assignment for a skill no longer in the graph | `orphan_assignments` — reported, skipped |
| `desc_hash` no longer matches the description | `category_stale: true`, **labels stay in effect** |
| an opt-in naming no installed plugin | `orphan_opt_ins` in `config --list` |

Staleness keeps working on yesterday's categories on purpose: a plugin update
that rewords 15 descriptions then changes nothing operationally, instead of
dumping 15 skills out of the index until someone notices.

`desc_hash` is computed by one shared function
([atlas_categories.py:44](../scripts/atlas_categories.py#L44)) so writer and
build can never disagree about what "stale" means.

## The CLI

```bash
python3 scripts/categorize.py [--cwd DIR] <subcommand>
```

| Subcommand | Input | Effect |
| --- | --- | --- |
| `status [--full]` | — | machine-readable state as JSON |
| `bootstrap` | stdin `{"taxonomy": [...], "assignments": {id: [labels]}}` | one-time: freeze the taxonomy + assign everything |
| `assign` | stdin `{"assignments": {id: [labels]}}` | assign into the frozen taxonomy |
| `confirm <id>…` | args | refresh `desc_hash`, keep labels |
| `add-category <name> <desc>` | args | append one category to the frozen taxonomy |
| `import <path>` | file | validate and install a hand-edited/downloaded `categories.json` |
| `config --show / --list / --add-searchable P / --remove-searchable P` | args | the searchable opt-in |

Payload-taking subcommands read JSON on **stdin** (heredoc-friendly under the
command's `Bash(python3:*)` grant).

### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | success (warnings may still appear on stderr) |
| 2 | **environment** problem: no `graph.json`, or invalid curated state already on disk |
| 3 | **this payload** was rejected — violations one per line on stderr; fix and retry |

The 2-vs-3 split is the useful part: 3 means *change what you are sending*, 2
means *the world is wrong, stop and report*.

### `status` output

[categorize.py:206](../scripts/categorize.py#L206) returns `bootstrapped`, the
taxonomy, `counts`, the full `uncategorized` and `stale` lists (each with
descriptions and tier), `orphan_assignments`, and `config`. When the scope is
**not** bootstrapped it automatically includes every registered skill's id and
description, so the bootstrap flow needs no second call.

## Bootstrap — once per scope

Runs **autonomously; there is no approval step** (DESIGN-PHASE2 §0 amendment 1).
The taxonomy still freezes — for search stability, not approval.

Requirements enforced by [`cmd_bootstrap`](../scripts/categorize.py#L250):

- **full coverage is mandatory** — a payload that leaves any registered skill
  unassigned is rejected with the missing ids named and **nothing is written**.
  If nothing fits a skill, the taxonomy is missing a category; add one.
- unknown ids are rejected; unknown labels are rejected;
- the taxonomy is validated *alone first*, so a malformed taxonomy reports as
  itself instead of as a cascade of "label not in taxonomy" errors;
- 8–12 categories is the design target — outside it you get a warning, not a
  rejection;
- the file is written **exactly once**: a rejected payload never leaves behind a
  frozen taxonomy with zero assignments.

**Writing the category descriptions is the real work.** Each line does three
jobs: search stage 1 routes tasks by reading it, the model assigns every later
skill by matching against it, and the user judges the taxonomy by it. Rules:

- describe the **task shape in user-intent terms**, not implementation terms;
- when two categories could be confused, let each description **name its side of
  the boundary**;
- a product earns its own category only when it **dominates** the collection;
  otherwise product identity lives in the skill descriptions, where stage 2 can
  still see it;
- **do not enumerate product/tool words** — the build derives token lists from
  membership automatically, and a hand-written list rots the day a new plugin
  joins the category.

**Assignment carries the search-safety load.** Stage 1 picks ONE shard from
one-line descriptions — a lossy guess — and the designed defense is overlap:
a skill present in every shard a plausible pick lands on makes the wrong-twin
pick harmless. Overlap that exists only where it doesn't matter is the failure
mode (measured 2026-08-11, DESIGN-ISSUES issue 3). Rules:

- **multi-home across confusable boundaries** — assign each skill to every
  category a realistic task needing it would plausibly route to, home first.
  The boundary clauses in the descriptions mark exactly the pairs to sweep: a
  boundary worth disclaiming in prose is a boundary whose straddling skills
  belong on both sides (a debugging methodology also lives in testing,
  because "my tests are failing" is a debugging task phrased as testing);
- a second home requires a **realistic task phrasing**, not a conceptual
  relation — when most skills sit in 3+ categories, shards bloat back toward
  the flat catalog the system exists to avoid;
- a **platform-locked** skill stays in its platform category — generic
  wording in its description ("theme", "tokens", "design") must not pull it
  into generic categories where it is dead weight for every non-platform
  task.

## Incremental — every run after

The taxonomy is frozen; unchanged skills are **never re-labeled**.

- `uncategorized` ids → match against the frozen descriptions, batch into **one**
  `assign` call, multi-homed by the same boundary rule as bootstrap.
- Nothing fits → `add-category`, then assign, and **call the addition out
  prominently in the report**. Silent taxonomy growth is how the category layout
  reshuffles under a search skill that memorized last week's shape.
- `stale` ids → re-read the current description. Labels still right → batch into
  `confirm`. Wrong → include in the `assign` payload with new labels.
- **A run must end with zero uncategorized skills.** Uncategorized is the
  transitional state between runs, never an acceptable end state.

## The derived refresh

Every state-changing subcommand finishes by re-deriving everything itself
([`_refresh_derived`](../scripts/categorize.py#L157)) — there is **no
post-categorize rebuild** in the flow (`/skill-atlas` is build → categorize →
render). The refresh:

1. re-annotates the graph's registered skill nodes from the new curated state,
2. updates `taxonomy` and the derived stats,
3. **recomputes the source fingerprint** — `categories.json` is a manifest
   input, so without this every next SessionStart would see a mismatch and
   full-rebuild,
4. rewrites `graph.json` and re-emits `catalog/`,
5. prints the `catalog:` summary line the flow checks.

`graph.dirty` is deliberately left alone — a refresh is not a re-discovery, and
clearing the flag could swallow a concurrent skill edit.

A refresh failure **warns instead of failing the command**
([`_finish`](../scripts/categorize.py#L181)): the curated write already landed
and is the source of truth, so failing would push the caller into retrying a
write that now reports "already bootstrapped". The next SessionStart self-heals
via the fingerprint mismatch.

Known accepted window: a `SKILL.md` edited externally *between* build and
refresh gets its new mtime baked into the recomputed fingerprint while the graph
still carries the old parse — hidden until the next change. In-session edits
stay covered by the `mark_dirty` hook.

## Changing the taxonomy after the freeze

Renaming or merging categories is a **hand-edit of `categories.json` (taxonomy
*and* every affected assignment)**, validated by `categorize.py import`, which
warns about orphaned and uncovered skills but rejects only true schema
violations. The long-term plan is editing in the atlas page with a download —
`import` is the validated landing pad for that (DESIGN-PHASE2 §0 amendment 3).
