---
description: Add plugins to, or remove them from, the zero-token searchable tier
allowed-tools: Bash(python3:*), Bash(claude plugin:*), AskUserQuestion, Skill
---

Edit the searchable tier: pick an action, pick the plugins, refresh.

A plugin is searchable only when BOTH halves hold — Claude Code has it
**disabled** (settings) and this scope **opted it in** (`config.json`). This
command owns both halves. The unit is a plugin, not a single skill: selecting
one moves all its skills together.

## 1. Read the current state

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_graph.py"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/categorize.py" config --list
```

Exit 1 is dangling defects elsewhere — carry on. Exit 2 is fatal: report
stderr and stop; if it names `categories.json` or `config.json` violations
that is curated state, so offer to fix it and NEVER regenerate it.

Show every plugin as a table — plugin, skills, tier — ordered `searchable` →
`off` → `enabled`. Mention any `orphan_opt_ins` (opt-ins naming no installed
plugin).

## 2. Ask the action — always

One AskUserQuestion, single-select. Ask it every time; never infer the action
from the rollup, and never skip it because one direction looks empty:

- **Add a plugin** — move a plugin into the searchable tier
- **Remove a plugin** — take a plugin out of it

Put the candidate count in each description. ("Other" is offered
automatically — honour whatever the user types there.) If the chosen action
has no candidates, say so plainly and stop; do not substitute the opposite.

## 3. Multi-select the plugins

One AskUserQuestion, `multiSelect: true`, options = candidates for the chosen
action only:

- **Add** → plugins at tier `off` first (already disabled — one call each),
  then `enabled` ones (these also need a disable). Give each option its skill
  count. An `enabled` plugin going searchable saves ~48 tokens per skill per
  session; an `off` plugin already costs nothing, so it gains findability, not
  tokens — don't present those as the same win.
- **Remove** → the current `searchable` plugins.

Max 4 options per question, 4 questions per call. If candidates exceed that,
offer the highest-payoff ones and **say which were not offered** — never let a
cap look like a complete list.

## 4. Apply

```bash
# add — disable first, ONLY if currently enabled, then opt in
claude plugin disable <plugin> --scope project
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/categorize.py" config --add-searchable <plugin>

# remove — opt out
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/categorize.py" config --remove-searchable <plugin>
```

Two things to confirm rather than assume:

- **The disable writes the user's settings.** Show the exact command first.
  `--scope project` matches `config.json`, which is also committed, so the two
  halves travel together; `local` keeps it out of git; `user` disables the
  plugin machine-wide while only this project can search it — name that
  mismatch if they pick it.
- **A removal leaves the plugin `off`, not enabled.** Different outcomes — ask
  which was meant, and run `claude plugin enable <plugin>` if they want it back
  in context.

On exit 3, fix exactly what stderr names and retry.

## 5. Refresh

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/build_graph.py"   # re-emits catalog/ shards too
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/render.py"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/categorize.py" status
```

That is the whole refresh a tier change needs. The build rewrites the shards
itself, and a toggle can never create an uncategorized skill: categorization
covers every *registered* skill whatever its tier, and opting in changes the
tier, not the registration.

**Only if `counts.uncategorized > 0`, invoke the skill-atlas skill** to file
them. That backlog is pre-existing drift — a plugin installed since the last
`/skill-atlas` run — but this is the moment it starts to hurt, because those
skills now surface in `catalog/uncategorized.md` instead of a real category.
Do not invoke it otherwise: a full atlas pass and a second report buy nothing
here.

Then report what only this command knows: each plugin's before → after tier, the
per-session token change (counting `enabled` → `searchable` moves only), which
settings scope was written, and anything not offered in step 3. Close on the
timing — graph, catalog and atlas are current now, but the context saving
starts at the **next session**, since enable/disable needs a restart.
