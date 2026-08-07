"""Staleness fingerprint (DESIGN §5.1): sha256 over sorted (path, mtime_ns,
size) of every SKILL.md AND every manifest. The manifests are not optional —
toggling enabledPlugins changes the graph and touches no skill file; without
them the graph goes silently stale.

Stat-only, no file reads. os.stat follows symlinks, so a change behind a
symlinked skill dir is seen.
"""

import hashlib
import os
import time


def compute(skill_paths, manifest_paths, deadline=None):
    """Returns 'sha256:<hex>', or None if `deadline` (a time.monotonic()
    value) passes mid-walk — a slow hook is worse than a stale graph."""
    entries = []
    for path in sorted({str(p) for p in list(skill_paths) + list(manifest_paths)}):
        if deadline is not None and time.monotonic() > deadline:
            return None
        try:
            stat = os.stat(path)
            entries.append(f"{path}|{stat.st_mtime_ns}|{stat.st_size}")
        except OSError:
            # A missing settings.local.json is normal; its appearance later
            # must flip the fingerprint, so absence is part of the hash.
            entries.append(f"{path}|missing")
    digest = hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
