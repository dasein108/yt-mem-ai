#!/bin/sh
# yt-ai installer bootstrap (POSIX).
# Usage: curl -LsSf https://raw.githubusercontent.com/dasein108/yt-ai/main/install.sh | sh
set -eu

if ! command -v uv >/dev/null 2>&1; then
  echo "yt-ai: installing uv (provides Python + uvx)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

if ! command -v uvx >/dev/null 2>&1; then
  echo "yt-ai: uvx not found on PATH after installing uv." >&2
  echo "Add uv's bin dir to PATH (usually ~/.local/bin) and re-run." >&2
  exit 1
fi

# uvx caches resolved versions; clear ours so this run picks up the latest release.
echo "yt-ai: fetching the latest published version..."
uv cache clean yt-ai >/dev/null 2>&1 || true

VERSION=$(uvx --refresh-package yt-ai --from yt-ai \
  python -c "import importlib.metadata as m; print(m.version('yt-ai'))" 2>/dev/null || true)
if [ -n "$VERSION" ]; then
  echo "yt-ai: installed version $VERSION"
else
  echo "yt-ai: installed the latest version"
fi

echo "yt-ai: ready. Run it with:"
echo "  uvx yt-ai --help"
echo "  uvx yt-ai serve        # start the local API for yt-ai-desktop"
