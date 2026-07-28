#!/bin/sh
# yt-mem-ai — interactive multi-select installer.
#
# Installs the yt-ai-mcp MCP server and/or host plugins for Claude Code,
# Claude Desktop, Codex, and Gemini — any combination in one run.
#
# Interactive (from a checkout):   sh integrations/install.sh
# One-liner / CI (non-interactive): pass matrix flags, e.g.
#   curl -LsSf https://raw.githubusercontent.com/dasein108/yt-mem-ai/main/integrations/install.sh \
#     | sh -s -- --claude-desktop=plugin --codex=mcp
#
# Flags:
#   --claude-code=plugin,mcp      --claude-desktop=plugin,mcp
#   --codex=plugin,mcp            --gemini=extension,mcp
#   --all-plugins   --all-mcp     -y (assume yes)   -h/--help
# Legacy: a single positional host (claude-code|claude-desktop|codex|gemini)
# selects that host's plugin/extension method.
set -eu

REPO="dasein108/yt-mem-ai"
RAW_ROOT="https://raw.githubusercontent.com/${REPO}/main"
RAW="${RAW_ROOT}/integrations"
DATA_DIR="${YT_MEM_AI_HOME:-$HOME/.yt-mem-ai}"

# --------------------------------------------------------------------------- #
# ui helpers
# --------------------------------------------------------------------------- #
msg()  { printf '%s\n' "yt-mem-ai: $*"; }
warn() { printf '%s\n' "yt-mem-ai: $*" >&2; }
die()  { warn "$*"; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

# ANSI palette (only when stdout is a terminal).
if [ -t 1 ]; then
  C_RESET=$(printf '\033[0m'); C_HEAD=$(printf '\033[1;36m'); C_SEL=$(printf '\033[1;32m')
  C_DIM=$(printf '\033[2m');   C_CUR=$(printf '\033[1;33m')
else
  C_RESET=; C_HEAD=; C_SEL=; C_DIM=; C_CUR=
fi
ESC=$(printf '\033')

# Where does this script live, and are the integration files next to it?
SCRIPT_DIR=""
case "${0:-}" in
  */*) SCRIPT_DIR=$(cd "$(dirname "$0")" 2>/dev/null && pwd || true) ;;
esac
LOCAL_MODE=0
if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/claude-code/.claude-plugin/plugin.json" ]; then
  LOCAL_MODE=1
fi

# --------------------------------------------------------------------------- #
# item matrix (1..8): host + method + label
# --------------------------------------------------------------------------- #
item_host()   { case "$1" in 1|2) echo claude-code;; 3|4) echo claude-desktop;; 5|6) echo codex;; 7|8) echo gemini;; esac; }
item_method() { case "$1" in 1) echo plugin;; 2) echo mcp;; 3) echo plugin;; 4) echo mcp;; 5) echo plugin;; 6) echo mcp;; 7) echo extension;; 8) echo mcp;; esac; }
item_label()  {
  case "$1" in
    1) echo "Claude Code    (Plugin: skills + commands)";;
    2) echo "Claude Code    (MCP only)";;
    3) echo "Claude Desktop (Bundle .mcpb)";;
    4) echo "Claude Desktop (MCP config)";;
    5) echo "Codex          (Plugin: skills + prompts + AGENTS.md)";;
    6) echo "Codex          (MCP only)";;
    7) echo "Gemini CLI     (Extension: skills + commands)";;
    8) echo "Gemini CLI     (MCP only)";;
  esac
}
DESKTOP_CFG=""
case "$(uname -s 2>/dev/null || echo unknown)" in
  Darwin) DESKTOP_CFG="$HOME/Library/Application Support/Claude/claude_desktop_config.json" ;;
  *)      DESKTOP_CFG="$HOME/.config/Claude/claude_desktop_config.json" ;;
esac
# Is the host present on the system? (probed once, cached in DET.)
_probe_detected() {
  case "$(item_host "$1")" in
    claude-code)    have claude && echo yes || echo no ;;
    claude-desktop) [ -e "$(dirname "$DESKTOP_CFG")" ] && echo yes || echo no ;;
    codex)          have codex && echo yes || echo no ;;
    gemini)         have gemini && echo yes || echo no ;;
  esac
}

# Is THIS host×method already installed? File/dir checks only (fast, no CLI).
# Best-effort: config-based targets are exact; plugin/bundle installs that a host
# records elsewhere may under-detect (shown unchecked; re-install is idempotent).
_probe_installed() {
  case "$1" in
    1) grep -qs 'yt-mem-ai' "$HOME/.claude.json" 2>/dev/null && echo yes || echo no ;;  # claude-code plugin (best-effort)
    2) grep -qs 'yt-mem-ai' "$HOME/.claude.json" 2>/dev/null && echo yes || echo no ;;  # claude-code mcp (best-effort)
    3) grep -qs '"yt-mem-ai"' "$DESKTOP_CFG" 2>/dev/null && echo yes || echo no ;;       # claude-desktop bundle
    4) grep -qs '"yt-mem-ai"' "$DESKTOP_CFG" 2>/dev/null && echo yes || echo no ;;       # claude-desktop mcp
    5) [ -e "$HOME/.codex/skills/yt/SKILL.md" ] && echo yes || echo no ;;   # codex plugin = native skills (no MCP)
    6) grep -qs '^\[mcp_servers\.yt-mem-ai\]' "$HOME/.codex/config.toml" 2>/dev/null && echo yes || echo no ;;
    7) [ -d "$HOME/.gemini/extensions/yt-mem-ai" ] && echo yes || echo no ;;             # gemini extension
    8) grep -qs 'yt-mem-ai' "$HOME/.gemini/settings.json" 2>/dev/null && echo yes || echo no ;;  # gemini mcp
  esac
}

# Cached membership (filled by compute_states before the picker runs).
DET=" "; INST=" "
item_detected() { case "$DET"  in *" $1 "*) echo yes;; *) echo no;; esac; }
item_installed(){ case "$INST" in *" $1 "*) echo yes;; *) echo no;; esac; }
compute_states() {
  for _i in 1 2 3 4 5 6 7 8; do
    [ "$(_probe_detected "$_i")"  = yes ] && DET="$DET$_i "
    [ "$(_probe_installed "$_i")" = yes ] && INST="$INST$_i "
  done
  # Pre-check whatever is already installed so its box shows [x] ("remember").
  for _i in 1 2 3 4 5 6 7 8; do case "$INST" in *" $_i "*) add_sel "$_i";; esac; done
}

# --------------------------------------------------------------------------- #
# selection state (space-delimited item ids; dash/bash-3 safe, no arrays)
# --------------------------------------------------------------------------- #
SEL=" "
is_sel()  { case "$SEL" in *" $1 "*) return 0;; esac; return 1; }
add_sel() { is_sel "$1" || SEL="$SEL$1 "; }
toggle()  { if is_sel "$1"; then SEL=$(printf '%s' "$SEL" | sed "s/ $1 / /"); else SEL="$SEL$1 "; fi; }
in_set()  { case " $2 " in *" $1 "*) return 0;; esac; return 1; }   # id, set-string
_any()    { [ -n "$(printf '%s' "$1" | tr -d ' ')" ]; }

# --------------------------------------------------------------------------- #
# argument parsing → selection + mode
# --------------------------------------------------------------------------- #
ASSUME_YES=0
NONINTERACTIVE=0
INTERACTIVE_PICKED=0
add_host_methods() { # host  csv-of-methods
  _h=$1; _methods=$2
  IFS=,; for _m in $_methods; do IFS=' '
    for _i in 1 2 3 4 5 6 7 8; do
      [ "$(item_host "$_i")" = "$_h" ] || continue
      [ "$(item_method "$_i")" = "$_m" ] || continue
      add_sel "$_i"; NONINTERACTIVE=1
    done
  done; IFS=' '
}
usage() { sed -n '2,20p' "$0" 2>/dev/null || echo "see header"; exit 0; }

for arg in "$@"; do
  case "$arg" in
    -h|--help) usage ;;
    -y|--yes) ASSUME_YES=1 ;;
    --all-plugins) for i in 1 3 5 7; do add_sel "$i"; done; NONINTERACTIVE=1 ;;
    --all-mcp)     for i in 2 4 6 8; do add_sel "$i"; done; NONINTERACTIVE=1 ;;
    --claude-code=*)    add_host_methods claude-code    "${arg#*=}" ;;
    --claude-desktop=*) add_host_methods claude-desktop "${arg#*=}" ;;
    --codex=*)          add_host_methods codex          "${arg#*=}" ;;
    --gemini=*)         add_host_methods gemini         "${arg#*=}" ;;
    # legacy single-host positional → that host's plugin/extension method
    claude-code)    add_sel 1; NONINTERACTIVE=1 ;;
    claude-desktop) add_sel 3; NONINTERACTIVE=1 ;;
    codex)          add_sel 5; NONINTERACTIVE=1 ;;
    gemini)         add_sel 7; NONINTERACTIVE=1 ;;
    *) die "unknown argument: $arg (try --help)" ;;
  esac
done

# No TTY (piped) and nothing selected → we can't show a checklist.
if [ "$NONINTERACTIVE" -eq 0 ] && [ ! -t 0 ]; then
  die "no selection and no TTY. Pass flags, e.g.: sh -s -- --claude-desktop=plugin --codex=mcp"
fi

# --------------------------------------------------------------------------- #
# interactive picker (portable numbered toggle; whiptail if available)
# --------------------------------------------------------------------------- #
picker_whiptail() {
  _args=""
  for i in 1 2 3 4 5 6 7 8; do
    _on=off; [ "$(item_installed "$i")" = yes ] && _on=on   # pre-check installed
    _args="$_args $i \"$(item_label "$i")\" $_on"
  done
  _chosen=$(eval whiptail --title "'yt-mem-ai installer'" \
    --checklist "'Select targets (space toggles, enter confirms):'" 20 74 8 $_args \
    3>&1 1>&2 2>&3) || return 1
  SEL=" "                                                    # whiptail result is authoritative
  for c in $_chosen; do add_sel "$(printf '%s' "$c" | tr -d '"')"; done
}

picker_plain() {
  while :; do
    printf '\n  yt-mem-ai installer — select targets\n\n'
    for i in 1 2 3 4 5 6 7 8; do
      mark=" "; is_sel "$i" && mark="X"
      det=""
      if [ "$(item_installed "$i")" = yes ]; then det="  (installed)"
      elif [ "$(item_detected "$i")" = no ]; then det="  (not detected)"; fi
      printf '   [%s] %s) %s%s\n' "$mark" "$i" "$(item_label "$i")" "$det"
    done
    printf '\n   Type a number to toggle, "a" all-detected, "i" install, "q" quit: '
    read -r choice || choice=q
    case "$choice" in
      [1-8]) toggle "$choice" ;;
      a|A) for i in 1 2 3 4 5 6 7 8; do [ "$(item_detected "$i")" = yes ] && add_sel "$i"; done ;;
      i|I) break ;;
      q|Q) msg "aborted."; exit 0 ;;
      *) : ;;
    esac
  done
}

# Arrow-key / space checkbox TUI (bash: works on macOS + Linux, no deps).
TUI_ROWS=11
tui_render() {
  _c=$1
  printf '  %syt-mem-ai installer%s\n' "$C_HEAD" "$C_RESET"
  printf '  %s↑/↓ move  ·  space toggle  ·  a all detected  ·  enter install  ·  q quit%s\n\n' "$C_DIM" "$C_RESET"
  for _i in 1 2 3 4 5 6 7 8; do
    if is_sel "$_i"; then _box="${C_SEL}[x]${C_RESET}"; else _box="[ ]"; fi
    _lab=$(item_label "$_i")
    if [ "$(item_installed "$_i")" = yes ]; then _lab="$_lab ${C_SEL}(installed)${C_RESET}"
    elif [ "$(item_detected "$_i")" = no ]; then _lab="$_lab ${C_DIM}(not detected)${C_RESET}"; fi
    if [ "$_i" = "$_c" ]; then
      printf '  %s❯%s %s %s%s%s\n' "$C_CUR" "$C_RESET" "$_box" "$C_CUR" "$_lab" "$C_RESET"
    else
      printf '    %s %s\n' "$_box" "$_lab"
    fi
  done
}

tui_bash() {
  _cur=1; _first=1
  printf '\033[?25l'                                  # hide cursor
  trap 'printf "\033[?25h\n"' EXIT
  trap 'printf "\033[?25h\n"; exit 130' INT
  while :; do
    if [ "$_first" = 1 ]; then _first=0; else printf '\033[%dA' "$TUI_ROWS"; fi
    tui_render "$_cur"
    # A failed read = EOF / Ctrl-D → quit cleanly (never spin the redraw loop).
    if ! IFS= read -rsn1 _k 2>/dev/null; then
      trap - EXIT INT; printf '\033[?25h\n'; msg "aborted."; exit 0
    fi
    case "$_k" in
      "$ESC")
        IFS= read -rsn2 -t 1 _r 2>/dev/null || _r=""
        case "$_r" in
          "[A") _cur=$(( _cur > 1 ? _cur - 1 : 8 )) ;;
          "[B") _cur=$(( _cur < 8 ? _cur + 1 : 1 )) ;;
        esac ;;
      k|K) _cur=$(( _cur > 1 ? _cur - 1 : 8 )) ;;
      j|J) _cur=$(( _cur < 8 ? _cur + 1 : 1 )) ;;
      " ") toggle "$_cur" ;;
      a|A) for _i in 1 2 3 4 5 6 7 8; do [ "$(item_detected "$_i")" = yes ] && add_sel "$_i"; done ;;
      q|Q) trap - EXIT INT; printf '\033[?25h\n'; msg "aborted."; exit 0 ;;
      # enter → confirm when there's anything to act on (a selection to install,
      # or installed state to diff against — e.g. unticking all = remove all).
      "")  { _any "$SEL" || _any "$INST"; } && break ;;
    esac
  done
  trap - EXIT INT
  printf '\033[?25h'                                  # show cursor
}

if [ "$NONINTERACTIVE" -eq 0 ]; then
  compute_states                                     # detect installed → pre-check [x]
  if [ -t 0 ] && [ -t 1 ] && [ -n "${BASH_VERSION:-}" ]; then
    tui_bash; INTERACTIVE_PICKED=1                    # rich arrow-key checkbox UI
  elif [ -t 0 ] && [ -t 1 ] && have bash; then
    exec bash "$0" "$@"                               # re-exec under bash for the TUI
  elif have whiptail && [ -t 0 ]; then
    picker_whiptail || picker_plain; INTERACTIVE_PICKED=1
  else
    picker_plain; INTERACTIVE_PICKED=1                # portable numbered fallback
  fi
fi

# --------------------------------------------------------------------------- #
# diff: selection vs. currently-installed → INSTALL set + UNINSTALL set
#   selected & not installed → install ;  installed & unselected → uninstall
#   selected & installed → leave as-is  ;  neither → ignore
# In flag/non-interactive mode INST is empty, so UNINSTALL is empty (flags never
# remove) — unchanged additive behavior.
# --------------------------------------------------------------------------- #
INSTALL=" "; UNINSTALL=" "
for i in 1 2 3 4 5 6 7 8; do
  if is_sel "$i"; then
    in_set "$i" "$INST" || INSTALL="$INSTALL$i "
  else
    in_set "$i" "$INST" && UNINSTALL="$UNINSTALL$i "
  fi
done
_any "$INSTALL" || _any "$UNINSTALL" || { msg "no changes."; exit 0; }

echo
msg "plan:"
for i in 1 2 3 4 5 6 7 8; do in_set "$i" "$INSTALL"   && printf '   %s+ install%s %s\n' "$C_SEL" "$C_RESET" "$(item_label "$i")"; done
for i in 1 2 3 4 5 6 7 8; do in_set "$i" "$UNINSTALL" && printf '   %s- remove %s %s\n' "$C_CUR" "$C_RESET" "$(item_label "$i")"; done

# Confirm. Removals are destructive → always confirm (default No), even after a
# picker. Install-only after an interactive pick needs no re-confirm.
if _any "$UNINSTALL" && [ "$ASSUME_YES" -eq 0 ] && [ -t 0 ]; then
  printf '\nApply this plan (includes removals)? [y/N] '; read -r ok || ok=n
  case "$ok" in y*|Y*) : ;; *) msg "aborted."; exit 0 ;; esac
elif ! _any "$UNINSTALL" && [ "$ASSUME_YES" -eq 0 ] && [ "$INTERACTIVE_PICKED" -eq 0 ] && [ -t 0 ]; then
  printf '\nProceed? [Y/n] '; read -r ok || ok=n
  case "$ok" in n*|N*) msg "aborted."; exit 0 ;; esac
fi

# --------------------------------------------------------------------------- #
# preflight: uv/uvx + data dir
# --------------------------------------------------------------------------- #
ensure_uv() {
  if ! have uv; then
    msg "installing uv (provides Python + uvx)…"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
  fi
  have uvx || die "uvx not on PATH after installing uv (add ~/.local/bin to PATH and re-run)."
  msg "fetching the latest yt-mem-ai[mcp]…"
  uv cache clean yt-mem-ai >/dev/null 2>&1 || true
  uvx --refresh-package yt-mem-ai --from "yt-mem-ai[mcp]" yt-ai-mcp --help >/dev/null 2>&1 || true
}
PY=$(command -v python3 2>/dev/null || true)
UVX=""
# Only bootstrap uv + the data dir when we're actually installing something.
if _any "$INSTALL"; then
  ensure_uv
  UVX=$(command -v uvx)
  mkdir -p "$DATA_DIR/lance" "$DATA_DIR/logs" "$DATA_DIR/downloads"
fi

# merge one stdio MCP server into a JSON config file's mcpServers map.
# args: FILE  SERVER_NAME   (uses $UVX and $DATA_DIR from env)
json_merge_server() {
  _file=$1; _name=$2
  mkdir -p "$(dirname "$_file")"
  if [ -n "$PY" ]; then
    YT_FILE="$_file" YT_NAME="$_name" YT_UVX="$UVX" YT_DATA="$DATA_DIR" "$PY" - <<'PYEOF'
import json, os
f, name, uvx, data = (os.environ[k] for k in ("YT_FILE","YT_NAME","YT_UVX","YT_DATA"))
cfg = {}
if os.path.exists(f):
    try: cfg = json.load(open(f))
    except Exception: cfg = {}
cfg.setdefault("mcpServers", {})[name] = {
    "command": uvx,
    "args": ["--from", "yt-mem-ai[mcp]", "yt-ai-mcp"],
    "env": {
        "YT_STORE_PATH": f"{data}/lance",
        "YT_LOG_FILE": f"{data}/logs/common.jsonl",
        "YT_DOWNLOADS_DIR": f"{data}/downloads",
    },
}
json.dump(cfg, open(f, "w"), indent=2)
print("wrote", f)
PYEOF
  elif [ ! -e "$_file" ]; then
    cat > "$_file" <<EOF
{
  "mcpServers": {
    "$_name": {
      "command": "$UVX",
      "args": ["--from", "yt-mem-ai[mcp]", "yt-ai-mcp"],
      "env": { "YT_STORE_PATH": "$DATA_DIR/lance", "YT_LOG_FILE": "$DATA_DIR/logs/common.jsonl", "YT_DOWNLOADS_DIR": "$DATA_DIR/downloads" }
    }
  }
}
EOF
    msg "wrote $_file"
  else
    warn "python3 not found and $_file already exists — add this server manually:"
    warn '  "yt-mem-ai": {"command": "'"$UVX"'", "args": ["--from","yt-mem-ai[mcp]","yt-ai-mcp"]}'
  fi
}

# delete one server from a JSON config's mcpServers map. args: FILE NAME
json_remove_server() {
  _file=$1; _name=$2
  [ -f "$_file" ] || return 0
  if [ -n "$PY" ]; then
    YT_FILE="$_file" YT_NAME="$_name" "$PY" - <<'PYEOF'
import json, os
f, name = os.environ["YT_FILE"], os.environ["YT_NAME"]
try:
    cfg = json.load(open(f))
except Exception:
    cfg = None
if isinstance(cfg, dict) and isinstance(cfg.get("mcpServers"), dict) and name in cfg["mcpServers"]:
    del cfg["mcpServers"][name]
    json.dump(cfg, open(f, "w"), indent=2)
    print("removed", name, "from", f)
PYEOF
  else
    warn "python3 not found — remove the \"$_name\" server from $_file by hand."
  fi
}

# delete the [mcp_servers.yt-mem-ai] (+ .env) sections from a Codex config.toml.
toml_remove_yt() {
  _file=$1
  [ -f "$_file" ] || return 0
  awk '
    /^[[:space:]]*\[/ { skip = ($0 ~ /^[[:space:]]*\[mcp_servers\.yt-mem-ai([].]|$)/) ? 1 : 0 }
    skip != 1 { print }
  ' "$_file" > "$_file.tmp" 2>/dev/null && mv "$_file.tmp" "$_file"
}

# --------------------------------------------------------------------------- #
# per-target installers
# --------------------------------------------------------------------------- #
src_dir() { # host → local integration dir (or empty in piped mode)
  [ "$LOCAL_MODE" -eq 1 ] && echo "$SCRIPT_DIR/$1" || echo ""
}

do_claude_code_mcp() {
  if have claude; then
    claude mcp add yt-mem-ai \
      -e "YT_STORE_PATH=$DATA_DIR/lance" \
      -e "YT_LOG_FILE=$DATA_DIR/logs/common.jsonl" \
      -e "YT_DOWNLOADS_DIR=$DATA_DIR/downloads" \
      -- "$UVX" --from "yt-mem-ai[mcp]" yt-ai-mcp \
      && msg "Claude Code: added MCP server 'yt-mem-ai'." \
      || warn "Claude Code: 'claude mcp add' failed — run it manually (see integrations/mcp/README.md)."
  else
    warn "Claude Code: 'claude' not on PATH. Install the CLI, then: claude mcp add yt-mem-ai -- uvx --from 'yt-mem-ai[mcp]' yt-ai-mcp"
  fi
}

do_claude_code_plugin() {
  _src=$(src_dir claude-code); [ -n "$_src" ] || _src="$REPO"
  msg "Claude Code plugin — run these inside Claude Code (no stable CLI for /plugin):"
  printf '     /plugin marketplace add %s\n' "$_src"
  printf '     /plugin install yt-mem-ai@yt-mem-ai\n'
  msg "(Ships the yt + yt-manager skills and /yt-* commands; they drive the yt-ai CLI via uvx. For MCP tools instead, pick 'Claude Code (MCP only)'.)"
}

do_claude_desktop_mcp() {
  json_merge_server "$DESKTOP_CFG" "yt-mem-ai"
  msg "Claude Desktop: MCP server merged into $(basename "$DESKTOP_CFG"). Restart Claude Desktop."
}

do_claude_desktop_plugin() {
  _src=$(src_dir claude-desktop)
  if [ -z "$_src" ]; then
    warn "Claude Desktop bundle needs the repo checkout — falling back to MCP config."
    do_claude_desktop_mcp; return
  fi
  # build.sh uses the mcpb CLI if present, else plain `zip` (a .mcpb is a zip).
  if ( cd "$_src" && sh build.sh ); then
    _out="$_src/yt-mem-ai.mcpb"
    if have open; then open "$_out" && msg "Claude Desktop: opened $_out to install."
    else msg "Built $_out — open it in Claude Desktop → Settings → Extensions."; fi
  else
    warn "Bundle build failed — falling back to MCP config."
    do_claude_desktop_mcp
  fi
}

CODEX_CFG="$HOME/.codex/config.toml"
do_codex_mcp() {
  mkdir -p "$HOME/.codex"
  if [ -f "$CODEX_CFG" ] && grep -q '^\[mcp_servers\.yt-mem-ai\]' "$CODEX_CFG" 2>/dev/null; then
    msg "Codex: 'yt-mem-ai' already in config.toml (left as-is)."
  else
    cat >> "$CODEX_CFG" <<EOF

[mcp_servers.yt-mem-ai]
command = "$UVX"
args = ["--from", "yt-mem-ai[mcp]", "yt-ai-mcp"]

[mcp_servers.yt-mem-ai.env]
YT_STORE_PATH = "$DATA_DIR/lance"
YT_LOG_FILE = "$DATA_DIR/logs/common.jsonl"
YT_DOWNLOADS_DIR = "$DATA_DIR/downloads"
EOF
    msg "Codex: appended MCP server to $CODEX_CFG."
  fi
}

do_codex_plugin() {
  # Native SKILL.md skills — Codex loads them from the User scope ~/.codex/skills/
  # (v0.117.0+). The skills drive the yt-ai CLI via uvx (no MCP, no package
  # install). The full .codex-plugin/ manifest is also usable via /plugins.
  mkdir -p "$HOME/.codex/skills" "$HOME/.codex/prompts"
  _src=$(src_dir codex)
  if [ -n "$_src" ]; then
    cp -RL "$_src/skills/yt" "$_src/skills/yt-manager" "$HOME/.codex/skills/" 2>/dev/null || true
    cp "$_src"/prompts/*.md "$HOME/.codex/prompts/" 2>/dev/null || true
    cp "$_src/AGENTS.md" "$HOME/.codex/AGENTS.md" 2>/dev/null || true
  else
    for s in yt yt-manager; do
      mkdir -p "$HOME/.codex/skills/$s"
      curl -LsSf "$RAW_ROOT/skills/$s/SKILL.md" -o "$HOME/.codex/skills/$s/SKILL.md" 2>/dev/null || true
    done
    for p in yt-summarize yt-highlights yt-qa yt-presentation yt-digest yt-review yt-group; do
      curl -LsSf "$RAW/codex/prompts/$p.md" -o "$HOME/.codex/prompts/$p.md" 2>/dev/null || true
    done
    curl -LsSf "$RAW/codex/AGENTS.md" -o "$HOME/.codex/AGENTS.md" 2>/dev/null || true
  fi
  msg "Codex: installed skills (yt, yt-manager) + prompts + ~/.codex/AGENTS.md. CLI runs via uvx."
}

do_gemini_mcp() { json_merge_server "$HOME/.gemini/settings.json" "yt-mem-ai"; msg "Gemini: MCP server merged into ~/.gemini/settings.json. Restart gemini."; }

do_gemini_extension() {
  if ! have gemini; then warn "Gemini: 'gemini' not on PATH — install the CLI, then re-run."; return; fi
  _src=$(src_dir gemini)
  if [ -n "$_src" ]; then
    gemini extensions install "$_src" && msg "Gemini: extension installed (restart gemini)." || warn "Gemini: install failed."
  else
    warn "Gemini extension needs the repo checkout (manifest lives in integrations/gemini/). Clone and re-run, or use --gemini=mcp."
  fi
}

# --------------------------------------------------------------------------- #
# per-target uninstallers
# --------------------------------------------------------------------------- #
undo_claude_code_plugin() {
  msg "Claude Code plugin — remove inside Claude Code:  /plugin uninstall yt-mem-ai@yt-mem-ai"
}
undo_claude_code_mcp() {
  if have claude; then
    claude mcp remove yt-mem-ai >/dev/null 2>&1 && msg "Claude Code: removed MCP server 'yt-mem-ai'." \
      || warn "Claude Code: 'claude mcp remove yt-mem-ai' failed (maybe not present)."
  else warn "Claude Code: 'claude' not on PATH — run: claude mcp remove yt-mem-ai"; fi
}
undo_claude_desktop_plugin() {
  msg "Claude Desktop bundle — remove in the app: Settings → Extensions → yt-mem-ai → Uninstall."
}
undo_claude_desktop_mcp() {
  json_remove_server "$DESKTOP_CFG" "yt-mem-ai"
  msg "Claude Desktop: removed MCP server from $(basename "$DESKTOP_CFG"). Restart Claude Desktop."
}
undo_codex_mcp() {
  toml_remove_yt "$HOME/.codex/config.toml"
  msg "Codex: removed MCP server from config.toml."
}
undo_codex_plugin() {
  undo_codex_mcp
  rm -rf "$HOME/.codex/skills/yt" "$HOME/.codex/skills/yt-manager" 2>/dev/null || true
  for p in yt-summarize yt-highlights yt-qa yt-presentation yt-digest yt-review yt-group; do
    rm -f "$HOME/.codex/prompts/$p.md" 2>/dev/null || true
  done
  msg "Codex: removed skills + prompts. (Left ~/.codex/AGENTS.md untouched — delete it by hand if it's ours.)"
}
undo_gemini_extension() {
  if have gemini; then
    gemini extensions uninstall yt-mem-ai >/dev/null 2>&1 && msg "Gemini: extension uninstalled (restart gemini)." \
      || warn "Gemini: 'gemini extensions uninstall yt-mem-ai' failed (maybe not installed)."
  else warn "Gemini: 'gemini' not on PATH — remove ~/.gemini/extensions/yt-mem-ai by hand."; fi
}
undo_gemini_mcp() {
  json_remove_server "$HOME/.gemini/settings.json" "yt-mem-ai"
  msg "Gemini: removed MCP server from ~/.gemini/settings.json. Restart gemini."
}

# --------------------------------------------------------------------------- #
# dispatch: removals first, then installs
# --------------------------------------------------------------------------- #
echo
for i in 1 2 3 4 5 6 7 8; do
  in_set "$i" "$UNINSTALL" || continue
  case "$i" in
    1) undo_claude_code_plugin ;;   2) undo_claude_code_mcp ;;
    3) undo_claude_desktop_plugin ;;4) undo_claude_desktop_mcp ;;
    5) undo_codex_plugin ;;         6) undo_codex_mcp ;;
    7) undo_gemini_extension ;;     8) undo_gemini_mcp ;;
  esac
done
for i in 1 2 3 4 5 6 7 8; do
  in_set "$i" "$INSTALL" || continue
  case "$i" in
    1) do_claude_code_plugin ;;   2) do_claude_code_mcp ;;
    3) do_claude_desktop_plugin ;;4) do_claude_desktop_mcp ;;
    5) do_codex_plugin ;;         6) do_codex_mcp ;;
    7) do_gemini_extension ;;     8) do_gemini_mcp ;;
  esac
done

echo
_any "$INSTALL" && msg "done. Data dir: $DATA_DIR (override with YT_MEM_AI_HOME)."
_any "$INSTALL" && msg "Set proxy/cookies/embedding vars from chat with 'yt-ai config set', or in each host's config — see integrations/mcp/README.md."
_any "$UNINSTALL" && ! _any "$INSTALL" && msg "done — removed the selected integration(s)."
