#!/usr/bin/env bash
# Prepare a release (dev only). The plugin cache is keyed by version number —
# `cache/<marketplace>/<plugin>/<version>/` is never re-extracted once it
# exists — so commits pushed without a version bump reach the marketplace
# metadata and the recorded gitCommitSha, but not the files anyone runs.
# A bump is therefore the only thing that ships code.
#
# Bumps both manifests, validates, tests, commits and tags. Does NOT push:
# the last word stays yours. Prints the push command when it is done.
#
#   dev/release.sh            # 0.5.0 -> 0.5.1
#   dev/release.sh minor      # 0.5.0 -> 0.6.0
#   dev/release.sh 1.0.0      # explicit
set -euo pipefail

cd "$(dirname "$0")/.."

PLUGIN=.claude-plugin/plugin.json
MARKET=.claude-plugin/marketplace.json
ARG="${1:-patch}"

# The bump is cut on RELEASE_BRANCH and reaches users through PUBLISH_BRANCH —
# the repo's default branch, the only ref the marketplace clone tracks. Keeping
# the publish branch a pure fast-forward mirror means the tag, the commit users
# install, and the branch tip are all the same object, and the two branches
# never drift.
RELEASE_BRANCH="${RELEASE_BRANCH:-develop}"
PUBLISH_BRANCH="${PUBLISH_BRANCH:-main}"
branch=$(git rev-parse --abbrev-ref HEAD)
if [ "$branch" != "$RELEASE_BRANCH" ]; then
  echo "release: on '$branch', but releases are cut on '$RELEASE_BRANCH'" >&2
  echo "         switch, or RELEASE_BRANCH=$branch make release to override" >&2
  exit 1
fi

# A stale branch tags an old tree while the newer commits ship unlabelled.
if git rev-parse --verify --quiet "origin/$RELEASE_BRANCH" >/dev/null; then
  behind=$(git rev-list --count "HEAD..origin/$RELEASE_BRANCH")
  if [ "$behind" -ne 0 ]; then
    echo "release: $behind commit(s) behind origin/$RELEASE_BRANCH — pull first" >&2
    exit 1
  fi
fi

# The fast-forward only holds while the publish branch carries nothing of its
# own. One commit made directly on it (a web edit, a hotfix) ends that quietly,
# and the next merge becomes a merge commit whose tree no tag describes.
for ref in "$PUBLISH_BRANCH" "origin/$PUBLISH_BRANCH"; do
  git rev-parse --verify --quiet "$ref" >/dev/null || continue
  if ! git merge-base --is-ancestor "$ref" HEAD; then
    ahead=$(git rev-list --count "HEAD..$ref")
    echo "release: $ref has $ahead commit(s) not on $RELEASE_BRANCH — it can no longer" >&2
    echo "         fast-forward. Merge it back down first:" >&2
    echo "           git checkout $RELEASE_BRANCH && git merge $ref" >&2
    exit 1
  fi
done

# Both manifests carry the version and must agree; `claude plugin tag`
# enforces that too, but failing here says so before anything is written.
cur_plugin=$(python3 -c "import json;print(json.load(open('$PLUGIN'))['version'])")
cur_market=$(python3 -c "import json;print(json.load(open('$MARKET'))['plugins'][0]['version'])")
if [ "$cur_plugin" != "$cur_market" ]; then
  echo "release: manifests disagree — plugin.json=$cur_plugin marketplace.json=$cur_market" >&2
  exit 1
fi

case "$ARG" in
  major|minor|patch)
    NEW=$(python3 - "$cur_plugin" "$ARG" <<'PY'
import sys
major, minor, patch = (int(p) for p in sys.argv[1].split("."))
kind = sys.argv[2]
if kind == "major":
    major, minor, patch = major + 1, 0, 0
elif kind == "minor":
    minor, patch = minor + 1, 0
else:
    patch += 1
print(f"{major}.{minor}.{patch}")
PY
)
    ;;
  [0-9]*.[0-9]*.[0-9]*) NEW="$ARG" ;;
  *) echo "release: expected major|minor|patch or an explicit X.Y.Z, got '$ARG'" >&2; exit 1 ;;
esac

echo "release: $cur_plugin -> $NEW"

# Textual replacement, not a json round-trip: keeps the hand-formatting and
# the \u escape in plugin.json's description exactly as committed. Each file
# holds the version string once, which is asserted rather than assumed.
python3 - "$cur_plugin" "$NEW" "$PLUGIN" "$MARKET" <<'PY'
import sys
old, new, *paths = sys.argv[1:]
needle = f'"version": "{old}"'
for path in paths:
    text = open(path, encoding="utf-8").read()
    if text.count(needle) != 1:
        sys.exit(f"release: expected exactly one {needle} in {path}, found {text.count(needle)}")
    open(path, "w", encoding="utf-8").write(text.replace(needle, f'"version": "{new}"'))
PY

echo "release: validating manifests"
claude plugin validate . --strict

echo "release: running the unit suite"
bash tests/run_tests.sh

cat <<EOF

release: v$NEW written to both manifests, validated, tests green.
         Nothing committed, tagged or pushed — that is yours.

  review:  git diff -- .claude-plugin/
  undo:    git checkout -- .claude-plugin/

  then:
    git commit -am "release v$NEW"
    claude plugin tag . -m "skill-atlas %s"     # optional — bookkeeping only
    git push
    git checkout $PUBLISH_BRANCH && git merge --ff-only $RELEASE_BRANCH
    git push --follow-tags
    git checkout $RELEASE_BRANCH

  --ff-only is the guard: if it refuses, $PUBLISH_BRANCH grew a commit of its
  own and the branches have drifted. Merge it back down before shipping.
EOF
