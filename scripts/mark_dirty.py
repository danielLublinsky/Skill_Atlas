"""PostToolUse(Write|Edit) hook — flag the graph stale (DESIGN §5.2).

Never rebuilds inline; the marker is consumed by the next SessionStart or an
explicit build. Deliberately import-light (no atlas_* modules) to keep hook
latency near zero. Always exits 0, never writes to stdout.
"""

import fnmatch
import json
import os
import sys

PATTERNS = (
    "*/SKILL.md",
    "*/skills/*",
    "*/.claude-plugin/plugin.json",
    "*/.claude/settings.json",
    "*/.claude/settings.local.json",
    "*/.claude/plugins/installed_plugins.json",
    # Phase 2 build inputs (hand-written — this file deliberately cannot
    # import atlas_paths, same as the manifest patterns above).
    "*/skill-atlas/categories.json",
    "*/skill-atlas/config.json",
)


def _dirty_marker_path():
    """Scope-local marker — and only for an already-initialized scope: the
    hook never creates `.claude/skill-atlas/` anywhere by itself."""
    home = os.path.join(os.getcwd(), ".claude", "skill-atlas")
    if not os.path.isdir(home):
        return None
    return os.path.join(home, "graph.dirty")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        file_path = (payload.get("tool_input") or {}).get("file_path", "")
        if not file_path:
            return 0
        normalized = file_path.replace(os.sep, "/")
        if any(fnmatch.fnmatch(normalized, pattern) for pattern in PATTERNS):
            marker = _dirty_marker_path()
            if marker is None:
                return 0
            with open(marker, "a", encoding="utf-8"):
                os.utime(marker, None)
    except BaseException:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
