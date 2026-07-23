---
name: yt-debugger
description: Use when debugging the yt_summary app (empty UI, a hung/failed command, an API/pipeline error). Runs the backend, introspects the API schema via /openapi.json, makes probe calls, and filters the unified logs/common.jsonl with jq to trace an issue across backend/electron/frontend.
---

# yt-debugger

Diagnose yt_summary end-to-end. All runtimes log to `logs/common.jsonl`
(`{ts, source, level, event, msg, ...ctx}`); `source ∈ backend|electron|frontend`.

## 1. Run the backend
```bash
uv run yt-ai serve &        # http://127.0.0.1:8000 ; kill %1 when done
```
Electron is a GUI — launch `npm --prefix frontend run electron:dev` manually if you need it; its
main-process events land in the same log with `source=electron`.

## 2. Understand the API (schema)
```bash
curl -s 127.0.0.1:8000/openapi.json | jq '.paths | keys'
curl -s 127.0.0.1:8000/openapi.json | jq '.paths["/videos/{video_id}"].get'
```

## 3. Probe endpoints
```bash
curl -s 127.0.0.1:8000/status  | jq
curl -s 127.0.0.1:8000/videos  | jq 'length'
curl -s 127.0.0.1:8000/jobs    | jq -c '.[] | {id,kind,status,error}'
```

## 4. Query the unified log with jq
```bash
LOG=logs/common.jsonl
jq -c 'select(.level=="error")' $LOG                      # all errors
jq -c 'select(.source=="electron")' $LOG                  # electron lifecycle (sidecar/api wait)
jq -c 'select(.event|startswith("fetch"))' $LOG           # a fetch's steps
jq -c 'select(.job_id=="<id>")' $LOG                      # one job's full trace
jq -c '{ts,source,event,msg}' $LOG | tail -30            # recent, compact
tail -f $LOG | jq -c '{ts,source,event,msg}'              # live tail
```

## 5. Correlate across runtimes
A failing UI action leaves a `source=frontend` `ui.api_error` line (with `status`/`path`); find the
matching backend `job.*`/`fetch.*` events near the same `ts` to see the server-side cause. If the
last backend line before a hang is e.g. `fetch.download` or a discover/cookie step, that's where it stalled.

## Notes
- The log is append-only JSON Lines; never edit it. Delete/rotate manually if it grows.
- Logging never raises — an absent line means the code path wasn't reached (or errored before logging).
