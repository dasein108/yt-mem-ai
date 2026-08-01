# yt-mem-ai — one installer (Windows PowerShell).
#
# Two steps:
#   1. what to install   Plugin (skills + yt-ai CLI)  |  MCP (typed tools)
#   2. where             Claude Code · Claude Desktop · Codex · Cursor · Antigravity
#                        · OpenClaw · Hermes
#
# Anything that can't be automated (Claude Desktop plugins live on your Claude
# account; a host whose CLI isn't on PATH) prints a bright WARNING with the exact
# manual steps.
#
#   powershell -ExecutionPolicy Bypass -File install.ps1                 # wizard
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Plugin -Codex  # direct
#   powershell -ExecutionPolicy Bypass -File install.ps1 -All
#   irm https://raw.githubusercontent.com/dasein108/yt-mem-ai/main/install.ps1 | iex   # CLI only
param(
  [switch]$Plugin,
  [switch]$Mcp,
  [switch]$ClaudeCode,
  [switch]$ClaudeDesktop,
  [switch]$Codex,
  [switch]$Cursor,
  [switch]$Antigravity,
  [switch]$Openclaw,
  [switch]$Hermes,
  [switch]$All,
  [switch]$Bootstrap,
  [switch]$Yes
)
$ErrorActionPreference = "Stop"
$Repo    = "dasein108/yt-mem-ai"
$RawRoot = "https://raw.githubusercontent.com/$Repo/main"
$Raw     = "$RawRoot/integrations"
$DataDir = if ($env:YT_MEM_AI_HOME) { $env:YT_MEM_AI_HOME } else { Join-Path $HOME ".yt-mem-ai" }

function Info($m) { Write-Host "yt-mem-ai: $m" }
function Have($c) { $null -ne (Get-Command $c -ErrorAction SilentlyContinue) }
function WarnBox($head, [string[]]$lines) {
  Write-Host ""
  Write-Host "  !  $head" -ForegroundColor Red
  foreach ($l in $lines) { Write-Host "     $l" -ForegroundColor White }
  Write-Host ""
}

$ScriptDir = if ($PSCommandPath) { Split-Path -Parent $PSCommandPath } else { "" }
$LocalMode = $ScriptDir -and (Test-Path (Join-Path $ScriptDir "integrations\claude-code\.claude-plugin\plugin.json"))
$Ing       = if ($ScriptDir) { Join-Path $ScriptDir "integrations" } else { "" }
$SkillsSrc = if ($ScriptDir) { Join-Path $ScriptDir "skills" } else { "" }

# ---- host paths ------------------------------------------------------------
$DesktopCfg    = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
$CodexCfg      = Join-Path $HOME ".codex\config.toml"
$CodexSkills   = Join-Path $HOME ".codex\skills"
$CursorMcp     = Join-Path $HOME ".cursor\mcp.json"
$CursorSkills  = Join-Path $HOME ".cursor\skills"
$GravityMcp    = Join-Path $HOME ".gemini\config\mcp_config.json"
$GravitySkills = Join-Path $HOME ".gemini\skills"
$OpenclawCfg   = Join-Path $HOME ".openclaw\openclaw.json"
$OpenclawSkills= Join-Path $HOME ".agents\skills"      # personal (cross-agent) skill root
$HermesCfg     = Join-Path $HOME ".hermes\config.yaml"
$HermesSkills  = Join-Path $HOME ".hermes\skills"
$CodexPrompts  = @("yt-summarize","yt-highlights","yt-qa","yt-presentation","yt-digest","yt-review","yt-group","yt-config","yt-setup")

$Methods = @(
  @{ id="plugin"; label="Plugin   - yt + yt-agent skills + the yt-ai CLI (auto-triggers on 'summarize this video')" },
  @{ id="mcp";    label="MCP      - yt-ai-mcp server: typed tools (fetch, search, save_summary, config_*)" }
)
$Hosts = @(
  @{ id="claude-code";    label="Claude Code    (claude CLI)" },
  @{ id="claude-desktop"; label="Claude Desktop (app)" },
  @{ id="codex";          label="Codex          (CLI + IDE - shared ~/.codex)" },
  @{ id="cursor";         label="Cursor         (~/.cursor)" },
  @{ id="antigravity";    label="Antigravity    (~/.gemini)" },
  @{ id="openclaw";       label="OpenClaw       (~/.agents/skills)" },
  @{ id="hermes";         label="Hermes         (~/.hermes)" }
)

function HostDetected($h) {
  switch ($h) {
    "claude-code"    { return (Have "claude") }
    "claude-desktop" { return (Test-Path (Split-Path -Parent $DesktopCfg)) }
    "codex"          { return ((Have "codex")       -or (Test-Path (Join-Path $HOME ".codex"))) }
    "cursor"         { return ((Have "cursor")      -or (Test-Path (Join-Path $HOME ".cursor"))) }
    "antigravity"    { return ((Have "antigravity") -or (Test-Path (Join-Path $HOME ".gemini"))) }
    "openclaw"       { return ((Have "openclaw")    -or (Test-Path (Join-Path $HOME ".openclaw"))) }
    "hermes"         { return ((Have "hermes")      -or (Test-Path (Join-Path $HOME ".hermes"))) }
  }
  return $false
}
function FileHas($path, $pattern) {
  return (Test-Path $path) -and (Select-String -Path $path -Pattern $pattern -Quiet -ErrorAction SilentlyContinue)
}
# Does this JSON config really register the server? A plain name match hits
# unrelated mentions (Claude Code stores a githubRepoPaths entry for a yt-mem-ai
# checkout), so look inside an mcpServers map - including project-scoped ones.
function JsonHasServer($path) {
  if (-not (Test-Path $path)) { return $false }
  try { $cfg = Get-Content $path -Raw | ConvertFrom-Json } catch { return $false }
  function Walk($n) {
    if ($null -eq $n) { return $false }
    if ($n -is [System.Management.Automation.PSCustomObject]) {
      $srv = $n.PSObject.Properties['mcpServers']
      if ($srv -and $srv.Value -and $srv.Value.PSObject.Properties['yt-mem-ai']) { return $true }
      $mcp = $n.PSObject.Properties['mcp']          # OpenClaw: mcp.servers
      if ($mcp -and $mcp.Value -and $mcp.Value.PSObject.Properties['servers'] -and
          $mcp.Value.servers.PSObject.Properties['yt-mem-ai']) { return $true }
      foreach ($p in $n.PSObject.Properties) { if (Walk $p.Value) { return $true } }
    } elseif ($n -is [System.Collections.IEnumerable] -and $n -isnot [string]) {
      foreach ($i in $n) { if (Walk $i) { return $true } }
    }
    return $false
  }
  return (Walk $cfg)
}
function PairInstalled($m, $h) {
  switch ("${m}:${h}") {
    "plugin:claude-code"    { return ((FileHas (Join-Path $HOME ".claude\settings.json") '"yt-mem-ai@yt-mem-ai"') -or (Test-Path (Join-Path $HOME ".claude\plugins\cache\yt-mem-ai"))) }
    # Claude Desktop plugins live on your Claude account - nothing local to probe.
    "plugin:claude-desktop" { return $false }
    "plugin:codex"          { return (Test-Path (Join-Path $CodexSkills   "yt\SKILL.md")) }
    "plugin:cursor"         { return (Test-Path (Join-Path $CursorSkills  "yt\SKILL.md")) }
    "plugin:antigravity"    { return (Test-Path (Join-Path $GravitySkills "yt\SKILL.md")) }
    "mcp:claude-code"       { return (JsonHasServer (Join-Path $HOME ".claude.json")) }
    "mcp:claude-desktop"    { return (JsonHasServer $DesktopCfg) }
    "mcp:codex"             { return (FileHas $CodexCfg "^\[mcp_servers\.yt-mem-ai\]") }
    "mcp:cursor"            { return (JsonHasServer $CursorMcp) }
    "mcp:antigravity"       { return (JsonHasServer $GravityMcp) }
    "plugin:openclaw"       { return (Test-Path (Join-Path $OpenclawSkills "yt\SKILL.md")) }
    "plugin:hermes"         { return (Test-Path (Join-Path $HermesSkills  "yt\SKILL.md")) }
    "mcp:openclaw"          { return (JsonHasServer $OpenclawCfg) }
    "mcp:hermes"            { return (FileHas $HermesCfg "^\s+yt-mem-ai:") }
  }
  return $false
}

# ---- selection -------------------------------------------------------------
$SelM = New-Object System.Collections.Generic.HashSet[string]
$SelH = New-Object System.Collections.Generic.HashSet[string]
$NonInteractive = $false
if ($Plugin)        { [void]$SelM.Add("plugin"); $NonInteractive = $true }
if ($Mcp)           { [void]$SelM.Add("mcp");    $NonInteractive = $true }
if ($Openclaw)      { [void]$SelH.Add("openclaw");       $NonInteractive = $true }
if ($Hermes)        { [void]$SelH.Add("hermes");         $NonInteractive = $true }
if ($ClaudeCode)    { [void]$SelH.Add("claude-code");    $NonInteractive = $true }
if ($ClaudeDesktop) { [void]$SelH.Add("claude-desktop"); $NonInteractive = $true }
if ($Codex)         { [void]$SelH.Add("codex");          $NonInteractive = $true }
if ($Cursor)        { [void]$SelH.Add("cursor");         $NonInteractive = $true }
if ($Antigravity)   { [void]$SelH.Add("antigravity");    $NonInteractive = $true }
if ($All) {
  $Methods | ForEach-Object { [void]$SelM.Add($_.id) }
  $Hosts   | ForEach-Object { [void]$SelH.Add($_.id) }
  $NonInteractive = $true
}
if ($NonInteractive) {
  if ($SelM.Count -eq 0) { [void]$SelM.Add("plugin") }
  if ($SelH.Count -eq 0) { $Hosts | ForEach-Object { [void]$SelH.Add($_.id) } }
}

# ---- uv / payload ----------------------------------------------------------
function EnsureUv {
  if (-not (Have "uvx")) {
    Info "installing uv (provides Python + uvx)..."
    powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$HOME\.local\bin;$env:Path"
  }
  if (-not (Have "uvx")) { throw "uvx not on PATH after installing uv." }
  return (Get-Command uvx).Source
}
$Uvx = $null; $McpBin = $null; $YtBin = $null
function EnsureCli {
  Info "installing the yt-ai CLI (uv tool install yt-mem-ai) - first run pulls ML deps..."
  uv tool install --force yt-mem-ai 2>$null
  $c = Get-Command yt-ai -ErrorAction SilentlyContinue
  $script:YtBin = if ($c) { $c.Source } else { $p = Join-Path $HOME ".local\bin\yt-ai.exe"; if (Test-Path $p) { $p } else { $null } }
  if ($script:YtBin) { Info "CLI ready: $($script:YtBin)" }
}
function EnsureMcp {
  Info "installing the yt-ai-mcp server (uv tool install 'yt-mem-ai[mcp]') - first run pulls ML deps..."
  uv tool install --force "yt-mem-ai[mcp]" 2>$null
  $c = Get-Command yt-ai-mcp -ErrorAction SilentlyContinue
  $script:McpBin = if ($c) { $c.Source } else { $p = Join-Path $HOME ".local\bin\yt-ai-mcp.exe"; if (Test-Path $p) { $p } else { $null } }
  if ($script:McpBin) { Info "server ready: $($script:McpBin)" }
}

# No arguments and no console input (piped `irm | iex`) - just bootstrap the CLI.
if ($Bootstrap -or (-not $NonInteractive -and [Console]::IsInputRedirected)) {
  $Uvx = EnsureUv; EnsureCli
  Info "ready:  yt-ai --help    (or: uvx yt-mem-ai --help)"
  Info "to wire up hosts, download install.ps1 and run it in a console."
  exit 0
}

# ---- wizard ----------------------------------------------------------------
function PickScreen($title, $hint, $items, $preselected, $statusFn) {
  $sel = New-Object System.Collections.Generic.HashSet[string]
  foreach ($p in $preselected) { [void]$sel.Add($p) }
  while ($true) {
    Write-Host ""
    Write-Host "  $title" -ForegroundColor Cyan
    Write-Host "  $hint"  -ForegroundColor DarkGray
    Write-Host ""
    $n = 0
    foreach ($it in $items) {
      $n++
      $mark = if ($sel.Contains($it.id)) { "x" } else { " " }
      $st = & $statusFn $it.id
      Write-Host ("   [{0}] {1}) {2} {3}" -f $mark, $n, $it.label, $st)
    }
    Write-Host ""
    $ans = Read-Host "   number = toggle, a = all, n = none, enter = continue, q = quit"
    switch -Regex ($ans) {
      '^$'      { return $sel }
      '^[aA]$'  { $items | ForEach-Object { [void]$sel.Add($_.id) } }
      '^[nN]$'  { $sel.Clear() }
      '^[qQ]$'  { Info "aborted."; exit 0 }
      '^\d+$'   {
        $i = [int]$ans
        if ($i -ge 1 -and $i -le $items.Count) {
          $id = $items[$i-1].id
          if ($sel.Contains($id)) { [void]$sel.Remove($id) } else { [void]$sel.Add($id) }
        }
      }
    }
  }
}

if (-not $NonInteractive) {
  # Step 1 is a single choice (no checkboxes): Plugin or MCP.
  $SelM = New-Object System.Collections.Generic.HashSet[string]
  while ($SelM.Count -eq 0) {
    Write-Host ""
    Write-Host "  yt-mem-ai - step 1/2: what to install" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "   1) Plugin  - yt/yt-agent skills + the yt-ai CLI"
    Write-Host "   2) MCP     - yt-ai-mcp server (typed tools)"
    Write-Host ""
    switch (Read-Host "   Choose [1-2] (q to quit)") {
      "1" { [void]$SelM.Add("plugin") }
      "2" { [void]$SelM.Add("mcp") }
      "q" { Info "aborted."; exit 0 }
      "Q" { Info "aborted."; exit 0 }
    }
  }

  $pre = @()
  foreach ($h in $Hosts) { foreach ($m in $SelM) { if (PairInstalled $m $h.id) { $pre += $h.id; break } } }
  $SelH = PickScreen "yt-mem-ai - step 2/2: where ($($SelM -join ' '))" `
    "untick an installed host to remove it" $Hosts $pre `
    { param($id) $out = @(); foreach ($m in $SelM) { if (PairInstalled $m $id) { $out += $m } }
      if ($out) { "(installed: $($out -join ' '))" } elseif (-not (HostDetected $id)) { "(not detected)" } else { "" } }
}

# ---- diff ------------------------------------------------------------------
$Install = @(); $Uninstall = @()
foreach ($m in $SelM) {
  foreach ($h in $Hosts) {
    if ($SelH.Contains($h.id)) {
      if (-not (PairInstalled $m $h.id)) { $Install += "${m}:$($h.id)" }
    } elseif (-not $NonInteractive) {
      if (PairInstalled $m $h.id) { $Uninstall += "${m}:$($h.id)" }
    }
  }
}
if ($Install.Count -eq 0 -and $Uninstall.Count -eq 0) { Info "no changes."; exit 0 }
Write-Host ""
Info "plan:"
foreach ($p in $Install)   { Write-Host "   + install $p" -ForegroundColor Green }
foreach ($p in $Uninstall) { Write-Host "   - remove  $p" -ForegroundColor Yellow }
if ($Uninstall.Count -gt 0 -and -not $Yes) {
  $ok = Read-Host "`nApply this plan (includes removals)? [y/N]"
  if ($ok -notmatch '^[yY]') { Info "aborted."; exit 0 }
}

# ---- preflight -------------------------------------------------------------
$Uvx = EnsureUv
New-Item -ItemType Directory -Force -Path (Join-Path $DataDir "lance"),(Join-Path $DataDir "logs"),(Join-Path $DataDir "downloads") | Out-Null
if ($Install | Where-Object { $_ -like "plugin:*" }) { EnsureCli }
if ($Install | Where-Object { $_ -like "mcp:*" })    { EnsureMcp }

# ---- writers ---------------------------------------------------------------
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
function RemoveServer($file) {
  if (-not (Test-Path $file)) { return }
  $cfg = Get-Content $file -Raw | ConvertFrom-Json
  if ($cfg.PSObject.Properties['mcpServers'] -and $cfg.mcpServers.PSObject.Properties['yt-mem-ai']) {
    $cfg.mcpServers.PSObject.Properties.Remove('yt-mem-ai')
    ($cfg | ConvertTo-Json -Depth 10) | Set-Content $file -Encoding UTF8
    Info "removed yt-mem-ai from $file"
  }
}
function MergeOpenclawServer {
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OpenclawCfg) | Out-Null
  $cfg = if (Test-Path $OpenclawCfg) { Get-Content $OpenclawCfg -Raw | ConvertFrom-Json } else { [pscustomobject]@{} }
  if (-not $cfg.PSObject.Properties['mcp']) { $cfg | Add-Member mcp ([pscustomobject]@{}) }
  if (-not $cfg.mcp.PSObject.Properties['servers']) { $cfg.mcp | Add-Member servers ([pscustomobject]@{}) }
  $cfg.mcp.servers | Add-Member -NotePropertyName "yt-mem-ai" -NotePropertyValue (ServerObj) -Force
  ($cfg | ConvertTo-Json -Depth 10) | Set-Content $OpenclawCfg -Encoding UTF8
  Info "OpenClaw: MCP server merged into ~/.openclaw/openclaw.json."
}
# Hermes keeps MCP servers in YAML; splice a fixed block (no YAML tooling in PS).
function MergeHermesServer {
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $HermesCfg) | Out-Null
  $cmd  = if ($McpBin) { $McpBin } else { $Uvx }
  $args = if ($McpBin) { "[]" } else { '["--from", "yt-mem-ai[mcp]", "yt-ai-mcp"]' }
  $block = @(
    "  yt-mem-ai:",
    "    command: `"$cmd`"",
    "    args: $args",
    "    env:",
    "      YT_STORE_PATH: `"$DataDir\lance`"",
    "      YT_LOG_FILE: `"$DataDir\logs\common.jsonl`"",
    "      YT_DOWNLOADS_DIR: `"$DataDir\downloads`"",
    "    enabled: true")
  $lines = if (Test-Path $HermesCfg) { @(Get-Content $HermesCfg) } else { @() }
  $out = @(); $skip = $false
  foreach ($ln in $lines) {                      # drop an existing entry first
    if ($skip -and ($ln -match '^\s{4,}' -or $ln.Trim() -eq "")) { continue }
    $skip = $false
    if ($ln -match '^\s{2}yt-mem-ai:\s*$') { $skip = $true; continue }
    $out += $ln
  }
  $idx = [Array]::FindIndex([string[]]$out, [Predicate[string]]{ param($l) $l -match '^mcp_servers:' })
  if ($idx -lt 0) { $out += @("", "mcp_servers:") + $block }
  else { $out = $out[0..$idx] + $block + $out[($idx+1)..($out.Count-1)] }
  ($out -join "`n") | Set-Content $HermesCfg -Encoding UTF8
  Info "Hermes: MCP server merged into ~/.hermes/config.yaml (restart Hermes, or /reload-mcp)."
}
function RemoveHermesServer {
  if (-not (Test-Path $HermesCfg)) { return }
  $out = @(); $skip = $false
  foreach ($ln in @(Get-Content $HermesCfg)) {
    if ($skip -and ($ln -match '^\s{4,}' -or $ln.Trim() -eq "")) { continue }
    $skip = $false
    if ($ln -match '^\s{2}yt-mem-ai:\s*$') { $skip = $true; continue }
    $out += $ln
  }
  ($out -join "`n") | Set-Content $HermesCfg -Encoding UTF8
}

function CopySkills($dest) {
  New-Item -ItemType Directory -Force -Path $dest | Out-Null
  foreach ($s in "yt","yt-agent") {
    if ($SkillsSrc -and (Test-Path (Join-Path $SkillsSrc $s))) {
      Copy-Item (Join-Path $SkillsSrc $s) $dest -Recurse -Force
    } else {
      $d = Join-Path $dest $s; New-Item -ItemType Directory -Force -Path $d | Out-Null
      try { Invoke-WebRequest "$RawRoot/skills/$s/SKILL.md" -OutFile (Join-Path $d "SKILL.md") } catch { }
    }
    $f = Join-Path (Join-Path $dest $s) "SKILL.md"
    if (-not (Test-Path $f) -or (Get-Item $f).Length -eq 0) {
      WarnBox "couldn't fetch the '$s' skill (no network, or GitHub unreachable)." @(
        "Copy it by hand from a checkout:  Copy-Item skills\$s $dest -Recurse",
        "or download:  $RawRoot/skills/$s/SKILL.md  ->  $f")
      return $false
    }
  }
  return $true
}
function HostMissingWarning($h) {
  if (HostDetected $h) { return }
  switch ($h) {
    "claude-code"    { WarnBox "Claude Code not found on PATH." @("Install it: npm i -g @anthropic-ai/claude-code", "Then re-run this installer.") }
    "claude-desktop" { WarnBox "Claude Desktop config dir not found - is the app installed?" @("Get it: https://claude.ai/download", "Config lands at: $DesktopCfg") }
    default          { WarnBox "$h not detected." @("Files are written anyway - the app picks them up once installed.") }
  }
}

function InstallPair($m, $h) {
  switch ("${m}:${h}") {
    "plugin:claude-code" {
      $src = if ($LocalMode) { Join-Path $Ing "claude-code" } else { $Repo }
      if (Have "claude") {
        claude plugin marketplace add $src 2>$null
        claude plugin install yt-mem-ai@yt-mem-ai
        Info "Claude Code: plugin installed (skills + /yt-* commands) -> ~/.claude/plugins."
      } else {
        WarnBox "Claude Code: the 'claude' CLI isn't on PATH, so the plugin can't be installed for you." @(
          "Inside Claude Code run:", "/plugin marketplace add $src", "/plugin install yt-mem-ai@yt-mem-ai")
      }
    }
    "plugin:claude-desktop" {
      WarnBox "Claude Desktop plugins live on your Claude ACCOUNT, not on disk - no script can install them." @(
        "Do this in the app (one minute):",
        "Customize (left sidebar) -> Plugins -> Personal plugins -> +",
        "-> Add marketplace -> Add from a repository",
        "-> https://github.com/$Repo -> Add -> Install 'yt-mem-ai'",
        "Uninstall the same way. Prefer typed tools? Re-run and tick MCP for Claude Desktop.")
    }
    "plugin:codex" {
      if (CopySkills $CodexSkills) {
        $p = Join-Path $HOME ".codex\prompts"; New-Item -ItemType Directory -Force -Path $p | Out-Null
        if ($LocalMode) {
          Copy-Item (Join-Path $Ing "codex\prompts\*.md") $p -Force
          Copy-Item (Join-Path $Ing "codex\AGENTS.md") (Join-Path $HOME ".codex\AGENTS.md") -Force
        } else {
          foreach ($n in $CodexPrompts) { try { Invoke-WebRequest "$Raw/codex/prompts/$n.md" -OutFile (Join-Path $p "$n.md") } catch { } }
          try { Invoke-WebRequest "$Raw/codex/AGENTS.md" -OutFile (Join-Path $HOME ".codex\AGENTS.md") } catch { }
        }
        Info "Codex: skills + prompts + AGENTS.md installed (CLI and IDE share ~/.codex)."
      }
    }
    "plugin:cursor"      { if (CopySkills $CursorSkills)  { Info "Cursor: skills installed -> ~/.cursor/skills (reload Cursor)." } }
    "plugin:antigravity" { if (CopySkills $GravitySkills) { Info "Antigravity: skills installed -> ~/.gemini/skills (restart Antigravity)." } }
    "mcp:claude-code" {
      if (Have "claude") {
        $svr = if ($McpBin) { @($McpBin) } else { @($Uvx,"--from","yt-mem-ai[mcp]","yt-ai-mcp") }
        claude mcp add -s user yt-mem-ai -e "YT_STORE_PATH=$DataDir\lance" -e "YT_LOG_FILE=$DataDir\logs\common.jsonl" -e "YT_DOWNLOADS_DIR=$DataDir\downloads" -- @svr
        Info "Claude Code: MCP server added."
      } else {
        WarnBox "Claude Code: the 'claude' CLI isn't on PATH." @("After installing it, run:", "claude mcp add yt-mem-ai -- $(if($McpBin){$McpBin}else{'uvx --from yt-mem-ai[mcp] yt-ai-mcp'})")
      }
    }
    "mcp:claude-desktop" { MergeServer $DesktopCfg; Info "Claude Desktop: MCP config written - restart the app." }
    "mcp:codex" {
      New-Item -ItemType Directory -Force -Path (Split-Path -Parent $CodexCfg) | Out-Null
      if (FileHas $CodexCfg "^\[mcp_servers\.yt-mem-ai\]") { Info "Codex: already configured." }
      else {
        $cmd  = if ($McpBin) { $McpBin } else { $Uvx }
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
        Info "Codex: MCP server appended to $CodexCfg"
      }
    }
    "mcp:cursor"      { MergeServer $CursorMcp;  Info "Cursor: MCP server added (reload Cursor)." }
    "mcp:antigravity" { MergeServer $GravityMcp; Info "Antigravity: MCP server added (restart Antigravity)." }
    "plugin:openclaw" { if (CopySkills $OpenclawSkills) { Info "OpenClaw: skills installed -> ~/.agents/skills." } }
    "plugin:hermes"   { if (CopySkills $HermesSkills)   { Info "Hermes: skills installed -> ~/.hermes/skills (use /yt and /yt-agent)." } }
    "mcp:openclaw"    { MergeOpenclawServer }
    "mcp:hermes"      { MergeHermesServer }
  }
}

function UninstallPair($m, $h) {
  switch ("${m}:${h}") {
    "plugin:claude-code" {
      if (Have "claude") { claude plugin uninstall yt-mem-ai@yt-mem-ai; Info "Claude Code: plugin uninstalled." }
      else { WarnBox "Claude Code: 'claude' not on PATH - remove it in-app:" @("/plugin uninstall yt-mem-ai@yt-mem-ai") }
    }
    "plugin:claude-desktop" { WarnBox "Claude Desktop: remove it in the app." @("Customize -> Plugins -> yt-mem-ai -> Uninstall") }
    "plugin:codex" {
      Remove-Item (Join-Path $CodexSkills "yt"),(Join-Path $CodexSkills "yt-agent") -Recurse -Force -ErrorAction SilentlyContinue
      foreach ($n in $CodexPrompts) { Remove-Item (Join-Path $HOME ".codex\prompts\$n.md") -Force -ErrorAction SilentlyContinue }
      Info "Codex: skills + prompts removed."
    }
    "plugin:cursor" {
      Remove-Item (Join-Path $CursorSkills "yt"),(Join-Path $CursorSkills "yt-agent") -Recurse -Force -ErrorAction SilentlyContinue
      Info "Cursor: skills removed."
    }
    "plugin:antigravity" {
      Remove-Item (Join-Path $GravitySkills "yt"),(Join-Path $GravitySkills "yt-agent") -Recurse -Force -ErrorAction SilentlyContinue
      Info "Antigravity: skills removed."
    }
    "mcp:claude-code" {
      if (Have "claude") { claude mcp remove -s user yt-mem-ai; Info "Claude Code: MCP server removed." }
      else { WarnBox "Claude Code: 'claude' not on PATH." @("Run: claude mcp remove yt-mem-ai") }
    }
    "mcp:claude-desktop" { RemoveServer $DesktopCfg; Info "Claude Desktop: MCP server removed - restart the app." }
    "mcp:codex" {
      if (Test-Path $CodexCfg) {
        $keep = @(); $skip = $false
        foreach ($line in Get-Content $CodexCfg) {
          if ($line -match '^\s*\[') { $skip = $line -match '^\s*\[mcp_servers\.yt-mem-ai(\]|\.)' }
          if (-not $skip) { $keep += $line }
        }
        $keep | Set-Content $CodexCfg -Encoding UTF8
        Info "Codex: MCP server removed from config.toml."
      }
    }
    "mcp:cursor"      { RemoveServer $CursorMcp;  Info "Cursor: MCP server removed." }
    "mcp:antigravity" { RemoveServer $GravityMcp; Info "Antigravity: MCP server removed." }
    "plugin:openclaw" {
      Remove-Item (Join-Path $OpenclawSkills "yt"),(Join-Path $OpenclawSkills "yt-agent") -Recurse -Force -ErrorAction SilentlyContinue
      Info "OpenClaw: skills removed."
    }
    "plugin:hermes" {
      Remove-Item (Join-Path $HermesSkills "yt"),(Join-Path $HermesSkills "yt-agent") -Recurse -Force -ErrorAction SilentlyContinue
      Info "Hermes: skills removed."
    }
    "mcp:openclaw" {
      if (Test-Path $OpenclawCfg) {
        $cfg = Get-Content $OpenclawCfg -Raw | ConvertFrom-Json
        if ($cfg.PSObject.Properties['mcp'] -and $cfg.mcp.PSObject.Properties['servers'] -and $cfg.mcp.servers.PSObject.Properties['yt-mem-ai']) {
          $cfg.mcp.servers.PSObject.Properties.Remove('yt-mem-ai')
          ($cfg | ConvertTo-Json -Depth 10) | Set-Content $OpenclawCfg -Encoding UTF8
        }
      }
      Info "OpenClaw: MCP server removed."
    }
    "mcp:hermes" { RemoveHermesServer; Info "Hermes: MCP server removed." }
  }
}

# ---- apply -----------------------------------------------------------------
Write-Host ""
foreach ($p in $Uninstall) { UninstallPair ($p -split ':')[0] ($p -split ':')[1] }
$warned = @()
foreach ($p in $Install) {
  $m, $h = ($p -split ':')
  if ($warned -notcontains $h) { HostMissingWarning $h; $warned += $h }
  InstallPair $m $h
}
Write-Host ""
if ($Install.Count -gt 0) {
  Info "done. Data dir: $DataDir (override with YT_MEM_AI_HOME)."
  Info "Configure any time:  yt-ai config set <KEY> <VALUE>"
  if ($SelM -contains "plugin") { Info "Try it: ask your assistant - summarize 'https://youtu.be/...'" }
} else {
  Info "done - removed the selected integration(s)."
}
