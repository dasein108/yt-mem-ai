# yt-mem-ai integrations — native plugins + MCP

Two ways to reach the engine, per host:

- **Native skills/plugins** (Claude Code, Codex, Cursor, Antigravity) ship the
  `yt` / `yt-manager` **skills** (+ slash commands where the host has them). The
  skills drive the `yt-ai` CLI by shelling out — run via `uvx yt-mem-ai <cmd>`,
  zero-install. This is the idiomatic path for each platform.
- **The `yt-ai-mcp` MCP server** (in the package) is **Claude Desktop's** only
  path (it can't run skills), and an optional typed-tool surface on the other
  hosts (Cursor and Antigravity expose both skills *and* MCP).

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

Flags: `--claude-code=plugin,mcp`, `--claude-desktop=bundle,mcp`,
`--codex=plugin,mcp`, `--cursor=skills,mcp`, `--antigravity=skills,mcp`
(alias `--gravity`), `--all-plugins`, `--all-mcp`, `-y`. The zero-effort path is
[`PROMPT.md`](PROMPT.md) — paste it into any agent.

## Host × delivery matrix

| Host | Native (skills) | MCP |
|---|---|---|
| **Claude Code** ([docs](claude-code/README.md)) | skills + `/yt-*` commands | `claude mcp add` |
| **Claude Desktop** ([docs](claude-desktop/README.md)) | — (no native skills) | `.mcpb` bundle **or** `claude_desktop_config.json` |
| **Codex** ([docs](codex/README.md)) | `~/.codex/skills/` + prompts + AGENTS.md | `~/.codex/config.toml` |
| **Cursor** ([docs](cursor/README.md)) | `~/.cursor/skills/` | merge `~/.cursor/mcp.json` |
| **Antigravity** ([docs](antigravity/README.md)) | `~/.gemini/skills/` | merge `~/.gemini/config/mcp_config.json` |

The same `yt` / `yt-manager` **SKILL.md** skills run natively on Claude Code,
Codex (v0.117.0+), Cursor, and Antigravity — all discovered from each host's
skills directory, all calling the `yt-ai` CLI via `uvx` (no package needed).
**Claude Desktop** is the one host without native skills, so it uses the **MCP**
column. Cursor and Antigravity expose **both** — pick skills, MCP, or both. Any
MCP install uses a fast, pre-installed `yt-ai-mcp` binary (`uv tool install`).

## The server itself

See [`mcp/README.md`](mcp/README.md) — tools, scenario prompts, config, and how
to run/inspect `yt-ai-mcp` directly.

## Config / secrets

The server reads `.env` / environment via the engine's `load_config()`. The
installer sets an absolute data dir (`~/.yt-mem-ai/`, override `YT_MEM_AI_HOME`)
so the store doesn't scatter across host working directories. Proxy (Webshare),
Chrome cookies, and embedding backend are all optional `YT_*` / `WEBSHARE_*`
vars — see the repo `.env.example`.
