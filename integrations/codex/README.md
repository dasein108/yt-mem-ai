# yt-mem-ai — OpenAI Codex CLI

Codex CLI (v0.117.0+, March 2026) runs the same `SKILL.md` skills as Claude Code.
The native path is **skills** — the `yt` / `yt-agent` skills drive the `yt-ai`
CLI via `uvx` (no MCP, no package install). MCP is a separate, optional wiring.

## Plugin (skills + prompts + AGENTS.md)

The reliable, non-interactive install (the installer does this for you) drops the
skills into the Codex **User** skill scope, plus the scenario prompts and the
project playbook:

```
# skills → ~/.codex/skills/ (loaded natively by Codex; they call `uvx yt-mem-ai …`)
cp -RL integrations/codex/skills/yt integrations/codex/skills/yt-agent ~/.codex/skills/
# scenario prompts (/yt-summarize, …) + playbook context
cp integrations/codex/prompts/*.md ~/.codex/prompts/ ; cp integrations/codex/AGENTS.md ~/.codex/AGENTS.md
```

This directory is also a valid Codex plugin (`.codex-plugin/plugin.json` with an
`interface` block + `skills/`), so you can instead add it to a marketplace and
install it from the in-app browser:

```
codex
/plugins      # browse marketplaces, install "yt-mem-ai", toggle it on
```

You need `uv`/`uvx` on PATH so the skills can run the CLI (the installer
bootstraps it).

## Config

Settings live in a global config file (`~/.yt-mem-ai/config.env`) — no config UI.
Run `/yt-setup` (first-run wizard: cookies browser, optional Webshare proxy,
embedding model) or `/yt-config` (view/change individual keys), or just ask the
`yt` skill in plain language ("set my Webshare login", "use the multilingual
embedding model"). All routes hit `uvx yt-mem-ai config …`, validate known keys,
and mask secrets.

## MCP only (optional)

If you want the typed MCP tool surface instead:

```
codex mcp add yt-mem-ai -- uvx --from 'yt-mem-ai[mcp]' yt-ai-mcp
# (or merge config.snippet.toml into ~/.codex/config.toml)
```

## One command

`sh install.sh --plugin --codex` (skills + prompts + AGENTS.md) or
`sh install.sh --mcp --codex` (the MCP server only). Covers the Codex CLI and
the IDE extension — both read `~/.codex`.
