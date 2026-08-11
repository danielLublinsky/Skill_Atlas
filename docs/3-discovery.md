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

[`discover()`](../scripts/atlas_discovery.py#L148):

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
   ([atlas_discovery.py:210](../scripts/atlas_discovery.py#L210)) — recorded,
   not drawn, unless a registered skill mentions it (see
   [4-graph-build.md](4-graph-build.md)).
5. the vendored built-in manifest → scope `builtin` (see below).

Only immediate children of a skill root are considered
([`_root_skill_dirs`](../scripts/atlas_discovery.py#L97)), and symlinks are
followed — a live user skill is often a symlinked directory.

## Built-ins: the fourth root has no directory

Skills that ship with Claude Code itself (`code-review`, `dataviz`,
`security-review`, …) live inside the binary — no `SKILL.md` on disk, no
plugin manifest entry, no CLI that lists them. Nothing walkable exists, so
they are enumerated from a **vendored manifest**,
[`scripts/builtin_skills.json`](../scripts/builtin_skills.json), curated and
updated with skill-atlas releases (the file records which Claude Code version
it was written against).

This closes the shadowing defect from DESIGN-ISSUES issue 1: search tells the
model never to look outside `catalog/`, so a built-in absent from every shard
was not merely missing — it was unreachable, even when it was the best match.

Properties of a built-in record ([`_builtin_records`](../scripts/atlas_discovery.py#L109)):

- `scope: "builtin"`, `path: null` — every downstream stage skips file work
  on path-less records; shards print a "ships with Claude Code" line instead
  of a path.
- **Tier reads `[enabled]`.** Built-ins are always session-loaded and
  natively invocable via the Skill tool. They are never `searchable` — that
  tier exists to bypass the plugin machinery, which built-ins don't use.
- Ids are bare invocation names, so a user/project skill sharing a built-in's
  name is a surfaced collision (`dataviz@user` / `dataviz@builtin`), same as
  any other duplicate.
- A missing or malformed manifest yields **no built-ins, never an error** —
  the file ships with the tool, so absence means a trimmed install, not a
  broken environment.
- Freshness rides the manifest side of the fingerprint:
  `builtins_path()` is in [`manifest_paths()`](../scripts/atlas_paths.py#L194),
  so editing or updating the vendored list rebuilds on next session;
  `skill_md_paths()` excludes path-less records.
- `SKILL_ATLAS_BUILTINS` overrides the manifest location — the testability
  seam; the test sandbox points it at a nonexistent file by default.

## Node ids are invocation strings

The id is the exact string Claude Code invokes the skill with — already unique,
already namespaced ([`_assign_ids`](../scripts/atlas_discovery.py#L235)):

- plugin skill → `<plugin>:<name>`
- user / project skill → bare `<name>`
- `name` comes from frontmatter `name:`, falling back to the directory name.

**Collisions are surfaced, never merged.** When two skills share an id, *both*
get the colliding id plus whatever separates them, each is flagged
`duplicate: true`, and the ambiguous invocation string lands in
`stats.duplicate_names`. Mentions of the bare name then resolve to neither. A
duplicate name is a real defect worth showing, not an edge case to paper over.

The discriminator is whichever record field actually differs, tried in order —
scope, then marketplace, then version, then all three
([`_disambiguate`](../scripts/atlas_discovery.py#L267)):

| Collision | Ids |
| --- | --- |
| project skill shadowing a user one | `graphify@user`, `graphify@project` |
| one plugin name from two marketplaces | `frontend-design:frontend-design@claude-plugins-official`, `…@claude-code-plugins` |

Scope comes first because it settles the shadowing case with the shortest
readable id. It is **not** sufficient on its own: two plugins of the same name
are both scope `plugin`, so `<name>@<scope>` mapped the whole group onto one id
and re-collided *silently*, detection having already run (DESIGN-ISSUES issue
2). Since ids are the join key for graph.json, the shards and
`categories.json`, uniqueness is an invariant —
[`_enforce_unique_ids`](../scripts/atlas_discovery.py#L294) is the backstop for
records that differ in nothing discovery can read, appending `@1`, `@2`.

> Assignments in `categories.json` are keyed by these ids, disambiguated form
> included. Renaming or un-shadowing a skill therefore *moves* its id — the old
> assignment becomes an `orphan_assignment` (reported, not fatal).

## Enabled state is an attribute, not a filter

A disabled skill still enters the graph. This rule exists because the author's
most-invoked plugin was disabled when the tool was designed — filtering on
enabled state would have hidden exactly the thing worth shouting about.

`enabled` is resolved from **merged** settings, lowest precedence first
([atlas_paths.py:143](../scripts/atlas_paths.py#L143)):

```text
~/.claude/settings.json  <  ~/.claude/settings.local.json
                         <  <scope>/.claude/settings.json
                         <  <scope>/.claude/settings.local.json
```

Keys are composite `<name>@<marketplace>` strings — that is how both
`settings.json` and `installed_plugins.json` key plugins. A plugin absent from
every `enabledPlugins` map defaults to **enabled**
([atlas_discovery.py:178](../scripts/atlas_discovery.py#L178)). Unreadable or
malformed settings files are skipped, not fatal.

## Reading `installed_plugins.json`

[`installed_plugins()`](../scripts/atlas_paths.py#L159). Per-plugin values are
**arrays** of install records. One record is chosen — project scope preferred,
else the first — and the total record count is surfaced as `install_records`
rather than hidden. `version` is opaque and may literally be `"unknown"`.

This function **raises** on an unreadable or unparseable manifest; the build maps
that to exit 2. That is deliberate: a broken manifest means the registered set
is unknowable, and a half-built graph would silently look like deletions.

## Frontmatter parsing

[`parse_frontmatter()`](../scripts/atlas_discovery.py#L25) is hand-rolled — no
YAML dependency. It handles quoted values and folded/literal block scalars
(`>`, `|`, `>-`, …) conservatively, and strips a leading BOM. Only `name:` and
`description:` are consumed. If you add a frontmatter field the graph should
carry, extend `_skill_record`, not the parser.

## light mode

`discover(light=True)` skips every file read — stat and paths only. The
fingerprint uses it ([`skill_md_paths()`](../scripts/atlas_discovery.py#L258)),
so enumeration logic can never drift between staleness checking and building.
Keep that property: any new discovery input must appear in both modes.

## Diagnostics

`naive_skillmd_count()` reports what the naive walk *would* have found. It is a
machine-wide `rglob` and therefore opt-in — `build_graph.py --naive-count` — so
default builds and the hook never pay for it.
