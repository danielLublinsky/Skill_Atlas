# skill-atlas — Design Spec

**Status:** Phase 1 shipped · Phase 2 (categorization + search) shipped 2026-08-07 (spec + amendments in [DESIGN-PHASE2.md](DESIGN-PHASE2.md))
**Scope:** Phase 1 — structural skill graph + HTML visualization + freshness hooks. Phase 2 —
three-tier skill catalog, model-assigned categories, and a search skill, specified in
[DESIGN-PHASE2.md](DESIGN-PHASE2.md).
**Explicitly out of scope:** usage tracking / invocation counting — fully specified, then dropped;
the condensed design and the arithmetic that killed it are recorded in §6. Also out of scope:
embeddings / RAG over skill *content* — the broader "no retrieval, no query interface" non-goal
was narrowed on 2026-08-06 when Phase 2 was reassigned (§0.5).

---

## 0. Revision — 2026-08-01

The first draft was written at the desk rather than at the machine. Its reasoning held up; its
premises about the environment did not. Checking them against the live filesystem turned up factual
errors in discovery, a data-collection layer that duplicates one Claude Code already ships, a join
key that cannot join, and a statistical problem that undermines the headline claim.

This section records the evidence and the decisions it forced, so a future reader sees *why* §4.1
looks the way it does instead of rediscovering the same facts with `find`.

### 0.1 Evidence

| Finding | Evidence |
| --- | --- |
| Claude Code already writes append-only per-session JSONL | 196 files, 71 MB, `~/.claude/projects/<cwd-slug>/<session_id>.jsonl` |
| Skill payload key is `skill`, value is namespaced | `{"name":"Skill","input":{"skill":"superpowers:brainstorming"}}` |
| Sub-agent transcripts are separate files under the parent session | 45 files at `<project>/<session_id>/subagents/agent-*.jsonl` |
| §4.1's original plugin glob matched nothing | real: `plugins/cache/<mp>/<plugin>/<version>/skills/**/SKILL.md` |
| "Any dir with SKILL.md" over-counts by ~60% | 104 on disk / 60 installed / 41 registered / 27 enabled |
| `plugin.json` may carry a `skills[]` allowlist — or not | `mattpocock-skills` registers 22 of 41; `superpowers` has no `skills` key |
| Most-used plugin is disabled | `enabledPlugins.superpowers = false`; 11 of 24 invocations |
| 42% of invocations hit built-ins with no file on disk | `dataviz`, `run`, `init`, `claude-api`, `verify`, `security-reviewer` |
| Usage signal is too sparse for a verdict | 14 in-collection invocations / 39 skills → λ≈0.36, P(zero)≈70% |
| `mentions` noise is bimodal by name shape | naive 91 edges (top: `implement` ×10) vs strict 48 |
| Real dangling reference found | `setup-matt-pocock-skills` cites `` `qa` `` — deprecated, unregistered |

### 0.2 Decisions

1. **Usage comes from existing transcripts.** Read `~/.claude/projects/**/*.jsonl`. No logging hooks.
2. **Discovery is manifest-driven.** `installed_plugins.json` → `plugin.json` `skills[]` (glob
   `skills/*/` fallback when absent) → `~/.claude/skills` + `<cwd>/.claude/skills`.
3. **Node id = the invocation string.** `superpowers:brainstorming`, `graphify`. Built-ins invoked
   but absent from disk get synthesized nodes with `scope: "builtin"`, `path: null`.
4. **Enabled is a node attribute, not a filter.** All registered skills enter the graph; `enabled`
   is rendered as a channel.
5. **Usage verdicts gate on event count, not session count.** Below the gate the usage view is
   inert and labelled "insufficient data".
6. **Unregistered `SKILL.md` is indexed, not drawn** — except when a registered skill points at one,
   which renders as a dangling node plus a red edge.
7. **`mentions` requires an unambiguous form**: backtick-quoted, slash-prefixed, or hyphenated name.
8. **One global graph, per-project usage facet.** Worktree and scratchpad dirs normalize to the
   parent repo.
9. **Field allowlist on transcript reads.** Extract `sessionId`, timestamp, project slug and
   `Skill.input.skill`; discard the line. Exceptions log path + line number + type, never content.
10. **Usage-driven visual channels stay off until the gate passes.**

### 0.3 The caveat this revision does not resolve

After these corrections the headline question — *"which parts are dead weight?"* — is gated off on
the author's own machine, and may stay that way indefinitely. The event rate is simply too low. This
document should not imply the join will light up.

What Phase 1 delivers with no usage data at all is still non-trivial: four real defects in this
collection were found during the grilling itself, before a line of code existed. They are recorded
in §11 as the standing argument that the structural half carries the tool.

### 0.4 Revision — 2026-08-06: Phase 2 dropped

§0.3's caveat matured into a decision. The gate needed ~117 in-collection events and had 14, with
no realistic path to closing the gap — skill invocation is simply too rare an event on a personal
machine. Rather than carry transcript-reading machinery, its privacy obligations, and three inert
visual channels for a verdict that may never be renderable, Phase 2 was cut from scope entirely:
nothing reads `~/.claude/projects`, no `usage.json` exists, and every usage-driven channel is gone
from the code. §6 keeps the condensed design and the arithmetic as an out-of-scope record — the
negative result is the finding, and it is worth keeping.

### 0.5 Revision — 2026-08-06: Phase 2 reassigned — categorization + search

The same day the usage phase was cut, its number was given to a different increment: a skill
**categorizer + search layer**, specified in [DESIGN-PHASE2.md](DESIGN-PHASE2.md). In §0.4, §2,
§6, §7.1, §10 and §11 below, "Phase 2" still refers to the dropped usage phase — those sections
are the historical record and are left as written.

The reassignment reverses one non-goal, deliberately and narrowly. §1 said *"Not a retrieval
layer. No embeddings, no index, no query interface."* What the new Phase 2 builds is an index
over skill **descriptions** (a category catalog) and a query interface (a search skill);
embeddings and retrieval over skill *content* stay out of scope. The motivation is the mirror
image of the measurement that killed usage tracking: invocations were too **sparse** to carry a
verdict, but descriptions are **dense** — every skill has one, always — and their per-session
injection cost (~48 tokens per enabled skill, §7.1) is exactly what becomes worth optimizing once
a multi-plugin collection outgrows its context budget. The three-tier model
(enabled / searchable / disabled), the curated taxonomy, and the full decision log are in the
phase doc. §10.3's overlap detection is absorbed by it.

---

## 1. Purpose

A Claude Code plugin that answers two questions nobody can currently answer about their own skill collection:

| Question | Answered by | Status |
| --- | --- | --- |
| What does my skill collection actually look like? | Phase 1 — graph + visualization | answerable today |
| Which parts of it are dead weight? | usage tracking | **out of scope — dropped (§6)** |
| Which skill fits this task, without paying every description into every session? | Phase 2 — categorization + search | **designed — [DESIGN-PHASE2.md](DESIGN-PHASE2.md)** |

The original thesis was that the value is in the join: a graph alone shows structure but not
relevance, usage counts alone show hit rates but not why something is orphaned, and rendering usage
*onto* the graph is what makes dead subgraphs visible at a glance.

**That thesis did not survive measurement.** Against a real collection, skill invocation is too
rare an event to support a per-skill verdict — 14 in-collection invocations across 39 skills over
151 sessions, where ~70% of skills would read as "never invoked" by chance alone. The join was
specified, then dropped; §6 keeps the condensed design and the arithmetic that killed it.

What Phase 1 answers without any usage data turned out to be the larger part of the value: which
files are actually loadable, which skills are switched off, which point at things that no longer
exist, and which are duplicated. Four such defects in this collection are recorded in §11. None of
them needed a single invocation to find.

### Non-goals

- Not a skill authoring tool. It observes; it does not edit SKILL.md files.
- Not a usage tracker. It never opens session transcripts and counts nothing — see §6.
- Not a *content*-retrieval layer. No embeddings, no RAG over skill bodies. *(Narrowed
  2026-08-06, §0.5: Phase 2 adds a description-level catalog and a search skill — the original
  blanket form of this non-goal is reversed to exactly that extent and no further.)*
- Not a productivity dashboard. No lines-of-code, no cost attribution.
- Not multi-user. Single machine, local files, no server.

---

## 2. Architecture

```text
  manifests + skill roots ─▶┌──────────────────────┐
  installed_plugins.json    │   build_graph.py     │──▶ graph.json
  settings.json             │   (static analysis)  │
  */plugin.json             └──────────────────────┘
  ~/.claude/skills                      ▲
  <cwd>/.claude/skills                  │ triggered by
                          ┌─────────────┴──────┐
                          │  staleness check   │  SessionStart
                          │  dirty flag        │  PostToolUse(Write|Edit → SKILL.md | manifest)
                          │  explicit build    │  /skill-atlas, CI, npm build
                          └────────────────────┘

                       graph.json ──▶ render.py ──▶ atlas.html
```

**Design rule that governs everything below:** the inputs are manifests and skill files, nothing
else — skill-atlas never opens `~/.claude/projects` (Claude Code's session transcripts; reading
them was Phase 2, dropped in §6). `graph.json` and `atlas.html` are derived artifacts and must be
safely regenerable from scratch at any time. If either is deleted or corrupted, the fix is to
rebuild, never to repair.

---

## 3. Data model

### 3.1 `graph.json`

Regenerated wholesale on every build. Never edited in place.

**Node ids are invocation strings.** A skill's id is the exact string Claude Code invokes it with —
`superpowers:brainstorming`, `graphify`. That string is already unique and already namespaced;
path-derived ids would have added a mapping for no benefit.

```jsonc
{
  "version": 2,
  "generated_at": "2026-08-01T09:14:22Z",
  "roots": ["/home/u/.claude/skills", "/repo/.claude/skills"],
  "source_fingerprint": "sha256:...",   // see §5.1
  "nodes": [
    {
      "id": "mattpocock-skills:tdd",     // the invocation string
      "type": "skill",                   // "skill" | "file"
      "name": "tdd",
      "description": "Test-driven development...",
      "path": ".../mattpocock-skills/1.2.0/skills/engineering/tdd/SKILL.md",
      "scope": "plugin",                 // "user" | "project" | "plugin"
      "plugin": "mattpocock-skills",
      "version": "1.2.0",                // installed plugin version, null otherwise
      "registered": true,                // in plugin.json skills[], or a user/project skill
      "enabled": true,                   // settings.json enabledPlugins; see §4.1
      "bytes": 3841,
      "mtime": "2026-07-19T11:02:00Z"
    },
    {
      "id": "file:.../tdd/references/red-green.md",
      "type": "file",
      "name": "red-green.md",
      "path": "...",
      "exists": true,
      "bytes": 1120
    }
  ],
  "edges": [
    { "source": "mattpocock-skills:tdd", "target": "file:...red-green.md",
      "kind": "references", "broken": false },
    { "source": "mattpocock-skills:tdd", "target": "mattpocock-skills:code-review",
      "kind": "mentions" },
    { "source": "mattpocock-skills:setup-matt-pocock-skills", "target": "skill?:qa",
      "kind": "dangling", "reason": "unregistered" }
  ],
  "stats": {
    "skills": 41, "enabled": 27, "unregistered": 63,
    "files": 96, "edges": 173, "broken_refs": 2, "dangling": 1, "orphans": 5,
    "duplicate_names": []
  }
}
```

**Edge kinds**

| kind | Meaning | Extraction |
| --- | --- | --- |
| `references` | SKILL.md points at a bundled file | markdown links + bare `references/…`, `scripts/…`, `assets/…` paths |
| `mentions` | SKILL.md names another *loadable* skill | strict match — see below |
| `dangling` | SKILL.md names a skill that cannot be loaded | same match; target is unregistered, disabled, or absent |

**`mentions` extraction is strict, and deliberately so.** The naive rule from the first draft —
word-boundary match on known skill names — produced 91 edges on the author's 41-skill collection,
dominated by skills whose names are ordinary English words (`implement` appeared in 10 other
SKILL.md files, essentially all as the verb). Precision is bimodal by name shape: hyphenated names
like `resolving-merge-conflicts` never collide by accident, single common words almost always do.

So a mention counts only when the name appears in an unambiguous form:

- backtick-quoted — `` `tdd` ``
- slash-prefixed — `skills/tdd`
- or the name is hyphenated / multi-word

This halves edge count to 48 and removes the `implement` class of false positive. It also preserves
the finding that motivated keeping `mentions` at all (§11.2), which appears as `` `qa` ``.

`mentions` remains a weak, inferred edge — it is not part of the Agent Skills spec, it is a
convention. Render it differently and never treat it as a hard dependency.

**`dangling` is the same extraction with a different target.** It is the one inferred edge worth
acting on: a live skill instructing the reader to use something that cannot be loaded is a defect in
either the skill or the install. It is the highest-value output the graph produces.

There is no second data file. An earlier revision specified `usage.json` (per-skill invocation
counts rolled up from session transcripts); it went with Phase 2 — see §6.

---

## 4. Phase 1 — Graph builder

### 4.1 Discovery

**"Any directory containing SKILL.md" is wrong**, and not marginally. On the author's machine it
yields 104 nodes of which ~63 are not skills: other authors' `deprecated/` and `in-progress/` trees,
stale cached plugin versions, and marketplace catalogue entries for plugins that were never
installed. A 60% false-positive rate on the primary node type, every one of which would land in the
"not invoked" column.

Discovery is therefore **manifest-driven**. The collection has four nested definitions and the graph
must be explicit about which one it means:

| Definition | Count here | Authority |
| --- | --- | --- |
| `SKILL.md` on disk | 104 | filesystem — *not used* |
| Under installed plugin paths | 60 | `installed_plugins.json` |
| **Registered** — enters the graph | **41** | each `plugin.json` `skills[]` |
| **Enabled** — loadable this session | **27** | `settings.json` `enabledPlugins` |

**Walk order:**

1. `~/.claude/skills/*/SKILL.md` → scope `user`
2. `<cwd>/.claude/skills/*/SKILL.md` → scope `project`
3. For each entry in `~/.claude/plugins/installed_plugins.json` → scope `plugin`:
   - take `installPath` (this is what excludes stale cached versions — `superpowers/6.1.1` and
     `6.2.0` both exist on disk; only `6.2.0` is installed)
   - read `<installPath>/.claude-plugin/plugin.json`
   - **if it has a `skills[]` array**, that array is the registered set, verbatim. Paths are relative
     to the plugin root and may nest arbitrarily — `mattpocock-skills` uses
     `./skills/engineering/tdd`, registering 22 of the 41 `SKILL.md` files it ships.
   - **if it has no `skills` key**, fall back to globbing `<installPath>/skills/*/SKILL.md`.
     `superpowers` has no `skills` key and all 14 of its skills register this way. This fallback is
     load-bearing, not a defensive nicety.

Never walk `~/.claude/plugins/marketplaces/` — that tree is the *catalogue* of installable plugins,
not the installed set. Counting it adds 31 phantom skills.

**Node id** is the invocation string (§3.1): `<plugin>:<name>` for plugin skills, bare `<name>` for
user and project skills. `name` comes from frontmatter `name:`, falling back to the directory name.

**Enabled state** is read from `settings.json` `enabledPlugins` and recorded as a node attribute —
it is *not* a discovery filter. A disabled skill still enters the graph. This matters: the author's
most-invoked plugin is currently disabled (§11.1), and filtering on enabled state would have made
that invisible at exactly the moment it was worth shouting about.

**Unregistered `SKILL.md` files are indexed but not drawn.** They are recorded with
`registered: false` and excluded from the canvas and from `stats.skills` — with one exception: if a
registered skill *mentions* an unregistered one, the target is drawn as a dangling node with a red
edge. That single exception is what surfaces §11.2.

**Collision handling:** two skills may share a `name` across scopes — e.g. a project skill shadowing
a user skill. Invocation strings collide too, since both are invoked as the bare name. Do not
silently merge or drop. Emit both nodes with disambiguated ids (`graphify@user`, `graphify@project`),
record a `duplicate_names` entry in `stats`, and resolve mentions of the bare name to neither.
Duplicate names are a real defect worth surfacing, not an edge case to paper over.

**Built-in skills** (`dataviz`, `run`, `init`, …) ship inside Claude Code and have no `SKILL.md`
anywhere on disk, so discovery cannot find them and they do not enter the graph. They only mattered
to usage accounting — 42% of recorded invocations hit them — which went with Phase 2 (§6).

### 4.2 Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Graph built, nothing dangling |
| 1 | Graph built, ≥1 dangling edge |
| 2 | Build failed (unreadable root, unparseable manifest, write error) |

Exit 1 covers **three** dangling kinds, not just the first:

- a `references` edge to a file that does not exist
- a `mentions` edge to an **unregistered** skill (`setup-matt-pocock-skills` → `qa`)
- a `mentions` edge to a **disabled** skill

All three mean the same thing operationally — a skill points somewhere the reader cannot follow.
Exit 1 makes the builder usable as a CI gate without a separate linting step.

---

## 5. Auto-update

The graph must never be silently stale. Four triggers, cheapest first.

### 5.1 Staleness check on `SessionStart`

Cheap fingerprint, not a full rebuild:

```text
fingerprint = sha256(sorted(
    [(path, mtime_ns, size) for every SKILL.md]
  + [(path, mtime_ns, size) for every manifest]        # <-- required
))

manifests = ~/.claude/plugins/installed_plugins.json
            ~/.claude/settings.json
            <installPath>/.claude-plugin/plugin.json   for each installed plugin
```

**The manifests are not optional.** Since §4.1 made discovery manifest-driven, the graph depends on
files that are not `SKILL.md`. Toggling `enabledPlugins.superpowers` changes the graph and touches no
skill file at all — under the first draft's fingerprint the graph would go silently stale, which §5
opens by forbidding. Installing or removing a plugin has the same property. The cost is a handful of
extra `stat` calls: on this machine, 5 manifests against 104 skill files.

Stat-only walk — no file reads. Compare against `source_fingerprint` in `graph.json`; rebuild only on
mismatch. Must complete in **< 200 ms for 500 skills** or it degrades session startup. If the walk
exceeds a 2s budget, abandon it, log, and let the session proceed with a stale graph. **A slow hook
is worse than a stale graph.**

This is the trigger that covers plugin installs, plugin enable/disable, `git pull`, manual file
drops, and anything else that happens outside a session.

### 5.2 Dirty flag on `PostToolUse`

Matcher `Write|Edit`. Write a `.dirty` marker if the touched path matches any of:

- `**/SKILL.md` or `**/skills/**`
- `**/.claude-plugin/plugin.json`
- `**/.claude/settings.json` or `**/.claude/settings.local.json`
- `**/.claude/plugins/installed_plugins.json`

Same reasoning as §5.1: the manifest paths are as load-bearing as the skill paths, and omitting them
leaves the exact same silent-staleness hole.

Do **not** rebuild inline — that puts filesystem work in the middle of a tool call. The marker is
consumed by the next `SessionStart`, by `Stop`, or by an explicit build.

Rationale: skill edits during a session are common while authoring, and rebuilding on each one is
wasted work. Deferring to a session boundary batches them.

### 5.3 Explicit

- `/skill-atlas` slash command — rebuild + report
- `python3 scripts/build_graph.py` — for `npm run build`, Makefile, CI
- Idempotent and safe to call concurrently (write to temp, atomic rename)

### 5.4 Hook wiring and invariants

| Event | Matcher | Script | Purpose |
| --- | --- | --- | --- |
| `SessionStart` | — | `check_stale.py` | fingerprint check (§5.1), rebuild on mismatch |
| `PostToolUse` | `Write\|Edit` | `mark_dirty.py` | flag graph stale (§5.2) |

**Hook invariants — non-negotiable:**

1. Always exit `0`. A non-zero hook can interrupt the session.
2. Never write to stdout (except the documented JSON contract, which these hooks don't use).
3. Swallow every exception to `debug.log` — path, line number and exception **type** only, never
   the content of whatever was being parsed.
4. Hard timeout 10s.
5. Never block on network or lock contention.

### 5.5 What is deliberately not built

A filesystem watcher. It needs a resident process, it fights with editors that write-then-rename, and it buys latency nobody needs — the graph is only read at session start and on demand. Revisit only if §5.1 proves too slow.

---

## 6. Usage tracking — OUT OF SCOPE (dropped 2026-08-06)

Phase 2 was fully specified against the live machine (rev. 2026-08-01), its downstream scaffolding
was built, and then the whole phase was cut. This section is the condensed record of what it would
have been and the arithmetic that killed it — kept so the next person tempted to build it starts
from the reason it isn't here. Nothing in this section is implemented, and none of it should be
implemented without clearing §6.2's bar.

### 6.1 What it would have been

- **Read Claude Code's own transcripts** (`~/.claude/projects/**/*.jsonl` — 196 files, 71 MB here)
  rather than logging anything. Claude Code already writes per-session JSONL for every session that
  ever ran, so history would have been retroactive — at the cost of coupling to an undocumented
  internal format that can change without notice.
- **A strict parse boundary**, because transcripts are the user's full conversation history:
  extract session id, timestamp, project slug and `Skill.input.skill` per line
  (the value is already the graph's node id — the join is an identity), discard everything else;
  `debug.log` limited to path + line + exception type, never line content; `~/.claude/projects`
  opened strictly read-only.
- **`rollup.py`** folding transcripts into a `usage.json` cache incrementally via per-file
  byte-offset watermarks, with `--rebuild` required to agree exactly with the incremental path.
  Sub-agent invocations counted separately (a sub-agent using a skill is the main agent's decision
  propagating, not an independent signal). Worktree and scratchpad slugs normalized into their
  parent repo — unnormalized, one repo here fragments into eight and every per-project figure is
  wrong. Invoked-but-absent built-ins synthesized as `scope: "builtin"` nodes.
- **Usage rendered onto the graph** — node area by session count, dashed border for never-invoked,
  recency fade — behind a statistical gate, with a per-project selector because usage is
  project-shaped (§11.4).

### 6.2 The arithmetic that killed it

Zero invocations cannot distinguish "never needed" (delete it) from "needed and missed" (fix the
description) from "could not be invoked" (it was disabled the whole time — §11.1 is exactly this,
and its 14 skills would all read as confident zeros). A zero only starts carrying information when
the expected event count per skill is high enough:

```text
gate:  events_in_collection ≥ 3 × skills_in_collection      (λ ≥ 3 ⇒ P(zero by chance) ≤ 5%)
```

The measured corpus: **14 in-collection invocations across 39 skills over 151 sessions** — λ ≈ 0.36,
so under a Poisson model P(a skill shows zero) = e^−0.36 ≈ 70% *even if usage were perfectly
uniform*. The gate needed ~117 events and had 14, with no realistic path to closing the gap: skill
invocation is simply too rare an event on a personal machine. A feature whose gate never opens is
dead weight of exactly the kind this tool exists to point at — so it was cut rather than shipped
inert, and cutting it also deleted the most sensitive surface in the design (transcript reading;
see §10.2).

**The honest negative result is the deliverable:** invocation frequency does not carry enough
signal to judge a personal skill collection. The structural graph carries the tool — all four §11
findings needed zero usage data.

Revisit only if the input changes shape: a documented usage API from Claude Code, or a team-scale
corpus where event density is an order of magnitude higher. The gate criterion above is the bar any
revival must clear before rendering a single usage pixel — lowering it is not a way to get answers
sooner, it is a way to get confident-looking wrong ones.

---

## 7. HTML visualization

Single self-contained `atlas.html` — D3 inlined, no CDN, no build step, opens from `file://`. Generated by `render.py` from `graph.json`.

### 7.1 Visual encoding

| Channel | Encodes |
| --- | --- |
| Node shape | rounded rect = skill, small circle = bundled file |
| Node color | scope — user / project / plugin |
| Node fill | stage colour = disabled, tinted = enabled — "hollow" is painted, never transparent, so edges running to the node centre stop at its border instead of crossing the label |
| Node stroke | grey dash = dangling target (unregistered/absent) |
| Edge style | solid = `references`, dotted = `mentions` |
| Edge color | red = broken reference or `dangling` edge |
| Edge width | uniform (no data to encode; resist the temptation) |

Usage-driven channels — node area by invocation count, dashed border for never-invoked, recency
fade — went with Phase 2 (§6). Every skill renders at uniform size and full opacity, and nothing in
the picture claims to know how often anything runs. What carries the atlas is scope colour,
disabled fill, and red dangling edges — which is where every finding in §11 actually shows up.

**Deliberately unencoded: token cost.** This was tested rather than assumed. The enabled collection's
descriptions total ~4,800 characters ≈ **1,200 tokens injected per session**, about 48 tokens per
skill. Real, but not decision-changing at this size; the channel would cost legibility to display a
number nobody would act on. Revisit past ~100 enabled skills, where the per-session cost becomes
material and, unlike invocation count, it is dense — every skill has one, always.

Also unencoded: file size, description length.

### 7.2 Layout

Force-directed, seeded deterministically so the same graph renders the same way twice — a layout that reshuffles on every build makes visual diffing impossible.

Cluster by scope. Orphan skills (degree 0) pinned to a labelled gutter rather than drifting to the edge of the canvas, since orphans are a primary finding and shouldn't be hard to find.

### 7.3 Interaction

- hover → tooltip: id, description, path, plugin + version, enabled state. It parks immediately
  left of the legend rather than trailing the cursor: a panel that follows the mouse covers the
  neighbourhood you hovered to inspect, and its text moves while you read it.
- click → pin node, highlight 1-hop neighbourhood, dim the rest. The whole reading freezes:
  the tooltip holds the clicked node and stays put once the cursor leaves, so a long
  description can actually be read and hovering elsewhere cannot desynchronise the panel from
  the highlight. Click the node again, or the background, to release.
- The incident edges are actively highlighted (thicker, full contrast), not merely spared the
  dimming — which edges connect is the answer being looked for, and broken edges keep their
  red under the highlight. Neighbouring file dots brighten and gain a ring rather than
  growing: at 4.5px a size change is unreadable, and a moving radius would shift the layout
  it sits in.
- search box → filter by name/description, live
- toggles: hide files, hide `mentions` edges, show dangling only, show unregistered
- legend, always visible, anchored top-right and never moved by anything else on the canvas —
  it is the key to the picture, so it has to be findable in the same place every time. It
  carries scope, state, edges and catalog; the shape rows are dropped (rect-vs-dot is
  self-evident) and so is the plugin-tag row.
- footer: view (global / project name), generated timestamp, node and defect counts, staleness
  warning if `graph.json` is older than the newest SKILL.md **or manifest**

### 7.4 Scale

Fine to 200 nodes. Between 200–600, collapse `file` nodes into a per-skill badge count by default. Above 600, force-directed layout stops being readable regardless of tuning — fall back to a sortable table and treat the graph view as a filtered drill-down. Do not attempt to make a 2,000-node hairball legible.

Manifest-driven discovery (§4.1) is also a scale decision, not only a correctness one: it takes this
collection from 104 skill nodes to 41, comfortably inside the first band. The naive walk would have
spent more than half the legibility budget rendering other people's `deprecated/` directories.

---

## 8. Layout & config

```text
skill-atlas/
├── .claude-plugin/plugin.json
├── hooks/hooks.json
├── scripts/
│   ├── build_graph.py      # manifests + skill roots → graph.json
│   ├── check_stale.py      # SessionStart fingerprint (§5.1)
│   ├── mark_dirty.py       # PostToolUse dirty flag (§5.2)
│   └── render.py           # graph.json → atlas.html
├── skills/skill-atlas/SKILL.md
├── commands/skill-atlas.md
└── README.md
```

Component directories live at plugin root. Only `plugin.json` goes in `.claude-plugin/` — nesting components inside it makes them silently invisible: the plugin loads, the components don't. All hook paths use `${CLAUDE_PLUGIN_ROOT}`.

Note during development: SKILL.md edits apply immediately, but changes to `hooks/`, `agents/`, and `.mcp.json` need `/reload-plugins` or a restart.

| Env var | Default | Meaning |
| --- | --- | --- |
| `SKILL_ATLAS_HOME` | `~/.claude/skill-atlas` | artifact root — derived files only |
| `SKILL_ATLAS_CLAUDE_DIR` | `~/.claude` | Claude Code config root (test seam) |
| `SKILL_ATLAS_AUTOBUILD` | `1` | `0` disables the SessionStart staleness check |

`SKILL_ATLAS_PROJECTS`, `SKILL_ATLAS_GATE_LAMBDA` and `SKILL_ATLAS_SUBAGENTS` are gone — all three
configured the dropped usage tracking (§6).

---

## 9. Milestones

| # | Deliverable | Done when |
| --- | --- | --- |
| 1 | `build_graph.py` | Against real roots: registered count matches the manifests, **not 104** |
| 2 | Dangling detection | Exits 1 and names `setup-matt-pocock-skills → qa` |
| 3 | ~~`rollup.py`~~ | dropped with Phase 2 (§6) |
| 4 | Auto-update | Toggling `enabledPlugins` rebuilds on next session start, unprompted |
| 5 | `render.py` | Self-contained HTML opens offline, encodings match §7.1 |
| 6 | Findings validated | Every structural §11 item (11.1–11.3) reproduced by the tool rather than by hand |

Validation is measured against the structural findings in §11, which the tool must reproduce
unaided. (§11.4 is usage evidence — it was measured once by hand during the grilling and exists to
justify §6, not to be reproduced.) Milestone 6 is the real one; everything before it is
unvalidated.

---

## 10. Open questions and standing constraints

### 10.1 Transcript format drift — resolved by dropping Phase 2

The standing risk of reading an undocumented internal format vanished when the reading did.
Nothing in the tool parses transcripts, so there is no format to drift against.

### 10.2 Privacy — mostly dissolved, one rule survives

With Phase 2 dropped this stopped being the most sensitive part of the design: skill-atlas reads
manifests and skill files only, and never opens `~/.claude/projects`. What survives, as a standing
rule rather than a constraint under pressure:

1. **`debug.log` never receives parsed content** (§5.4 invariant 3). A parse error naturally wants
   to log the offending line; log path, line number and exception type only. The rule costs nothing
   and keeps the log safe no matter what future inputs are parsed.
2. **Derived artifacts show real paths and, in project views, real directory names.** An
   `atlas.html` screenshot disclosing a project's existence is a smaller exposure than the Phase 2
   transcript concern was, but sharing one is still a decision, not an accident.

### 10.3 Overlap detection — absorbed into the categorization phase (2026-08-06)

Two skills with near-identical descriptions is a real defect and cheap to detect with token overlap.
It is also, unlike usage, **dense** — every skill has a description, so the signal does not depend on
an event rate that may never arrive. With Phase 2 gone, this is the natural next thing to build on
top of the pure structural graph.

**Absorbed 2026-08-06:** the categorization + search phase (§0.5, DESIGN-PHASE2.md) subsumes
this. Model-assigned categories put near-duplicates in the same bucket, where they are visible
side by side in the atlas; ranked multi-match search returns them together at the one moment a
duplicate actually matters — when one of them is about to be used. The dense-signal argument in
the paragraph above is the same one that motivated the whole phase.

### 10.4 Whether the usage gate would ever open — resolved: no, and Phase 2 was dropped for it

The question this section used to hold — wait for more sessions, or accept the negative result —
was answered on 2026-08-06 by cutting the phase. The record is §6; the accurate negative result
stands: *invocation frequency does not carry enough signal to judge a personal skill collection.*

**Resolved earlier** (first draft's questions 1–4): payload shape, sub-agent attribution (both now
§6.1), `mentions` value (§3.1 — kept, made strict), project scoping (global graph + per-project
views, §7.3).

---

## 11. Findings on the author's collection

Recorded because they are the standing evidence that Phase 1 pays for itself. All four were found by
hand while stress-testing this document, before any code existed — which is the argument that the
structural half carries the tool and the usage half is garnish.

### 11.1 The most-used plugin is disabled

`settings.json` has `enabledPlugins.superpowers = false`. `superpowers` accounts for **11 of 24
recorded invocations — 46%**, by a wide margin the most-used plugin in the collection. Its 14 skills
are installed, registered, and invisible to every session.

This is the finding that set §4.1's rule that enabled state is an attribute rather than a filter. A
tool that showed only enabled skills would have gone silent on precisely the thing worth shouting
about.

### 11.2 A live skill points at a deprecated one

`mattpocock-skills/skills/engineering/setup-matt-pocock-skills/SKILL.md:40`:

> Skills like `to-tickets`, `triage`, `to-spec`, and `qa` read from and write to it…

`to-tickets`, `triage` and `to-spec` are registered. **`qa` is in `deprecated/` and absent from
`plugin.json`'s `skills[]`** — it cannot be loaded. A registered skill is instructing the reader to
use something that does not exist.

This is the `dangling` edge kind (§3.1) and the reason `mentions` survived rather than being cut. It
is also the single highest-value output the graph produces to date.

### 11.3 Sixty percent of `SKILL.md` files are not skills

104 `SKILL.md` on disk; 41 registered. The gap is `deprecated/`, `in-progress/`, `personal/` and
`misc/` trees inside third-party plugins (19 in `mattpocock-skills` alone), stale cached plugin
versions, and 31 marketplace catalogue entries for plugins that were never installed.

`superpowers` has both `6.1.1` and `6.2.0` cached while only `6.2.0` is installed — a naive walk
counts its 14 skills twice.

### 11.4 Usage is project-shaped, not collection-shaped

| Sessions | Project | Invocations |
| --- | --- | --- |
| 64 | `sloop-test` | 4 |
| 38 | `Contiki-AI` | 2 |
| 16 | `Contiki-AI-content` | **11** |
| 3 | `SLoop` | 5 |

The largest project by session count has almost no skill usage; a project with 11% of the sessions
holds 46% of the invocations. Any global per-skill average blends these into a number that describes
none of them — which is why the Phase 2 spec carried per-project facets (§6.1), and one more reason
a global usage verdict was never going to be honest.

Note also that `sloop-test` appears on disk as **eight** project directories once git worktrees are
counted. Unnormalized, this table is wrong before it is even interpreted.

These numbers are the one-off 2026-08-01 hand measurement that killed Phase 2; the tool
deliberately does not reproduce them (§6).
