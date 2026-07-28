# yt-mem-ai integrations — native plugins + MCP

Two ways to reach the engine, per host:

- **Native plugins/extensions** (Claude Code, Codex, Gemini) ship the `yt` /
  `yt-manager` **skills** (+ slash commands). The skills drive the `yt-ai` CLI by
  shelling out — run via `uvx yt-mem-ai <cmd>`, zero-install. This is the
  idiomatic path for each platform; **no MCP involved.**
- **The `yt-ai-mcp` MCP server** (in the package) is for **Claude Desktop** —
  which can't run skills — and for headless / other MCP hosts (Cursor, tool
  runners) that want a typed tool surface. Optional everywhere else.

## Install (interactive)

From a checkout, run the multi-select installer and tick the targets you want:

```
sh integrations/install.sh        # macOS/Linux  (Windows: integrations\install.ps1)
```

You get an **arrow-key checkbox UI** — `↑`/`↓` (or `j`/`k`) to move, **space** to
toggle, `a` to select all detected hosts, **enter** to install, `q` to quit —
so you can tick, e.g., `[x] Claude Desktop (Bundle)` **and** `[x] Codex (MCP)` in
one run. Undetected hosts are dimmed but still selectable. **Already-installed
targets are auto-detected, pre-checked `[x]`, and labeled `(installed)`.** The
picker is a **diff**: tick a new target to install it, **untick an installed one
to remove it** (uninstall), leave it checked to keep it. On enter you get a plan
(`+ install` / `- remove`); any removals require an extra confirm. (Falls back to
a numbered menu on terminals without cursor addressing.) Non-interactive / piped
runs are install-only. Piped:

```
curl -LsSf https://raw.githubusercontent.com/dasein108/yt-mem-ai/main/integrations/install.sh \
  | sh -s -- --claude-desktop=plugin --codex=mcp
```

Flags: `--claude-code=plugin,mcp`, `--claude-desktop=plugin,mcp`,
`--codex=plugin,mcp`, `--gemini=extension,mcp`, `--all-plugins`, `--all-mcp`,
`-y`. The zero-effort path is [`PROMPT.md`](PROMPT.md) — paste it into any agent.

## Host × delivery matrix

| Host | Native plugin (skills + CLI) | MCP (optional) |
|---|---|---|
| **Claude Code** ([docs](claude-code/README.md)) | skills + `/yt-*` commands | `claude mcp add` |
| **Claude Desktop** ([docs](claude-desktop/README.md)) | — (no native skills) | `.mcpb` bundle **or** `claude_desktop_config.json` |
| **Codex** ([docs](codex/README.md)) | `.codex-plugin` skills + prompts + AGENTS.md | `~/.codex/config.toml` server |
| **Gemini CLI** ([docs](gemini/README.md)) | extension: skills + `/yt:*` commands | merge `~/.gemini/settings.json` |

The same `yt` / `yt-manager` **SKILL.md** skills run natively on Claude Code,
Codex (v0.117.0+, `~/.codex/skills/`), and Gemini extensions — and they call the
`yt-ai` CLI via `uvx` (no package or MCP server needed). **Claude Desktop** is
the one host without native skills, so it uses the **MCP** column (its scenarios
come through MCP prompts). The MCP column is also there for anyone who wants the
typed tool surface on the other hosts — it's optional, not required.

## The server itself

See [`mcp/README.md`](mcp/README.md) — tools, scenario prompts, config, and how
to run/inspect `yt-ai-mcp` directly.

## Config / secrets

The server reads `.env` / environment via the engine's `load_config()`. The
installer sets an absolute data dir (`~/.yt-mem-ai/`, override `YT_MEM_AI_HOME`)
so the store doesn't scatter across host working directories. Proxy (Webshare),
Chrome cookies, and embedding backend are all optional `YT_*` / `WEBSHARE_*`
vars — see the repo `.env.example`.
