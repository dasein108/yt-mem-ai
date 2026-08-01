# Zero-effort install prompt

Paste this into any coding agent (Claude Code, Codex, Cursor, Antigravity, …) and
it will download and wire up yt-mem-ai for the host(s) you name — no manual steps.

---

Install the **yt-mem-ai** YouTube AI engine for me. One installer at the repo
root (`install.sh`) does both deliveries: `--plugin` = the `yt` / `yt-agent`
**skills** + the `yt-ai` CLI, `--mcp` = the **`yt-ai-mcp` server**. Do this:

1. Download the installer and run it with what I asked for:

   **macOS/Linux:**
   ```
   curl -LsSf https://raw.githubusercontent.com/dasein108/yt-mem-ai/main/install.sh -o /tmp/yt-install.sh
   sh /tmp/yt-install.sh --plugin --codex --cursor      # skills
   sh /tmp/yt-install.sh --mcp --claude-desktop         # MCP server
   ```

   **Windows (PowerShell):** download `install.ps1` from the same repo root and
   run it with switches, e.g. `-Plugin -Codex -Cursor` / `-Mcp -ClaudeDesktop`.

   Methods: `--plugin`, `--mcp`. Hosts: `--claude-code`, `--claude-desktop`,
   `--codex` (CLI + IDE), `--cursor`, `--antigravity`, `--openclaw`, `--hermes`.
   Also `--all`, `-y`.
   Run it with no flags in a terminal for the two-step wizard.

2. If a step prints in-app instructions — Claude Code's `/plugin marketplace add
   …` / `/plugin install …`, or Claude Desktop's Customize → Plugins flow — run
   or relay them for me. Claude Desktop plugins are account-side and cannot be
   scripted; its scriptable path is `install.sh --mcp --claude-desktop`.

3. Confirm the result: skills → the host lists `yt` / `yt-agent`; MCP → the
   `yt-mem-ai` tools (`fetch`, `search`, `discover`, …) are available. Then stop
   — don't ingest anything yet.

Targets I want: **<edit here, e.g. skills for Codex + MCP for Claude Desktop>**.

---

> The installers need `uv`/`uvx` (they install uv automatically) and store data
> under `~/.yt-mem-ai/` (override with `YT_MEM_AI_HOME`). To wire skills up by
> hand instead, see `skills/README.md`; for a manual MCP config entry, see
> `integrations/mcp/README.md`.
