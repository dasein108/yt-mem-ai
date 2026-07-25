# Repository Instructions — yt-ai (engine)

This repo is the Python engine published to PyPI as `yt-ai`. The desktop UI is
a separate repo (`yt-ai-desktop`) that consumes this engine over the local HTTP
API only — never import Python across the boundary.

## Surface parity

When adding, changing, or removing a user-facing operation, keep every surface
in sync in the same change:

- Core logic in `yt_summary/` (single source of truth).
- CLI in `yt_summary/cli.py` (thin `run_*` cores over the same core).
- The REST API lives in the `yt-ai-desktop` repo's backend (it imports this
  package). When you change a CLI core (`run_*`, `open_store`) that the API
  consumes, keep that repo's backend in sync.
- Canonical skills in `skills/<name>/SKILL.md` (the `.claude/skills/<name>`
  symlinks are thin pointers — never duplicate the body).
- Tests in `tests/` (offline via the injectable seams; no network, no model
  downloads).

The CLI and API are thin adapters over the same core — do not fork logic into
either surface.

## Packaging

- Version comes from git tags via `hatch-vcs`. Do not hand-edit a version.
- Release = push a `v*` tag; `.github/workflows/publish-pypi.yml` builds and
  publishes via PyPI Trusted Publishing (OIDC, no stored token).

## Deferred (phase 2, not in this repo yet)

- `yt_summary/server.py` MCP server + `yt_summary/installer/` cross-agent
  config writer. When added, they become additional surfaces under "Surface
  parity" above and get their own `yt-ai-mcp` / `yt-ai-install` console scripts.
