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
  Also use when asked whether a skill exists for something. Returns one
  match: invoke it with the Skill tool if enabled, otherwise read the
  SKILL.md at the returned path and follow it. Skip only for trivial
  one-step requests, or when an already-loaded skill obviously covers
  the task.
---

# skill-search

Read `_index.md`, then **one** shard, from `./.claude/skill-atlas/catalog/`
(cwd-relative). Missing → say search is unavailable, suggest `/skill-atlas`,
work without a skill; never use another directory's catalog.

## 1 — category

Index lines are `name(count) — description — tokens`. The description decides;
its `…; see <other>` carve-out is the strongest signal — treat it as routing.
Tokens only corroborate: the list truncates, so a hit favours a category and a
miss proves nothing. Counts overlap; *a* right bucket suffices.

## 2 — shard

Entries are `## <id> [enabled|searchable] (stale)`, description, path, and
`also in:` — its other categories, where a sharper sibling may live. Prefer
specific over broad; between near-identical entries take `[enabled]`, then the
sharper description, silently.

A second shard only if the winner's `also in:` names an unread category, or
nothing rose above weak. Never a third. `uncategorized.md` counts; serving from
it, say so and suggest `/skill-atlas`.

## 3 — name it, then work

One line, then continue the task in the same turn:
`Using <id>.` — or `No skill fits — proceeding without one.`

Nothing else, ever: never narrate the search, name a category or shard, list
runners-up, echo a path, announce intent, ask permission, or summarise after.
Reading a `[searchable]` SKILL.md is internal work.

## Using it

`[enabled]` → Skill tool. `[searchable]` → Read that path and follow it as
plain instructions; `allowed-tools` and auto-triggering do not apply. Never
look outside `catalog/` — absent from every shard means disabled by choice, and
"no skill fits" is a first-class answer. Never force one.
