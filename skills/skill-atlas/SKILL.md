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

Full flow: build → `categorize.py status` → categorize (below; each write
refreshes graph + catalog itself) → render → report. Everything is **fully
project-local**: all artifacts and curated state live in
`./.claude/skill-atlas/` of the directory you run in (auto-created on first
build — any directory becomes an atlas scope by running this), covering the
machine's plugins + user skills + this directory's own `.claude/skills/`.
Different directories are independent worlds with independent taxonomies.
The first build drops a `.gitignore` inside the atlas dir covering the
derived files (`graph.json`, `atlas.html`, `catalog/`, `graph.dirty`,
`debug.log`) — commit it together with `categories.json`: the curated
categorization belongs in version control.

## Categorization

All catalog writes go through `categorize.py` — never edit categories.json
free-hand. Exit 3 means the payload was rejected: stderr names every
violation; fix and retry.

Every successful `bootstrap` / `assign` / `confirm` / `add-category` call
refreshes graph.json and `catalog/` itself and prints a `catalog:` summary
line — no rebuild needed afterwards. If a call warns the derived refresh
failed, run `build_graph.py` once before rendering.

- **`bootstrapped: false`** → bootstrap autonomously, no approval step. The
  status output already lists every skill's id + description; draft 8–12
  categories with one-line descriptions (user-intent task shapes; name the
  boundary between confusable categories; a product earns a category only
  when it dominates; never enumerate product words — the build derives
  token lists from membership), assign EVERY skill (ordered list, first =
  display home; multi-home across confusable boundaries — search reads ONE
  shard, so assign each skill to every category a realistic task needing it
  would plausibly route to, and the boundary clauses in the descriptions
  mark exactly the pairs to sweep; a second home needs a realistic task
  phrasing, not a conceptual relation; platform-locked skills stay in their
  platform category; the CLI rejects incomplete coverage — if nothing fits,
  the taxonomy is missing a category, so create it), and pipe
  `{"taxonomy": [...], "assignments": {id: [labels]}}` into
  `categorize.py bootstrap` via heredoc.
- **`bootstrapped: true`** → the taxonomy is frozen. Batch-assign the
  `uncategorized` list into it with `categorize.py assign`, multi-homing by
  the same rule as bootstrap (every category a realistic task would route
  to, not just the best single fit); when nothing
  fits, `categorize.py add-category <name> "<desc>"` then assign — and call
  the addition out prominently in the report. For `stale` entries re-read
  the description: labels still right → `categorize.py confirm <ids…>`,
  wrong → reassign. Never touch unchanged skills. **A run must end with
  zero uncategorized skills** — uncategorized is a transitional state
  between runs, never an acceptable end state.
- **Every registered skill in this scope's graph is categorized** —
  plugins, user skills, and this directory's own project skills alike
  (including collision-renamed ids like `name@user` / `name@project`).

## Interpreting exit codes

- `0` — built, nothing dangling.
- `1` — built AND at least one defect: a broken bundled-file reference, or a
  mention of an unregistered/disabled skill. **Report each finding** — these
  are real defects. Uncategorized/stale counts are NOT defects, only TODO
  states for categorization.
- `2` — build failed. If stderr names categories.json/config.json
  violations, that is curated state failing loud: report the violations,
  offer to fix the file or `categorize.py import <path>` a corrected one.
  Otherwise check stderr and `./.claude/skill-atlas/debug.log`.

## Contract

- Reads only skill files and manifests. It never reads session transcripts
  and records no usage data.
- `graph.json`, `atlas.html` and `catalog/` are derived caches — safe to
  delete, always rebuildable.
- **`categories.json` is curated state — the one exception to
  rebuild-never-repair.** Never delete or regenerate it; regeneration
  discards the frozen taxonomy and every assignment. Each scope carries
  its own complete file (taxonomy + assignments) in
  `./.claude/skill-atlas/` — commit it with the repo. `config.json`
  (the searchable-plugins opt-in) is per-scope user config.
- The taxonomy freezes at bootstrap. Renaming or merging categories is a
  hand-edit of categories.json (taxonomy AND assignments) validated via
  `categorize.py import`, followed by a rebuild.
- This skill, the build and the hooks never write Claude Code's own config —
  recommend enabling a plugin, never flip `enabledPlugins` yourself. The one
  exception is the `/skill-atlas:edit-searchable` command, where disabling a
  plugin IS the user's explicit selection and is confirmed before it runs;
  automated paths stay read-only on settings.
- The atlas shows structure only (what is loadable, what is broken). Do NOT
  tell the user which skills are unused or "dead" — the tool does not
  measure usage, deliberately (DESIGN §6).
