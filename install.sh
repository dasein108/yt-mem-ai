#!/bin/sh
# yt-mem-ai installer (POSIX).
#
# Run in a terminal (or with host flags) and it launches the interactive
# host installer (Claude Code / Claude Desktop / Codex / Gemini — plugin or MCP,
# any combination). Piped with no args (`curl … | sh`) it just bootstraps the
# CLI package. Force one mode with --bootstrap or --interactive.
#
#   sh install.sh                         # interactive toggle picker
#   sh install.sh --codex=mcp --gemini=extension   # non-interactive
#   curl -LsSf .../install.sh | sh        # package bootstrap only
set -eu

REPO="dasein108/yt-mem-ai"
RAW_ROOT="https://raw.githubusercontent.com/${REPO}/main"

# Where does this script live (empty when piped via curl)?
DIR=""
case "${0:-}" in
  */*) DIR=$(cd "$(dirname "$0")" 2>/dev/null && pwd || true) ;;
  *) [ -f "./integrations/install.sh" ] && DIR=$(pwd) || true ;;
esac

MODE=""   # auto | bootstrap | interactive
ARGS=""
for a in "$@"; do
  case "$a" in
    --bootstrap) MODE=bootstrap ;;
    --interactive) MODE=interactive ;;
    *) ARGS="$ARGS $a" ;;
  esac
done

# Decide: interactive host installer, or plain package bootstrap.
if [ -z "$MODE" ]; then
  if [ -n "$ARGS" ] || [ -t 0 ]; then MODE=interactive; else MODE=bootstrap; fi
fi

if [ "$MODE" = interactive ]; then
  # Prefer the local checkout's installer; otherwise fetch it.
  # shellcheck disable=SC2086
  if [ -n "$DIR" ] && [ -f "$DIR/integrations/install.sh" ]; then
    exec sh "$DIR/integrations/install.sh" $ARGS
  fi
  echo "yt-mem-ai: fetching the interactive installer…"
  # shellcheck disable=SC2086
  exec sh -c "curl -LsSf '$RAW_ROOT/integrations/install.sh' | sh -s -- $ARGS"
fi

# --- package bootstrap (piped, no args) ------------------------------------
if ! command -v uv >/dev/null 2>&1; then
  echo "yt-mem-ai: installing uv (provides Python + uvx)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
if ! command -v uvx >/dev/null 2>&1; then
  echo "yt-mem-ai: uvx not found on PATH after installing uv." >&2
  echo "Add uv's bin dir to PATH (usually ~/.local/bin) and re-run." >&2
  exit 1
fi

echo "yt-mem-ai: fetching the latest published version..."
uv cache clean yt-mem-ai >/dev/null 2>&1 || true
VERSION=$(uvx --refresh-package yt-mem-ai --from yt-mem-ai \
  python -c "import importlib.metadata as m; print(m.version('yt-mem-ai'))" 2>/dev/null || true)
if [ -n "$VERSION" ]; then
  echo "yt-mem-ai: installed version $VERSION"
else
  echo "yt-mem-ai: installed the latest version"
fi

echo "yt-mem-ai: ready. Run it with:"
echo "  uvx yt-mem-ai --help          # or, once installed, the 'yt-ai' command"
echo
echo "yt-mem-ai: to wire up host plugins/MCP (Claude/Codex/Gemini), run the"
echo "  interactive installer:  sh install.sh --interactive"
echo "  or:  curl -LsSf $RAW_ROOT/integrations/install.sh | sh -s -- --help"
