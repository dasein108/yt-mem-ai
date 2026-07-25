#!/usr/bin/env bash
# Launch the desktop UI dev stack: local API (yt-ai serve) + Vite dev server.
# Vite proxies /api -> 127.0.0.1:$YT_API_PORT. Ctrl-C stops both.
#
#   ./dev.sh                 # API on :8000, Vite on :5173
#   YT_API_PORT=8010 ./dev.sh
set -euo pipefail

cd "$(dirname "$0")"
API_PORT="${YT_API_PORT:-8000}"

cleanup() {
  trap - INT TERM EXIT
  # Kill each child and its descendants (uv->python, vite->node grandchildren).
  for pid in "${API_PID:-}" "${VITE_PID:-}"; do
    [ -n "$pid" ] || continue
    pkill -P "$pid" 2>/dev/null || true
    kill "$pid" 2>/dev/null || true
  done
}
trap cleanup INT TERM EXIT

echo "→ starting API on :$API_PORT"
uv run yt-ai serve --port "$API_PORT" &
API_PID=$!

# Point Vite's proxy at the chosen API port (default matches vite.config.ts).
echo "→ starting Vite dev server (proxying /api -> :$API_PORT)"
( cd frontend && YT_API_PORT="$API_PORT" npm run dev ) &
VITE_PID=$!

echo "→ UI: http://localhost:5173   API: http://127.0.0.1:$API_PORT   (Ctrl-C to stop)"
wait
