# yt-mem-ai — Cursor

Cursor supports both **Agent Skills** (`SKILL.md`) and **MCP servers**, so you can
install either or both.

## Skills

Cursor auto-discovers skills from `~/.cursor/skills/<name>/SKILL.md` (global) — no
manifest, no registration. Drop the `yt` and `yt-agent` skills in and reload:

```
mkdir -p ~/.cursor/skills
cp -RL integrations/cursor/skills/yt integrations/cursor/skills/yt-agent ~/.cursor/skills/
```

They drive the `yt-ai` CLI via `uvx yt-mem-ai <cmd>` (zero-install). Invoke with
`/yt` in Agent chat, or let the agent pick them up automatically. Reload Cursor
after copying.

## MCP

Merge the server into `~/.cursor/mcp.json`:

```json
{ "mcpServers": { "yt-mem-ai": {
  "command": "<abs path to yt-ai-mcp>", "args": [],
  "env": { "YT_STORE_PATH": "/Users/you/.yt-mem-ai/lance" } } } }
```

The installer runs `uv tool install 'yt-mem-ai[mcp]'` and fills in the absolute
`yt-ai-mcp` binary path (fast startup, no cold-start download).

## One command

`sh install.sh --plugin --cursor` (skills) and/or `sh install.sh --mcp --cursor`
(MCP server) — or run `sh install.sh` bare and tick Cursor in the wizard.
