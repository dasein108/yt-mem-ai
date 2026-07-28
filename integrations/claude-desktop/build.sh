#!/bin/sh
# Build the Claude Desktop extension bundle (yt-mem-ai.mcpb) from manifest.json.
# Requires the mcpb CLI: npm install -g @anthropic-ai/mcpb
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
cd "$here"

if ! command -v mcpb >/dev/null 2>&1; then
  echo "mcpb CLI not found. Install it with:" >&2
  echo "  npm install -g @anthropic-ai/mcpb" >&2
  exit 1
fi

# Validate then pack. `mcpb pack <dir> <out>` zips the directory (manifest.json
# at its root) into a .mcpb. No Python deps are bundled — the server runs the
# published package via uvx at launch, so uv/uvx must be on PATH.
mcpb validate manifest.json
mcpb pack . yt-mem-ai.mcpb
echo "Built $here/yt-mem-ai.mcpb — double-click it (or drag into Claude Desktop → Settings → Extensions) to install."
