# yt-mem-ai — OpenAI Codex CLI

Codex CLI (v0.117.0+, March 2026) has a first-class **plugin** system that bundles
skills + MCP servers + app connectors, and it runs the same `SKILL.md` skills as
Claude Code. So "Plugin" here = native skills + the MCP server (+ prompts and
AGENTS.md); "MCP" = just the server.

## Plugin (skills + MCP)

The reliable, non-interactive install (installer does this for you) drops the
`yt` / `yt-manager` skills into the Codex **User** skill scope and wires the MCP
server:

```
# skills → ~/.codex/skills/ (loaded natively by Codex)
cp -RL integrations/codex/skills/yt integrations/codex/skills/yt-manager ~/.codex/skills/
# MCP server
codex mcp add yt-mem-ai -- uvx --from 'yt-mem-ai[mcp]' yt-ai-mcp
# (or merge config.snippet.toml into ~/.codex/config.toml)
# optional: scenario prompts + project playbook
cp integrations/codex/prompts/*.md ~/.codex/prompts/ ; cp integrations/codex/AGENTS.md ~/.codex/AGENTS.md
```

This directory is also a valid Codex plugin (`.codex-plugin/plugin.json` with an
`interface` block, `skills/`, and inline `mcpServers`), so you can instead add it
to a marketplace and install it from the in-app browser:

```
codex
/plugins      # browse marketplaces, install "yt-mem-ai", toggle it on
```

## MCP only

```
codex mcp add yt-mem-ai -- uvx --from 'yt-mem-ai[mcp]' yt-ai-mcp
```

## One command

`integrations/install.sh` → **Codex (Plugin)** (skills + MCP + prompts + AGENTS)
or **Codex (MCP)** (server only).
