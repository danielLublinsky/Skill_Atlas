"""Atomic artifact writes and the single guarded debug logger.

debug_log() is the ONLY place anything is ever logged. Its contract is the
privacy boundary from DESIGN §10.2: it records a path, a line number and an
exception TYPE NAME — never message text, never line content. Transcript
parse errors naturally want to log the offending line; this signature is
shaped so they can't.
"""

import datetime
import json
import os
import tempfile
from pathlib import Path

import atlas_paths


def atomic_write_json(path, obj) -> None:
    _atomic_write(path, json.dumps(obj, indent=2, sort_keys=True) + "\n")


def atomic_write_text(path, text: str) -> None:
    _atomic_write(path, text)


def _atomic_write(path, text: str) -> None:
    """Write to a temp file in the target directory, then os.replace().
    Safe under concurrent builds: last writer wins, never a torn file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def debug_log(component: str, path, lineno: int, exc: BaseException) -> None:
    """Record a failure: path, line number, exception type name. Nothing else.

    The exception's message is deliberately discarded — str(exc) can embed
    content from the file being parsed (e.g. json.JSONDecodeError context).
    Only the type survives.
    """
    label = type(exc).__name__ if isinstance(exc, BaseException) else "UnknownError"
    _append(f"{component} {path}:{lineno} {label}")


def debug_note(component: str, note: str) -> None:
    """Short operational notes from hooks (durations, skipped runs). Callers
    must pass fixed strings or numbers they constructed — never file
    content."""
    _append(f"{component} {note}")


def _append(line: str) -> None:
    try:
        log = atlas_paths.debug_log_path()
        log.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {line}\n")
    except OSError:
        pass
