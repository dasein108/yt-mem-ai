# yt-mem-ai integrations — MCP + host plugins

One MCP server (`yt-ai-mcp`, in the `yt-mem-ai` package) exposes the whole engine
to every major agentic host. Everything here is a thin wrapper around it.

## Install (interactive)

From a checkout, run the multi-select installer and tick the targets you want:

```
sh integrations/install.sh        # macOS/Linux  (Windows: integrations\install.ps1)
```

You get an **arrow-key checkbox UI** — `↑`/`↓` (or `j`/`k`) to move, **space** to
toggle, `a` to select all detected hosts, **enter** to install, `q` to quit —
so you can tick, e.g., `[x] Claude Desktop (Bundle)` **and** `[x] Codex (MCP)` in
one run. Undetected hosts are dimmed but still selectable. **Already-installed
targets are auto-detected, pre-checked `[x]`, and labeled `(installed)`** — untick
to skip them, or just add new ones (re-installing is idempotent). (Falls back to a
numbered menu on terminals without cursor addressing.) Non-interactive / piped:

```
curl -LsSf https://raw.githubusercontent.com/dasein108/yt-mem-ai/main/integrations/install.sh \
  | sh -s -- --claude-desktop=plugin --codex=mcp
```

Flags: `--claude-code=plugin,mcp`, `--claude-desktop=plugin,mcp`,
`--codex=plugin,mcp`, `--gemini=extension,mcp`, `--all-plugins`, `--all-mcp`,
`-y`. The zero-effort path is [`PROMPT.md`](PROMPT.md) — paste it into any agent.

## Host × delivery matrix

| Host | Plugin-style | MCP-only |
|---|---|---|
| **Claude Code** ([docs](claude-code/README.md)) | skills + `/yt-*` commands + MCP | `claude mcp add` |
| **Claude Desktop** ([docs](claude-desktop/README.md)) | `.mcpb` bundle (double-click) | merge `claude_desktop_config.json` |
| **Codex** ([docs](codex/README.md)) | `.codex-plugin` (skills + MCP) + prompts + AGENTS.md | `~/.codex/config.toml` server |
| **Gemini CLI** ([docs](gemini/README.md)) | extension (skills + MCP + `/yt:*` commands) | merge `~/.gemini/settings.json` |

The same `yt` / `yt-manager` **SKILL.md** skills run natively on Claude Code,
Codex (v0.117.0+, `~/.codex/skills/`), and Gemini extensions — so each plugin
delivers the real scenarios, not just prompts. **Claude Desktop** is the one host
without native skills (it only loads MCP), so its "plugin" is the `.mcpb` bundle
and scenarios there come through MCP prompts.

## The server itself

See [`mcp/README.md`](mcp/README.md) — tools, scenario prompts, config, and how
to run/inspect `yt-ai-mcp` directly.

## Config / secrets

The server reads `.env` / environment via the engine's `load_config()`. The
installer sets an absolute data dir (`~/.yt-mem-ai/`, override `YT_MEM_AI_HOME`)
so the store doesn't scatter across host working directories. Proxy (Webshare),
Chrome cookies, and embedding backend are all optional `YT_*` / `WEBSHARE_*`
vars — see the repo `.env.example`.
