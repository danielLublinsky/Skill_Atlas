# skill-atlas — Design Record

**What this file is.** The historical record: what was considered, what was
chosen, what was dropped, and why. It is *not* a description of how the system
works today — that lives in [docs/](docs/README.md), one file per component,
and the code is the authority over both. When a doc and this record disagree,
the doc wins; when the code and a doc disagree, the code wins.

Merged 2026-08-14 from the two original specs (`DESIGN.md`, Phase 1; and
`DESIGN-PHASE2.md`, categorization + search). Phase 2's implementation
amendments have been **applied into the body** rather than left as an override
layer on top of superseded text. Sections 1–11 keep their original numbers, so
existing `DESIGN §x` citations in the source still resolve; Phase 2 occupies
12–16.

**Status:** Phase 1 shipped. Phase 2 shipped 2026-08-07, fully project-local
since 2026-08-08 (§15).

---

## 1. Purpose

A Claude Code plugin answering questions nobody can currently answer about
their own skill collection:

| Question | Answered by | Status |
| --- | --- | --- |
| What does my skill collection actually look like? | graph + visualization (§4, §7) | shipped |
| Which parts of it are dead weight? | usage tracking | **dropped — §6** |
| Which skill fits this task, without paying every description into every session? | categorization + search (§13, §14) | shipped |

The original thesis was that the value lay in the **join**: a graph shows
structure but not relevance, usage counts show hit rates but not why something
is orphaned, and rendering usage *onto* the graph is what makes dead subgraphs
visible at a glance.

**That thesis did not survive measurement.** Skill invocation is too rare an
event to support a per-skill verdict — 14 in-collection invocations across 39
skills over 151 sessions, where ~70% of skills would read as "never invoked" by
chance alone. The join was specified, then dropped (§6).

What the structural half answers without any usage data turned out to be the
larger part of the value: which files are actually loadable, which skills are
switched off, which point at things that no longer exist, which are duplicated.
Four such defects are recorded in §11, all found by hand while stress-testing
this document, before a line of code existed.

### Non-goals

- Not a skill authoring tool. It observes; it never edits `SKILL.md` files.
- Not a usage tracker. It never opens session transcripts and counts nothing (§6).
- Not a *content*-retrieval layer. No embeddings, no RAG over skill bodies.
  *(Narrowed 2026-08-06: Phase 2 adds a description-level catalog and a search
  skill — the blanket form of this non-goal is reversed to exactly that extent
  and no further.)*
- Not a productivity dashboard. No lines-of-code, no cost attribution.
- Not multi-user. Single machine, local files, no server.
- Never writes Claude Code's own config. skill-atlas reads `settings.json`; it
  does not flip `enabledPlugins`. Recommend, never act.

---

## 2. Architecture

```text
  manifests + skill roots ─▶┌──────────────────────┐
  installed_plugins.json    │   build_graph.py     │──▶ graph.json ──▶ catalog/
  settings.json             │   (static analysis)  │              └─▶ atlas.html
  */plugin.json             └──────────────────────┘
  ~/.claude/skills                      ▲
  <cwd>/.claude/skills                  │ triggered by
                          ┌─────────────┴──────┐
                          │  staleness check   │  SessionStart
                          │  dirty flag        │  PostToolUse(Write|Edit)
                          │  explicit build    │  /skill-atlas, CI, make
                          └────────────────────┘
```

**The rule that governs everything below:** the inputs are manifests and skill
files, nothing else — skill-atlas never opens `~/.claude/projects` (Claude
Code's session transcripts; reading them was the dropped usage phase, §6).

**Derived artifacts are rebuilt, never repaired.** `graph.json`, `atlas.html`
and `catalog/` must be safely regenerable from scratch at any time. If one is
deleted or corrupted, the fix is to rebuild.

Phase 2 added a second file class that this rule explicitly does **not** cover —
see §13.1. The artifact directory therefore holds three classes with three
different loss semantics:

| File | Class | On corruption or loss |
| --- | --- | --- |
| `graph.json`, `atlas.html`, `catalog/` | derived | delete and rebuild — never repair |
| `categories.json` | **curated** | restore from backup; regeneration loses the taxonomy |
| `config.json` | user config | user rewrites it; five lines |

---

## 3. Data model

### 3.1 `graph.json`

Regenerated wholesale on every build, never edited in place.

**Node ids are invocation strings.** A skill's id is the exact string Claude
Code invokes it with — `superpowers:brainstorming`, `graphify`. That string is
already unique and already namespaced; path-derived ids would have added a
mapping for no benefit. Ids escalate to a disambiguated form
(`name@user`, `name@project`, `plugin:name@marketplace`) on collision rather
than merging or dropping — duplicate names are a real defect worth surfacing.

**Edge kinds**

| kind | Meaning | Extraction |
| --- | --- | --- |
| `references` | SKILL.md points at a bundled file | markdown links + bare `references/…`, `scripts/…`, `assets/…` paths |
| `mentions` | SKILL.md names another *loadable* skill | strict match — see below |
| `dangling` | SKILL.md names a skill that cannot be loaded | same match; target unregistered, disabled, or absent |

**`mentions` extraction is strict, and deliberately so.** The naive rule —
word-boundary match on known skill names — produced 91 edges on a 41-skill
collection, dominated by skills whose names are ordinary English words
(`implement` appeared in 10 other SKILL.md files, essentially all as the verb).
Precision is bimodal by name shape: hyphenated names like
`resolving-merge-conflicts` never collide by accident, single common words
almost always do. So a mention counts only in an unambiguous form: backtick-
quoted, slash-prefixed, or hyphenated/multi-word. This halved edge count to 48
and removed the `implement` class of false positive, while preserving the
finding that justified keeping `mentions` at all (§11.2).

`mentions` remains a weak, inferred edge — not part of the Agent Skills spec, a
convention. Render it differently and never treat it as a hard dependency.

**`dangling` is the same extraction with a different target**, and it is the one
inferred edge worth acting on: a live skill instructing the reader to use
something that cannot be loaded is a defect in either the skill or the install.
It is the highest-value output the graph produces.

There is no second data file. An earlier revision specified `usage.json`; it
went with the usage phase (§6). Phase 2's additions to `graph.json` are in
§13.3.

---

## 4. Graph builder

### 4.1 Discovery

**"Any directory containing SKILL.md" is wrong**, and not marginally. It yields
104 nodes of which ~63 are not skills: other authors' `deprecated/` and
`in-progress/` trees, stale cached plugin versions, and marketplace catalogue
entries for plugins never installed. A 60% false-positive rate on the primary
node type.

Discovery is therefore **manifest-driven**. The collection has four nested
definitions and the graph must be explicit about which it means:

| Definition | Count when measured | Authority |
| --- | --- | --- |
| `SKILL.md` on disk | 104 | filesystem — *not used* |
| Under installed plugin paths | 60 | `installed_plugins.json` |
| **Registered** — enters the graph | **41** | each `plugin.json` `skills[]` |
| **Enabled** — loadable this session | **27** | `settings.json` `enabledPlugins` |

Decisions that fell out of this, each load-bearing:

- **`installPath` excludes stale cached versions.** `superpowers/6.1.1` and
  `6.2.0` both exist on disk; only one is installed.
- **The `skills[]` glob fallback is not a defensive nicety.** `mattpocock-skills`
  has an explicit array registering 22 of the 41 files it ships;
  `superpowers` has no `skills` key at all and registers its 14 by glob.
- **Never walk `~/.claude/plugins/marketplaces/`** — that tree is the catalogue
  of installable plugins, not the installed set. Counting it adds 31 phantoms.
- **Enabled is an attribute, not a filter.** A disabled skill still enters the
  graph. The most-invoked plugin in the measured collection was disabled
  (§11.1); filtering on enabled state would have hidden that at exactly the
  moment it was worth shouting about.
- **Unregistered `SKILL.md` files are indexed but not drawn** — except when a
  registered skill mentions one, which renders as a dangling node plus a red
  edge. That single exception is what surfaces §11.2.
- **Built-ins ship inside the Claude Code binary** with no file on disk. They
  were originally out of the graph entirely; Phase 2 brought them in via a
  vendored manifest, since a built-in can *shadow* a plugin skill of the same
  name in the catalog. See docs/3.

### 4.2 Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Built, nothing dangling |
| 1 | Built, ≥1 dangling edge |
| 2 | Build failed (unreadable root, unparseable manifest, invalid curated state, write error) |

Exit 1 covers three dangling kinds — a `references` edge to a missing file, a
`mentions` edge to an unregistered skill, a `mentions` edge to a disabled one.
All three mean the same thing operationally: a skill points somewhere the reader
cannot follow. This makes the builder usable as a CI gate with no separate
linting step.

Exit 1 stays **reserved for dangling references**. Uncategorized and stale
skills are TODO states for the next `/skill-atlas` run, not defects, and never
affect the exit code (§13.3).

---

## 5. Freshness

The graph must never be silently stale. Four triggers, cheapest first.

### 5.1 Staleness check on `SessionStart`

A cheap fingerprint, not a full rebuild: `sha256` over sorted
`(path, mtime_ns, size)` for every `SKILL.md` **and every manifest**.

**The manifests are not optional.** Since §4.1 made discovery manifest-driven,
the graph depends on files that are not `SKILL.md`. Toggling
`enabledPlugins.superpowers` changes the graph and touches no skill file at all;
under a skill-files-only fingerprint the graph would go silently stale, which
this section opens by forbidding. Installing or removing a plugin has the same
property. The cost is a handful of extra `stat` calls.

Phase 2 grew the input set by two — `categories.json` and `config.json` — by
exactly the same argument (§13.3).

Stat-only walk, no file reads. Must complete in **< 200 ms for 500 skills** or
it degrades session startup; if the walk exceeds a 2s budget, abandon it, log,
and let the session proceed with a stale graph. **A slow hook is worse than a
stale graph.**

This trigger covers plugin installs, enable/disable, `git pull`, manual file
drops — anything happening outside a session.

### 5.2 Dirty flag on `PostToolUse`

Matcher `Write|Edit`. Write a `.dirty` marker when the touched path is a
`SKILL.md`, anything under a `skills/` tree, a `plugin.json`, a `settings.json`,
`installed_plugins.json`, or Phase 2's curated files. Same reasoning as §5.1:
omitting the manifest paths leaves the identical silent-staleness hole.

Do **not** rebuild inline — that puts filesystem work in the middle of a tool
call. The marker is consumed at the next session boundary or explicit build.
Skill edits during a session are common while authoring; deferring batches them.

### 5.3 Explicit

`/skill-atlas`, `python3 scripts/build_graph.py`, `make build`. Idempotent and
safe to call concurrently — write to temp, atomic rename.

### 5.4 Hook invariants — non-negotiable

1. Always exit `0`. A non-zero hook can interrupt the session.
2. Never write to stdout, except the documented SessionStart JSON contract —
   which §14.3's index line deliberately uses.
3. Swallow every exception to `debug.log` — path, line number and exception
   **type** only, never the content of whatever was being parsed.
4. Hard timeout 10s.
5. Never block on network or lock contention.
6. Never initialize a scope. The hooks operate only where
   `.claude/skill-atlas/` already exists (§15).

### 5.5 Deliberately not built: a filesystem watcher

It needs a resident process, it fights editors that write-then-rename, and it
buys latency nobody needs — the graph is only read at session start and on
demand. Revisit only if §5.1 proves too slow.

---

## 6. Usage tracking — dropped 2026-08-06

Fully specified against the live machine, its downstream scaffolding built, then
the whole phase cut. This is the condensed record plus the arithmetic that
killed it, kept so the next person tempted to build it starts from the reason it
isn't here. **Nothing in this section is implemented**, and none of it should be
without clearing §6.2's bar.

### 6.1 What it would have been

- **Read Claude Code's own transcripts** (`~/.claude/projects/**/*.jsonl` — 196
  files, 71 MB) rather than logging anything, making history retroactive — at
  the cost of coupling to an undocumented internal format.
- **A strict parse boundary**, because transcripts are the user's full
  conversation history: extract session id, timestamp, project slug and
  `Skill.input.skill` per line (the value is already the graph's node id — the
  join is an identity), discard everything else.
- **`rollup.py`** folding transcripts into `usage.json` incrementally via
  per-file byte-offset watermarks. Sub-agent invocations counted separately.
  Worktree and scratchpad slugs normalized into their parent repo —
  unnormalized, one repo here fragments into eight.
- **Usage rendered onto the graph** — node area by session count, dashed border
  for never-invoked, recency fade — behind a statistical gate, with a
  per-project selector because usage is project-shaped (§11.4).

### 6.2 The arithmetic that killed it

Zero invocations cannot distinguish "never needed" (delete it) from "needed and
missed" (fix the description) from "could not be invoked" (it was disabled the
whole time — §11.1 is exactly this, and its 14 skills would all read as
confident zeros). A zero carries information only when the expected event count
is high enough:

```text
gate:  events_in_collection ≥ 3 × skills_in_collection    (λ ≥ 3 ⇒ P(zero by chance) ≤ 5%)
```

Measured: **14 in-collection invocations across 39 skills over 151 sessions** —
λ ≈ 0.36, so P(a skill shows zero) = e^−0.36 ≈ 70% *even if usage were perfectly
uniform*. The gate needed ~117 events and had 14, with no realistic path to
closing the gap. A feature whose gate never opens is dead weight of exactly the
kind this tool exists to point at, so it was cut rather than shipped inert —
which also deleted the most sensitive surface in the design (§10.2).

**The honest negative result is the deliverable:** invocation frequency does not
carry enough signal to judge a personal skill collection. All four §11 findings
needed zero usage data.

Revisit only if the input changes shape — a documented usage API, or a
team-scale corpus an order of magnitude denser. The gate above is the bar any
revival must clear before rendering a single usage pixel; lowering it is not a
way to get answers sooner, it is a way to get confident-looking wrong ones.

---

## 7. HTML visualization

Single self-contained `atlas.html` — D3 inlined, no CDN, no build step, opens
from `file://`.

### 7.1 Visual encoding

| Channel | Encodes |
| --- | --- |
| Node shape | rounded rect = skill, small circle = bundled file |
| Node color | scope — user / project / plugin |
| Node fill | flat = disabled, tinted = enabled, distinct stroke = searchable (§12) |
| Node stroke | grey dash = dangling target |
| Edge style | solid = `references`, dotted = `mentions`, membership edges in category view |
| Edge color | red = broken reference or dangling edge |
| Edge width | uniform — no data to encode; resist the temptation |

"Hollow" fills are painted, never transparent, so edges running to a node centre
stop at its border instead of crossing the label.

Usage-driven channels — node area by invocation count, dashed border for
never-invoked, recency fade — went with §6. Every skill renders at uniform size
and full opacity, and nothing in the picture claims to know how often anything
runs.

**Deliberately unencoded: token cost.** Tested rather than assumed. The enabled
collection's descriptions totalled ~4,800 characters ≈ 1,200 tokens per session,
~48 tokens per skill. Real, but not decision-changing at that size. That same
number is what Phase 2 exists to arbitrage once a collection outgrows it (§12).
Also unencoded: file size, description length.

### 7.2 Layout

Force-directed, seeded deterministically so the same graph renders the same way
twice — a layout that reshuffles every build makes visual diffing impossible.
Cluster by scope.

**Amended 2026-08-07: no gutters.** The original design pinned orphans, and
later unregistered skills, to labelled gutters. Both are gone. Orphans float as
ordinary nodes and settle near their own cluster; unregistered skills carry
their originating plugin and cluster with it, because "this plugin ships skills
its manifest never registers" is the finding, and a lane off to the side severs
it from the plugin it indicts. They obey the plugin filter for the same reason.

### 7.3 Interaction

Hover parks a tooltip beside the legend rather than trailing the cursor — a
panel that follows the mouse covers the neighbourhood you hovered to inspect.
Click pins a node and freezes the whole reading: 1-hop neighbourhood
highlighted, the rest dimmed, tooltip held so a long description can actually be
read. Incident edges are actively highlighted rather than merely spared the
dimming — which edges connect *is* the answer being looked for. Neighbouring
file dots brighten and gain a ring rather than growing: at 4.5px a size change is
unreadable and a moving radius shifts the layout it sits in.

The legend is anchored top-right and never moved by anything else on the canvas —
it is the key to the picture, so it must be findable in the same place every
time. Filters live behind a dropdown carrying a count of active filters, since a
hidden checkbox that silently reshapes the graph is worse than no checkbox.

**View tabs, not a filter.** Scope view and category view (§14) are tabs centred
on the control bar: swapping the whole picture is a different act from
subtracting from it.

### 7.4 Scale

Fine to 200 nodes. From 200–600, collapse `file` nodes into a per-skill badge
count. Above 600, force-directed layout stops being readable regardless of
tuning — fall back to a sortable table and treat the graph as a filtered
drill-down. Do not attempt to make a 2,000-node hairball legible.

Manifest-driven discovery (§4.1) is a scale decision as much as a correctness
one: it takes the measured collection from 104 nodes to 41, comfortably inside
the first band.

---

## 8. Layout & config

Component directories live at plugin root. Only `plugin.json` goes in
`.claude-plugin/` — nesting components inside it makes them silently invisible:
the plugin loads, the components don't. All hook paths use
`${CLAUDE_PLUGIN_ROOT}`.

During development, `SKILL.md` edits apply immediately, but changes to `hooks/`,
`agents/` and `.mcp.json` need `/reload-plugins` or a restart.

| Env var | Default | Meaning |
| --- | --- | --- |
| `SKILL_ATLAS_CLAUDE_DIR` | `~/.claude` | Claude Code config root (test seam) |
| `SKILL_ATLAS_AUTOBUILD` | `1` | `0` disables the SessionStart staleness check |
| `SKILL_ATLAS_BUILTINS` | vendored | override the built-in manifest path (test seam) |

Removed: `SKILL_ATLAS_HOME` (2026-08-08 — artifacts always live in the
`.claude/skill-atlas` of their scope, §15). `SKILL_ATLAS_PROJECTS`,
`SKILL_ATLAS_GATE_LAMBDA` and `SKILL_ATLAS_SUBAGENTS` all configured the dropped
usage tracking (§6).

---

## 9. Validation

The standing rule for both phases: **a milestone is done when the live machine
says so, not when the code compiles.** Validation is measured against the
structural findings in §11, which the tool must reproduce unaided — the unit
suite runs against fixtures and never touches the real `~/.claude`, while
`dev/smoke_live.py` makes read-only structural assertions against the real
machine.

§11.4 is usage evidence, measured once by hand to justify §6; it is deliberately
not reproduced by the tool.

---

## 10. Open questions and standing constraints

### 10.1 Resolved

Transcript format drift — dissolved when the reading was dropped; nothing parses
transcripts, so there is no format to drift against. Payload shape and
sub-agent attribution — both moot with §6. `mentions` value — kept, made strict
(§3.1). Whether the usage gate would ever open — answered no, and the phase was
cut for it (§6.2).

### 10.2 Privacy

With §6 dropped this stopped being the most sensitive part of the design:
skill-atlas reads manifests and skill files only, and never opens
`~/.claude/projects`. Two standing rules survive:

1. **`debug.log` never receives parsed content** (§5.4 invariant 3). A parse
   error naturally wants to log the offending line; log path, line number and
   exception type only. The rule costs nothing and keeps the log safe no matter
   what future inputs are parsed.
2. **Derived artifacts show real paths and, in project views, real directory
   names.** Sharing an `atlas.html` screenshot is a decision, not an accident.
   This extends to the catalog shards, which carry the same descriptions already
   present in `graph.json`.

Phase 2 added no new sensitive surface: `categories.json` holds skill ids and
category labels, nothing more.

### 10.3 Overlap detection — absorbed into categorization

Two skills with near-identical descriptions is a real defect, cheap to detect,
and — unlike usage — **dense**: every skill has a description, so the signal
does not depend on an event rate that may never arrive. That density argument is
what motivated Phase 2 in the first place.

Absorbed rather than built separately: model-assigned categories put
near-duplicates in the same bucket, where they are visible side by side in the
atlas, and search meets them at the one moment a duplicate actually matters —
when one of them is about to be used. See §14.1 for how search resolves them.

### 10.4 Still open

- **Taxonomy governance after the freeze.** Renaming or merging categories is a
  hand-edit of curated state plus a re-run. Fine at 13 categories; a
  `/skill-atlas retag` flow is the likely shape if it ever isn't. This is the
  gap behind existing scopes keeping under-homed assignments.
- **Search adoption is unmeasured.** The index line mitigates silent non-use,
  but whether the model reliably calls search before barehanded attempts needs
  observing. If adoption is poor, the next lever is the search skill's own
  description, then a CLAUDE.md policy line — escalate only on evidence.
- **Empty categories after plugin removal:** keep (stable taxonomy) or prune at
  the next run (tidy index)? Leaning keep — stage 1 tolerates a zero count, and
  pruning reshuffles what the model memorized.
- **Per-skill opt-in/opt-out** inside a plugin ("all of X except Y") — deferred
  with §16's granularity decision until a concrete case demands it.
- **A static classifier for new skills** (designed 2026-08-07, explicitly not
  first-step). After bootstrap the cache is labeled data, so a deterministic
  TF-IDF-style classifier could assign clearly-fitting new skills into the frozen
  taxonomy at rebuild time — confidence-gated, additive-only, marked provisional.
  Deferred until the first-step mechanism proves annoying in practice; at
  plugin-install pace the uncategorized bucket may never grow fast enough.

---

## 11. Findings on the author's collection

The standing evidence that the structural half pays for itself. All four were
found by hand while stress-testing this document, before any code existed.

### 11.1 The most-used plugin is disabled

`enabledPlugins.superpowers = false`, while `superpowers` accounted for **11 of
24 recorded invocations — 46%**, by a wide margin the most-used plugin. Its 14
skills were installed, registered, and invisible to every session. This is the
finding that set §4.1's rule that enabled state is an attribute, not a filter.

### 11.2 A live skill points at a deprecated one

`setup-matt-pocock-skills/SKILL.md:40` reads *"Skills like `to-tickets`,
`triage`, `to-spec`, and `qa` read from and write to it…"*. The first three are
registered. **`qa` is in `deprecated/` and absent from `plugin.json`'s
`skills[]`** — it cannot be loaded. A registered skill instructing the reader to
use something that does not exist. This is the `dangling` edge kind (§3.1) and
the reason `mentions` survived rather than being cut.

### 11.3 Sixty percent of `SKILL.md` files are not skills

104 on disk; 41 registered. The gap is `deprecated/`, `in-progress/`,
`personal/` and `misc/` trees inside third-party plugins (19 in
`mattpocock-skills` alone), stale cached versions, and 31 marketplace catalogue
entries for plugins never installed.

### 11.4 Usage is project-shaped, not collection-shaped

| Sessions | Project | Invocations |
| --- | --- | --- |
| 64 | `sloop-test` | 4 |
| 38 | `Contiki-AI` | 2 |
| 16 | `Contiki-AI-content` | **11** |
| 3 | `SLoop` | 5 |

The largest project by session count has almost no skill usage; a project with
11% of the sessions holds 46% of the invocations. Any global per-skill average
blends these into a number describing none of them. `sloop-test` also appears on
disk as **eight** directories once git worktrees are counted — unnormalized,
this table is wrong before it is interpreted. These are the one-off hand
measurements that killed §6; the tool deliberately does not reproduce them.

---

## 12. Phase 2 — the three-tier model

Two measured facts about how Claude Code loads skills:

- An **enabled** skill costs ~48 tokens *every session* — its frontmatter
  description is injected at session start whether or not it is ever used.
- A **disabled** skill costs nothing and is completely invisible: no injection,
  the Skill tool cannot invoke it, the model does not know it exists. The
  `SKILL.md` is still on disk and still readable as a plain file.

Multi-plugin users sit on the wrong side of both at once. Plugins ship skills in
bulk, so a collection grows to 80–150 descriptions competing for context,
several doing essentially the same thing — and the only native remedies are "pay
for all of them every session" or "make them cease to exist."

Phase 2 arbitrages the gap with a third tier:

| Tier | In context? | Findable? | Invocable? | Cost / session |
| --- | --- | --- | --- | --- |
| **Enabled** | yes — description injected | natively | Skill tool | ~48 tokens each |
| **Searchable** | no | via the search skill | `Read` the SKILL.md, follow it | 0 |
| **Disabled** | no | **no** | no | 0 |

- **Searchable** is the new tier: plugins disabled in `settings.json` but opted
  in via skill-atlas's own config (§13.2). Using one deliberately bypasses the
  plugin machinery and loses `allowed-tools` enforcement and auto-triggering — an
  accepted trade for zero standing cost.
- **Disabled and not opted in means disabled.** Search must never serve it. A
  plugin disabled because it is broken does not come back through a side door.
  This is enforced at emit time: tier-off skills never enter a shard.
- The tier is **derived, never stored**: `enabled` wins, then `searchable`, else
  off. Opt-in is per-plugin. Standalone user and project skills have no disable
  toggle in Claude Code, so tier 2 is in practice a plugin-skill tier.

**Honest scale note, in the spirit of §6.** At 27 enabled skills the savings are
real but modest. The design pays for itself on collections of 80–150 skills,
where injection cost reaches 4–7k tokens per session and near-duplicates
measurably confuse native selection. The justification is scale-dependent and
this record says so rather than implying otherwise. The measured per-search cost
and its honest baseline are in docs/6 — they were *worse* than this document
originally estimated, and the estimate was corrected rather than the claim
defended.

---

## 13. Categorization

### 13.1 `categories.json` — curated state, not a cache

The first file in the system that is neither source nor derived. §2's rule —
*derived artifacts are rebuilt, never repaired* — explicitly does **not** apply:
a regeneration re-proposes categories differently and discards any hand-edits.
Treat it as configuration you cannot cheaply recreate.

- **Assignments are keyed by node id**, including collision disambiguation
  (§3.1).
- **`categories` is an ordered, non-empty list.** Multiple categories per skill
  are allowed and are a recall feature (§14.1); the first entry is the single
  place the renderer draws the node.
- **`desc_hash` makes staleness derivable.** No `stale` flag is ever stored —
  the build compares the recorded hash against the current description.
- **Written only through a validating helper** (schema check plus atomic
  tmp-rename). The model never free-hands this JSON.
- **Invalid hand-edits fail loud.** A present-but-invalid `categories.json` or
  `config.json` fails the build with exit 2 naming every violation — same class
  as an unparseable manifest, no tolerate-and-degrade for curated state. The
  boundary: environmental drift is *not* an edit error. An assignment whose
  skill left the graph is reported as `orphan_assignments` and skipped; a stale
  `desc_hash` is the designed stale state. The SessionStart hook never breaks a
  session over this — it swallows the failure and keeps the last-good graph;
  the explicit build is where violations print.
- **The taxonomy and the assignments are model-generated and then frozen.**
  There is no hand-repair path by design; fixing bad categorization means fixing
  the instructions that generate it and re-bootstrapping the scope.

**Future editing direction:** editing in the atlas page (rename categories, drag
skills) with a download of the resulting `categories.json` — a static `file://`
page cannot write to disk. `categorize.py import <path>` exists as the validated
landing pad.

### 13.2 `config.json` — the searchable opt-in

`{"version": 1, "searchable_plugins": [...]}`. Per-plugin, nothing finer, on day
one. A plugin listed here whose skills are disabled lands in tier 2. Per-skill
overrides are deferred (§10.4).

### 13.3 `graph.json` v3, and shared annotation

Per skill node: `categories` (ordered; `[]` means the visible **uncategorized**
bucket), `category_stale`, `searchable`. `stats` gains `uncategorized`,
`stale_categories`, `searchable`. The **frozen taxonomy rides in `graph.json`**
under a top-level `taxonomy` key, so shard emission and the category view are
single-source — `graph.json` alone — with no second read of `categories.json`.

**The fingerprint grows by two files.** §5.1's argument for including manifests
applies verbatim: editing `categories.json` or `config.json` changes
`graph.json` while touching no `SKILL.md`, so both join the fingerprint and the
§5.2 matchers.

**Exit codes are untouched** — uncategorized and stale are TODO states, not
defects (§4.2).

**Categorize-driven refresh; no post-categorize rebuild** (2026-08-10). Every
state-changing `categorize.py` subcommand re-annotates the graph's skill nodes,
updates `taxonomy` and derived stats, recomputes the fingerprint (stat-only —
`categories.json` is a manifest input, so without this every next SessionStart
would rebuild), rewrites `graph.json` and re-emits the shards itself. The
`/skill-atlas` flow is build → categorize → render, with no second build. The
annotation and stat derivation are **shared code**, so the build path and the
refresh path cannot drift. The refresh never clears `graph.dirty` — it is not a
re-discovery. Accepted window: a `SKILL.md` edited externally between build and
refresh gets its new mtime baked into the recomputed fingerprint while the graph
carries the old parse; in-session edits stay covered by the dirty hook.

### 13.4 The single model moment

`build_graph.py` stays model-free forever and read-only toward
`categories.json`. All intelligence runs inside `/skill-atlas`, where a model is
already present, already paid for, and already reporting to the user. No API
keys, no network in the build, **no model calls in hooks** — a 10s hook timeout
could not fit one anyway.

### 13.5 Bootstrap — writing the category descriptions

**Bootstrap is autonomous** (amended 2026-08-07 — the original design had a user
approval step). `/skill-atlas` drafts the taxonomy *and* writes the full
categorization in one run, reporting the result informationally. The taxonomy
still freezes at bootstrap — for **search stability**, not approval — and later
runs assign into it. When nothing fits, the model adds a category through an
explicit CLI act and calls it out: additions are always visible, never silent. A
model left unsupervised will happily produce 20 categories for 41 skills; the
target is 8–12.

**Writing the category descriptions is the real work.** Each line does three
jobs at once: search stage 1 routes tasks by reading it, the model assigns every
later skill by matching against it, and the user judges the taxonomy by it.

- Describe the task shape in **user-intent terms**, not implementation terms.
- **When two categories could be confused, each description names its side of
  the boundary.** This carve-out is what search treats as its strongest routing
  signal.
- **Multi-home across confusable boundaries.** Overlap is the defense against a
  wrong stage-1 pick, and it has to be instructed, not merely permitted — when
  it was only permitted, the categorizing model minimized it and confusable
  pairs shared almost no members. A second home requires a realistic task
  phrasing that would land there; platform-locked skills stay out of generic
  categories.
- **Product-based categories are legitimate** when a product dominates the
  collection; otherwise products share a capability bucket and product identity
  lives in the skill descriptions, where stage 2 can still see it.
- **Concrete tokens beat abstractions** — tasks say "send a discord message",
  never "perform messaging". But the curated sentence does *not* hand-enumerate
  them: a hand-written list rots the day a new plugin joins the category. The
  sentence carries intent and boundary; the build derives the enumeration
  (§14.2).

**Full coverage is mandatory** (2026-08-07 user decision). Bootstrap rejects
incomplete coverage (exit 3, missing ids named, nothing written), and a run must
end with zero uncategorized skills. The uncategorized bucket remains, but
strictly as the *transitional* state for skills installed between runs — never
as an acceptable end state.

### 13.6 Invalidation — stale, not dropped

When a description changes, the assignment's `desc_hash` stops matching and the
node is marked `category_stale` — **but the old labels stay in effect**. Search
keeps working on yesterday's categories; the next run re-confirms or moves the
entry. The failure mode this buys: a plugin update that rewords 15 descriptions
changes nothing operationally, instead of dumping 15 skills out of the index
until someone notices.

### 13.7 Degradation — `/skill-atlas` is an optimizer, not a dependency

**Categorization improves search economics; its absence must never break search
correctness.** The failure mode is "search got expensive", never "skills became
unfindable".

| State | Behaviour |
| --- | --- |
| never run, nothing opted in | Phase 2 inert; the system *is* Phase 1. Supported, not broken. |
| opted in, never categorized | everything sits in `uncategorized.md`; correct results at roughly full-catalog cost. The index line names the fix. |
| run exactly once | the gold state, decaying *visibly*: everything labeled stays labeled (frozen taxonomy + stale-keeps-labels); only skills installed since degrade, into the uncategorized bucket. |

Two commitments this forces: `uncategorized` is a permanent, first-class bucket,
always in the stage-1 index and always emitted as a shard even against an empty
taxonomy; and the index line carries the uncategorized count, which is the one
standing channel that makes decay visible and names the fix without a nag hook
or a dialog.

**Category freshness needs no new hook.** Skills arrive when a plugin is
installed — a deliberate act a few times a month, not a stream. Structural
freshness is already covered by §5's hooks, and the worst interim state is a
skill sitting visibly in the uncategorized bucket, still findable. That is an
acceptable staleness model for a monthly event.

---

## 14. Catalog and search

### 14.1 Shards

Loading every dormant description into every session is the thing being avoided;
loading the whole catalog at query time would just move that cost to the query.
So the catalog is **sharded** — one file per category plus `uncategorized.md` —
and a search reads the index plus one shard.

Shards are **derived artifacts**, emitted from `graph.json` alone:
deterministic, no model, rebuild-never-repair. A multi-category skill appears in
every shard it belongs to; **that overlap is the point, not redundancy** —
stage 1's pick does not have to be *the* right bucket, only *a* right one.
Category counts consequently sum to more than the skill count and must be
presented as overlapping, never as a partition.

**Duplicates surface at decision time.** Near-identical skills share a category,
so they meet the reader exactly when one is about to be used — §10.3's overlap
detection, absorbed. The original design had search present them side by side
for the user to arbitrate; that was replaced in 2026-08-14 by a silent
deterministic tiebreak, because a search that stops to ask a question costs more
than the duplicate does.

### 14.2 The derived token list

Each index line carries the member skills' names, appended automatically by the
build so concrete product words ("discord", "bigquery") are always present and
always in sync with membership, with no curation (§13.5). It is a **name index,
not a keyword index** — it helps exactly when a skill's name is the product
word, and it is length-capped, so it can only ever *add* confidence. Search
treats a miss in the token list as evidence of nothing.

### 14.3 Session index line

With the long tail dark, nothing in context advertises that it exists — the
failure mode that silently degrades the system to "you have 12 skills" is the
model simply never calling search. Mitigation: the existing SessionStart hook
injects **one line**, ~54 tokens, built from `graph.json` stats. No model, no
new hook, using the documented stdout JSON contract that §5.4 invariant 2
already carves out.

It is **silent when nothing is dormant** — the line pays for the searchable
tier, and an inert scope stays byte-identical to Phase 1. The
`Run /skill-atlas to categorize` nag appears only when the uncategorized count
is nonzero, and is a **suggestion, never an instruction**: the session is not
asked to spend tokens on work the user did not request. Together with search's
own in-answer suggestion, this is the sole nag channel for catalog decay.

### 14.4 The search skill's description is the whole triggering surface

The searchable tier removes triggering from every skill inside it, so the
system's entire triggering burden funnels through one frontmatter field — the
most load-bearing 1,024 characters in the plugin. Two deliberate choices: it
names *generic* task shapes rather than the user's actual category names (those
are live and travel in the index line; the description is static), and it spells
out its own **skip** conditions, because a search that fires on "what's 2+2"
burns more than it ever saves.

It is a starting point validated against should-trigger and shouldn't-trigger
prompts, revised on measurement, never on prose review.

**The search body is a budget, not just a protocol.** Rewritten 2026-08-14 after
measurement showed a search cost ~2,700 tokens against ~4,300 for simply loading
every description once — an arbitrage that broke even at under two searches per
session. The rewrite bounded the shard budget explicitly (one is the norm, three
the ceiling, with a named trigger for opening another) and replaced the ranked-
match report with a single line naming the pick before the task continues. A
search is a lookup inside a task, not a deliverable.

---

## 15. Fully project-local

**No global state at all** (2026-08-08 user decision, superseding an earlier
global/project split). Every artifact and curated file lives in
`<scope>/.claude/skill-atlas/`, where the scope is the directory skill-atlas
runs in: graph, atlas, catalog shards, a complete per-scope `categories.json`
with its own taxonomy, `config.json`, dirty marker and debug log. **Scopes
bootstrap independently and may diverge** — that is accepted, not a bug.

- **Auto-init:** an explicit build in any directory creates its atlas dir. The
  hooks operate only where that dir already exists and never initialize one, so
  sessions in untouched directories stay untouched and emit nothing.
- **`skill-search` reads `./.claude/skill-atlas/catalog/` and never falls back**
  to another directory's catalog — a parent's catalog would serve skills this
  project never opted into.
- The previous global state was retired without migration: each scope
  re-bootstraps on its next run.
- Inputs are unchanged — discovery still reads the machine's plugins, user
  skills and settings from `~/.claude`.

---

## 16. Phase 2 — deliberately not built

- **Auto-toggling `enabledPlugins`.** The obvious "one-click enable from the
  atlas" writes to Claude Code's config; skill-atlas stays read-only toward
  `settings.json`.
- **Per-skill opt-in granularity** — per-plugin covers the install-shaped
  reality; revisit on a concrete case.
- **Embeddings or any content index.** Descriptions and categories carry the
  search; if they ever don't, the fix is better descriptions — a skill-authoring
  defect the atlas should *surface*, not paper over with retrieval.
- **A categorization hook.** No model runs outside `/skill-atlas`, ever.
- **Files and structural edges in the category view.** It contains only category
  hubs, member skills and membership edges; the structural picture belongs to the
  scope view, and the structural toggles grey out there.
