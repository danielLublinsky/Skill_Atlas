# 4 — Graph build

**Entry point:** [build_graph.py](../scripts/build_graph.py).
**Helpers:** [atlas_extract.py](../scripts/atlas_extract.py) (edges),
[atlas_annotate.py](../scripts/atlas_annotate.py) (Phase 2 fields + stats),
[atlas_io.py](../scripts/atlas_io.py) (atomic writes).
**Tests:** [test_graph.py](../tests/test_graph.py),
[test_extract.py](../tests/test_extract.py).

```bash
python3 scripts/build_graph.py [--cwd DIR] [--check] [--quiet] [--naive-count]
```

`--check` builds and reports **without writing anything** — the CI gate.

## What `build()` does

[build_graph.py:60](../scripts/build_graph.py#L60), in order:

1. `set_scope(cwd)`, then `atlas_discovery.discover()` → skill records.
2. Load the curated files **strictly** — a schema violation raises
   `CategoriesError` and becomes exit 2 with every violation on stderr.
3. `atlas_annotate.annotate_skills()` — stamps `categories`, `category_stale`
   and `searchable` onto every skill record, so node assembly, stats, shards and
   the renderer all see them for free.
4. For each skill: read the body, extract `references` and `mentions` edges.
5. Compute orphans (degree 0), the fingerprint, the stat block.
6. Assemble `graph.json` (version 3) and return `(graph, exit_code)`.

`main()` then writes `graph.json`, emits `catalog/` shards, drops the
`.gitignore` on a first run, and clears `graph.dirty`.

## Edge extraction

Both extractors are **classification-free** — they return tokens; `build_graph`
decides whether a mention is healthy or dangling.

### `references` — a skill → its own bundled files

[atlas_extract.py:56](../scripts/atlas_extract.py#L56). Markdown links plus bare
`references/…`, `scripts/…`, `assets/…` paths, resolved against the skill
directory. URLs, `mailto:`, anchors and absolute paths are skipped; fragments
are stripped; results are deduped in first-appearance order. A target that is
not a file makes the edge `broken: true`.

### `mentions` — a skill naming another skill

[atlas_extract.py:84](../scripts/atlas_extract.py#L84). **Strict by design.** A
word-boundary match on known names produced 91 edges on a 41-skill collection,
dominated by names that are ordinary English words (`implement` appeared in ten
other files, all as the verb). A mention counts only in an unambiguous form:

- backtick-quoted — `` `tdd` ``
- slash-prefixed — `skills/tdd`
- a bare name that is hyphenated or multi-word — `resolving-merge-conflicts`

Strictness halved the edge count and removed the `implement` class of false
positive while keeping the finding that justified the edge at all.

Two more rules that are easy to break by accident:

- **Fenced code blocks are stripped first** — a mention inside a fence is
  documentation, not instruction. **Inline code spans are kept**: backtick
  mentions *are* inline code.
- **Frontmatter never reaches extraction**
  ([`split_frontmatter_body`](../scripts/atlas_extract.py#L27)) — a skill naming
  itself in its own frontmatter must not create an edge. Its own name and id are
  excluded as well.

`mentions` is a weak, inferred edge — a convention, not part of the Agent Skills
spec. Render it differently and never treat it as a hard dependency.

### `dangling` — the payload edge

Same extraction, different target
([`_classify_mention`](../scripts/build_graph.py#L32)):

| Target state | Edge | `reason` |
| --- | --- | --- |
| registered **and** enabled | `mentions` | — |
| registered but **disabled** | `dangling` | `disabled` |
| in the unregistered index | `dangling` | `unregistered` |
| nowhere at all | `dangling` | `absent` |
| ambiguous bare name (a duplicate) | *no edge* | — |

A `dangling` edge means a live skill is telling the reader to use something that
cannot be loaded — a defect in either the skill or the install. It is the
highest-value output the graph produces. Unregistered/absent targets get a
synthesized `skill?:<name>` node so the breakage is visible on the canvas.

Two token forms can resolve to the same target; a `(target, kind)` key
deduplicates them into one edge
([build_graph.py:133](../scripts/build_graph.py#L133)).

## `graph.json` (version 3)

Regenerated wholesale, never edited in place. Shape:

```jsonc
{
  "version": 3,
  "generated_at": "2026-08-11T09:14:22Z",
  "view": "local",
  "scope": "/abs/path/to/scope",
  "project": "Skill_Atlas",
  "roots": ["/home/u/.claude/skills", "/repo/.claude/skills"],
  "source_fingerprint": "sha256:…",
  "taxonomy": [ { "name": "testing", "description": "…" } ],   // frozen, rides along
  "nodes": [
    { "id": "mattpocock-skills:tdd", "type": "skill", "name": "tdd",
      "description": "…", "path": "…/SKILL.md", "scope": "plugin",
      "plugin": "mattpocock-skills", "plugin_key": "mattpocock-skills@mp",
      "marketplace": "mp", "version": "1.2.3",
      "registered": true, "enabled": true, "bytes": 3841, "mtime": "…",
      "categories": ["testing"], "category_stale": false, "searchable": false },
    { "id": "file:…/references/red-green.md", "type": "file",
      "name": "red-green.md", "path": "…", "exists": true, "bytes": 1120 },
    { "id": "skill?:qa", "type": "skill", "name": "qa",
      "registered": false, "enabled": false, "dangling": true }
  ],
  "edges": [
    { "source": "…:tdd", "target": "file:…", "kind": "references", "broken": false },
    { "source": "…:tdd", "target": "…:code-review", "kind": "mentions" },
    { "source": "…:setup", "target": "skill?:qa", "kind": "dangling",
      "reason": "unregistered" }
  ],
  "unregistered_index": [ { "name": "qa", "path": "…", "plugin": "…", "scope": "plugin" } ],
  "stats": { … }
}
```

`unregistered_index` is *indexed, not drawn* — the visualization's "show
unregistered" toggle synthesizes those nodes client-side.

### `stats`

| Key | Meaning |
| --- | --- |
| `skills`, `enabled`, `unregistered`, `files`, `edges` | counts |
| `broken_refs`, `dangling`, `orphans`, `orphan_ids` | structural findings |
| `duplicate_names` | id collisions (see [3](3-discovery.md)) |
| `uncategorized`, `stale_categories`, `searchable` | Phase 2 TODO counts |
| `orphan_assignments` | assignments whose skill left the graph — drift, not a defect |
| `catalog` | `{dormant, categories: {name: count}, uncategorized}` — the search-facing rollup, tiers 1+2 only. The session index line is built from this alone. |
| `skillmd_on_disk` | only with `--naive-count` |

The Phase 2 block comes from
[`phase2_stats()`](../scripts/atlas_annotate.py#L33), shared with
`categorize.py`'s refresh path so the two emitters cannot drift. Zero-count
categories are kept — the frozen taxonomy is a stable index shape.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | built, nothing dangling |
| 1 | built, **and** ≥1 broken reference or dangling mention |
| 2 | build failed — unreadable root, unparseable manifest, invalid curated state, write error |

Exit 1 is a **report, not a failure**: `graph.json` was written and is valid.
`make build` tolerates it; `make check` enforces it as a CI gate.

**Uncategorized and stale never affect the exit code.** They are TODO states for
the next `/skill-atlas` run, not defects. Do not "fix" this by folding them in.

On exit 2 from curated state, `main()` prints every violation and tells the user
to fix the file or `categorize.py import` a corrected one — it must **never**
delete or regenerate `categories.json`
([build_graph.py:282](../scripts/build_graph.py#L282)).

## Reporting

[`report()`](../scripts/build_graph.py#L210) prints one summary line plus every
dangling and broken-reference finding by name. Agents surfacing this to a user
should name the findings — those are real defects — and keep uncategorized/stale
counts clearly separate as TODOs.
