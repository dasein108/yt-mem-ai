# yt-mem-ai installer bootstrap (Windows PowerShell).
# Usage: irm https://raw.githubusercontent.com/dasein108/yt-mem-ai/main/install.ps1 | iex
$ErrorActionPreference = "Stop"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Host "yt-mem-ai: installing uv (provides Python + uvx)..."
  irm https://astral.sh/uv/install.ps1 | iex
  $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

Write-Host "yt-mem-ai: fetching the latest published version..."
uv cache clean yt-mem-ai *> $null

Write-Host "yt-mem-ai: ready. Run it with:"
Write-Host "  uvx yt-mem-ai --help          # or, once installed, the 'yt-ai' command"
