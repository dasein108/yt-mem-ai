# PRD: YouTube AI CLI

## Vision

Build a developer-first CLI that can:

1.  Download YouTube audio/video.
2.  Obtain a transcript via:
    -   Whisper / WhisperX
    -   Unofficial transcript API (when available)
3.  Summarize the content with an LLM.
4.  Detect highlights.
5.  Produce structured outputs (Markdown/JSON).
6.  Serve as the foundation for a future desktop/mobile SaaS.

------------------------------------------------------------------------

# Goals

-   Fast local experimentation
-   Extensible architecture
-   Provider-agnostic
-   CLI-first

------------------------------------------------------------------------

# CLI Commands

``` bash
yt-ai download <url>
yt-ai transcript <url>
yt-ai transcript --provider whisper <url>
yt-ai transcript --provider youtube <url>
yt-ai summarize <url>
yt-ai highlights <url>
yt-ai analyze <url>
```

------------------------------------------------------------------------

# Pipeline

``` text
URL
 │
 ├── Metadata
 │
 ├── Transcript
 │      ├── YouTube transcript (preferred if available)
 │      └── Whisper / WhisperX
 │
 ├── Chunking
 │
 ├── LLM
 │      ├── Summary
 │      ├── Highlights
 │      ├── Chapters
 │      ├── Action items
 │      └── Tags
 │
 └── Markdown / JSON
```

------------------------------------------------------------------------

# Transcript Providers

## Provider 1 --- Unofficial transcript API

Pros

-   Fast
-   Cheap
-   No GPU

Cons

-   Not available for every video
-   Depends on undocumented endpoints

Example libraries

-   youtube-transcript-api
-   yt-dlp metadata support

------------------------------------------------------------------------

## Provider 2 --- Whisper / WhisperX

Pipeline

``` text
YouTube
    ↓
Download audio
    ↓
WhisperX
    ↓
Transcript
```

Pros

-   Works without captions
-   Multilingual
-   Better quality
-   Timestamped

------------------------------------------------------------------------

# Downloading

Install

``` bash
brew install yt-dlp ffmpeg
```

or

``` bash
pip install -U yt-dlp
```

Download best audio

``` bash
yt-dlp -f "bestaudio/best" URL
```

Extract mp3

``` bash
yt-dlp -x --audio-format mp3 URL
```

List formats

``` bash
yt-dlp -F URL
```

Python

``` python
from yt_dlp import YoutubeDL

opts = {
    "format":"bestaudio/best",
    "outtmpl":"downloads/%(title)s.%(ext)s"
}

with YoutubeDL(opts) as ydl:
    ydl.download([url])
```

------------------------------------------------------------------------

# Whisper

``` python
import whisper

model = whisper.load_model("large-v3")

result = model.transcribe(
    "audio.m4a",
    word_timestamps=True
)
```

------------------------------------------------------------------------

# Outputs

## Summary

-   Executive summary
-   Bullet points
-   Key ideas

## Highlights

``` text
12:15
Best explanation of MCP

18:32
Important benchmark

31:08
Implementation demo
```

## Chapters

Automatic semantic chapters.

------------------------------------------------------------------------

# Future Features

-   Personalized recommendations
-   Cross-video knowledge graph
-   Semantic search
-   Ask questions about a video
-   Compare multiple videos
-   Daily digest
-   Duplicate-topic detection

------------------------------------------------------------------------

# Suggested Tech Stack

-   TypeScript
-   Node.js
-   Commander.js
-   yt-dlp
-   FFmpeg
-   WhisperX
-   OpenAI / local LLM
-   SQLite (cache)
-   Chroma or LanceDB (embeddings)

------------------------------------------------------------------------

# Project Structure

``` text
packages/
    cli/
    downloader/
    transcript/
    summarizer/
    llm/
    embeddings/
    cache/
```

------------------------------------------------------------------------

# Risks

-   Unofficial transcript endpoints may break.
-   Downloading YouTube media for commercial services may have Terms of
    Service implications.
-   Prefer official APIs where possible for metadata and discovery.

------------------------------------------------------------------------

# MVP

-   Download audio
-   Transcript (YouTube + Whisper fallback)
-   Summary
-   Highlights
-   Markdown output
-   JSON output
-   Batch processing
