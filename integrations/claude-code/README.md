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
  `/yt-digest`, `/yt-review`, `/yt-group`, `/yt-config`, `/yt-setup`.

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

There is **no separate config UI** — settings live in a global config file
(`~/.yt-mem-ai/config.env`) that the plugin reads on every call. You change it
from chat.

**First run: `/yt-setup`** — a short interactive wizard that walks you through
the cookies browser, optional Webshare proxy, and embedding model, then verifies.
Start here. After that, tweak individual settings with `/yt-config` or plain
language (below).

**1. The `/yt-config` command** (discoverable, same in Claude Code and Desktop):

```
/yt-config list                                  # every setting, value, source
/yt-config set WEBSHARE_PROXY_USERNAME <user>    # secrets masked when shown back
/yt-config set WEBSHARE_PROXY_PASSWORD <pass>
/yt-config set YT_USE_WEBSHARE true              # turn the proxy on
/yt-config set YT_COOKIES_BROWSER chrome         # fix the "not a bot" check
/yt-config get YT_EMBEDDING_MODEL
/yt-config unset HF_TOKEN
```

**2. Plain language via the `yt` skill** — no slash command needed. Just ask:

> "set my Webshare proxy login to `<user>` / `<pass>` and turn the proxy on"
> "switch to the multilingual embedding model, then re-embed"
> "which browser is yt-ai pulling cookies from?"

The `yt` skill's *Configure & maintain* flow maps the request to the same
`uvx yt-mem-ai config …` CLI. Only known keys are accepted, choice-constrained
values are validated, and secrets are masked on read (`--reveal` to see them).
Values persist to `~/.yt-mem-ai/config.env` and take effect on the next call.
Full key list: run `/yt-config list` or see the repo `.env.example`.

(If you added the MCP server, the equivalent `config_*` tools are available too.)
