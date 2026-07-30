# yt-mem-ai — Google Antigravity ("Gravity")

Antigravity (IDE + CLI) supports both **Skills** (`SKILL.md`) and **MCP servers**,
shared across its CLI/IDE via the `~/.gemini/` config tree.

## Skills

Antigravity auto-discovers skills from `~/.gemini/skills/<name>/SKILL.md` (shared
across CLI, IDE, SDK). Drop the `yt` and `yt-agent` skills in:

```
mkdir -p ~/.gemini/skills
cp -RL integrations/antigravity/skills/yt integrations/antigravity/skills/yt-agent ~/.gemini/skills/
```

They drive the `yt-ai` CLI via `uvx yt-mem-ai <cmd>` (zero-install). Restart
Antigravity to pick them up.

## MCP

Merge the server into `~/.gemini/config/mcp_config.json`:

```json
{ "mcpServers": { "yt-mem-ai": {
  "command": "<abs path to yt-ai-mcp>", "args": [],
  "env": { "YT_STORE_PATH": "/Users/you/.yt-mem-ai/lance" } } } }
```

The installer runs `uv tool install 'yt-mem-ai[mcp]'` and fills in the absolute
`yt-ai-mcp` binary path (fast startup). You can also add it via Antigravity's
MCP store → Manage MCP Servers → View raw config.

> Antigravity reuses the `~/.gemini/` directory (it's Gemini-based), but under
> different files than the Gemini CLI — `~/.gemini/config/mcp_config.json` and
> `~/.gemini/skills/`, not `settings.json`/`extensions/`.

## One command

`sh install.sh --plugin --antigravity` (skills) and/or `sh install.sh --mcp
--antigravity` (MCP server); `--gravity` is an alias. Bare `sh install.sh`
shows the wizard.
