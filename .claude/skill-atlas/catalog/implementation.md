# implementation — executing planned work - development loops, running plans, parallelizing agents, building prototypes
<!-- derived by skill-atlas; do not edit. [enabled]: invoke with the Skill tool. [searchable]: Read the SKILL.md at the path and follow it as instructions. -->

## mattpocock-skills:implement [enabled]
Implement a piece of work based on a spec or set of tickets.
- path: /home/danson/.claude/plugins/cache/claude-plugins-official/mattpocock-skills/1.2.3/skills/engineering/implement/SKILL.md

## mattpocock-skills:prototype [enabled]
Build a throwaway prototype to answer a design question. Use when the user wants to sanity-check whether a state model or logic feels right, or explore what a UI should look like.
- path: /home/danson/.claude/plugins/cache/claude-plugins-official/mattpocock-skills/1.2.3/skills/engineering/prototype/SKILL.md
- also in: planning

## mattpocock-skills:tdd [enabled]
Test-driven development. Use when the user wants to build features or fix bugs test-first, mentions "red-green-refactor", or wants integration tests.
- path: /home/danson/.claude/plugins/cache/claude-plugins-official/mattpocock-skills/1.2.3/skills/engineering/tdd/SKILL.md

## mattpocock-skills:wizard [enabled]
Generate an interactive bash wizard that walks a human through steps only they can perform. Use when provisioning infrastructure, setting up credentials or CI secrets, walking an unfamiliar third-party dashboard, or running a one-off migration or cutover. Don't invoke this for steps the agent can perform itself.
- path: /home/danson/.claude/plugins/cache/claude-plugins-official/mattpocock-skills/1.2.3/skills/engineering/wizard/SKILL.md

## superpowers:dispatching-parallel-agents [searchable]
Use when facing 2+ independent tasks that can be worked on without shared state or sequential dependencies
- path: /home/danson/.claude/plugins/cache/claude-plugins-official/superpowers/6.2.0/skills/dispatching-parallel-agents/SKILL.md
- also in: agent-tooling

## superpowers:executing-plans [searchable]
Use when you have a written implementation plan to execute in a separate session with review checkpoints
- path: /home/danson/.claude/plugins/cache/claude-plugins-official/superpowers/6.2.0/skills/executing-plans/SKILL.md
- also in: planning

## superpowers:subagent-driven-development [searchable]
Use when executing implementation plans with independent tasks in the current session
- path: /home/danson/.claude/plugins/cache/claude-plugins-official/superpowers/6.2.0/skills/subagent-driven-development/SKILL.md
- also in: agent-tooling

## superpowers:test-driven-development [searchable]
Use when implementing any feature or bugfix, before writing implementation code
- path: /home/danson/.claude/plugins/cache/claude-plugins-official/superpowers/6.2.0/skills/test-driven-development/SKILL.md
