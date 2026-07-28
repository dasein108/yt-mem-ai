#!/bin/sh
# Publish built artifacts to PyPI, loading UV_PUBLISH_TOKEN from .env on demand.
#
#   sh scripts/publish.sh                       # publish everything in dist/
#   sh scripts/publish.sh dist/yt_mem_ai-0.5.0* # publish a specific version
#
# The token lives in .env (gitignored) as UV_PUBLISH_TOKEN=pypi-…  — never
# committed. Rotate it on PyPI if it's ever exposed.
set -eu

cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

# Load secrets (UV_PUBLISH_TOKEN, and anything else) from .env into the env.
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

: "${UV_PUBLISH_TOKEN:?UV_PUBLISH_TOKEN is not set — add it to .env (see .env.example)}"

# Default to everything built; pass explicit files to publish one version.
if [ "$#" -eq 0 ]; then
  set -- dist/*
fi

echo "yt-mem-ai: publishing to PyPI: $*"
exec uv publish "$@"
