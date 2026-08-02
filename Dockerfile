# Runs the yt-ai-mcp MCP server over stdio.
#
# Used by registries (e.g. Glama) that verify a server starts and answers
# introspection, and usable directly:
#   docker build -t yt-mem-ai .
#   docker run -i --rm -v yt-mem-ai:/data yt-mem-ai
#
# The library lives in the /data volume, so it survives container restarts.
FROM python:3.12-slim

# yt-dlp needs ffmpeg for audio extraction; the Whisper fallback needs it too.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY yt_mem_ai ./yt_mem_ai
COPY skills ./skills

# hatch-vcs derives the version from git, which isn't in the image — pin it so
# the build doesn't need the repo history.
ENV SETUPTOOLS_SCM_PRETEND_VERSION=0.0.0 \
    HATCH_VCS_PRETEND_VERSION=0.0.0 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir '.[mcp]'

ENV YT_MEM_AI_HOME=/data \
    YT_STORE_PATH=/data/lance \
    YT_LOG_FILE=/data/logs/common.jsonl \
    YT_DOWNLOADS_DIR=/data/downloads
VOLUME /data

ENTRYPOINT ["yt-ai-mcp"]
