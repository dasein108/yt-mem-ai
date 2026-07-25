#!/usr/bin/env bash
# Launch the local API (yt-ai serve). The desktop UI lives in the separate
# yt-ai-desktop repo; point its Vite dev proxy / Electron sidecar at this API.
#
#   ./dev.sh                 # API on :8000
#   YT_API_PORT=8010 ./dev.sh
set -euo pipefail

cd "$(dirname "$0")"
API_PORT="${YT_API_PORT:-8000}"

echo "→ starting API on :$API_PORT (Ctrl-C to stop)"
echo "  UI: run the yt-ai-desktop repo against http://127.0.0.1:$API_PORT"
exec uv run yt-ai serve --port "$API_PORT"
