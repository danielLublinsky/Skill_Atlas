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
not visible in the code. [DESIGN.md](../DESIGN.md) is the historical record for
both phases — what was considered, what was chosen, what was dropped, and why.
It is not a description of current behaviour. Sections worth knowing:

| § | Holds |
| --- | --- |
| 6 | usage tracking — fully specified, then cut, with the arithmetic that killed it |
| 10.2 | the two standing privacy rules |
| 10.4 | what is still open |
| 11 | the four findings that justify the tool |
| 12–14 | the three-tier model, categorization, catalog and search |
| 15 | fully project-local — the decision that reshaped the most code |
| 16 | what Phase 2 deliberately does not build |

When a doc here disagrees with DESIGN.md, the doc wins; when the code disagrees
with either, the code wins — say so rather than propagating it.
