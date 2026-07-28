#!/bin/sh
# Build the Claude Desktop extension bundle (yt-mem-ai.mcpb) from manifest.json.
# A .mcpb is just a ZIP with manifest.json at its root, so the mcpb CLI is
# OPTIONAL — we fall back to `zip`.
#
# If YT_MCP_BIN is set (absolute path to an installed `yt-ai-mcp`), the packed
# manifest launches that binary directly instead of `uvx` — so Claude Desktop
# starts the server instantly (no heavy uvx cold-start) and finds it without
# relying on the GUI app's PATH. The committed manifest.json is never modified;
# packing happens in a temp dir.
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
cd "$here"

if command -v python3 >/dev/null 2>&1; then
  python3 -c "import json; json.load(open('manifest.json'))" \
    || { echo "manifest.json is not valid JSON" >&2; exit 1; }
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
cp manifest.json "$tmp/manifest.json"
[ -f README.md ] && cp README.md "$tmp/README.md" || true

# Resolve the launch command to an absolute binary when requested.
if [ -n "${YT_MCP_BIN:-}" ] && command -v python3 >/dev/null 2>&1; then
  YT_MCP_BIN="$YT_MCP_BIN" python3 - "$tmp/manifest.json" <<'PY'
import json, os, sys
p = sys.argv[1]; m = json.load(open(p))
m["server"]["entry_point"] = "yt-ai-mcp"
m["server"]["mcp_config"]["command"] = os.environ["YT_MCP_BIN"]
m["server"]["mcp_config"]["args"] = []
json.dump(m, open(p, "w"), indent=2)
PY
fi

out="$here/yt-mem-ai.mcpb"
rm -f "$out"
if command -v mcpb >/dev/null 2>&1; then
  ( cd "$tmp" && mcpb validate manifest.json && mcpb pack . "$out" )
elif command -v zip >/dev/null 2>&1; then
  ( cd "$tmp" && zip -q "$out" manifest.json && { [ -f README.md ] && zip -q "$out" README.md || true; } )
else
  echo "Need either the mcpb CLI (npm i -g @anthropic-ai/mcpb) or 'zip'." >&2
  exit 1
fi

echo "Built $out — double-click it (or Claude Desktop → Settings → Extensions → Install from file)."
