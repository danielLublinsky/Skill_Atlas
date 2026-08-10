# Skill Atlas

A Claude Code plugin that makes the skills you rarely use cost nothing —
and still lets the model find them, by **searching a graph of your
collection instead of preloading it**.

## 1. The problem, and the third tier

Claude Code injects every enabled skill's description into every session:
roughly 48 tokens each, whether you use it or not. At 100+ skills across
a pile of plugins that's thousands of tokens per session, and
near-duplicate skills quietly compete for the model's attention.

Disabling a skill fixes the cost and loses the skill. So Skill Atlas adds
a tier in between:

| Tier | Description in context? | Findable? | Cost per session |
| --- | --- | --- | --- |
| **enabled** | yes | natively | ~48 tokens each |
| **searchable** | no | via `skill-search` | 0 |
| **disabled** | no | no | 0 |

A **searchable** skill is dormant — its description never enters your
context — but it stays discoverable on demand. All that advertises the
dormant tier is a ~50-token line injected at session start.

## 2. Categorization, and the two-read search

Discovery is token-efficient because the catalog is **hierarchical**, not
flat. Everything derives from the graph:

**Categorization happens once, by the model.** On the first `/skill-atlas`
run it reads every skill description and drafts 8–12 categories named for
*user-intent task shapes*, not products — then assigns every skill an
ordered list of labels (the first is its display home) and **freezes the
taxonomy**. Later runs only file new skills into it, add a category when
genuinely nothing fits, and re-confirm entries whose description changed
(each assignment carries a hash of the description it was made against —
edit the skill, and it resurfaces as stale). Categorization is
tier-blind: every registered skill gets filed whatever its tier.

**The build turns that into a two-level catalog.** `catalog/_index.md` is
one line per category — `name(count) — description — member tokens` —
where the token list is derived from membership, never curated, so it
can't drift. Then one shard per category, each entry an id, a tier tag,
the description, and a path.

**Search reads at most two files.** `skill-search` — the one skill that
stays always-on — reads the ~10-line index, picks a single category, and
reads that one shard. Never the whole catalog. Counts overlap across
categories on purpose: the pick doesn't have to land on *the* right
bucket, only *a* right one. An **[enabled]** hit gets invoked natively; a
**[searchable]** hit is read from its path and followed as instructions.
Tier-off skills are excluded when shards are written, so a disabled
plugin can never return through a side door.

## 3. The graph, and what it knows about your skills

Discovery is **manifest-driven** — `installed_plugins.json` → each
`plugin.json` → settings — so marketplace catalogues, stale cached plugin
versions, and deprecated trees never pollute the picture. (The naive
"every directory with a SKILL.md" count is reported alongside for
comparison; it over-counts by about 60% on a real machine.)

Skills are nodes. The edges are the interesting part:

- **references** — a skill pointing at its own bundled files (markdown
  links, plus bare `references/`, `scripts/`, `assets/` paths). Flagged
  **broken** when the file isn't there.
- **mentions** — a skill naming another skill. Deliberately strict: only
  backticked, `skills/<name>`, or unambiguous hyphenated names count, and
  fenced code blocks are stripped first. Loose word-boundary matching
  produced 91 edges on a 41-skill collection, almost all of them names
  that happen to be ordinary English words.
- **dangling** — a mention that can't be followed, tagged with why:
  the target is `disabled`, `unregistered`, or `absent` entirely.

From that you also get duplicate names (a mention ambiguous between two
skills is attributed to neither), orphans with no edges at all, and an
exit code you can gate CI on — `1` means at least one broken reference or
dangling mention.

`atlas.html` renders it as a self-contained page you open from `file://`,
zero network requests, with two views:

- **scope** — the structural picture. Skills coloured by origin
  (user / project / plugin), outlined by state (enabled, disabled,
  searchable), wired by references and mentions, with broken and dangling
  edges called out in red and bundled files as leaf nodes. Filters for
  hiding files or mentions, isolating dangling only, or surfacing
  unregistered skills.
- **categories** — the same skills as hub-and-spoke around their
  category hubs. Solid edge to the home category, dashed to anything it's
  also filed under, hub size tracking member count, stale labels marked.
  Search `cat:<name>` to isolate one.

## 4. Install and use

```bash
git clone https://github.com/danielLublinsky/Skill_Atlas.git
claude plugin marketplace add ./Skill_Atlas
claude plugin install skill-atlas@skill-atlas
```

- **`/skill-atlas`** — build the graph, categorize what's new, render the
  atlas. Run it once to set up; a SessionStart hook keeps it fresh after.
- **`/skill-atlas:edit-searchable`** — move plugins in and out of the
  searchable tier, interactively.

A plugin is searchable only when **both** halves hold — Claude Code has
it disabled, *and* this scope opted it in. `edit-searchable` does both;
by hand it's `claude plugin disable <plugin>` plus `categorize.py config
--add-searchable <plugin>`. The unit is a plugin, not a single skill.

All state is project-local, in `./.claude/skill-atlas/`. **Commit
`categories.json`** — it's your curated taxonomy, and the one file that
isn't a rebuildable cache; gitignore `graph.json`, `atlas.html`,
`catalog/`, `graph.dirty`, and `debug.log` beside it. Skill Atlas reads
manifests and skill files only; it never opens `~/.claude/projects`, and
it deliberately does not track usage.

Full spec and the reasoning behind every decision: [DESIGN.md](DESIGN.md)
(graph and visualization) and [DESIGN-PHASE2.md](DESIGN-PHASE2.md)
(categorization and search).
