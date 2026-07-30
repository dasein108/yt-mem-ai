---
description: Ingest + analyze an arbitrary set of videos into a group synthesis.
argument-hint: <ids/urls | channel | date range>
---

Use the **yt-agent** skill, scenario D (group), for: $ARGUMENTS

Resolve the set (comma list of ids/URLs, a channel via `channel-list`, or a date
range), ingest each, run per-video analysis, then write `groups/<label>.md`
(executive synthesis + one section per video).
