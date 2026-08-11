# 1 — Overview

## What this is

A Claude Code plugin that reads the machine's **skill manifests** and turns them
into three things:

1. a structural **graph** of every registered skill (`graph.json`),
2. a **category catalog** over that graph (`catalog/*.md`) that a search skill
   queries in two cheap reads,
3. a self-contained **visualization** (`atlas.html`).

The problem it solves: Claude Code injects every *enabled* skill's description
into every session (~48 tokens each), and a *disabled* skill is invisible.
Skill Atlas adds a third tier between them.

| Tier | Description in context? | Findable? | How it is used | Cost/session |
| --- | --- | --- | --- | --- |
| **enabled** | yes | natively | `Skill` tool | ~48 tokens |
| **searchable** | no | via `skill-search` | `Read` the SKILL.md, follow it as instructions | 0 |
| **disabled** | no | **no** | not at all | 0 |

A plugin is **searchable** only when *both* halves hold: Claude Code has it
disabled (`settings.json`) **and** this scope opted it in (`config.json`). The
tier is always derived, never stored — `enabled` wins, then `searchable`, else
off ([atlas_annotate.py:27](../scripts/atlas_annotate.py#L27),
[atlas_shards.py:42](../scripts/atlas_shards.py#L42)).

## Pipeline

```text
  INPUTS (read-only, never written)
  ~/.claude/plugins/installed_plugins.json
  <installPath>/.claude-plugin/plugin.json          ┌─────────────────┐
  ~/.claude/settings*.json + <scope>/.claude/…  ──▶ │  atlas_discovery│
  ~/.claude/skills/*/SKILL.md                       │  + atlas_paths  │
  <scope>/.claude/skills/*/SKILL.md                 └────────┬────────┘
                                                             │ skill records
  CURATED (hand-editable, committed)                         ▼
  <scope>/.claude/skill-atlas/categories.json ──▶ ┌──────────────────────┐
  <scope>/.claude/skill-atlas/config.json     ──▶ │    build_graph.py    │
                                                  │  atlas_extract edges │
                                                  │  atlas_annotate tier │
                                                  └───────┬──────────────┘
                                                          ▼
                                                      graph.json
                                                    ╱      │      ╲
                                          atlas_shards  render.py  categorize.py
                                                ▼          ▼          │
                                          catalog/*.md  atlas.html    ╰─▶ writes
                                                ▲                        categories.json
                                                │                        then re-derives
                                          skill-search                   graph + catalog
```

Every arrow above is offline, deterministic and stdlib-only. **No model runs
anywhere in this pipeline** except inside the `/skill-atlas` command, where a
model drafts the taxonomy and assigns skills through the `categorize.py` CLI.

## Module map

| File | Role |
| --- | --- |
| [scripts/atlas_paths.py](../scripts/atlas_paths.py) | every path, env var, settings merge; the scope concept |
| [scripts/atlas_io.py](../scripts/atlas_io.py) | atomic writes + the one guarded logger |
| [scripts/atlas_discovery.py](../scripts/atlas_discovery.py) | manifest-driven walk → skill records, ids, collisions |
| [scripts/atlas_extract.py](../scripts/atlas_extract.py) | `references` / `mentions` extraction from SKILL.md bodies |
| [scripts/atlas_fingerprint.py](../scripts/atlas_fingerprint.py) | stat-only staleness hash |
| [scripts/atlas_categories.py](../scripts/atlas_categories.py) | curated-state schema, validation, validating writer |
| [scripts/atlas_annotate.py](../scripts/atlas_annotate.py) | shared category/tier annotation + derived stats |
| [scripts/atlas_shards.py](../scripts/atlas_shards.py) | `graph.json` → `catalog/_index.md` + shards |
| [scripts/build_graph.py](../scripts/build_graph.py) | **entry point** — the full build |
| [scripts/categorize.py](../scripts/categorize.py) | **entry point** — the CLI the model drives |
| [scripts/render.py](../scripts/render.py) | **entry point** — `graph.json` → `atlas.html` |
| [scripts/check_stale.py](../scripts/check_stale.py) | **hook** — SessionStart rebuild + index line |
| [scripts/mark_dirty.py](../scripts/mark_dirty.py) | **hook** — PostToolUse dirty flag |
| [scripts/template/atlas_template.html](../scripts/template/atlas_template.html) | the visualization (D3 + placeholders) |
| [skills/](../skills/), [commands/](../commands/) | the agent-facing surface: 2 skills, 2 slash commands |

## The three file classes

They live side by side in `<scope>/.claude/skill-atlas/` and have **different
loss semantics**. Confusing them is the most damaging mistake available here.

| File | Class | If lost or corrupt |
| --- | --- | --- |
| `graph.json`, `atlas.html`, `catalog/` | derived | delete and rebuild — **never repair** |
| `categories.json` | **curated** | restore from backup; regeneration destroys the frozen taxonomy and every assignment |
| `config.json` | user config | user rewrites it (a few lines) |
| `graph.dirty`, `debug.log` | transient | ignore |

## Invariants

Break one of these and something else in the system quietly stops being true.

1. **Inputs are manifests and skill files only.** `~/.claude/projects` (session
   transcripts) is never opened, and no usage is measured — deliberately
   (DESIGN §6). Never tell a user which skills are "unused" or "dead".
2. **Never write Claude Code's own config.** `settings.json` is read-only to the
   build and the hooks. The single exception is
   [`/skill-atlas:edit-searchable`](../commands/edit-searchable.md), where
   disabling a plugin *is* the user's confirmed selection.
3. **`debug_log()` records path + line + exception *type name* only** — never a
   message, never file content ([atlas_io.py:45](../scripts/atlas_io.py#L45)).
   That is the privacy boundary; it holds no matter what future inputs get
   parsed.
4. **Hooks always exit 0, never block, never print outside the documented JSON
   contract.** A slow hook is worse than a stale graph.
5. **Every artifact write is atomic** (temp file + `os.replace`) — concurrent
   builds give last-writer-wins, never a torn file.
6. **Curated state fails loud.** An invalid `categories.json` / `config.json`
   fails the build with exit 2 and every violation named; it is never
   tolerated-and-degraded, and never regenerated.
7. **Environmental drift is not an error.** An assignment whose skill left the
   graph (`orphan_assignments`) and a stale `desc_hash` are reported states, not
   failures.
8. **Tier-off skills never reach `catalog/`.** A plugin the user disabled and
   did not opt in must not come back through a side door.
9. **Scopes are independent worlds.** Nothing is global; nothing falls back to
   another directory's atlas.

## Where to go next

Working on the build path? → [3](3-discovery.md), [4](4-graph-build.md).
Working on categories or search? → [5](5-categorization.md), [6](6-catalog-and-search.md).
Working on the page? → [7](7-rendering.md). Hooks? → [8](8-freshness-and-hooks.md).
