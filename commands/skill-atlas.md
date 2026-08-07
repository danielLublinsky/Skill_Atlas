---
description: Rebuild the skill graph and render the atlas, then report findings
allowed-tools: Bash(python3:*)
---

Rebuild the skill-atlas graph and visualization, then report:

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_graph.py"`.
2. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/render.py"`.
3. Report the summary line per view (skills / enabled / files / edges),
   every dangling or broken-reference finding by name, and the atlas
   path(s). Both scripts build the global view and — when the current
   directory has its own `.claude/` — a project view written to
   `.claude/skill-atlas/atlas.html` inside the project, with that
   project's enabledPlugins overrides applied. If a project atlas was
   created, suggest adding `.claude/skill-atlas/` to the project's
   .gitignore. If the build exited 1, present the findings as defects
   worth fixing; if 2, diagnose from stderr.
