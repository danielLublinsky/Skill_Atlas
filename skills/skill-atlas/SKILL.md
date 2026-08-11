---
name: skill-atlas
description: Graph, categorize and visualize the installed Claude Code skill collection. Use when the user wants to map, audit or categorize their skills, move skills into the searchable tier, or asks which skills are broken, dangling, dead, disabled or duplicated — and for any mention of the skill atlas, skill graph or skill catalog.
allowed-tools: Bash(python3:*), Read
---

# skill-atlas

Builds a structural graph of every registered skill on this machine,
maintains a model-assigned category catalog over it, and renders both as a
self-contained HTML atlas. Discovery is manifest-driven
(installed_plugins.json → plugin.json → settings.json), so marketplace
catalogues, stale cached plugin versions and deprecated trees never pollute
the picture.

Everything is **fully project-local**: all artifacts and curated state live
in `./.claude/skill-atlas/` of the directory you run in (auto-created on
first build — any directory becomes an atlas scope by running this),
covering the machine's plugins + user skills + this directory's own
`.claude/skills/`. Different directories are independent worlds with
independent taxonomies.

The flow is **build → categorize → render → report**. All scripts live under
`${CLAUDE_PLUGIN_ROOT}/scripts/` and are Python 3 stdlib-only.

## 1. Build

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_graph.py"
```

Exit 1 is findings, not failure — carry on and report them (see exit codes
below). If it exits 2 naming categories.json or config.json violations: that
is hand-editable curated state — report each violation, offer to fix the
file (or install a corrected one via `categorize.py import <path>`), and
NEVER delete or regenerate it. Other exit-2 causes: diagnose from stderr and
`./.claude/skill-atlas/debug.log`.

## 2. Categorize

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/categorize.py" status
```

All catalog writes go through `categorize.py` — never edit categories.json
free-hand. On exit 3 the payload was rejected: stderr names every violation;
fix exactly what it names and retry.

Every successful `bootstrap` / `assign` / `confirm` / `add-category` call
refreshes graph.json and `catalog/` itself and ends with a `catalog:` summary
line — no rebuild afterwards. If a call instead warns that the derived
refresh failed, run `build_graph.py` once before rendering. **The run's final
`catalog:` line must show 0 uncategorized.** Then branch on `bootstrapped`:

### `bootstrapped: false` → bootstrap now, autonomously (no approval step)

The status output already includes every skill's id and description
(`skills`). Draft 8–12 categories, each with a one-line description,
following these rules:

- describe the task shape in user-intent terms, not implementation terms;
- when two categories could be confused, let each description name its side
  of the boundary;
- a product gets its own category only when it dominates the collection;
- do NOT enumerate product/tool words in the description — the build derives
  token lists from membership automatically.

Assign EVERY skill to one or more categories, ordered (first entry is its
display home) — full coverage is mandatory and the CLI rejects a bootstrap
that leaves any skill unassigned; if nothing fits a skill, the taxonomy is
missing a category, so create it. Assignment rules:

- **Multi-home across confusable boundaries.** Search reads ONE shard,
  picked from the one-line descriptions, so a skill filed on only one side
  of a confusable pair is invisible to every task phrased in the twin's
  terms. Assign each skill to EVERY category a realistic task needing it
  would plausibly route to, home first — a debugging methodology also
  belongs in testing ("my tests are failing" is a debugging task phrased
  as testing); a design-interrogation skill also belongs in discovery.
  The boundary clauses written into the descriptions mark exactly the
  pairs to sweep: a boundary worth disclaiming in prose is a boundary
  whose straddling skills belong on both sides.
- A second home needs a realistic task phrasing, not a conceptual
  relation — when most skills sit in 3+ categories, the shards bloat back
  toward the flat catalog this system exists to avoid.
- A platform-locked skill (usable only on one vendor's stack) stays in
  its platform category — never file it into a generic category its
  wording happens to match.

Then write it in one call:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/categorize.py" bootstrap <<'EOF'
{"taxonomy": [{"name": "testing", "description": "writing, running and structuring tests"}],
 "assignments": {"some-plugin:tdd": ["testing"]}}
EOF
```

### `bootstrapped: true` → incremental

The taxonomy is frozen — assign into it, never re-label unchanged skills:

- For every id in `uncategorized`: match its description against the frozen
  taxonomy's one-line descriptions; batch all fits into ONE
  `categorize.py assign` call (same stdin shape as bootstrap, without
  "taxonomy"). The bootstrap assignment rules apply here too: multi-home
  the skill into every category a realistic task would route to, not just
  its best single fit.
- If nothing fits a skill: add a category yourself —
  `categorize.py add-category <name> "<one-line description>"`, then assign —
  and call the addition out prominently in the report.
- For every id in `stale`: re-read its current description. Labels still
  right → batch into `categorize.py confirm <id> <id> …`. Wrong → include in
  the `assign` payload with new labels.
- **A run must end with zero uncategorized skills** — uncategorized is a
  transitional state between runs, never an acceptable end state. If the
  last `catalog:` line still reports uncategorized > 0, something was
  missed — go back and assign it.
- **Every registered skill in this scope's graph is categorized** —
  plugins, user skills, and this directory's own project skills alike
  (including collision-renamed ids like `name@user` / `name@project`).

## 3. Render

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/render.py"
```

## 4. Report

The summary line per view (skills / enabled / files / edges / uncategorized /
stale); every dangling or broken-reference finding by name (these are real
defects); what categorization did this run — newly assigned
(id → categories), stale confirmed vs moved, any category you added; and the
atlas path (`./.claude/skill-atlas/atlas.html`). The first build in a repo
drops a `.gitignore` inside `.claude/skill-atlas/` covering the derived files
(`graph.json`, `atlas.html`, `catalog/`, `graph.dirty`, `debug.log`) — commit
it together with `categories.json` (this project's curated categorization)
and `config.json`. Caveat: a repo that ignores `.claude/` wholesale swallows
that nested file; it needs negation rules before `categories.json` can be
committed.

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
- `3` — (`categorize.py` writes only) the payload was rejected; stderr names
  every violation. Fix and retry.

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
