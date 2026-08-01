# yt-mem-ai skills — canonical playbooks

Two skills, checked in here as the single source of truth. Every host
integration (Claude Code plugin, Codex, Cursor, Antigravity) installs *these
files*; the MCP server serves the same text as prompts.

| Skill | What it does |
|---|---|
| [`yt/SKILL.md`](yt/SKILL.md) | the entry point — any `yt-ai` operation + full pipelines (daily routine, single video) |
| [`yt-agent/SKILL.md`](yt-agent/SKILL.md) | scenarios — one video → summary / highlights / Q&A / presentation; subscriptions → daily digest; cross-video review; arbitrary video group |

Both drive the `yt-ai` CLI by shelling out (`uvx yt-mem-ai <cmd>`, or `yt-ai
<cmd>` if installed). They never touch the LanceDB store directly.

## Automatic install

```bash
sh install.sh --plugin        # skills + the yt-ai CLI (add hosts, or run bare for the wizard)
```

## Manual install (any host that loads SKILL.md files)

Copy the two directories into the host's skills folder:

```bash
# Claude Code (project scope)     → .claude/skills/
# Claude Code (user scope)        → ~/.claude/skills/
# Codex (v0.117.0+)               → ~/.codex/skills/
# Cursor                          → ~/.cursor/skills/
# Antigravity                     → ~/.gemini/skills/
# OpenClaw                        → ~/.agents/skills/
# Hermes                          → ~/.hermes/skills/
cp -R skills/yt skills/yt-agent ~/.codex/skills/

# or without a checkout:
mkdir -p ~/.cursor/skills/yt ~/.cursor/skills/yt-agent
curl -LsSf https://raw.githubusercontent.com/dasein108/yt-mem-ai/main/skills/yt/SKILL.md \
  -o ~/.cursor/skills/yt/SKILL.md
curl -LsSf https://raw.githubusercontent.com/dasein108/yt-mem-ai/main/skills/yt-agent/SKILL.md \
  -o ~/.cursor/skills/yt-agent/SKILL.md
```

The CLI must be reachable: `uv tool install yt-mem-ai` (gives `yt-ai`) or just
have `uvx` on PATH (the skills fall back to `uvx yt-mem-ai <cmd>`).

Restart / reload the host, then ask in plain language:

```
summarize 'https://youtu.be/…'
highlights for 'https://youtu.be/…'
process my subscriptions into today's digest
```

## No-skill-support host? Paste it

Any LLM chat can run these playbooks — paste the contents of `yt/SKILL.md` into
the conversation and state the request. The steps are plain CLI calls
(`yt-ai fetch`, `yt-ai show --json`, `yt-ai search`, `yt-ai save-summary`), so a
model with shell access can follow them verbatim.

Hosts that speak MCP get the same playbooks as **prompts** (`yt_summarize`,
`yt_highlights`, `yt_qa`, `yt_presentation`, `yt_digest`, `yt_review`,
`yt_group`) — see [`../integrations/mcp/README.md`](../integrations/mcp/README.md).

## Where artifacts land

`summaries/`, `digests/<DATE>.md`, `reviews/<DATE>.md`, `slides/<id>.md`,
`groups/<label>.md` in the working directory; summaries are also persisted into
the store via `yt-ai save-summary` so `compile` / `supercut` can use them.
Artifacts keep each video's original language unless you ask for a translation.
