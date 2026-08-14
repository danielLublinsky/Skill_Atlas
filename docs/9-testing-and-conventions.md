# 9 — Testing and conventions

## Running the suite

```bash
make test                              # bash tests/run_tests.sh → unittest discover -v
python3 -m unittest tests.test_graph   # one module
make smoke                             # read-only assertions against the REAL machine
make check                             # CI gate: exit 1 on any dangling/broken edge
```

Stdlib `unittest` only — no pytest, no pip, no venv. 117 tests, ~4 s.

**Current state: 116 pass, 1 fails.**
`test_render.test_self_contained_no_external_references` asserts `<link` is
absent from the rendered page, and commit `1ab42f2` added an inlined data-URI
favicon (`<link rel="icon" href="data:image/svg+xml,…">`). The page is still
fully self-contained; the assertion is over-strict and should test for external
schemes (`http://`, `//cdn`, `src="` on a non-data URI) rather than for the
`<link>` tag. Fix the test, not the favicon.

## The sandbox — no test ever touches the real `~/.claude`

[tests/helpers.py](../tests/helpers.py). `EnvSandbox` copies
[tests/fixtures/fakehome/](../tests/fixtures/fakehome/) into a temp dir, points
`SKILL_ATLAS_CLAUDE_DIR` at the copy, and sets the in-process scope to a neutral
temp dir standing in for "some directory the user runs skill-atlas in".

```python
with helpers.EnvSandbox(copy_fixtures=True) as sandbox:
    graph, code = build_graph.build(cwd=sandbox.tmp)
```

- `sandbox.tmp` — the neutral scope (no `.claude` of its own).
- `sandbox.project_dir` — the fixture project, for project-skill and
  scope-override tests.
- Fixture manifests carry a `__CLAUDE_DIR__` placeholder rewritten to the copied
  tree's real path; the symlinked user skill is recreated if the checkout lost
  it.
- Env vars and the process scope are restored on exit.

Curated-state fixtures are **builders, not files** (`approved_categories`,
`write_categories`, `write_config`, `searchable_config`) because the atlas dir
only exists at runtime. `write_categories` deliberately bypasses the validating
writer so tests can plant hand-edited and broken states.

The fixture tree is designed to exercise the hard cases: an allowlist plugin and
a no-`skills`-key plugin, a stale cached version (`alpha/0.9.0` beside
`1.0.0`), a marketplace catalogue entry for an uninstalled plugin, a
`deprecated/` tree, a symlinked user skill, and a name collision between user
and project scope.

## What each module covers

| Module | Guards |
| --- | --- |
| [test_paths.py](../tests/test_paths.py) | env defaults, settings precedence, install-record selection, atomic writes, the `debug_log` privacy contract |
| [test_discovery.py](../tests/test_discovery.py) | the exact registered set, stale-version and marketplace exclusion, allowlist vs. glob fallback, symlinks, duplicates, light-mode agreement, frontmatter parsing |
| [test_extract.py](../tests/test_extract.py) | each mention form, bare-common-word rejection, fence stripping, self-mention and frontmatter exclusion, reference dedup |
| [test_fingerprint.py](../tests/test_fingerprint.py) | stability, skill/settings/manifest sensitivity, the appearing-`settings.local.json` case, deadline abort |
| [test_graph.py](../tests/test_graph.py) | exit codes, node/stat shape, scope independence, first-run `.gitignore`, category merge, loud-vs-tolerated curated failures, mention dedup |
| [test_categories.py](../tests/test_categories.py) | schema round-trip, every rejection class, the derived refresh, the full CLI surface |
| [test_categorize_flow.py](../tests/test_categorize_flow.py) | bootstrap → incremental with **no reshuffling**, scopes as independent worlds, stale-then-confirmed |
| [test_shards.py](../tests/test_shards.py) | index/shard shape, tier inclusion rules, empty-taxonomy degradation, determinism, stale-shard removal, plugin packaging + the `skill-search` frontmatter |
| [test_hooks.py](../tests/test_hooks.py) | inert-when-uninitialized, every rebuild trigger, exit-0-always, the index line and its nag |
| [test_render.py](../tests/test_render.py) | self-containment, `</` escaping, round-trip, determinism, category-view markup, the staleness flag |

## Live checks

- `make smoke` — [dev/smoke_live.py](../dev/smoke_live.py): read-only structural
  assertions against the real machine, isolated by symlinking real inputs into a
  temp claude dir.
- `make m4-check` / `make phase2-check` — these **print manual procedures**;
  they assert nothing. Both cover things only a real session can show: a
  plugin toggle rebuilding on next start, the index line appearing in a fresh
  session's context, a dormant skill being found and used end to end.

## Conventions for landing a change

1. **Read the docs for the area first**, then DESIGN.md for why it is shaped
   that way. DESIGN.md is the historical record, not a description of current
   behaviour; the code overrides both.
2. **Stdlib only.** No dependency has ever been added, and the plugin's install
   story depends on that.
3. **Docstrings carry the *why*.** Every module here opens with the reasoning and
   the measurement behind its rule. Match that: a change that removes a
   non-obvious constraint should remove its justification too, and one that adds
   a constraint should say what breaks without it.
4. **New build input?** Add it to `manifest_paths()` *and* `mark_dirty.PATTERNS`.
5. **New skill node field?** Produce it in `_skill_record`/`annotate_skills`, and
   let shards and the template read it — never re-derive facts in two places.
   `atlas_annotate.py` exists precisely because two writers emit `graph.json`.
6. **Touching curated state?** It goes through `atlas_categories.write_*`.
   Validation runs before the temp file exists, so a rejection leaves the file on
   disk untouched.
7. **Keep outputs deterministic** — sorted, timestamp-free where it matters
   (shards, `atlas.html`).
8. **Never widen `debug_log`.** Path, line, exception type name. That is the
   privacy boundary and it costs nothing to keep.
9. **Never write Claude Code's own config** outside the one confirmed
   `edit-searchable` path.
10. **Add the test in the module that owns the behaviour**, and prefer asserting
    the *contract* (exit code, emitted file, absent side effect) over internals.

## Agent-facing surfaces are code too

[skills/](../skills/) and [commands/](../commands/) are instructions a model
executes; changing them changes behaviour as surely as editing Python. Two are
especially load-bearing:

- `skill-search`'s frontmatter description — the entire triggering surface for
  the dormant tier ([6](6-catalog-and-search.md)).
- `skills/skill-atlas/SKILL.md` — the bootstrap/incremental branch logic. Its
  rules must stay in step with what `categorize.py` actually enforces (full
  coverage, frozen taxonomy, exit 3 semantics).

Keep both in sync with the CLI, and re-check `test_shards.TestSkillSearchPackaging`
after any edit to plugin registration or that frontmatter. One name may not be
claimed twice: a `commands/<x>.md` beside a skill named `<x>` registers two
components under one address, so the later one is unreachable while both still
cost session tokens — `test_no_duplicate_component_names` pins that.
