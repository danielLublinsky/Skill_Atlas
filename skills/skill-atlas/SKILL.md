---
name: skill-atlas
description: Graph, categorize and visualize the installed Claude Code skill collection. Use when the user asks about their skill atlas, skill graph, skill catalog, categorizing skills, making skills searchable, dangling or broken skills, disabled plugins, duplicate skill names, or wants to visualize/audit what skills are actually loadable. Triggers - "skill atlas", "skill graph", "map my skills", "categorize my skills", "skill catalog", "which skills are dead", "dangling skills", "audit my skills".
---

# skill-atlas

Builds a structural graph of every registered skill on this machine,
maintains a model-assigned category catalog over it, and renders both as a
self-contained HTML atlas. Discovery is manifest-driven
(installed_plugins.json → plugin.json → settings.json), so marketplace
catalogues, stale cached plugin versions and deprecated trees never pollute
the picture.

## How to run

All scripts live under `${CLAUDE_PLUGIN_ROOT}/scripts/` and are Python 3
stdlib-only:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_graph.py"   # → graph.json, exit 1 if dangling
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/categorize.py" status   # categorization TODO list
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/render.py"        # → atlas.html
```

Full flow: build → `categorize.py status` → categorize (below) → rebuild →
render → report. Both build and render produce the global view
(`~/.claude/skill-atlas/atlas.html`) and, when the current directory carries
its own `.claude/`, a **project view** at `.claude/skill-atlas/atlas.html`
(suggest gitignoring the derived files there — but NOT
`categories.json`, the project's curated categorization, which belongs in
version control).

## Categorization

All catalog writes go through `categorize.py` — never edit categories.json
free-hand. Exit 3 means the payload was rejected: stderr names every
violation; fix and retry.

- **`bootstrapped: false`** → bootstrap autonomously, no approval step. Read
  `status --full` (every id + description), draft 8–12 categories with
  one-line descriptions (user-intent task shapes; name the boundary between
  confusable categories; a product earns a category only when it dominates;
  never enumerate product words — the build derives token lists from
  membership), assign EVERY skill (ordered list, first = display home; the
  CLI rejects incomplete coverage — if nothing fits, the taxonomy is missing
  a category, so create it), and pipe
  `{"taxonomy": [...], "assignments": {id: [labels]}}` into
  `categorize.py bootstrap` via heredoc.
- **`bootstrapped: true`** → the taxonomy is frozen. Batch-assign the
  `uncategorized` list into it with `categorize.py assign`; when nothing
  fits, `categorize.py add-category <name> "<desc>"` then assign — and call
  the addition out prominently in the report. For `stale` entries re-read
  the description: labels still right → `categorize.py confirm <ids…>`,
  wrong → reassign. Never touch unchanged skills. **A run must end with
  zero uncategorized skills** — uncategorized is a transitional state
  between runs, never an acceptable end state.
- **Project skills are categorized too.** categorize.py follows the view
  automatically: run from a project directory it operates on that
  project's graph, so project-scope skills and collision-renamed ids
  (`name@user` / `name@project`) are assigned like any other skill.

## Interpreting exit codes

- `0` — built, nothing dangling.
- `1` — built AND at least one defect: a broken bundled-file reference, or a
  mention of an unregistered/disabled skill. **Report each finding** — these
  are real defects. Uncategorized/stale counts are NOT defects, only TODO
  states for categorization.
- `2` — build failed. If stderr names categories.json/config.json
  violations, that is curated state failing loud: report the violations,
  offer to fix the file or `categorize.py import <path>` a corrected one.
  Otherwise check stderr and `~/.claude/skill-atlas/debug.log`.

## Contract

- Reads only skill files and manifests. It never reads session transcripts
  and records no usage data.
- `graph.json`, `atlas.html` and `catalog/` are derived caches — safe to
  delete, always rebuildable.
- **`categories.json` is curated state — the one exception to
  rebuild-never-repair.** Never delete or regenerate it; regeneration
  discards the frozen taxonomy and every assignment. Suggest backing it up.
  It is split per scope: the global file (`~/.claude/skill-atlas/`) holds
  the taxonomy plus user/plugin assignments; each project's
  `.claude/skill-atlas/categories.json` holds only that project's
  view-local assignments (no taxonomy) and travels with the repo.
  `config.json` is user config (the searchable-plugins opt-in, global).
- The taxonomy freezes at bootstrap. Renaming or merging categories is a
  hand-edit of categories.json (taxonomy AND assignments) validated via
  `categorize.py import`, followed by a rebuild.
- skill-atlas never writes Claude Code's own config — recommend enabling a
  plugin, never flip `enabledPlugins` itself.
- The atlas shows structure only (what is loadable, what is broken). Do NOT
  tell the user which skills are unused or "dead" — the tool does not
  measure usage, deliberately (DESIGN §6).
