#!/usr/bin/env bash
# Run the full unit test suite. Stdlib only — no pip, no venv required.
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 -m unittest discover -s tests -v
