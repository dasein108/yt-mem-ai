# Configurable embeddings + `reembed` migration

**Date:** 2026-07-26 · **Repo:** engine `yt-mem-ai`

## Purpose

Let the user choose the embedding provider/model (local sentence-transformers or
OpenAI) — notably a **multilingual** model so semantic search works on non-English
(e.g. Russian) transcripts — and migrate an existing library to a new model
**without re-fetching**, via a `yt-ai reembed` command.

OpenRouter is intentionally out of scope: it is a chat-completions gateway with no
`/embeddings` endpoint.

## Current state

`build_embedder(cfg)` already supports two backends via LanceDB's embedding registry:
- `local` → `sentence-transformers`, default `all-MiniLM-L6-v2` (English-centric, 384-d).
- `openai` → default `text-embedding-3-small`, requires `OPENAI_API_KEY`.

Config keys exist: `YT_EMBEDDING_BACKEND` (`local|openai`), `YT_EMBEDDING_MODEL`,
`OPENAI_API_KEY`, `HF_TOKEN`. The gap is (a) polish/validation/docs and (b) a
migration path when the model changes (existing chunks are in the old vector space).

## Providers (polish `build_embedder`)

- Keep `local` and `openai`. No new backend.
- **Validation:** on an unknown `embedding_backend`, raise a clear `ValueError`
  (already does). For `openai` without a key, raise a clear message (already does).
- **Docs:** README + `.env.example` document both backends and recommend
  `paraphrase-multilingual-MiniLM-L12-v2` (local, 384-d, 50+ languages) for
  non-English libraries, and `text-embedding-3-large` (openai) for quality.
- No code change to the two backends beyond keeping the current behavior; the
  feature's substance is the `reembed` command + docs.

## `yt-ai reembed` command

Rebuild the `chunks` table with the **current config's** embedder, re-embedding
existing chunk text (keeps chunk spans; does not re-chunk — raw segments aren't
persisted, only chunk rows are).

- **Core:** `run_reembed(cfg, db=None) -> int` (returns chunks re-embedded).
  1. Read all rows from the `chunks` table: `id, video_id, start_s, end_s, text`.
  2. Build the new embedder: `build_embedder(cfg)`.
  3. `store.rebuild_chunks(db, embedder, rows)` — drop the `chunks` table, recreate
     it with `chunk_schema(embedder)` (new vector dim), insert the rows (text is the
     embedder's SourceField → auto re-embedded), and rebuild the chunks FTS index.
  4. Return the row count.
- **Command:** `@app.command() def reembed()` → `load_config()`, prints
  `"re-embedded <N> chunks with <backend>:<model>"`. On a zero-chunk store, prints
  `"no chunks to re-embed"` and exits 0.
- **Store helper:** `rebuild_chunks(db, embedder, rows: list[dict]) -> None` in
  `store/db.py`, mirroring `replace_chunks`/`init_db`'s table handling (drop +
  create + insert + `_ensure_fts`).

## Data flow

```
(user edits .env: YT_EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2)
yt-ai reembed
  → read all chunks (text + spans) from the old table
  → build_embedder(cfg)  # new model
  → drop+recreate chunks table @ new dim; insert rows → auto-embed; rebuild FTS
  → "re-embedded 1234 chunks with local:paraphrase-multilingual-MiniLM-L12-v2"
```

## Error handling

| Case | Behavior |
|---|---|
| unknown `embedding_backend` | `ValueError` (clear) at `build_embedder` |
| `openai` backend, no key | `ValueError` naming `OPENAI_API_KEY` |
| empty `chunks` table | print "no chunks to re-embed", exit 0 (no-op) |
| model download / API failure | propagates; the old table was already dropped only after the new one is built — rebuild is drop-then-recreate, so do the recreate defensively (build new table before dropping old, or recreate under the same name atomically per LanceDB semantics) |

Note: recreating the same-named `chunks` table with a changed schema — follow
`init_db`'s pattern (LanceDB `create_table` with a fresh schema after drop). Guard
so a failure mid-rebuild leaves a recoverable state (re-running `reembed` fixes it).

## Testing (offline, `tests/test_embeddings.py` + `tests/test_cli.py`)

- `build_embedder`: local default, openai-without-key raises, unknown backend raises.
- `rebuild_chunks` (db test): seed chunks with `FakeEmbedder` (dim A), rebuild with a
  **second fake embedder at dim B**, assert the chunks table now has dim-B vectors,
  same row count, same text/spans, and FTS still queryable.
- `run_reembed`: returns the chunk count; zero-chunk store → 0; uses the injected db.
- All offline via the registered fake embedders (no network, no model download).

## Scope / non-goals

Engine only. Non-goals: OpenRouter embeddings (infeasible), re-chunking (needs raw
segments, not persisted), automatic re-embed on config change (explicit command only),
per-video reembed (whole-store rebuild only — the table's embedder is global).
