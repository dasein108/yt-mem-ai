# yt-mem-ai — Claude Desktop

Claude Desktop has two mechanisms:

- **Plugin** (Customize → **Plugins**) — bundles the `yt` / `yt-manager`
  **skills**, which run in Desktop **chat** and **auto-trigger** on "summarize
  this video," exactly like Codex. **This is the one you want.**
- **Extension / MCP** (Settings → Extensions, or `claude_desktop_config.json`) —
  an MCP server: typed tools, **no skills**, no auto-workflow. Optional; only if
  you specifically want the tool surface.

## Recommended — install the Plugin (skills)

In Claude Desktop: **Customize** (left sidebar) → **Plugins** → *Personal
plugins* → **+** → **Add marketplace** → **Add from a repository** →
`https://github.com/dasein108/yt-mem-ai` → **Add**, then **Install** the
`yt-mem-ai` plugin. Ask "summarize 'https://youtu.be/…'" and it runs the workflow
via `uvx yt-mem-ai` (so `uv`/`uvx` must be on PATH). The same plugin works on
**claude.ai web** and **Claude Cowork**.

If the `claude` CLI is on your PATH and its plugin store is shared with Desktop,
`integrations/install.sh` → **Claude Code (Plugin)** installs it for you
(`claude plugin marketplace add … && claude plugin install yt-mem-ai@yt-mem-ai`).

## Optional — MCP tools (no skills)

If you want the typed MCP tool surface instead, add the server to
`claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/`).
`integrations/install.sh` → **Claude Desktop (MCP config)** does this, pointing
at a pre-installed absolute `yt-ai-mcp` binary (`uv tool install 'yt-mem-ai[mcp]'`)
so it starts instantly:

```json
{ "mcpServers": { "yt-mem-ai": {
  "command": "/Users/you/.local/bin/yt-ai-mcp", "args": [],
  "env": { "YT_STORE_PATH": "/Users/you/.yt-mem-ai/lance" } } } }
```

The server sends `instructions` on connect that tell the model when to use its
tools — but the **Plugin (skills)** is the smoother path for "summarize this
video." The old one-click `.mcpb` bundle was dropped (fussy cold-start; the
plugin supersedes it).
