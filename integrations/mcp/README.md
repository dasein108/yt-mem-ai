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

**`analyze_video(url)`** — the one-step entry point: ingest a video and return
its transcript so the model can summarize / highlight / Q&A it. This is what a
host like Claude Desktop calls on "summarize this video."

Plus the granular ops: `fetch`, `show`, `status`, `list_videos`, `search`,
`save_summary`, `discover`, `fetch_pending`, `channel_list`, `like`, `dislike`,
`recommend`, `compile`, `supercut`, `frame`, `reembed`, and the config tools
`config_list`, `config_get`, `config_set`, `config_unset`.

## Server instructions (the "skill" for MCP hosts)

The server sends an `instructions` string on connect that MCP clients (Claude
Desktop, Cursor, …) inject into the model's context — telling it *when* to reach
for these tools and the ingest→transcript→summarize→save workflow. This is why a
plain "summarize this YouTube video" actually triggers the tools on hosts that
can't run a SKILL.md skill.

## Reconfigure from chat

Any agent can read and change settings live via the config tools — e.g. set the
Webshare proxy login, switch the embedding model, or point at a cookies browser:

```
config_set("WEBSHARE_PROXY_USERNAME", "…")     # + WEBSHARE_PROXY_PASSWORD
config_set("YT_EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
config_list()                                   # see every key, value, source
```

`config_set` writes the global config file (`~/.yt-mem-ai/config.env`) by default
and takes effect on the next tool call (no restart). It only accepts known keys
(the `.env` variables); secrets are masked in output unless `reveal=true`. If a
key is also set as a process env var in the host config, that wins — `config_set`
returns a `warning` saying so. Equivalent CLI: `yt-ai config set/get/list/unset`.

## Prompts (scenarios)

`yt_summarize`, `yt_highlights`, `yt_qa`, `yt_presentation`, `yt_digest`,
`yt_review`, `yt_group` — assembled from the checked-in `skills/yt` and
`skills/yt-agent` playbooks, so hosts without Claude Code skills still get the
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
