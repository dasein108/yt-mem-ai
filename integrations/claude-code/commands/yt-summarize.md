---
description: Summarize a YouTube video (exec summary + key bullets), grounded in the transcript.
argument-hint: <url-or-video-id>
---

Use the **yt-agent** skill, scenario A (summarize), for: $ARGUMENTS

Ensure the video is ingested (captions → whisper), reuse a stored summary if
present, and persist the result with `save-summary`. Produce the artifact in the
video's original language.
