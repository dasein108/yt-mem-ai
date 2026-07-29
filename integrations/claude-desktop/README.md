# yt-mem-ai — Claude Desktop

Claude Desktop has two mechanisms, and they're different:

- **Plugin** (Customize → **Plugins**) — bundles the `yt` / `yt-manager`
  **skills**, which run in Desktop **chat**. This is the one that makes
  "summarize this video" auto-trigger, exactly like Codex. **Recommended.**
- **Extension** (`.mcpb`, Settings → **Extensions**) — an MCP-server bundle:
  tools + prompts, **no skills**. The model calls tools but has no workflow
  unless it reads the server `instructions`; use it if you specifically want the
  typed MCP tool surface.

## Recommended — install the Plugin (skills auto-trigger)

In Claude Desktop: **Customize** (left sidebar) → **Plugins** → in *Personal
plugins* click **+** → **Add marketplace** → **Add from a repository** →
`https://github.com/dasein108/yt-mem-ai` → **Add**, then **Install** the
`yt-mem-ai` plugin. The `yt`/`yt-manager` skills now work in chat; ask
"summarize 'https://youtu.be/…'" and it runs the workflow (via `uvx yt-mem-ai`,
so `uv`/`uvx` must be on PATH). Skills also work the same way on **claude.ai web**
and **Claude Cowork**.

## Alternative — the MCP Extension (`.mcpb`)

### Option A — Bundle

```
sh integrations/claude-desktop/build.sh      # no mcpb CLI needed — a .mcpb is just a zip
```

`build.sh` uses the `mcpb` CLI if you have it, otherwise plain `zip` (a `.mcpb`
is a ZIP with `manifest.json` at the root). Then double-click `yt-mem-ai.mcpb`
(or Claude Desktop → Settings → Extensions → Install from file). Claude Desktop
prompts for the data directory and optional proxy/cookies config.

> The bundle is a thin launcher — the server runs the published package via
> `uvx` at startup (no bundled Python), so `uv`/`uvx` must be on PATH. If the
> bundle is fussy, **Option B (MCP config) is simpler and just as capable.**

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

## Reliability — why a fresh extension may show "could not connect"

Two Claude-Desktop-specific gotchas, both handled by the installer:

1. **Heavy cold start.** `uvx --from 'yt-mem-ai[mcp]' yt-ai-mcp` downloads the
   whole engine on first run (`lancedb`, `sentence-transformers` → **torch**,
   hundreds of MB). Desktop's MCP handshake times out long before that finishes.
2. **GUI PATH.** The app doesn't inherit your shell `PATH`, so a bare `"uvx"`
   command may not be found.

**The fix the installer applies:** it runs `uv tool install 'yt-mem-ai[mcp]'`
once (downloads the deps, creates a stable `yt-ai-mcp` binary) and points the
extension/config at that **absolute binary** with no args — so Desktop starts it
instantly and always finds it. To do it by hand:

```
uv tool install 'yt-mem-ai[mcp]'     # one-time; pulls ML deps
which yt-ai-mcp                       # e.g. /Users/you/.local/bin/yt-ai-mcp
```

then set that path as the server `command` (args `[]`) in Option A's manifest
(`YT_MCP_BIN=... sh build.sh`) or Option B's config.

**After installing, flip the extension's toggle to Enabled** — a freshly added
extension is Disabled until you turn it on (and it shows *MCP tools*, never
skills; Claude Desktop can't run skills).
