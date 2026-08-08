# agent-tooling — operating the Claude Code ecosystem itself - setup, skill authoring and discovery, automation recommendations
<!-- derived by skill-atlas; do not edit. [enabled]: invoke with the Skill tool. [searchable]: Read the SKILL.md at the path and follow it as instructions. -->

## claude-code-setup:claude-automation-recommender [enabled]
Analyze a codebase and recommend Claude Code automations (hooks, subagents, skills, plugins, MCP servers). Use when user asks for automation recommendations, wants to optimize their Claude Code setup, mentions improving Claude Code workflows, asks how to first set up Claude Code for a project, or wants to know what Claude Code features they should use.
- path: /home/danson/.claude/plugins/cache/claude-plugins-official/claude-code-setup/1.0.0/skills/claude-automation-recommender/SKILL.md

## claude-md-management:claude-md-improver [enabled]
Audit and improve CLAUDE.md files in repositories. Use when user asks to check, audit, update, improve, or fix CLAUDE.md files. Scans for all CLAUDE.md files, evaluates quality against templates, outputs quality report, then makes targeted updates. Also use when the user mentions "CLAUDE.md maintenance" or "project memory optimization".
- path: /home/danson/.claude/plugins/cache/claude-plugins-official/claude-md-management/1.0.0/skills/claude-md-improver/SKILL.md
- also in: writing

## skill-atlas:skill-atlas [enabled]
Graph, categorize and visualize the installed Claude Code skill collection. Use when the user asks about their skill atlas, skill graph, skill catalog, categorizing skills, making skills searchable, dangling or broken skills, disabled plugins, duplicate skill names, or wants to visualize/audit what skills are actually loadable. Triggers - "skill atlas", "skill graph", "map my skills", "categorize my skills", "skill catalog", "which skills are dead", "dangling skills", "audit my skills".
- path: /home/danson/.claude/plugins/cache/skill-atlas/skill-atlas/0.4.0/skills/skill-atlas/SKILL.md

## skill-atlas:skill-search [enabled]
Find the best skill for the current task across the entire skill library, including the dormant majority whose descriptions are never loaded into context. Use this before starting any nontrivial task — coding, debugging, git operations, planning, reviewing, writing docs, building UI, handling data or config — even when no loaded skill seems relevant and even when the user does not name a tool or domain: the library usually holds a specialist that stays invisible until searched. Returns ranked matches with descriptions, paths and usage: invoke enabled matches with the Skill tool; for dormant matches, read the SKILL.md at the returned path and follow it. Skip only for trivial one-step requests, or when an already-loaded skill obviously covers the task.
- path: /home/danson/.claude/plugins/cache/skill-atlas/skill-atlas/0.4.0/skills/skill-search/SKILL.md

## skill-creator:skill-creator [enabled]
Create new skills, modify and improve existing skills, and measure skill performance. Use when users want to create a skill from scratch, edit, or optimize an existing skill, run evals to test a skill, benchmark skill performance with variance analysis, or optimize a skill's description for better triggering accuracy.
- path: /home/danson/.claude/plugins/cache/claude-plugins-official/skill-creator/unknown/skills/skill-creator/SKILL.md

## superpowers:dispatching-parallel-agents [searchable]
Use when facing 2+ independent tasks that can be worked on without shared state or sequential dependencies
- path: /home/danson/.claude/plugins/cache/claude-plugins-official/superpowers/6.2.0/skills/dispatching-parallel-agents/SKILL.md
- also in: implementation

## superpowers:subagent-driven-development [searchable]
Use when executing implementation plans with independent tasks in the current session
- path: /home/danson/.claude/plugins/cache/claude-plugins-official/superpowers/6.2.0/skills/subagent-driven-development/SKILL.md
- also in: implementation

## superpowers:using-superpowers [searchable]
Use when starting any conversation - establishes how to find and use skills, requiring skill invocation before ANY response including clarifying questions
- path: /home/danson/.claude/plugins/cache/claude-plugins-official/superpowers/6.2.0/skills/using-superpowers/SKILL.md

## superpowers:writing-skills [searchable]
Use when creating new skills, editing existing skills, or verifying skills work before deployment
- path: /home/danson/.claude/plugins/cache/claude-plugins-official/superpowers/6.2.0/skills/writing-skills/SKILL.md
- also in: writing
