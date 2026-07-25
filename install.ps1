# yt-ai installer bootstrap (Windows PowerShell).
# Usage: irm https://raw.githubusercontent.com/dasein108/yt-ai/main/install.ps1 | iex
$ErrorActionPreference = "Stop"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Host "yt-ai: installing uv (provides Python + uvx)..."
  irm https://astral.sh/uv/install.ps1 | iex
  $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

Write-Host "yt-ai: fetching the latest published version..."
uv cache clean yt-ai *> $null

Write-Host "yt-ai: ready. Run it with:"
Write-Host "  uvx yt-ai --help"
