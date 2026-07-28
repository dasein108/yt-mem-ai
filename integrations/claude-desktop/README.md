# yt-mem-ai — Claude Desktop extension (`.mcpb`)

Claude Desktop only loads MCP servers (not Claude Code skills), so this packages
the `yt-ai-mcp` server as a one-click `.mcpb` bundle. Scenario playbooks are
available as MCP **prompts** (summarize / highlights / digest / review / group).

## Option A — Bundle (recommended)

```
sh integrations/claude-desktop/build.sh      # needs: npm i -g @anthropic-ai/mcpb
```

Then double-click `yt-mem-ai.mcpb` (or Claude Desktop → Settings → Extensions →
Install from file). Claude Desktop prompts for the data directory and optional
proxy/cookies config.

## Option B — MCP config (no bundle)

Add the server directly to `claude_desktop_config.json`
(macOS: `~/Library/Application Support/Claude/`,
Windows: `%APPDATA%\Claude\`):

```json
{
  "mcpServers": {
    "yt-mem-ai": {
      "command": "uvx",
      "args": ["--from", "yt-mem-ai[mcp]", "yt-ai-mcp"],
      "env": { "YT_STORE_PATH": "/Users/you/.yt-mem-ai/lance" }
    }
  }
}
```

The interactive installer wires either path: `integrations/install.sh` → select
**Claude Desktop (Bundle)** or **Claude Desktop (MCP config)**.

## Reconfigure from chat

Beyond the install-time `user_config` prompts, you can change any setting later
by just asking Claude — it uses the `config_set` / `config_list` MCP tools (e.g.
"set my Webshare proxy password", "use the multilingual embedding model"). Values
persist to `~/.yt-mem-ai/config.env` and take effect on the next call. Since
Claude Desktop is MCP-only, these tools are the in-chat way to reconfigure without
re-editing `claude_desktop_config.json`.

## PATH caveat

Claude Desktop launches the server with the GUI app's environment, which often
does **not** include `~/.local/bin` (where `uv`/`uvx` install). If the server
fails to start, either add uv's bin dir to a login-shell PATH the app inherits,
or replace `"uvx"` with its absolute path (`which uvx`) in the config / manifest.
The installer detects and substitutes the absolute `uvx` path for you.
