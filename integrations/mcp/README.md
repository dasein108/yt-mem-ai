# yt-ai-mcp — the raw MCP server

One MCP server (`yt_mem_ai/mcp_server.py`) exposes the whole engine to any
MCP-capable host. Everything under `integrations/` is a thin wrapper around it.

## Run it

```
uvx --from 'yt-mem-ai[mcp]' yt-ai-mcp          # stdio transport
# or, from a source checkout:
uv run --extra mcp yt-ai-mcp
```

## Generic MCP config

Any host that speaks MCP over stdio:

```json
{
  "mcpServers": {
    "yt-mem-ai": {
      "command": "uvx",
      "args": ["--from", "yt-mem-ai[mcp]", "yt-ai-mcp"],
      "env": { "YT_STORE_PATH": "/absolute/path/to/.yt-mem-ai/lance" }
    }
  }
}
```

## Tools

`fetch`, `show`, `status`, `list_videos`, `search`, `save_summary`, `discover`,
`fetch_pending`, `channel_list`, `like`, `dislike`, `recommend`, `compile`,
`supercut`, `frame`, `reembed`.

## Prompts (scenarios)

`yt_summarize`, `yt_highlights`, `yt_qa`, `yt_presentation`, `yt_digest`,
`yt_review`, `yt_group` — assembled from the checked-in `skills/yt` and
`skills/yt-manager` playbooks, so hosts without Claude Code skills still get the
full workflows.

## Config / secrets

The server reads `.env` / environment via `load_config()` (proxy, cookies,
embedding backend, store path). Set an absolute `YT_STORE_PATH` so the store
doesn't scatter across whatever directory the host launches the server in. See
the repo `.env.example` for every variable.

## Inspect

```
npx @modelcontextprotocol/inspector uvx --from 'yt-mem-ai[mcp]' yt-ai-mcp
```
