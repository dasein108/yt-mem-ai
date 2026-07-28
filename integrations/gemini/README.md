# yt-mem-ai — Gemini CLI extension

Packages the `yt-ai-mcp` server + `/yt:*` custom commands + `GEMINI.md` context
into a Gemini CLI extension.

## Install

```
gemini extensions install ./integrations/gemini
```

or from GitHub once pushed:

```
gemini extensions install https://github.com/dasein108/yt-mem-ai
```

Restart Gemini CLI to activate. You get:

- **MCP tools** (`yt-mem-ai` server): fetch / show / search / discover / …
- **Skills**: `yt`, `yt-manager` (the native `SKILL.md` scenario playbooks,
  auto-discovered from the extension's `skills/`).
- **Commands**: `/yt:summarize`, `/yt:highlights`, `/yt:digest`, `/yt:group`.
- **Context**: `GEMINI.md`.

## MCP-only

To wire just the tools without the commands/context, merge the `mcpServers`
block from `gemini-extension.json` into `~/.gemini/settings.json`.

The interactive installer does either: `integrations/install.sh` → select
**Gemini (Extension)** or **Gemini (MCP)**.
