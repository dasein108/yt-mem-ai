#!/bin/sh
# yt-mem-ai installer bootstrap (POSIX).
# Usage: curl -LsSf https://raw.githubusercontent.com/dasein108/yt-mem-ai/main/install.sh | sh
set -eu

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

# uvx caches resolved versions; clear ours so this run picks up the latest release.
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
