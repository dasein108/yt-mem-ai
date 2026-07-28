#!/bin/sh
# Build the Claude Desktop extension bundle (yt-mem-ai.mcpb) from manifest.json.
# A .mcpb is just a ZIP with manifest.json at its root, so the mcpb CLI is
# OPTIONAL — we fall back to `zip`. The server runs the published package via
# uvx at launch (no bundled code), so uv/uvx must be on PATH when it runs.
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
cd "$here"

# Sanity-check the manifest is valid JSON before packing.
if command -v python3 >/dev/null 2>&1; then
  python3 -c "import json,sys; json.load(open('manifest.json'))" \
    || { echo "manifest.json is not valid JSON" >&2; exit 1; }
fi

rm -f yt-mem-ai.mcpb
if command -v mcpb >/dev/null 2>&1; then
  mcpb validate manifest.json
  mcpb pack . yt-mem-ai.mcpb
elif command -v zip >/dev/null 2>&1; then
  # manifest.json must be at the archive root.
  zip -q yt-mem-ai.mcpb manifest.json
  [ -f README.md ] && zip -q yt-mem-ai.mcpb README.md || true
else
  echo "Need either the mcpb CLI (npm i -g @anthropic-ai/mcpb) or 'zip'." >&2
  exit 1
fi

echo "Built $here/yt-mem-ai.mcpb — double-click it (or Claude Desktop → Settings → Extensions → Install from file)."
