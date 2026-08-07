#!/usr/bin/env bash
# One-time (dev only) fetch of the vendored D3 build. The committed copy at
# vendor/d3.v7.min.js is what render.py inlines; this script exists so the
# provenance of that file is reproducible. Never runs at build or view time.
set -euo pipefail

VERSION="7.9.0"
SHA256="f2094bbf6141b359722c4fe454eb6c4b0f0e42cc10cc7af921fc158fceb86539"
URL="https://cdn.jsdelivr.net/npm/d3@${VERSION}/dist/d3.min.js"
OUT="$(dirname "$0")/../vendor/d3.v7.min.js"

curl -sSL --fail -o "${OUT}.tmp" "$URL"
echo "${SHA256}  ${OUT}.tmp" | sha256sum -c -
mv "${OUT}.tmp" "$OUT"
echo "vendor/d3.v7.min.js pinned at d3@${VERSION} (${SHA256})"
