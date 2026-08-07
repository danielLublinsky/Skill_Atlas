---
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
---

# skill-search

Two-stage search over the skill catalog. Total budget: the index plus at
most two shards — never read the whole catalog.

## Locate the catalog

`~/.claude/skill-atlas/catalog/`. If `catalog/_index.md` does not exist, say
search is unavailable, suggest running `/skill-atlas`, and proceed without a
skill.

## Stage 1 — pick a category

Read `catalog/_index.md` ONLY (~10 lines). Each line is
`name(count) — what the category covers — concrete member tokens`. Match the
task against the descriptions and tokens; pick ONE category — two at most.
Counts overlap (a skill can live in several categories), so the pick doesn't
have to be *the* right bucket, only *a* right one.

## Stage 2 — browse one shard

Read `catalog/<category>.md` ONLY. Entries are
`## <id> [enabled|searchable]` + description + path. Rank against the task
and return the top 1–3 matches with id, description, path and tier. When two
results are near-identical, present them side by side and say so — surfacing
duplicates at decision time is a feature.

## Using a result

- **[enabled]** — invoke it natively with the Skill tool.
- **[searchable]** — the skill is dormant: Read the SKILL.md at the listed
  path and follow it as plain instructions. Frontmatter `allowed-tools`
  enforcement and auto-triggering do NOT apply on this path; apply judgment.
- Never hunt for SKILL.md files outside `catalog/` — a skill absent from
  every shard is disabled by choice and must not come back through a side
  door.

## The uncategorized shard

When no category fits, or the index shows a nonzero `uncategorized(N)` worth
checking, read `catalog/uncategorized.md` — note it may be large. Whenever
you serve a result from it, say so and suggest running `/skill-atlas` to
file the stragglers.

## No match

A first-class answer: say no skill fits and proceed without one. Never force
a fit.
