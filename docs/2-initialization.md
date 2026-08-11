# 2 — Initialization

How the system comes into existence: installation, what a **scope** is, what the
first run creates, and every knob that changes where things land.

## Install

```bash
git clone https://github.com/danielLublinsky/Skill_Atlas.git
claude plugin marketplace add ./Skill_Atlas
claude plugin install skill-atlas@skill-atlas
```

Python 3, stdlib only. No pip, no venv, no network at build or view time (D3 is
vendored at [vendor/d3.v7.min.js](../vendor/d3.v7.min.js); its provenance is
reproducible via [dev/fetch_d3.sh](../dev/fetch_d3.sh), which is dev-only).

The plugin registers two skills and two commands
([.claude-plugin/plugin.json](../.claude-plugin/plugin.json),
[hooks/hooks.json](../hooks/hooks.json)):

| Surface | What it does |
| --- | --- |
| `/skill-atlas` (command + skill) | build → categorize → render → report |
| `/skill-atlas:edit-searchable` | move plugins in/out of the searchable tier |
| `skill-search` (skill) | the two-stage catalog query — the one always-enabled cost |
| SessionStart hook | rebuild if stale, inject the index line |
| PostToolUse(Write\|Edit) hook | drop the dirty marker |

Working on the plugin itself: SKILL.md edits apply immediately, but changes to
`hooks/`, `agents/` or `.mcp.json` need `/reload-plugins` or a restart.

## The scope — the central concept

A **scope** is simply *the directory skill-atlas runs in*. Everything it owns
lives in `<scope>/.claude/skill-atlas/`. There is no global artifact root, no
merge across directories, and no fallback:

- each scope has its **own complete `categories.json`** — its own frozen
  taxonomy *and* its assignments; two scopes may diverge entirely;
- each scope has its own `config.json`, `graph.json`, `catalog/`, `atlas.html`;
- `skill-search` reads `./.claude/skill-atlas/catalog/` and **never** looks
  elsewhere.

The *inputs* are still machine-wide: the same installed plugins and the same
`~/.claude/skills` are discovered from every scope. What changes per scope is
this directory's own `.claude/skills/` and its `settings.json` overrides
([atlas_paths.py:124](../scripts/atlas_paths.py#L124)).

The scope is process-wide state, set exactly once by each entry point before any
path resolves ([atlas_paths.py:22](../scripts/atlas_paths.py#L22)). Every entry
point accepts `--cwd` to point at a different directory.

> **Running from `$HOME`:** `<scope>/.claude` would *be* the user config dir, so
> `has_local_skills_root()` returns False and user skills are not double-counted
> ([atlas_paths.py:103](../scripts/atlas_paths.py#L103)).

## Auto-init: how a directory becomes a scope

**An explicit run creates the scope directory; the hooks never do.**

- `build_graph.py` (or `/skill-atlas`) writing `graph.json` creates
  `.claude/skill-atlas/` via the atomic writer's `mkdir`
  ([build_graph.py:270](../scripts/build_graph.py#L270)).
- The SessionStart hook returns immediately when the directory does not exist
  ([check_stale.py:81](../scripts/check_stale.py#L81)); `mark_dirty` likewise
  ([mark_dirty.py:27](../scripts/mark_dirty.py#L27)). Sessions in untouched
  directories stay untouched and emit nothing.
- A **failed** build in an untouched directory must not create the directory
  either — that would arm the hook. This is why `debug_log` refuses to create
  its own parent ([atlas_io.py:63](../scripts/atlas_io.py#L63)), and it is
  covered by `test_failed_build_does_not_initialize_scope`.

## What the first build creates

```text
<scope>/.claude/skill-atlas/
├── .gitignore        # written once, on the run that creates the dir
├── graph.json        # derived
├── catalog/          # derived — _index.md + one shard per category + uncategorized.md
├── atlas.html        # derived (after render.py)
├── categories.json   # curated — appears at bootstrap
├── config.json       # user config — appears on the first `config --add-searchable`
├── graph.dirty       # transient marker
└── debug.log         # transient
```

The `.gitignore` it drops ([build_graph.py:240](../scripts/build_graph.py#L240))
ignores the derived siblings and nothing else. **Commit it together with
`categories.json` and `config.json`** — the curated categorization belongs in
version control. It is written only on the run that creates the directory, so
deleting it is a user choice that sticks.

> **Gotcha:** a repo that ignores `.claude/` wholesale swallows that nested
> file. Git cannot re-include anything under a directory ignored with a trailing
> slash — this repo's own [.gitignore](../.gitignore) shows the negation pattern
> that works (`.claude/*`, then `!.claude/skill-atlas/`, then
> `.claude/skill-atlas/*`, then the `!` re-includes).

## First run, end to end

```bash
/skill-atlas                    # build → categorize (bootstrap) → render → report
```

On a fresh scope this **bootstraps autonomously — there is no approval step**.
`categorize.py status` reports `bootstrapped: false` and automatically includes
every skill's id and description; the model drafts 8–12 categories and assigns
every skill in one `categorize.py bootstrap` call. Full coverage is mandatory —
see [5-categorization.md](5-categorization.md).

Nothing is opted into the searchable tier yet; that is `/skill-atlas:edit-searchable`.
Until then Phase 2 is inert and the system behaves exactly like Phase 1 — a
supported state, not a broken one.

## Without the plugin

```bash
make build      # graph.json + catalog/ from the live manifests
make render     # atlas.html
make check      # CI gate: exit 1 on any broken reference or dangling mention
make test       # unit suite against fixtures — never touches the real ~/.claude
make smoke      # read-only structural assertions against the real machine
```

`make build` deliberately tolerates exit 1 (findings are a report, not a
failure) and stops only on exit 2 ([Makefile:6](../Makefile#L6)).

## Environment variables

| Var | Default | Meaning |
| --- | --- | --- |
| `SKILL_ATLAS_CLAUDE_DIR` | `~/.claude` | Claude Code config root — **inputs only**. The test seam: the suite and `dev/smoke_live.py` redirect it at a throwaway tree. |
| `SKILL_ATLAS_AUTOBUILD` | `1` | `0` disables the SessionStart staleness rebuild entirely. |

`SKILL_ATLAS_HOME` was **removed** (DESIGN-PHASE2 §0 amendment 8) — artifacts
always live in the `.claude/skill-atlas` of their scope. `SKILL_ATLAS_PROJECTS`,
`SKILL_ATLAS_GATE_LAMBDA` and `SKILL_ATLAS_SUBAGENTS` went with the dropped
usage phase. If you find any of these names in a doc, that doc is stale.
