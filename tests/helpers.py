"""Shared test plumbing: sys.path for scripts/, and an env sandbox that
points the whole system at a throwaway copy of the fixture tree. No test
ever touches the real ~/.claude."""

import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "fakehome"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

ENV_VARS = [
    "SKILL_ATLAS_CLAUDE_DIR",
    "SKILL_ATLAS_HOME",
    "SKILL_ATLAS_AUTOBUILD",
]

# Fixture manifests use this placeholder for absolute install paths; the
# sandbox rewrites it to the copied tree's real location.
PLACEHOLDER = "__CLAUDE_DIR__"


class EnvSandbox:
    def __init__(self, copy_fixtures: bool = False):
        self.copy_fixtures = copy_fixtures
        self.tmp = None
        self.claude = None
        self._saved = {}

    def __enter__(self):
        self._saved = {name: os.environ.get(name) for name in ENV_VARS}
        self.tmp = Path(tempfile.mkdtemp(prefix="skill-atlas-test-"))
        self.claude = self.tmp / "claude"
        if self.copy_fixtures:
            shutil.copytree(FIXTURES, self.claude, symlinks=True)
            self._rewrite_placeholders()
            self._ensure_symlink()
        else:
            self.claude.mkdir()
        os.environ["SKILL_ATLAS_CLAUDE_DIR"] = str(self.claude)
        os.environ["SKILL_ATLAS_HOME"] = str(self.tmp / "atlas-home")
        os.environ.pop("SKILL_ATLAS_AUTOBUILD", None)
        return self

    def __exit__(self, *exc_info):
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False

    def _rewrite_placeholders(self):
        manifest = self.claude / "plugins" / "installed_plugins.json"
        if manifest.exists():
            text = manifest.read_text(encoding="utf-8")
            manifest.write_text(text.replace(PLACEHOLDER, str(self.claude)), encoding="utf-8")

    def _ensure_symlink(self):
        """Recreate the symlinked user skill if the checkout/copy lost it."""
        link = self.claude / "skills" / "linked-skill"
        if not link.exists() and not link.is_symlink():
            link.symlink_to("../linktarget", target_is_directory=True)

    @property
    def project_dir(self) -> Path:
        return self.claude / "project"
