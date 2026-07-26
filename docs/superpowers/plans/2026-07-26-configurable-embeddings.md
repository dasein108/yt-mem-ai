# Configurable embeddings + `reembed` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `yt-ai reembed` command that re-embeds the whole `chunks` table with the current embedding config, so the user can switch models (e.g. to a multilingual one) without re-fetching. Formalize the local/OpenAI backends via docs.

**Architecture:** A store helper `rebuild_chunks(db, embedder, rows)` drops + recreates the `chunks` table with a new embedder (new vector dim) and re-inserts existing chunk text (auto re-embedded) + rebuilds FTS. A thin CLI `reembed` command over a testable `run_reembed(cfg, db)` core. Offline-testable via two fake embedders at different dims.

**Tech Stack:** LanceDB embedding registry, sentence-transformers/OpenAI backends, Typer, pytest with registered fake embedders.

## Global Constraints

- Engine repo `yt-mem-ai` (package `yt_mem_ai`) only.
- No new embedding backend — keep `local` + `openai`; OpenRouter is out of scope.
- `reembed` re-embeds existing chunk rows (keeps `id/video_id/start_s/end_s/text`); it does NOT re-chunk (raw segments aren't persisted).
- Tests are offline via registered fake embedders — no network, no model downloads.
- The `chunks` table's embedder is global (per-store), so `reembed` rebuilds the whole table, not per-video.

---

## Task 1: store layer — `all_chunks` + `rebuild_chunks`

**Files:**
- Modify: `yt_mem_ai/store/db.py`
- Modify: `tests/support.py` (add a second fake embedder at a different dim)
- Test: `tests/test_db.py`

**Interfaces:**
- Produces:
  - `all_chunks(db) -> list[dict]` — every chunk row as `{id, video_id, start_s, end_s, text}` (no vector).
  - `rebuild_chunks(db, embedder, rows: list[dict]) -> None` — drop + recreate the `chunks` table with `chunk_schema(embedder)`, insert rows (text auto-embeds), rebuild FTS.
  - `tests/support.py`: `fake_embedder_16()` (registered `"fake16"`, `ndims()==16`).

- [ ] **Step 1: Add the second fake embedder to `tests/support.py`**

Append to `tests/support.py`:
```python
@register("fake16")
class FakeEmbedder16(TextEmbeddingFunction):
    def generate_embeddings(self, texts):
        return [self._vec(t) for t in texts]

    def ndims(self) -> int:
        return 16

    def _vec(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [digest[i % len(digest)] / 255.0 for i in range(16)]


def fake_embedder_16():
    return get_registry().get("fake16").create()
```

- [ ] **Step 2: Write the failing db test**

Append to `tests/test_db.py`:
```python
def test_rebuild_chunks_reembeds_at_new_dim(tmp_path):
    from tests.support import fake_embedder_16
    conn = _db(tmp_path)  # init_db with the dim-8 fake embedder
    # seed chunks for two videos via the existing dim-8 path
    from yt_mem_ai.store.embeddings import chunk_segments
    from yt_mem_ai.store.models import Segment
    for vid in ("v1", "v2"):
        rows = chunk_segments(vid, [Segment(vid, 0.0, 5.0, f"hello {vid}"),
                                    Segment(vid, 5.0, 10.0, f"world {vid}")], 3.0)
        store.replace_chunks(conn, vid, rows)
    before = store.all_chunks(conn)
    assert len(before) >= 2
    assert len(before[0]["vector"]) if "vector" in before[0] else True  # all_chunks strips vector
    assert set(before[0]) == {"id", "video_id", "start_s", "end_s", "text"}

    # rebuild with a dim-16 embedder
    store.rebuild_chunks(conn, fake_embedder_16(), before)
    tbl = conn.open_table("chunks")
    rows = tbl.search().limit(1000).to_list()
    assert len(rows) == len(before)                      # same count
    assert len(rows[0]["vector"]) == 16                  # new dim
    assert {r["text"] for r in rows} == {r["text"] for r in before}  # same text
    # FTS still works
    hits = tbl.search("hello", query_type="fts").limit(5).to_list()
    assert any("hello" in h["text"] for h in hits)
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest tests/test_db.py -q -k rebuild_chunks`
Expected: FAIL — `AttributeError: module 'yt_mem_ai.store.db' has no attribute 'all_chunks'`.

- [ ] **Step 4: Implement `all_chunks` + `rebuild_chunks`**

In `yt_mem_ai/store/db.py`, add after `list_chunks`:
```python
_CHUNK_FIELDS = ("id", "video_id", "start_s", "end_s", "text")


def all_chunks(db: lancedb.DBConnection) -> list[dict]:
    """Every chunk row as {id, video_id, start_s, end_s, text} (vector stripped)."""
    tbl = db.open_table("chunks")
    rows = tbl.search().limit(100_000_000).to_list()
    return [{k: r[k] for k in _CHUNK_FIELDS} for r in rows]


def rebuild_chunks(db: lancedb.DBConnection, embedder, rows: list[dict]) -> None:
    """Drop + recreate the chunks table with `embedder` and re-insert `rows`
    (text is the embedder's SourceField → auto re-embedded). Rebuilds FTS."""
    if "chunks" in db.table_names():
        db.drop_table("chunks")
    tbl = db.create_table("chunks", schema=chunk_schema(embedder))
    if rows:
        clean = [{k: r[k] for k in _CHUNK_FIELDS} for r in rows]
        tbl.add(clean)
        _ensure_fts(tbl, "text")
```
(`chunk_schema` is already imported at the top of `db.py`.)

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/test_db.py -q -k rebuild_chunks`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add yt_mem_ai/store/db.py tests/support.py tests/test_db.py
git commit -m "feat(store): all_chunks + rebuild_chunks (re-embed whole chunks table at a new dim)"
```

---

## Task 2: CLI — `run_reembed` + `reembed` command

**Files:**
- Modify: `yt_mem_ai/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `store.all_chunks`, `store.rebuild_chunks` (Task 1); `build_embedder`, `open_store`, `load_config` (cli.py).
- Produces: `run_reembed(cfg, db=None) -> int`; a Typer `reembed` command.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:
```python
def test_run_reembed_rebuilds_with_current_embedder(tmp_path, monkeypatch):
    from yt_mem_ai import cli
    from yt_mem_ai.store.models import Segment
    from yt_mem_ai.store.embeddings import chunk_segments
    from tests.support import fake_embedder_16
    cfg = _cfg(tmp_path)
    conn = _db(tmp_path)
    rows = chunk_segments("v1", [Segment("v1", 0.0, 5.0, "alpha"),
                                 Segment("v1", 5.0, 10.0, "beta")], 3.0)
    store.replace_chunks(conn, "v1", rows)
    # force the "current" embedder to the dim-16 fake
    monkeypatch.setattr(cli, "build_embedder", lambda c: fake_embedder_16())
    n = cli.run_reembed(cfg, db=conn)
    assert n == len(rows) and n >= 1
    got = conn.open_table("chunks").search().limit(100).to_list()
    assert len(got[0]["vector"]) == 16


def test_run_reembed_empty_store_returns_zero(tmp_path, monkeypatch):
    from yt_mem_ai import cli
    from tests.support import fake_embedder_16
    monkeypatch.setattr(cli, "build_embedder", lambda c: fake_embedder_16())
    conn = _db(tmp_path)  # no chunks added
    assert cli.run_reembed(_cfg(tmp_path), db=conn) == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_cli.py -q -k run_reembed`
Expected: FAIL — `AttributeError: module 'yt_mem_ai.cli' has no attribute 'run_reembed'`.

- [ ] **Step 3: Implement `run_reembed` + `reembed` command**

In `yt_mem_ai/cli.py`, add (near the other `run_*` cores / commands):
```python
def _embedding_model_name(cfg) -> str:
    if cfg.embedding_model:
        return cfg.embedding_model
    return "all-MiniLM-L6-v2" if cfg.embedding_backend == "local" else "text-embedding-3-small"


def run_reembed(cfg, db=None) -> int:
    if db is None:
        db = open_store(cfg)
    rows = store.all_chunks(db)
    if not rows:
        return 0
    embedder = build_embedder(cfg)
    store.rebuild_chunks(db, embedder, rows)
    return len(rows)


@app.command()
def reembed():
    """Re-embed all stored chunks with the current YT_EMBEDDING_* config.

    Use after changing YT_EMBEDDING_BACKEND / YT_EMBEDDING_MODEL to migrate the
    library to a new model (e.g. a multilingual one) without re-fetching.
    """
    cfg = load_config()
    n = run_reembed(cfg)
    if n == 0:
        typer.echo("no chunks to re-embed")
    else:
        typer.echo(f"re-embedded {n} chunks with {cfg.embedding_backend}:{_embedding_model_name(cfg)}")
```
Note: `run_reembed` calls `build_embedder` as a cli module global so the test's `monkeypatch.setattr(cli, "build_embedder", ...)` intercepts it — `build_embedder` is already imported into cli via `from .store.embeddings import build_embedder, chunk_segments`; keep it that way.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_cli.py -q -k run_reembed`
Expected: PASS.

- [ ] **Step 5: Full suite + lint + help sanity**

Run: `uv run pytest -q && uv run ruff check yt_mem_ai/cli.py yt_mem_ai/store/db.py && uv run yt-ai reembed --help`
Expected: whole suite passes; ruff clean; `reembed --help` shows the command.

- [ ] **Step 6: Commit**

```bash
git add yt_mem_ai/cli.py tests/test_cli.py
git commit -m "feat(cli): add 'reembed' command + run_reembed core"
```

---

## Task 3: Docs — README + `.env.example`

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Document embedding config + reembed in the README**

In `README.md`, add after the Config paragraph (the `Config (.env): ...` block):
```markdown
**Embeddings:** `YT_EMBEDDING_BACKEND=local|openai`. Local uses
sentence-transformers (`YT_EMBEDDING_MODEL`, default `all-MiniLM-L6-v2`) — for
non-English libraries set `paraphrase-multilingual-MiniLM-L12-v2` (384-d, 50+
languages) so semantic search works cross-language. `openai` uses
`text-embedding-3-small|large` (needs `OPENAI_API_KEY`). After changing the model,
run `yt-ai reembed` to migrate the existing library (re-embeds all chunks; no
re-fetch).
```

Also add the command to the README Commands block, after `yt-ai frame ...`:
```
yt-ai reembed                # re-embed all chunks with the current YT_EMBEDDING_* config
```

- [ ] **Step 2: Recommend the multilingual model in `.env.example`**

In `.env.example`, change the embedding-model line to note the multilingual option:
```
YT_EMBEDDING_MODEL=
# local: all-MiniLM-L6-v2 (default, English) | paraphrase-multilingual-MiniLM-L12-v2 (multilingual)
# openai: text-embedding-3-small | text-embedding-3-large   (needs OPENAI_API_KEY + YT_EMBEDDING_BACKEND=openai)
```
(Insert these as comment lines immediately below the existing `YT_EMBEDDING_MODEL=` line; keep `YT_EMBEDDING_MODEL=` empty.)

- [ ] **Step 3: Note reembed in CLAUDE.md**

In `CLAUDE.md`, add a bullet to the `store/` module-map entry (or near it):
```markdown
- `reembed` (CLI) — `run_reembed` rebuilds the `chunks` table with the current
  `build_embedder(cfg)` (via `store.rebuild_chunks`), migrating the library to a
  new embedding model without re-fetching.
```

- [ ] **Step 4: Commit**

```bash
git add README.md .env.example CLAUDE.md
git commit -m "docs: embedding backends + reembed migration"
```

---

## Self-Review notes

- **Coverage:** store rebuild + dim change (T1), CLI core + empty-store (T2), docs (T3). The two-fake-embedder approach proves the re-embed actually changes the vector space (dim 8 → 16), the strongest offline check.
- **Interfaces consistent:** `rebuild_chunks(db, embedder, rows)` and `all_chunks(db)` identical in spec, T1, and T2's caller; `run_reembed` calls `build_embedder`/`store.*` as module globals so tests monkeypatch cleanly.
- **No re-chunk:** `_CHUNK_FIELDS` keeps text+spans only; re-embed reuses chunk text. Documented as a non-goal.
- **FTS:** `rebuild_chunks` calls `_ensure_fts(tbl, "text")` after insert, mirroring `replace_chunks`, so keyword search survives the migration.
