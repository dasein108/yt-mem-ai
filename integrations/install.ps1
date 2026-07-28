# yt-mem-ai — Windows installer (PowerShell).
#
# Interactive:      powershell -ExecutionPolicy Bypass -File integrations\install.ps1
# Non-interactive:  ... -ClaudeDesktop mcp -Codex plugin -Cursor skills,mcp
#
# Mirrors install.sh's host x method matrix (Claude Code, Claude Desktop, Codex,
# Cursor, Antigravity; Claude Code plugin is an in-app /plugin step).
param(
  [string[]]$ClaudeCode,
  [string[]]$ClaudeDesktop,
  [string[]]$Codex,
  [string[]]$Cursor,
  [string[]]$Antigravity,
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
  @{ id=1;  host="claude-code";    method="plugin"; label="Claude Code    (Plugin: skills + commands)" },
  @{ id=2;  host="claude-code";    method="mcp";    label="Claude Code    (MCP only)" },
  @{ id=3;  host="claude-desktop"; method="bundle"; label="Claude Desktop (Bundle .mcpb)" },
  @{ id=4;  host="claude-desktop"; method="mcp";    label="Claude Desktop (MCP config)" },
  @{ id=5;  host="codex";          method="plugin"; label="Codex          (Plugin: skills + prompts + AGENTS.md)" },
  @{ id=6;  host="codex";          method="mcp";    label="Codex          (MCP only)" },
  @{ id=7;  host="cursor";         method="skills"; label="Cursor         (Skills)" },
  @{ id=8;  host="cursor";         method="mcp";    label="Cursor         (MCP only)" },
  @{ id=9;  host="antigravity";    method="skills"; label="Antigravity    (Skills)" },
  @{ id=10; host="antigravity";    method="mcp";    label="Antigravity    (MCP only)" }
)
$Sel = New-Object System.Collections.Generic.HashSet[int]
function AddHost($h, $methods) { foreach ($m in $methods) { foreach ($it in $Items) { if ($it.host -eq $h -and $it.method -eq $m) { [void]$Sel.Add($it.id) } } } }

if ($AllPlugins) { 1,5,7,9  | ForEach-Object { [void]$Sel.Add($_) } }
if ($AllMcp)     { 2,4,6,8,10 | ForEach-Object { [void]$Sel.Add($_) } }
if ($ClaudeCode)    { AddHost "claude-code"    $ClaudeCode }
if ($ClaudeDesktop) { AddHost "claude-desktop" $ClaudeDesktop }
if ($Codex)         { AddHost "codex"          $Codex }
if ($Cursor)        { AddHost "cursor"         $Cursor }
if ($Antigravity)   { AddHost "antigravity"    $Antigravity }

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

# For any MCP target, install a persistent absolute-path yt-ai-mcp binary
# (fast start; avoids the uvx cold-start timeout and GUI PATH issues).
$McpBin = $null
$mcpIds = 2,3,4,6,8,10
if ($mcpIds | Where-Object { $Sel.Contains($_) }) {
  Info "installing the yt-ai-mcp server (uv tool install 'yt-mem-ai[mcp]') — first run pulls ML deps…"
  uv tool install --force "yt-mem-ai[mcp]" 2>$null
  $c = Get-Command yt-ai-mcp -ErrorAction SilentlyContinue
  if ($c) { $McpBin = $c.Source } else { $p = Join-Path $HOME ".local\bin\yt-ai-mcp.exe"; if (Test-Path $p) { $McpBin = $p } }
}

function ServerObj {
  [ordered]@{
    command = if ($McpBin) { $McpBin } else { $Uvx }
    args    = if ($McpBin) { @() } else { @("--from","yt-mem-ai[mcp]","yt-ai-mcp") }
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
$CursorMcp  = Join-Path $HOME ".cursor\mcp.json"
$GravityMcp = Join-Path $HOME ".gemini\config\mcp_config.json"
$SkillsSrc  = Join-Path (Split-Path -Parent $ScriptDir) "skills"   # canonical skills/

function CopySkills($dest) {
  New-Item -ItemType Directory -Force -Path $dest | Out-Null
  foreach ($s in "yt","yt-manager") {
    if (Test-Path (Join-Path $SkillsSrc $s)) { Copy-Item (Join-Path $SkillsSrc $s) $dest -Recurse -Force }
    else {
      $d = Join-Path $dest $s; New-Item -ItemType Directory -Force -Path $d | Out-Null
      Invoke-WebRequest "https://raw.githubusercontent.com/dasein108/yt-mem-ai/main/skills/$s/SKILL.md" -OutFile (Join-Path $d "SKILL.md")
    }
  }
}
function MergeCodex {
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $CodexCfg) | Out-Null
  if ((Test-Path $CodexCfg) -and (Select-String -Path $CodexCfg -Pattern '^\[mcp_servers\.yt-mem-ai\]' -Quiet)) { Info "Codex: already configured."; return }
  $cmd = if ($McpBin) { $McpBin } else { $Uvx }
  $args = if ($McpBin) { "[]" } else { '["--from", "yt-mem-ai[mcp]", "yt-ai-mcp"]' }
  @"

[mcp_servers.yt-mem-ai]
command = "$cmd"
args = $args

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
    2 { if (Have "claude") { $svr = if ($McpBin) { @($McpBin) } else { @($Uvx,"--from","yt-mem-ai[mcp]","yt-ai-mcp") }; claude mcp add yt-mem-ai -e "YT_STORE_PATH=$DataDir\lance" -- @svr; Info "Claude Code: MCP added." } else { Info "Claude Code: 'claude' not found." } }
    3 { Info "Claude Desktop bundle: build with integrations/claude-desktop/build.sh (or add the MCP config, -ClaudeDesktop mcp)." }
    4 { MergeServer $DesktopCfg; Info "Restart Claude Desktop." }
    5 { CopySkills (Join-Path $HOME ".codex\skills"); CopyCodexExtras; Info "Codex: skills installed (skills run yt-ai via uvx)." }
    6 { MergeCodex }
    7 { CopySkills (Join-Path $HOME ".cursor\skills"); Info "Cursor: skills installed → ~/.cursor/skills (reload Cursor)." }
    8 { MergeServer $CursorMcp; Info "Cursor: MCP added to ~/.cursor/mcp.json (reload Cursor)." }
    9 { CopySkills (Join-Path $HOME ".gemini\skills"); Info "Antigravity: skills installed → ~/.gemini/skills (restart Antigravity)." }
    10 { MergeServer $GravityMcp; Info "Antigravity: MCP added to ~/.gemini/config/mcp_config.json (restart Antigravity)." }
  }
}
Info "done. Data dir: $DataDir"
