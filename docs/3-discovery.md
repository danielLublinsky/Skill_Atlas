# 3 — Discovery

**Files:** [atlas_paths.py](../scripts/atlas_paths.py) (where things are),
[atlas_discovery.py](../scripts/atlas_discovery.py) (what exists).
**Tests:** [test_paths.py](../tests/test_paths.py),
[test_discovery.py](../tests/test_discovery.py).

Discovery answers one question: *which skills exist, and which of them count?*
Everything downstream inherits its answer.

## The rule: manifest-driven, never a filesystem walk

"Any directory containing a `SKILL.md`" over-counts by ~60% on a real machine —
104 files on disk against 41 registered skills. The gap is other authors'
`deprecated/` and `in-progress/` trees, stale cached plugin versions, and
marketplace catalogue entries for plugins that were never installed.

Four nested definitions exist, and the code is explicit about which one it means:

| Definition | Authority | Used? |
| --- | --- | --- |
| `SKILL.md` on disk | filesystem | **no** — diagnostic only (`--naive-count`) |
| under an installed plugin path | `installed_plugins.json` | intermediate |
| **registered** — enters the graph | each `plugin.json`'s `skills[]` | **yes** |
| **enabled** — loadable this session | merged `settings.json` | an *attribute*, not a filter |

**Never walk `~/.claude/plugins/marketplaces/`.** That tree is the catalogue of
*installable* plugins, not the installed set.

## Walk order

[`discover()`](../scripts/atlas_discovery.py#L108):

1. `~/.claude/skills/*/SKILL.md` → scope `user`
2. `<scope>/.claude/skills/*/SKILL.md` → scope `project` (skipped when the scope
   *is* the home directory — see [2-initialization.md](2-initialization.md))
3. every record in `installed_plugins.json` → scope `plugin`:
   - take `installPath` — the only ground truth. This is what excludes stale
     cached versions (`superpowers/6.1.1` and `6.2.0` can both sit on disk while
     only one is installed).
   - read `<installPath>/.claude-plugin/plugin.json`.
   - **if it has a `skills[]` array**, that array is the registered set,
     verbatim. Entries are plugin-root-relative and may nest arbitrarily
     (`./skills/engineering/tdd`).
   - **if it has no `skills` key**, glob `<installPath>/skills/*/SKILL.md`. This
     fallback is load-bearing, not a defensive nicety — `superpowers` registers
     all 14 of its skills this way.
4. everything else under an install path is indexed as **unregistered**
   ([atlas_discovery.py:169](../scripts/atlas_discovery.py#L169)) — recorded,
   not drawn, unless a registered skill mentions it (see
   [4-graph-build.md](4-graph-build.md)).

Only immediate children of a skill root are considered
([`_root_skill_dirs`](../scripts/atlas_discovery.py#L96)), and symlinks are
followed — a live user skill is often a symlinked directory.

## Node ids are invocation strings

The id is the exact string Claude Code invokes the skill with — already unique,
already namespaced ([`_assign_ids`](../scripts/atlas_discovery.py#L189)):

- plugin skill → `<plugin>:<name>`
- user / project skill → bare `<name>`
- `name` comes from frontmatter `name:`, falling back to the directory name.

**Collisions are surfaced, never merged.** When two skills share an id (a
project skill shadowing a user one), *both* get disambiguated ids —
`graphify@user`, `graphify@project` — each is flagged `duplicate: true`, and the
name lands in `stats.duplicate_names`. Mentions of the bare name then resolve to
neither. A duplicate name is a real defect worth showing, not an edge case to
paper over.

> Assignments in `categories.json` are keyed by these ids, disambiguated form
> included. Renaming or un-shadowing a skill therefore *moves* its id — the old
> assignment becomes an `orphan_assignment` (reported, not fatal).

## Enabled state is an attribute, not a filter

A disabled skill still enters the graph. This rule exists because the author's
most-invoked plugin was disabled when the tool was designed — filtering on
enabled state would have hidden exactly the thing worth shouting about.

`enabled` is resolved from **merged** settings, lowest precedence first
([atlas_paths.py:134](../scripts/atlas_paths.py#L134)):

```text
~/.claude/settings.json  <  ~/.claude/settings.local.json
                         <  <scope>/.claude/settings.json
                         <  <scope>/.claude/settings.local.json
```

Keys are composite `<name>@<marketplace>` strings — that is how both
`settings.json` and `installed_plugins.json` key plugins. A plugin absent from
every `enabledPlugins` map defaults to **enabled**
([atlas_discovery.py:137](../scripts/atlas_discovery.py#L137)). Unreadable or
malformed settings files are skipped, not fatal.

## Reading `installed_plugins.json`

[`installed_plugins()`](../scripts/atlas_paths.py#L150). Per-plugin values are
**arrays** of install records. One record is chosen — project scope preferred,
else the first — and the total record count is surfaced as `install_records`
rather than hidden. `version` is opaque and may literally be `"unknown"`.

This function **raises** on an unreadable or unparseable manifest; the build maps
that to exit 2. That is deliberate: a broken manifest means the registered set
is unknowable, and a half-built graph would silently look like deletions.

## Frontmatter parsing

[`parse_frontmatter()`](../scripts/atlas_discovery.py#L24) is hand-rolled — no
YAML dependency. It handles quoted values and folded/literal block scalars
(`>`, `|`, `>-`, …) conservatively, and strips a leading BOM. Only `name:` and
`description:` are consumed. If you add a frontmatter field the graph should
carry, extend `_skill_record`, not the parser.

## light mode

`discover(light=True)` skips every file read — stat and paths only. The
fingerprint uses it ([`skill_md_paths()`](../scripts/atlas_discovery.py#L212)),
so enumeration logic can never drift between staleness checking and building.
Keep that property: any new discovery input must appear in both modes.

## Diagnostics

`naive_skillmd_count()` reports what the naive walk *would* have found. It is a
machine-wide `rglob` and therefore opt-in — `build_graph.py --naive-count` — so
default builds and the hook never pay for it.
