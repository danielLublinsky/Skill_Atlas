---
description: Rebuild the skill graph, categorize skills into the catalog, render the atlas, then report
allowed-tools: Bash(python3:*)
---

Rebuild the skill-atlas graph, keep the category catalog current, render the
visualization, then report. All scripts live under `${CLAUDE_PLUGIN_ROOT}/scripts/`.

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_graph.py"`. If it exits 2
   naming categories.json or config.json violations: that is hand-editable
   curated state — report each violation, offer to fix the file (or install a
   corrected one via `categorize.py import <path>`), and NEVER delete or
   regenerate it. Other exit-2 causes: diagnose from stderr.

2. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/categorize.py" status` and branch:

   **`bootstrapped: false` → bootstrap now, autonomously (no approval step).**
   Run `status --full` and read every skill's id and description. Draft 8–12
   categories, each with a one-line description, following these rules:
   - describe the task shape in user-intent terms, not implementation terms;
   - when two categories could be confused, let each description name its side
     of the boundary;
   - a product gets its own category only when it dominates the collection;
   - do NOT enumerate product/tool words in the description — the build derives
     token lists from membership automatically.
   Assign every skill to one or more categories, ordered (first entry is its
   display home). Then write it in one call — on exit 3, fix exactly what
   stderr names and retry:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/categorize.py" bootstrap <<'EOF'
   {"taxonomy": [{"name": "testing", "description": "writing, running and structuring tests"}],
    "assignments": {"some-plugin:tdd": ["testing"]}}
   EOF
   ```

   **`bootstrapped: true` → incremental.** The taxonomy is frozen — assign into
   it, never re-label unchanged skills:
   - For every id in `uncategorized`: match its description against the frozen
     taxonomy's one-line descriptions; batch all fits into ONE
     `categorize.py assign` call (same stdin shape as bootstrap, without
     "taxonomy").
   - If nothing fits a skill: add a category yourself —
     `categorize.py add-category <name> "<one-line description>"`, then assign —
     and call the addition out prominently in the report.
   - For every id in `stale`: re-read its current description. Labels still
     right → batch into `categorize.py confirm <id> <id> …`. Wrong → include in
     the `assign` payload with new labels.

3. Rerun `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_graph.py"`, then
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/render.py"`.

4. Report: the summary line per view (skills / enabled / files / edges /
   uncategorized / stale); every dangling or broken-reference finding by name
   (these are real defects); what categorization did this run — newly assigned
   (id → categories), stale confirmed vs moved, any category you added; and the
   atlas path(s). Both scripts build the global view and — when the current
   directory has its own `.claude/` — a project view at
   `.claude/skill-atlas/atlas.html`; suggest gitignoring `.claude/skill-atlas/`
   the first time a project atlas appears.
