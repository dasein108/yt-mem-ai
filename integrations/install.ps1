# yt-mem-ai — Windows installer (PowerShell).
#
# Interactive:      powershell -ExecutionPolicy Bypass -File integrations\install.ps1
# Non-interactive:  ... -ClaudeDesktop plugin,mcp -Codex mcp -Gemini extension
#
# Mirrors install.sh's host x method matrix for Windows hosts (Claude Desktop,
# Codex, Gemini; Claude Code plugin is an in-app /plugin step).
param(
  [string[]]$ClaudeCode,
  [string[]]$ClaudeDesktop,
  [string[]]$Codex,
  [string[]]$Gemini,
  [switch]$AllPlugins,
  [switch]$AllMcp,
  [switch]$Yes
)
$ErrorActionPreference = "Stop"
$DataDir = if ($env:YT_MEM_AI_HOME) { $env:YT_MEM_AI_HOME } else { Join-Path $HOME ".yt-mem-ai" }
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Local = Test-Path (Join-Path $ScriptDir "claude-code\.claude-plugin\plugin.json")

function Info($m) { Write-Host "yt-mem-ai: $m" }
function Have($c) { $null -ne (Get-Command $c -ErrorAction SilentlyContinue) }

# ---- selection matrix ------------------------------------------------------
$Items = @(
  @{ id=1; host="claude-code";    method="plugin";    label="Claude Code    (Plugin)" },
  @{ id=2; host="claude-code";    method="mcp";       label="Claude Code    (MCP only)" },
  @{ id=3; host="claude-desktop"; method="plugin";    label="Claude Desktop (Bundle .mcpb)" },
  @{ id=4; host="claude-desktop"; method="mcp";       label="Claude Desktop (MCP config)" },
  @{ id=5; host="codex";          method="plugin";    label="Codex          (Plugin: MCP + prompts + AGENTS.md)" },
  @{ id=6; host="codex";          method="mcp";       label="Codex          (MCP only)" },
  @{ id=7; host="gemini";         method="extension"; label="Gemini CLI     (Extension)" },
  @{ id=8; host="gemini";         method="mcp";       label="Gemini CLI     (MCP only)" }
)
$Sel = New-Object System.Collections.Generic.HashSet[int]
function AddHost($h, $methods) { foreach ($m in $methods) { foreach ($it in $Items) { if ($it.host -eq $h -and $it.method -eq $m) { [void]$Sel.Add($it.id) } } } }

if ($AllPlugins) { 1,3,5,7 | ForEach-Object { [void]$Sel.Add($_) } }
if ($AllMcp)     { 2,4,6,8 | ForEach-Object { [void]$Sel.Add($_) } }
if ($ClaudeCode)    { AddHost "claude-code"    $ClaudeCode }
if ($ClaudeDesktop) { AddHost "claude-desktop" $ClaudeDesktop }
if ($Codex)         { AddHost "codex"          $Codex }
if ($Gemini)        { AddHost "gemini"         $Gemini }

if ($Sel.Count -eq 0) {
  Write-Host "`n  yt-mem-ai installer — select targets (comma-separated numbers)`n"
  foreach ($it in $Items) { "   {0}) {1}" -f $it.id, $it.label | Write-Host }
  $ans = Read-Host "`n  Numbers"
  foreach ($n in ($ans -split '[,\s]+')) { if ($n -match '^[1-8]$') { [void]$Sel.Add([int]$n) } }
}
if ($Sel.Count -eq 0) { Info "nothing selected."; exit 0 }

# ---- preflight -------------------------------------------------------------
if (-not (Have "uvx")) {
  Info "installing uv (provides Python + uvx)…"
  powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
  $env:Path = "$HOME\.local\bin;$env:Path"
}
if (-not (Have "uvx")) { throw "uvx not on PATH after installing uv." }
$Uvx = (Get-Command uvx).Source
New-Item -ItemType Directory -Force -Path (Join-Path $DataDir "lance"),(Join-Path $DataDir "logs"),(Join-Path $DataDir "downloads") | Out-Null

function ServerObj {
  [ordered]@{
    command = $Uvx
    args    = @("--from","yt-mem-ai[mcp]","yt-ai-mcp")
    env     = [ordered]@{
      YT_STORE_PATH    = (Join-Path $DataDir "lance")
      YT_LOG_FILE      = (Join-Path $DataDir "logs\common.jsonl")
      YT_DOWNLOADS_DIR = (Join-Path $DataDir "downloads")
    }
  }
}
function MergeServer($file) {
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $file) | Out-Null
  $cfg = if (Test-Path $file) { Get-Content $file -Raw | ConvertFrom-Json } else { [pscustomobject]@{} }
  if (-not $cfg.PSObject.Properties['mcpServers']) { $cfg | Add-Member mcpServers ([pscustomobject]@{}) }
  $cfg.mcpServers | Add-Member -NotePropertyName "yt-mem-ai" -NotePropertyValue (ServerObj) -Force
  ($cfg | ConvertTo-Json -Depth 10) | Set-Content $file -Encoding UTF8
  Info "wrote $file"
}

$DesktopCfg = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
$CodexCfg   = Join-Path $HOME ".codex\config.toml"

function MergeCodex {
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $CodexCfg) | Out-Null
  if ((Test-Path $CodexCfg) -and (Select-String -Path $CodexCfg -Pattern '^\[mcp_servers\.yt-mem-ai\]' -Quiet)) { Info "Codex: already configured."; return }
  @"

[mcp_servers.yt-mem-ai]
command = "$Uvx"
args = ["--from", "yt-mem-ai[mcp]", "yt-ai-mcp"]

[mcp_servers.yt-mem-ai.env]
YT_STORE_PATH = "$DataDir\lance"
YT_LOG_FILE = "$DataDir\logs\common.jsonl"
YT_DOWNLOADS_DIR = "$DataDir\downloads"
"@ | Add-Content $CodexCfg
  Info "Codex: appended MCP server to $CodexCfg"
}
function CopyCodexExtras {
  $p = Join-Path $HOME ".codex\prompts"; New-Item -ItemType Directory -Force -Path $p | Out-Null
  if ($Local) { Copy-Item (Join-Path $ScriptDir "codex\prompts\*.md") $p -Force; Copy-Item (Join-Path $ScriptDir "codex\AGENTS.md") (Join-Path $HOME ".codex\AGENTS.md") -Force }
  Info "Codex: prompts + AGENTS.md installed."
}

foreach ($it in ($Items | Where-Object { $Sel.Contains($_.id) })) {
  switch ($it.id) {
    1 { Info "Claude Code plugin — run in Claude Code:  /plugin marketplace add $([string]($(if($Local){$ScriptDir+'\claude-code'}else{'dasein108/yt-mem-ai'})));  /plugin install yt-mem-ai@yt-mem-ai" }
    2 { if (Have "claude") { claude mcp add yt-mem-ai -e "YT_STORE_PATH=$DataDir\lance" -- $Uvx --from "yt-mem-ai[mcp]" yt-ai-mcp; Info "Claude Code: MCP added." } else { Info "Claude Code: 'claude' not found." } }
    3 { Info "Claude Desktop bundle: build with 'mcpb pack' in a repo checkout, then double-click the .mcpb (see integrations/claude-desktop/README.md)." }
    4 { MergeServer $DesktopCfg; Info "Restart Claude Desktop." }
    5 { MergeCodex; CopyCodexExtras }
    6 { MergeCodex }
    7 { if (Have "gemini") { if ($Local) { gemini extensions install (Join-Path $ScriptDir "gemini"); Info "Gemini extension installed (restart gemini)." } else { Info "Gemini extension needs a repo checkout; use -Gemini mcp instead." } } else { Info "Gemini CLI not found." } }
    8 { MergeServer (Join-Path $HOME ".gemini\settings.json"); Info "Restart gemini." }
  }
}
Info "done. Data dir: $DataDir"
