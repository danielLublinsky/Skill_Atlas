# Skill_Atlas

A Claude Code plugin (`skill-atlas`) for a skill collection that has
outgrown anyone's ability to eyeball it. Two halves:

**The atlas — shipped.** A structural map of every *registered* skill
(manifest-driven — not "any directory containing SKILL.md", which
over-counts by ~60% on a real machine), rendered as a single
self-contained `atlas.html` that opens offline from `file://`. It
answers: which skills are actually loadable, which are switched off,
which point at things that no longer exist, and which are duplicated.

**The catalog + search — shipped.** Claude Code injects every enabled
skill's description into every session (~48 tokens per skill, used or
not); a multi-plugin collection of 100+ skills costs thousands of tokens
per session, and near-duplicate skills silently compete for the model's
attention. skill-atlas adds a third tier between enabled and disabled —
**searchable**: zero tokens per session, still findable. Skills get
model-assigned categories (drafted autonomously by `/skill-atlas` at
first run, then frozen), the build derives a compact catalog from them
(`catalog/_index.md` + one shard per category), and one always-enabled
`skill-search` skill routes any task to the right skill in two small
reads — the category index, then a single category's entries — instead
of one giant preload. A ~50-token session index line advertises the
dormant tier. The full spec, with every decision and its reason, is
[DESIGN-PHASE2.md](DESIGN-PHASE2.md).

| Tier | In context? | Findable? | Cost / session |
| --- | --- | --- | --- |
| enabled | yes — description injected | natively | ~48 tokens each |
| searchable (opt-in, per plugin) | no | via the search skill | 0 |
| disabled | no | no — disable keeps meaning disable | 0 |

It deliberately does **not** count skill invocations. Usage tracking was
fully specified, measured against a real machine, and dropped: skill
invocation is too rare an event for zero-counts to mean anything on a
personal collection. The design record and the arithmetic are in
[DESIGN.md](DESIGN.md) §6; the rest of the design rationale and evidence
is in the same file.

## Quick start

```bash
python3 scripts/build_graph.py   # manifests + skill roots → graph.json + catalog/ shards
python3 scripts/render.py        # graph.json → ./.claude/skill-atlas/atlas.html
python3 scripts/categorize.py status            # categorization TODO list
python3 scripts/categorize.py config --list     # per-plugin tier rollup
python3 scripts/categorize.py config --add-searchable <plugin>   # opt a disabled plugin into the searchable tier
```

## Managing the searchable tier

A plugin is searchable only when **both** halves hold: Claude Code has it
disabled, and this scope opted it in. `--add-searchable` is the second
half only — on a still-enabled plugin it changes nothing, because
`enabled` wins the tier resolution. The first half is
`claude plugin disable <plugin>`.

`/skill-atlas:edit-searchable` does both, interactively. It lists every
plugin with its tier and skill count, always asks first whether you are
**adding a plugin** or **removing** one, multi-selects which, asks which
settings scope to write, then rebuilds the catalog and `atlas.html`.
Removing a plugin from the tier leaves it **off**, not enabled — the
command asks which you meant.

The unit is a plugin, not an individual skill: selecting one moves all its
skills together (per-skill overrides are deferred — DESIGN-PHASE2 §10).

A tier change needs no re-categorization: categorization is tier-blind
(every *registered* skill is filed whatever its tier) and `build_graph.py`
re-emits the shards itself, so an opted-in plugin's skills simply start
appearing there. The command falls back to `/skill-atlas` only when
`uncategorized > 0` — pre-existing drift from a plugin installed since the
last run, whose skills would otherwise surface in `catalog/uncategorized.md`
instead of a real category.

Pick the settings scope to match `config.json`, which is committed:
`--scope project` keeps the disable and the opt-in travelling together.
`--scope user` disables the plugin machine-wide while only this project can
search it.

Categorization itself runs inside `/skill-atlas` (the one place a model
is present): first run bootstraps 8–12 categories over every skill
description and freezes the taxonomy; later runs assign new skills into
it and re-confirm stale ones. All writes go through the validating
`categorize.py` CLI — `categories.json` is curated state, never
free-handed and never regenerated.

Everything is **fully project-local**: all artifacts and curated state
live in `./.claude/skill-atlas/` of the directory you run in, created on
first build (any directory becomes an atlas scope by running the build
there). The view covers the machine's installed plugins + user skills +
that directory's own `.claude/skills/`, with the directory's own
`enabledPlugins` overrides applied. Different directories are fully
independent worlds — separate graphs, catalogs, taxonomies. Gitignore the
derived files in `.claude/skill-atlas/` (`graph.json`, `atlas.html`,
`catalog/`, `graph.dirty`, `debug.log`) but **commit `categories.json`** —
it is the project's curated categorization and shareable with the team.

`build_graph.py` exit codes make it usable as a CI gate:

| Code | Meaning |
| --- | --- |
| 0 | Graph built, nothing dangling |
| 1 | ≥1 defect: broken file reference, or a mention of an unregistered/disabled skill |
| 2 | Build failed |

## Install as a plugin (auto-update hooks)

```bash
git clone https://github.com/danielLublinsky/Skill_Atlas.git
claude plugin marketplace add ./Skill_Atlas
claude plugin install skill-atlas@skill-atlas
```

(The repository is `Skill_Atlas`; the plugin and marketplace are both
named `skill-atlas`.)

Two hooks keep the graph fresh; neither logs anything:

- **SessionStart** — operates only in directories that already carry a
  `.claude/skill-atlas/` (an explicit build is the opt-in; the hook never
  initializes anything). Stat-only fingerprint over every SKILL.md *and*
  every manifest (installed_plugins.json, settings files, each
  plugin.json, plus this scope's categories.json and config.json);
  rebuilds graph and catalog shards on mismatch. Aborts at 2 s — a slow
  hook is worse than a stale graph. When the searchable tier is nonempty
  it also emits the ~50-token index line into session context via the
  documented SessionStart JSON contract — its only stdout, ever.
- **PostToolUse (Write|Edit)** — flags the graph dirty when a skill file or
  manifest is edited; the flag is consumed at the next session start.

After changing `hooks/` you need `/reload-plugins` or a restart; SKILL.md
edits apply immediately. Hook-script iteration goes through
`claude plugin update skill-atlas`.

### Verifying auto-update (milestone 4, manual)

`make m4-check` prints the procedure: toggle any `enabledPlugins` entry in
`~/.claude/settings.json`, start a new session, and confirm
`graph.json`'s `generated_at` advanced with the toggle reflected — no
SKILL.md was touched, which is exactly the case a naive fingerprint misses.

## Privacy

skill-atlas reads manifests and skill files only. It never opens
`~/.claude/projects` (Claude Code's session transcripts) — the feature
that would have is dropped (DESIGN.md §6). Two notes that still apply:

1. `debug.log` receives file path, line number and exception **type** only,
   never the content of whatever was being parsed.
2. `atlas.html` shows real filesystem paths, and a project view is named
   after the project directory. Fine locally; sharing a screenshot is a
   decision, not an accident.

## Configuration

Artifacts always live in `./.claude/skill-atlas/` of the directory
skill-atlas runs in — graph, atlas, `catalog/`, curated `categories.json`
and `config.json` alike. There is no global artifact root and no location
override.

| Env var | Default | Meaning |
| --- | --- | --- |
| `SKILL_ATLAS_CLAUDE_DIR` | `~/.claude` | Claude Code config root (test seam) |
| `SKILL_ATLAS_AUTOBUILD` | `1` | `0` disables the SessionStart staleness check |

All derived files (`graph.json`, `atlas.html`, `catalog/`) are caches:
deletable at any time, rebuilt from scratch on the next run. If one is
corrupted the fix is rebuild, never repair. The exceptions are *not*
caches: **`categories.json` is curated state** — deleting it discards the
frozen taxonomy and every assignment (back it up; a hand-edit that breaks
its schema fails the build loud with the violations named, and
`categorize.py import <path>` installs a corrected file after
validation) — and `config.json` is a five-line opt-in list you can
rewrite. Each scope's `categories.json` is complete — its own taxonomy
plus every assignment — and is meant to be **committed with the repo**;
gitignore the derived files next to it, not the curated one. See
DESIGN-PHASE2.md §3.4 and §0 amendment 8.

## Development

```bash
make test    # unit suite against fixtures — never touches your ~/.claude
make smoke   # read-only structural checks against the live machine
make build render
```

Layout: `scripts/atlas_*.py` are shared modules (path/env resolution,
discovery, extraction, fingerprint, atomic IO); entry points are
`build_graph.py`, `render.py`, and the two hook scripts. Tests run against
a synthetic `~/.claude` in `tests/fixtures/fakehome/` that reproduces every
discovery trap found on a real machine (array-valued install records,
`skills[]` allowlists vs flat globs, stale cached versions, marketplace
phantoms, symlinked skills, name collisions, and a twin of a real dangling
defect).

`vendor/d3.v7.min.js` is D3 7.9.0 (ISC license, © Mike Bostock), fetched
once by `dev/fetch_d3.sh` with a pinned sha256 and inlined into
`atlas.html` at render time — the output makes zero network requests.

## Status

- **Phase 1** — structural graph + visualization + freshness hooks:
  **complete**.
- **Phase 2** — categorization + search: **complete**
  ([DESIGN-PHASE2.md](DESIGN-PHASE2.md)) — validating writer +
  `categorize.py` CLI, graph v3 (categories / staleness / searchable
  tier), autonomous `/skill-atlas` bootstrap, catalog shards +
  `skill-search`, session index line, and a by-category atlas view
  (hub-and-spoke, toggleable; scope view stays the default).
- **Usage tracking** — dropped, out of scope; the design and the
  arithmetic that killed it are recorded in DESIGN.md §6.
