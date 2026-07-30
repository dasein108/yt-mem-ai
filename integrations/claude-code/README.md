# yt-mem-ai — Claude Code plugin

A native Claude Code plugin: the `yt` and `yt-agent` **skills** + `/yt-*` slash
commands. The skills drive the `yt-ai` CLI by shelling out (`uvx yt-mem-ai …`,
zero-install) — **no MCP server involved**. If you'd rather have MCP tools, see
*MCP-only* below; the two are independent.

## Install

From this repo (local marketplace):

```
/plugin marketplace add ./integrations/claude-code
/plugin install yt-mem-ai@yt-mem-ai
```

Or from GitHub once pushed:

```
/plugin marketplace add dasein108/yt-mem-ai
/plugin install yt-mem-ai@yt-mem-ai
```

The installer does this for you via the `claude` CLI:
`sh install.sh --plugin --claude-code` runs
`claude plugin marketplace add … && claude plugin install yt-mem-ai@yt-mem-ai`,
installing into `~/.claude/plugins`. That store is **Claude Code's only** —
Claude Desktop keeps its plugins on your Claude account, so add it there
separately via Customize → Plugins (see
[`../claude-desktop/README.md`](../claude-desktop/README.md)).

## What you get

- **Skills**: `yt`, `yt-agent` (the full scenario playbooks).
- **Commands**: `/yt-summarize`, `/yt-highlights`, `/yt-qa`, `/yt-presentation`,
  `/yt-digest`, `/yt-review`, `/yt-group`.

The skills run every operation through the `yt-ai` CLI via `uvx` — so you need
`uv`/`uvx` on PATH (the installer bootstraps it), but **no package install and no
MCP server**.

## MCP-only (optional, independent)

If you want the typed MCP tool surface instead of (or alongside) the skills:

```
claude mcp add yt-mem-ai -- uvx --from 'yt-mem-ai[mcp]' yt-ai-mcp
```

(installer → **Claude Code (MCP only)**). That's a separate wiring — the plugin
itself no longer bundles MCP.

## Config

Reconfigure from chat with the CLI — `yt-ai config set KEY VALUE` /
`yt-ai config list` (e.g. "set my Webshare proxy login", "switch to the
multilingual embedding model"). Values persist to `~/.yt-mem-ai/config.env` and
take effect on the next call; secrets are masked. See the repo `.env.example`.
(If you added the MCP server, the equivalent `config_*` tools are available too.)
