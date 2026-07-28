# yt-mem-ai — Claude Code plugin

Bundles the `yt` and `yt-manager` skills, the `/yt-*` slash commands, and the
`yt-ai-mcp` tool server into one installable Claude Code plugin.

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

The interactive installer does this for you: `integrations/install.sh` →
select **Claude Code (Plugin)**.

## What you get

- **Skills**: `yt`, `yt-manager` (the full scenario playbooks).
- **Commands**: `/yt-summarize`, `/yt-highlights`, `/yt-qa`, `/yt-presentation`,
  `/yt-digest`, `/yt-review`, `/yt-group`.
- **MCP tools** (`yt-mem-ai` server): `fetch`, `show`, `status`, `list_videos`,
  `search`, `save_summary`, `discover`, `fetch_pending`, `channel_list`, `like`,
  `dislike`, `recommend`, `compile`, `supercut`, `frame`, `reembed`, and the
  config tools `config_list`, `config_get`, `config_set`, `config_unset`.

## MCP-only (no plugin)

If you just want the tools without the skills/commands:

```
claude mcp add yt-mem-ai -- uvx --from 'yt-mem-ai[mcp]' yt-ai-mcp
```

## Config

The server reads `.env`/env vars via `load_config()`. The bundled `.mcp.json`
sets an absolute store under `~/.yt-mem-ai/` so data doesn't scatter across the
host's working directory. Override any `YT_*` / `WEBSHARE_*` / cookie var in the
`env` block or your shell. See the repo `.env.example`.

**Reconfigure from chat** — ask Claude to set anything and it uses the `config_*`
tools (no file editing): e.g. "set my Webshare proxy login", "switch to the
multilingual embedding model". `config_set` persists to `~/.yt-mem-ai/config.env`
and takes effect on the next call; `config_list` shows every setting and its
source. Equivalent CLI: `yt-ai config set/get/list`.
