---
name: skill-atlas
description: Graph and visualize the installed Claude Code skill collection. Use when the user asks about their skill atlas, skill graph, dangling or broken skills, disabled plugins, duplicate skill names, or wants to visualize/audit what skills are actually loadable. Triggers - "skill atlas", "skill graph", "map my skills", "which skills are dead", "dangling skills", "audit my skills".
---

# skill-atlas

Builds a structural graph of every registered skill on this machine and
renders it as a self-contained HTML atlas. Discovery is manifest-driven
(installed_plugins.json → plugin.json → settings.json), so marketplace
catalogues, stale cached plugin versions and deprecated trees never
pollute the picture.

## How to run

All scripts live under `${CLAUDE_PLUGIN_ROOT}/scripts/` and are Python 3
stdlib-only:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_graph.py"   # → graph.json, exit 1 if dangling
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/render.py"        # → atlas.html
```

Both commands produce the global view (`~/.claude/skill-atlas/atlas.html`)
and, when the current directory carries its own `.claude/`, a **project
view** written into the project at `.claude/skill-atlas/atlas.html` — the
same skill universe but with that project's skills and its own
enabledPlugins overrides. Run build first, then render, then tell the user
where the atlas file(s) landed and offer to open them. When a project
atlas was created for the first time, suggest gitignoring
`.claude/skill-atlas/`.

## Interpreting exit codes

- `0` — graph built, nothing dangling.
- `1` — graph built AND at least one defect found: a broken bundled-file
  reference, a mention of an unregistered skill, or a mention of a skill in
  a disabled plugin. **Report each finding from stdout to the user** — these
  are real defects (a skill instructing the reader to use something that
  cannot be loaded).
- `2` — build failed; check stderr and `~/.claude/skill-atlas/debug.log`.

## Contract

- Reads only skill files and manifests (installed_plugins.json,
  settings.json, plugin.json). It never reads session transcripts and
  records no usage data.
- `graph.json` and `atlas.html` are derived caches — safe to delete,
  always rebuildable.
- The atlas shows structure only (what is loadable, what is broken). Do
  NOT tell the user which skills are unused or "dead" — the tool does not
  measure usage, deliberately (DESIGN §6).
