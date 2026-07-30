# yt-mem-ai — Claude Desktop

Claude Desktop has two mechanisms:

- **Plugin** (Customize → **Plugins**) — bundles the `yt` / `yt-agent`
  **skills**, which run in Desktop **chat** and auto-trigger on "summarize this
  video." **Manual only** — see below.
- **MCP server** (`claude_desktop_config.json`) — typed tools, no auto-workflow.
  The only path a script can set up for Desktop.

## Skills — install in the app (not scriptable)

Desktop keeps its plugin list **on your Claude account**, not on disk. The local
`~/.claude/plugins` store belongs to **Claude Code**; Desktop chat does not read
it, so `claude plugin install` does *not* make a plugin appear in Desktop (and
you can't uninstall a Desktop plugin from the CLI either). `install.sh`
therefore prints these steps for the Claude Desktop row instead of writing files:

> **Customize** (left sidebar) → **Plugins** → *Personal plugins* → **+** →
> **Add marketplace** → **Add from a repository** →
> `https://github.com/dasein108/yt-mem-ai` → **Add** → **Install** `yt-mem-ai`

Then ask: *summarize 'https://youtu.be/…'*. The skills shell out to the CLI, so
`uv`/`uvx` must be on PATH (`uv tool install yt-mem-ai` gives you `yt-ai`
directly). Uninstall the same way: Customize → Plugins → **Uninstall**.

The same plugin works on **claude.ai web** and **Claude Cowork**.

## MCP tools — scripted

```bash
sh install.sh --mcp --claude-desktop
```

It runs `uv tool install 'yt-mem-ai[mcp]'` and merges the server into
`claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/`,
Windows: `%APPDATA%\Claude\`) pointing at the absolute binary, so Desktop starts
it instantly:

```json
{ "mcpServers": { "yt-mem-ai": {
  "command": "/Users/you/.local/bin/yt-ai-mcp", "args": [],
  "env": { "YT_STORE_PATH": "/Users/you/.yt-mem-ai/lance" } } } }
```

Restart Desktop afterwards. The server sends `instructions` on connect that tell
the model when to use its tools, and also exposes the skill playbooks as
**prompts** (`yt_summarize`, `yt_digest`, …). The old one-click `.mcpb` bundle
was dropped (fussy cold start).
