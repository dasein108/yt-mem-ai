# yt-mem-ai integrations — skills + MCP

Two ways to reach the engine, **one installer** at the repo root:

| | What it installs |
|---|---|
| **Plugin** (recommended) | the `yt` / `yt-agent` [skills](../skills/README.md) per host **+ the `yt-ai` CLI** they shell out to |
| **MCP** | the `yt-ai-mcp` server (typed tools) merged into a host's MCP config |

## Install

```
sh install.sh          # macOS/Linux  (Windows: powershell -File install.ps1)
```

Two steps: **1)** what — a single choice, **Plugin** or **MCP** (run it twice,
or pass `--all-methods`, to get both); **2)** where — tick hosts: Claude Code,
Claude Desktop, Codex, Cursor, Antigravity. `↑`/`↓` (or `j`/`k`) move, **enter** selects/continues; on the host
screen **space** toggles, `a` all, `n` none, `q` quits. Falls back to a numbered
menu without bash/cursor addressing.

Already-installed targets come **pre-ticked**; the second screen is a **diff** —
untick an installed host to remove it. You get a plan (`+ install` / `- remove`)
and removals need an extra confirm. A method you *don't* tick in step 1 is never
touched, so choosing Plugin can't disturb your MCP configs.

Anything that can't be automated prints a **bright warning with the exact manual
steps** — Claude Desktop plugins (account-side), a host whose CLI isn't on PATH,
or a skill file that couldn't be fetched.

Non-interactive (never removes anything):

```
sh install.sh --plugin --codex --cursor
sh install.sh --mcp --claude-desktop
sh install.sh --all                       # every method × every host
curl -LsSf https://raw.githubusercontent.com/dasein108/yt-mem-ai/main/install.sh | sh   # CLI only
```

Flags: `--plugin` `--mcp` `--all-methods` · `--claude-code` `--claude-desktop`
`--codex` `--cursor` `--antigravity` (alias `--gravity`) `--all-hosts` ·
`--all` `-y` `--bootstrap` `-h`. Manual MCP config (any host, no script):
[`mcp/README.md`](mcp/README.md). Manual skills: [`../skills/README.md`](../skills/README.md).
The zero-effort path is [`PROMPT.md`](PROMPT.md) — paste it into any agent.

## Host × delivery matrix

| Host | Plugin (skills) | MCP |
|---|---|---|
| **Claude Code** ([docs](claude-code/README.md)) | plugin → `~/.claude/plugins` (skills + `/yt-*` commands) | `claude mcp add` |
| **Claude Desktop** ([docs](claude-desktop/README.md)) | **in-app only** — Customize → Plugins (account-side, not scriptable) | merge `claude_desktop_config.json` |
| **Codex** ([docs](codex/README.md)) — CLI *and* IDE, shared `~/.codex` | `~/.codex/skills/` + prompts + AGENTS.md | `~/.codex/config.toml` |
| **Cursor** ([docs](cursor/README.md)) | `~/.cursor/skills/` | merge `~/.cursor/mcp.json` |
| **Antigravity** ([docs](antigravity/README.md)) | `~/.gemini/skills/` | merge `~/.gemini/config/mcp_config.json` |

The same `yt` / `yt-agent` **SKILL.md** files run on Claude Code, Codex
(v0.117.0+), Cursor, and Antigravity — see [`../skills/README.md`](../skills/README.md)
for what they do and how to install or paste them **by hand**.

**Claude Desktop is the exception.** Its plugins are stored on your Claude
account, not on disk (`~/.claude/plugins` belongs to Claude Code — Desktop chat
does not read it), so no script can install or uninstall a Desktop plugin.
`install.sh` therefore just prints the in-app steps for that host: Customize →
Plugins → Add marketplace → `github.com/dasein108/yt-mem-ai` → Install. The
scriptable Desktop path is MCP (`sh install.sh --mcp --claude-desktop`).

## The server itself

See [`mcp/README.md`](mcp/README.md) — tools, scenario prompts, config, and how
to run/inspect `yt-ai-mcp` directly.

## Config / secrets

The server reads `.env` / environment via the engine's `load_config()`. The
installer sets an absolute data dir (`~/.yt-mem-ai/`, override `YT_MEM_AI_HOME`)
so the store doesn't scatter across host working directories. Proxy (Webshare),
Chrome cookies, and embedding backend are all optional `YT_*` / `WEBSHARE_*`
vars — see the repo `.env.example`.
