#!/usr/bin/env bash
# Local one-command build:  ./make.sh   (fetch new activities -> weather -> generate index.html)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${PYTHON:-python3}"
echo "▶ Fetch Garmin (you log in once)…"; "$PY" "$HERE/fetch_garmin.py"
echo "▶ Air temperature (optional)…"; "$PY" "$HERE/backfill_weather.py" || echo "  (skipped — weather fetch failed; the page builds without it)"
echo "▶ Generate…"; "$PY" "$HERE/generate.py"
echo "✓ Open: $HERE/index.html"
