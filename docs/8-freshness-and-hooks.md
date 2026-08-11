# 8 — Freshness and hooks

**Files:** [check_stale.py](../scripts/check_stale.py) (SessionStart),
[mark_dirty.py](../scripts/mark_dirty.py) (PostToolUse),
[atlas_fingerprint.py](../scripts/atlas_fingerprint.py),
[hooks/hooks.json](../hooks/hooks.json).
**Tests:** [test_hooks.py](../tests/test_hooks.py),
[test_fingerprint.py](../tests/test_fingerprint.py).

The governing rule: **the graph must never be silently stale.** Four triggers,
cheapest first.

| Trigger | Mechanism |
| --- | --- |
| SessionStart | fingerprint check → rebuild on mismatch, then inject the index line |
| PostToolUse(Write\|Edit) | drop `graph.dirty`; the next session boundary consumes it |
| explicit | `/skill-atlas`, `build_graph.py`, `make build` |
| — | **no filesystem watcher**, deliberately (see the end of this doc) |

## Hook invariants — non-negotiable

1. **Always exit 0.** A non-zero hook can interrupt the session.
2. **Never write to stdout** except the documented SessionStart JSON contract.
3. **Swallow every exception** into `debug.log` — path, line, exception *type*
   only, never parsed content.
4. **Hard timeout 10 s** (set in [hooks.json](../hooks/hooks.json)).
5. **Never block** on network or lock contention.
6. **Never initialize a scope.** The hooks operate only where
   `.claude/skill-atlas/` already exists.

`check_stale.main()` catches `BaseException`, and even the fallback logging is
wrapped in its own `try` ([check_stale.py:137](../scripts/check_stale.py#L137)).
`mark_dirty` is deliberately **import-light** — no `atlas_*` modules at all — to
keep per-edit latency near zero, which is why its path patterns are hand-written
rather than imported.

## The fingerprint

[`compute()`](../scripts/atlas_fingerprint.py#L15):

```text
sha256(sorted(
    [(path, mtime_ns, size) for every SKILL.md]
  + [(path, mtime_ns, size) for every manifest]
))
```

**The manifests are not optional.** Since discovery is manifest-driven, the
graph depends on files that are not `SKILL.md`: toggling
`enabledPlugins.superpowers` changes the graph and touches no skill file at all.
`manifest_paths()` ([atlas_paths.py:185](../scripts/atlas_paths.py#L185)) covers:

- `~/.claude/plugins/installed_plugins.json`
- every settings file in the precedence chain
- each installed plugin's `.claude-plugin/plugin.json`
- **this scope's `categories.json` and `config.json`** — editing curated state
  changes the graph while touching no skill file, the same hole as above.

Three properties to preserve:

- **Stat-only, no file reads.** Must complete in < 200 ms for 500 skills or it
  degrades session startup.
- **Absence hashes as `|missing`.** A `settings.local.json` that does not exist
  yet is normal; its later *appearance* must flip the fingerprint.
- **Deadline-abortable.** The walk takes a `time.monotonic()` deadline and
  returns `None` when it passes. A slow hook is worse than a stale graph.

Adding any new build input means adding it to `manifest_paths()` (or to
`skill_md_paths()`) — otherwise the graph goes silently stale, which is the one
thing this whole section exists to forbid.

## SessionStart — `check_stale.py`

Matcher `startup|resume|clear|compact`. [`run()`](../scripts/check_stale.py#L66):

1. `SKILL_ATLAS_AUTOBUILD=0` → return immediately.
2. Scope not initialized → return immediately. **The hook never creates
   anything.**
3. Decide whether to rebuild, in order:
   - `graph.dirty` exists → `reason = "dirty-flag"`
   - no stored fingerprint → `reason = "no-graph"`
   - computed ≠ stored → `reason = "fingerprint-mismatch"`
   - the walk hit the 2 s deadline (`FINGERPRINT_DEADLINE_SECONDS`) → log
     `fingerprint-deadline-exceeded`, return `None`, proceed stale.
4. On a rebuild: `build_graph.build()`, atomic-write `graph.json`, re-emit
   `catalog/` shards, unlink the dirty marker.
5. Log `rebuilt <reason> total_ms=…` or `fresh total_ms=…` via `debug_note`.
6. `main()` then prints the index line — and only that — as
   `{"hookSpecificOutput": {"hookEventName": "SessionStart",
   "additionalContext": …}}`.

An invalid `categories.json` **must never break a session**: the hook swallows
the failure and keeps the last-good graph. The violations print from the
explicit build instead (`test_invalid_categories_never_breaks_session`).

The index line itself is documented in
[6-catalog-and-search.md](6-catalog-and-search.md).

## PostToolUse — `mark_dirty.py`

Matcher `Write|Edit`. Reads the hook payload from stdin, takes
`tool_input.file_path`, normalizes separators, and matches against
[`PATTERNS`](../scripts/mark_dirty.py#L13):

```text
*/SKILL.md                     */.claude/settings.json
*/skills/*                     */.claude/settings.local.json
*/.claude-plugin/plugin.json   */.claude/plugins/installed_plugins.json
*/skill-atlas/categories.json  */skill-atlas/config.json
```

On a match it touches `<cwd>/.claude/skill-atlas/graph.dirty` — **only if that
directory already exists**. It never rebuilds inline: that would put filesystem
work in the middle of a tool call, and skill edits come in bursts while
authoring, so deferring to a session boundary batches them. Garbage on stdin
exits 0 silently.

Keep this file's pattern list in sync with `manifest_paths()` by hand. The
duplication is deliberate — the import cost is the thing being avoided — so a
new build input needs editing in **both** places.

## Why no filesystem watcher

It needs a resident process, it fights editors that write-then-rename, and it
buys latency nobody needs — the graph is read only at session start and on
demand. Revisit only if the fingerprint walk proves too slow.

## Debugging a hook

Hooks are silent by contract, so start at the log:

```bash
tail ./.claude/skill-atlas/debug.log      # "check_stale rebuilt … total_ms=…"
SKILL_ATLAS_AUTOBUILD=0 …                 # bisect: is the rebuild the problem?
python3 scripts/build_graph.py            # the same work, but loud
```

Remember the log **never** contains messages or file content — only a component,
a path, a line number and an exception type name. If you need more than that,
reproduce with the explicit build; do not loosen the logger.

Changes under `hooks/` need `/reload-plugins` or a restart to take effect.
