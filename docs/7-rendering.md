# 7 — Rendering

**Files:** [render.py](../scripts/render.py) (100 lines of assembly),
[scripts/template/atlas_template.html](../scripts/template/atlas_template.html)
(993 lines — the actual visualization),
[vendor/d3.v7.min.js](../vendor/d3.v7.min.js).
**Tests:** [test_render.py](../tests/test_render.py).

```bash
python3 scripts/render.py [--cwd DIR]     # graph.json → atlas.html
```

## What `render.py` does

[`render()`](../scripts/render.py#L54) is pure assembly — three string
substitutions into the template:

| Placeholder | Replaced with |
| --- | --- |
| `__TITLE__` | `skill-atlas · <project>`, HTML-escaped |
| `/*__D3__*/` | the vendored D3 source, inlined |
| `__DATA_JSON__` | `{"graph": …, "meta": …}` as JSON |

Two subtleties worth keeping:

- **`</` is escaped to `<\/`** in the data payload
  ([render.py:63](../scripts/render.py#L63)) so a description containing `</script>`
  cannot terminate the surrounding block. `test_script_terminator_escaped_in_data`
  guards it.
- **The staleness banner is computed at render time**
  ([`_graph_is_stale`](../scripts/render.py#L27)) — JS under `file://` cannot
  stat files. It compares `graph.json`'s mtime against every SKILL.md *and every
  manifest* in the scope.

### Two hard properties

1. **Self-contained.** The page opens from `file://` with zero network requests:
   no CDN, no external stylesheet, no remote font, no build step.
2. **Deterministic.** No render timestamp; the same inputs produce
   byte-identical output, so visual diffing works. The force layout is seeded
   deterministically in the template
   ([mulberry32](../scripts/template/atlas_template.html#L330)) for the same
   reason — a layout that reshuffles every build makes diffing impossible.

`render.py` exits 2 with a pointer to `build_graph.py` when there is no
`graph.json`.

## The template

Everything after `__DATA_JSON__` is plain D3 with no build step. Landmarks:

| Line | Section |
| --- | --- |
| [11](../scripts/template/atlas_template.html#L11) | `<style>` — CSS custom properties, light/dark via `color-scheme` |
| [290–318](../scripts/template/atlas_template.html#L290) | markup: view tabs, filter menu, plugin menu, canvas, legend, tooltip, table |
| [329](../scripts/template/atlas_template.html#L329) | deterministic randomness (`mulberry32`, `hashCode`) |
| [344](../scripts/template/atlas_template.html#L344) | model building — node copies, edge filtering, per-plugin colours |
| [385](../scripts/template/atlas_template.html#L385) | controls: `viewMode`, filter toggles, `summarizeFilters` |
| [489](../scripts/template/atlas_template.html#L489) | `activeGroups` — the plugin filter |
| [507](../scripts/template/atlas_template.html#L507) | `renderLegend` |
| [549](../scripts/template/atlas_template.html#L549) | footer: counts, staleness, TODO states |
| [574](../scripts/template/atlas_template.html#L574) | `buildTable` — the >600-node fallback |
| [611](../scripts/template/atlas_template.html#L611) | `visibleModel` — filters + category-hub synthesis |
| [681](../scripts/template/atlas_template.html#L681) | `drawGraph` — the simulation and all interaction |
| [970](../scripts/template/atlas_template.html#L970) | `useTable = nodeTotal > 600` |

## The two views

**Scope view is the default** (DESIGN §7.3). Tabs sit centred
on the control bar, apart from the filter dropdown: swapping the whole picture
is a different act from subtracting from it.

### Scope view — the structural picture

Clusters by scope/plugin. This is where every structural finding shows up.

| Channel | Encodes |
| --- | --- |
| node shape | rounded rect = skill, small circle = bundled file |
| node colour | scope — user / project / plugin (per-plugin hue derived from the name) |
| node fill | painted "hollow" = disabled, tinted = enabled. Painted, never transparent, so edges stop at the border instead of crossing the label |
| node stroke | grey dash = dangling target; a distinct stroke marks **searchable**, so it cannot be confused with plain disabled |
| edge style | solid = `references`, dotted = `mentions` |
| edge colour | red = broken reference or dangling edge |
| edge width | uniform — there is no data to encode; resist the temptation |

Orphans and unregistered skills float as ordinary nodes near their own cluster —
the gutters were removed. An unregistered skill carries its originating plugin
and obeys the plugin filter, because "this plugin ships skills its manifest never
registers" *is* the finding, and a lane off to the side severs it from the plugin
it indicts.

**Deliberately unencoded:** token cost, file size, description length, and
anything usage-derived (there is no usage data — see DESIGN §6).

### Category view — pure catalog

Hub-and-spoke: one synthesized hub per category labelled `name (count)`, with
member skills attached. Solid edge to the display home (`categories[0]`), lighter
/dashed edges to additional memberships — so a multi-category skill hangs
*between* its hubs and same-bucket near-duplicates become obvious with no extra
machinery.

The model here contains **only** category hubs, member skills and membership
edges. No files, no `references`, no `mentions`, no dangling targets — the
structural toggles grey out. Hubs are synthesized at render time from the nodes'
`categories` field; they never exist in `graph.json`. An `uncategorized` hub
renders whenever its count is nonzero. Search `cat:<name>` in the search box to
isolate a category.

## Interaction

- **hover** → tooltip parked immediately left of the legend, never trailing the
  cursor: a panel that follows the mouse covers the neighbourhood you hovered to
  inspect, and its text moves while you read it.
- **click** → pin the node, highlight the 1-hop neighbourhood, dim the rest. The
  whole reading freezes so a long description can actually be read. Click again,
  or the background, to release.
- Incident edges are **actively highlighted** (thicker, full contrast), not
  merely spared the dimming — which edges connect is the answer being looked
  for. Broken edges keep their red under the highlight. Neighbouring file dots
  brighten and gain a ring rather than growing: at 4.5 px a size change is
  unreadable, and a moving radius would shift the layout it sits in.
- **search box** → live filter on name/description, plus `cat:<name>`.
- **filters dropdown** → hide files, hide `mentions`, dangling only, show
  unregistered, and "hide disabled non-searchable". The count of active filters
  shows on the summary: a hidden checkbox that silently reshapes the graph is
  worse than no checkbox. In category view the structural toggles grey out and
  only the dormant one stays live
  ([template:428](../scripts/template/atlas_template.html#L428)).
- **legend** → always visible, anchored top-right, never displaced. It is the key
  to the picture, so it must be findable in the same place every time.
- **footer** → view, generated timestamp, node and defect counts, TODO states,
  and the staleness warning.

## Scale bands

| Nodes | Behaviour |
| --- | --- |
| ≤ 200 | force-directed, fine as is |
| > 200 | `ctl.files` defaults to checked ([template:436](../scripts/template/atlas_template.html#L436)) — `file` nodes collapse into a per-skill badge count ([template:858](../scripts/template/atlas_template.html#L858)) |
| > 600 | fall back to the sortable table (`useTable`); the graph becomes a filtered drill-down |

Do not try to make a 2,000-node hairball legible. Manifest-driven discovery is
partly a scale decision: it takes a real collection from ~104 nodes to ~41.

## Changing the template

`render.py` only substitutes; all behaviour lives in the HTML. Guardrails:

- keep the page **self-contained** — no new external URL of any kind. Inline
  assets as data URIs, as the favicon does.
- keep output **deterministic** — no `Date.now()`, no unseeded randomness.
- new node/edge attributes must be produced by the build and read from
  `GRAPH.nodes`; the template never derives facts the graph should own.

> **Known failing test:** `test_render.test_self_contained_no_external_references`
> asserts `<link` is absent, which the inlined data-URI favicon added in
> `1ab42f2` now trips. The page is still self-contained; the assertion is
> over-strict and should test for external *schemes* instead. See
> [9-testing-and-conventions.md](9-testing-and-conventions.md).
