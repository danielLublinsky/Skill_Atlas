# docs/ — component guide for agents

Read [1-overview.md](1-overview.md) first: it carries the architecture, the
module map and the invariants every other doc assumes. After that, jump
straight to the component you are touching.

| # | Doc | Read it when you are touching… |
| --- | --- | --- |
| 1 | [overview](1-overview.md) | anything — the map, the tiers, the invariants |
| 2 | [initialization](2-initialization.md) | install, scopes, what a first run creates, env vars |
| 3 | [discovery](3-discovery.md) | which skills exist: manifests, ids, collisions, enabled state |
| 4 | [graph build](4-graph-build.md) | `graph.json`, edge extraction, exit codes |
| 5 | [categorization](5-categorization.md) | `categories.json`, the taxonomy, `categorize.py` |
| 6 | [catalog & search](6-catalog-and-search.md) | `catalog/` shards, `skill-search`, the session index line |
| 7 | [rendering](7-rendering.md) | `atlas.html`, the D3 template, visual encodings |
| 8 | [freshness & hooks](8-freshness-and-hooks.md) | SessionStart / PostToolUse, the fingerprint |
| 9 | [testing & conventions](9-testing-and-conventions.md) | the suite, the sandbox, how to land a change |

These docs describe **how the system works today** and the reasoning that is
not visible in the code. The two design specs remain the historical record —
what was considered, what was dropped, and why:

- [DESIGN.md](../DESIGN.md) — Phase 1: graph, discovery, freshness, visualization.
  §6 records the usage-tracking phase that was specified and then cut.
- [DESIGN-PHASE2.md](../DESIGN-PHASE2.md) — Phase 2: the three-tier model,
  categorization and search. **§0 amendments override its body text**;
  amendment 8 (fully project-local) is the one that reshaped the most code.

When a doc here disagrees with a design spec, the code wins and this folder is
wrong — say so rather than propagating it.
