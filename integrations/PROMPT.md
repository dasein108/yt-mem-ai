# Zero-effort install prompt

Paste this into any coding agent (Claude Code, Codex, Gemini, Cursor, …) and it
will download and wire up yt-mem-ai for the host(s) you name — no manual steps.

---

Install the **yt-mem-ai** YouTube AI engine for me. It ships an MCP server
(`yt-ai-mcp`) plus host plugins. Do this:

1. Run the installer, selecting the targets I want (edit the flags):

   **macOS/Linux:**
   ```
   curl -LsSf https://raw.githubusercontent.com/dasein108/yt-mem-ai/main/integrations/install.sh \
     | sh -s -- --claude-desktop=plugin --codex=mcp
   ```

   **Windows (PowerShell):**
   ```
   irm https://raw.githubusercontent.com/dasein108/yt-mem-ai/main/integrations/install.ps1 \
     | iex; # then re-run install.ps1 with -ClaudeDesktop plugin -Codex mcp
   ```

   Valid flags (mix freely): `--claude-code=plugin,mcp`,
   `--claude-desktop=plugin,mcp`, `--codex=plugin,mcp`, `--gemini=extension,mcp`,
   `--all-plugins`, `--all-mcp`.

2. If a step prints an in-app command (Claude Code's `/plugin marketplace add …`
   / `/plugin install …`), run it for me in that host.

3. Confirm the `yt-mem-ai` MCP tools (`fetch`, `search`, `discover`, …) are
   available, then stop — don't ingest anything yet.

Targets I want: **<edit here, e.g. Claude Desktop as a plugin + Codex as MCP>**.

---

> The installer needs `uv`/`uvx` (it installs uv automatically) and, for the
> Claude Desktop bundle, the `mcpb` CLI (`npm i -g @anthropic-ai/mcpb`). It
> stores data under `~/.yt-mem-ai/` (override with `YT_MEM_AI_HOME`).
