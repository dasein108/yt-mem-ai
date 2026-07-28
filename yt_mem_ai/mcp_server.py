# yt_mem_ai/mcp_server.py
"""MCP server exposing the yt-mem-ai engine to any MCP host.

This is a thin protocol adapter over the same `run_*` cores that `cli.py`
exposes — no business logic lives here. Every tool loads config, opens the
LanceDB store, calls the matching core, and returns JSON-serializable data.
Scenario playbooks (summarize / highlights / digest / review / group) ship as
MCP *prompts* assembled from the checked-in SKILL.md files, so hosts that can't
run Claude Code skills (Codex, Gemini, Claude Desktop) still get the workflows.

Run it:  uvx --from 'yt-mem-ai[mcp]' yt-ai-mcp   (stdio transport)
Requires the optional `mcp` dependency: `pip install 'yt-mem-ai[mcp]'`.
"""
from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import cli
from . import settings as settings_mod
from .store import db as store
from .transcript import CaptionsBlocked, TranscriptUnavailable

mcp = FastMCP("yt-mem-ai")


# --------------------------------------------------------------------------- #
# serialization helpers (mirror the CLI `--json` output shapes)
# --------------------------------------------------------------------------- #
def _video_dict(v) -> dict:
    """Full video row, matching `yt-ai list --json`."""
    return {
        "video_id": v.video_id, "title": v.title, "url": v.url,
        "status": v.status, "live_status": v.live_status,
        "channel_id": v.channel_id, "channel": v.channel,
        "published_at": v.published_at, "duration_s": v.duration_s,
        "tags": v.tags, "description": v.description,
    }


def _open(cfg):
    return cli.open_store(cfg)


# --------------------------------------------------------------------------- #
# tools — one per CLI op
# --------------------------------------------------------------------------- #
@mcp.tool()
def fetch(url: str, force: bool = False, captions_only: bool = False,
          whisper: bool = False) -> dict:
    """Download + transcribe + embed + store a single video (idempotent).

    Set captions_only=True for the fast captions-only path (no audio, no
    whisper); on `status: "no_captions"` retry with whisper=True. Streams are
    transcribed on demand here (unlike batch fetch_pending, which skips them).
    Returns {video_id, status}.
    """
    cfg = cli.load_config()
    try:
        vid = cli.run_fetch(url, cfg, force=force, captions_only=captions_only,
                            force_whisper=whisper, include_streams=True)
    except TranscriptUnavailable as exc:
        return {"video_id": None, "status": "no_captions", "message": str(exc)}
    except CaptionsBlocked as exc:
        return {"video_id": None, "status": "captions_blocked", "message": str(exc)}
    return {"video_id": vid, "status": "ok"}


@mcp.tool()
def show(video_id: str) -> dict:
    """Return stored metadata + full transcript for a video (or {error: ...}).

    Includes `transcript_lang` (source language) and any stored `summary`.
    """
    cfg = cli.load_config()
    db = _open(cfg)
    v = store.get_video(db, video_id)
    if not v:
        return {"error": "not found", "video_id": video_id}
    out = _video_dict(v)
    out["transcript"] = store.get_transcript_text(db, video_id) or ""
    out["transcript_lang"] = store.get_transcript_lang(db, video_id)
    out["summary"] = store.get_summary(db, video_id)
    return out


@mcp.tool()
def status() -> dict:
    """Return video counts grouped by lifecycle status."""
    cfg = cli.load_config()
    db = _open(cfg)
    return dict(store.count_by_status(db))


@mcp.tool()
def list_videos(status: str | None = None, since: str | None = None,
                channel: str | None = None, limit: int | None = None) -> list[dict]:
    """List stored videos, optionally filtered by status/date/channel and capped.

    `since` is a YYYY-MM-DD date; `status` is one of
    discovered/downloaded/transcribed/summarized/stream.
    """
    cfg = cli.load_config()
    vids = cli.run_list(cfg, status=status, since=since, channel=channel, limit=limit)
    return [_video_dict(v) for v in vids]


@mcp.tool()
def search(query: str, mode: str = "hybrid", k: int = 10) -> list[dict]:
    """Search transcript chunks. mode = hybrid | vector | fts.

    Use this to anchor highlight timestamps — each hit carries `start_s` and a
    `ts` (MM:SS). Never invent timestamps; take them from a hit whose
    `video_id` matches.
    """
    cfg = cli.load_config()
    hits = cli.run_search(cfg, query, mode=mode, k=k)
    for h in hits:
        h["ts"] = cli._fmt_ts(h.get("start_s", 0.0))
    return hits


@mcp.tool()
def save_summary(video_id: str, summary_md: str, highlights: str = "[]",
                 qa: str = "[]") -> dict:
    """Persist a model-generated summary for a video (marks it 'summarized').

    `highlights` is a JSON array of {start_s, label}; `qa` a JSON array of
    {q, a}. These are strings of JSON, matching the CLI `save-summary` command.
    """
    cfg = cli.load_config()
    cli.run_save_summary(cfg, video_id, summary_md, highlights, qa)
    return {"status": "saved", "video_id": video_id}


@mcp.tool()
def discover(after: str | None = None, deep: bool = False,
             min_duration: int = 120) -> dict:
    """Discover new subscription uploads and store them as 'discovered'.

    Incremental by default (advances a high-water mark); pass `after`
    (YYYY-MM-DD) to override the cutoff. Returns {new_count, videos}.
    """
    cfg = cli.load_config()
    fresh, new_count = cli.run_discover(cfg, after=after, deep=deep,
                                        min_duration=min_duration)
    return {"new_count": new_count, "videos": [_video_dict(v) for v in fresh]}


@mcp.tool()
def fetch_pending(since: str | None = None, limit: int | None = None) -> dict:
    """Batch download + transcribe + embed all pending 'discovered' videos.

    Continues past per-video failures; streams are auto-marked and skipped.
    `since` defaults to today. Returns {ok, failed, results:[{video_id,outcome}]}.
    """
    cfg = cli.load_config()
    results = cli.run_fetch_pending(cfg, since=since, limit=limit)
    ok = sum(1 for _, outcome in results if outcome == "ok")
    return {
        "ok": ok, "failed": len(results) - ok,
        "results": [{"video_id": vid, "outcome": outcome} for vid, outcome in results],
    }


@mcp.tool()
def channel_list(url: str, limit: int = 20, after: str | None = None,
                 before: str | None = None) -> list[dict]:
    """Enumerate a channel's recent uploads (does NOT ingest them).

    `url` is a channel URL or @handle; `after`/`before` are YYYY-MM-DD bounds.
    Feed the returned URLs to `fetch` to ingest a group.
    """
    cfg = cli.load_config()
    vids = cli.run_channel_list(cfg, url, limit=limit, after=after, before=before)
    return [_video_dict(v) for v in vids]


@mcp.tool()
def like(video_id: str) -> dict:
    """Mark a video as liked (feeds taste-based recommendations)."""
    cfg = cli.load_config()
    cli.run_feedback(cfg, video_id, 1)
    return {"status": "liked", "video_id": video_id}


@mcp.tool()
def dislike(video_id: str) -> dict:
    """Mark a video as disliked (feeds taste-based recommendations)."""
    cfg = cli.load_config()
    cli.run_feedback(cfg, video_id, -1)
    return {"status": "disliked", "video_id": video_id}


@mcp.tool()
def recommend(limit: int = 20) -> list[dict]:
    """Rank unrated fetched videos by learned taste (like − dislike centroid)."""
    cfg = cli.load_config()
    db = _open(cfg)
    ranked = cli.run_recommend(cfg, limit=limit, db=db)
    out = []
    for vid, score in ranked:
        v = store.get_video(db, vid)
        if v is None:
            continue
        row = _video_dict(v)
        row["score"] = round(score, 4)
        out.append(row)
    return out


@mcp.tool()
def compile(since: str | None = None, max_minutes: float = 20) -> dict:
    """Compile deep-linked highlights from summarized videos (fast, no download).

    Budget-bounded by `max_minutes`; `since` (YYYY-MM-DD) defaults to today.
    Returns {clips:[{video_id, start_s, ...}]} — each clip has a watch deep link.
    """
    from dataclasses import asdict
    cfg = cli.load_config()
    clips = cli.run_compile(cfg, since=since, max_minutes=max_minutes)
    return {"clips": [asdict(c) for c in clips]}


@mcp.tool()
def supercut(since: str | None = None, max_minutes: float = 20,
             out: str | None = None) -> dict:
    """Render an actual video supercut of highlights (SLOW: re-downloads clips + ffmpeg).

    Needs network + local ffmpeg. `since` defaults to today; output defaults to
    supercuts/<since>.mp4. Returns {out_path, rendered, failed, labeled}.
    """
    cfg = cli.load_config()
    res = cli.run_supercut(cfg, since=since, max_minutes=max_minutes, out=out)
    return {
        "out_path": str(res.out_path), "rendered": len(res.rendered),
        "failed": len(res.failed), "labeled": res.labeled,
    }


@mcp.tool()
def frame(video_id: str, at: str, out: str | None = None) -> dict:
    """Grab a still frame from an ingested video at a timestamp (needs yt-dlp + ffmpeg).

    `at` is seconds or HH:MM:SS. Returns {path}.
    """
    cfg = cli.load_config()
    path = cli.run_frame(cfg, video_id, at, out)
    return {"path": str(path)}


@mcp.tool()
def config_list(reveal: bool = False) -> list[dict]:
    """List every yt-mem-ai setting with its effective value, source, and description.

    Source is env | project | global | default. Secret values (API keys, proxy
    password) are masked unless reveal=True. Use this to see what's configurable
    and what's currently set before changing anything.
    """
    return settings_mod.list_settings(reveal=reveal)


@mcp.tool()
def config_get(key: str, reveal: bool = False) -> dict:
    """Get one setting's effective value and where it comes from (env/project/global/default)."""
    try:
        return settings_mod.get_setting(key, reveal=reveal)
    except settings_mod.UnknownKey:
        return {"error": "unknown setting", "key": key}


@mcp.tool()
def config_set(key: str, value: str, scope: str = "global") -> dict:
    """Set a yt-mem-ai setting (e.g. WEBSHARE_PROXY_USERNAME, YT_EMBEDDING_MODEL).

    Persists to the global config file (`~/.yt-mem-ai/config.env`) by default so
    it applies to this server regardless of working directory; pass scope="project"
    to write ./.env instead. Takes effect on the next tool call (no restart) unless
    the same key is set as a process env var — the returned `warning` flags that.
    Only known keys are accepted (see config_list).
    """
    try:
        return settings_mod.set_setting(key, value, scope=scope)
    except settings_mod.UnknownKey:
        return {"error": "unknown setting", "key": key,
                "hint": "call config_list to see valid keys"}
    except ValueError as exc:
        return {"error": str(exc), "key": key}


@mcp.tool()
def config_unset(key: str, scope: str = "global") -> dict:
    """Remove a setting from the global (or scope="project") config file."""
    try:
        return settings_mod.unset_setting(key, scope=scope)
    except settings_mod.UnknownKey:
        return {"error": "unknown setting", "key": key}


@mcp.tool()
def reembed() -> dict:
    """Rebuild all chunk embeddings with the current YT_EMBEDDING_* config.

    Use after switching embedding backend/model (e.g. to a multilingual one) to
    migrate the library without re-fetching. Returns {reembedded}.
    """
    cfg = cli.load_config()
    return {"reembedded": cli.run_reembed(cfg)}


# --------------------------------------------------------------------------- #
# scenario prompts — assembled from the checked-in SKILL.md playbooks
# --------------------------------------------------------------------------- #
_SKILL_FALLBACK = (
    "Drive the yt-mem-ai MCP tools. Ensure the video is ingested (fetch, "
    "captions→whisper), reuse a stored summary if present, anchor every "
    "highlight timestamp with `search` (never invent one), produce artifacts in "
    "the video's original language, and persist via `save_summary`."
)


def _load_skill(name: str) -> str:
    """Read a checked-in SKILL.md playbook.

    Works from a source checkout (skills/<name>/SKILL.md at the repo root) and
    from an installed wheel (force-included at yt_mem_ai/_skills/<name>.md).
    Falls back to a short inline playbook if neither is found.
    """
    here = Path(__file__).resolve().parent
    candidates = [
        here / "_skills" / f"{name}.md",              # installed wheel
        here.parent / "skills" / name / "SKILL.md",   # source checkout
    ]
    for path in candidates:
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            continue
    return _SKILL_FALLBACK


def _playbook(instruction: str, skill: str = "yt") -> str:
    return (
        f"{instruction}\n\n"
        "All data access goes through the yt-mem-ai MCP tools (fetch, show, "
        "search, list_videos, discover, fetch_pending, channel_list, "
        "save_summary, compile, ...). Follow this playbook:\n\n"
        f"{_load_skill(skill)}"
    )


@mcp.prompt(title="Summarize a YouTube video")
def yt_summarize(video: str) -> str:
    """Summarize one video (URL or id): exec summary + key bullets."""
    return _playbook(
        f"Scenario A (summarize) for: {video}. Produce an executive summary "
        "(2–4 sentences) plus key bullets, and persist it with save_summary.")


@mcp.prompt(title="Highlight a YouTube video")
def yt_highlights(video: str) -> str:
    """Extract timestamped, deep-linked highlights for one video."""
    return _playbook(
        f"Scenario A (highlights) for: {video}. Produce 3–8 highlights as "
        "`MM:SS — label` with watch?v=<id>&t=<start>s deep links; anchor every "
        "timestamp with the search tool.")


@mcp.prompt(title="Q&A over a YouTube video")
def yt_qa(video: str) -> str:
    """Generate a grounded Q&A set for one video."""
    return _playbook(
        f"Scenario A (qa) for: {video}. Produce 3–6 grounded question/answer "
        "pairs, all drawn from the transcript.")


@mcp.prompt(title="Presentation from a YouTube video")
def yt_presentation(video: str) -> str:
    """Build a slide deck (slides/<id>.md) from one video."""
    return _playbook(
        f"Scenario A (presentation) for: {video}. Write a `---`-separated slide "
        "deck to slides/<video_id>.md (title, one slide per theme with a quote "
        "+ MM:SS, takeaways + watch link).")


@mcp.prompt(title="Daily subscriptions digest")
def yt_digest(date: str = "") -> str:
    """Process the latest subscription uploads into digests/<DATE>.md."""
    day = f" for {date}" if date else ""
    return _playbook(
        f"Scenario B (daily digest){day}. Run discover + fetch_pending, analyze "
        "each of the day's transcribed videos, and compose digests/<DATE>.md "
        "(executive digest + one section per video).")


@mcp.prompt(title="Cross-video subscriptions review")
def yt_review(since: str = "") -> str:
    """Write a cross-video themes essay to reviews/<DATE>.md."""
    window = f" since {since}" if since else ""
    return _playbook(
        f"Scenario C (subscriptions review){window}. Write ONE cross-video "
        "essay to reviews/<DATE>.md — common threads, contradictions, trends — "
        "no per-video sections; cite specific moments with title + MM:SS links.")


@mcp.prompt(title="Analyze a group of videos")
def yt_group(videos: str) -> str:
    """Ingest + analyze an arbitrary set → groups/<label>.md."""
    return _playbook(
        f"Scenario D (group) for: {videos}. Resolve the set (comma list of "
        "ids/URLs, a channel via channel_list, or a date range), ingest each, "
        "run per-video analysis, then write groups/<label>.md (executive "
        "synthesis + one section per video).")


def main() -> None:
    """Console entry point (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
