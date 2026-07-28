# yt-mem-ai — Gemini CLI extension

A native Gemini extension: the `yt` / `yt-manager` **skills** + `/yt:*` custom
commands + `GEMINI.md` context. The skills drive the `yt-ai` CLI via `uvx` — no
MCP server bundled.

## Install

```
gemini extensions install ./integrations/gemini
```

or from GitHub once pushed:

```
gemini extensions install https://github.com/dasein108/yt-mem-ai
```

Restart Gemini CLI to activate. You get:

- **Skills**: `yt`, `yt-manager` (native `SKILL.md` playbooks, auto-discovered
  from the extension's `skills/`; they run `uvx yt-mem-ai …`).
- **Commands**: `/yt:summarize`, `/yt:highlights`, `/yt:qa`, `/yt:presentation`,
  `/yt:digest`, `/yt:review`, `/yt:group`.
- **Context**: `GEMINI.md`.

Needs `uv`/`uvx` on PATH so the skills can run the CLI (the installer bootstraps
it).

## MCP-only (optional)

If you want the typed MCP tool surface instead, merge an `mcpServers` entry into
`~/.gemini/settings.json`:

```json
{ "mcpServers": { "yt-mem-ai": {
  "command": "uvx", "args": ["--from", "yt-mem-ai[mcp]", "yt-ai-mcp"] } } }
```

The interactive installer does either: `integrations/install.sh` → select
**Gemini (Extension)** or **Gemini (MCP)**.
