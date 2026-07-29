#!/bin/sh
# yt-mem-ai — interactive multi-select installer.
#
# Installs native skills/plugins and/or the yt-ai-mcp MCP server for Claude Code,
# Claude Desktop, Codex, Cursor, and Antigravity — any combination in one run.
#
# Interactive (from a checkout):   sh integrations/install.sh
# One-liner / CI (non-interactive): pass matrix flags, e.g.
#   curl -LsSf https://raw.githubusercontent.com/dasein108/yt-mem-ai/main/integrations/install.sh \
#     | sh -s -- --cursor=skills --codex=plugin
#
# Flags:
#   --claude-code=plugin,mcp      --claude-desktop=mcp
#   --codex=plugin,mcp            --cursor=skills,mcp
#   --antigravity=skills,mcp      (alias: --gravity=…)
#   --all-plugins   --all-mcp     -y (assume yes)   -h/--help
# Legacy: a single positional host (claude-code|claude-desktop|codex|cursor|
# antigravity) selects that host's native (skills/plugin) method.
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
# item matrix (1..9): host + method + label
# (Claude Desktop's recommended path is the Plugin — installed via the Claude
#  Code plugin CLI, item 1, on the shared plugin store — so Desktop keeps only a
#  bare MCP-config escape hatch here; the fussy .mcpb bundle was dropped.)
# --------------------------------------------------------------------------- #
ITEM_IDS="1 2 3 4 5 6 7 8 9"
item_host()   { case "$1" in 1|2) echo claude-code;; 3) echo claude-desktop;; 4|5) echo codex;; 6|7) echo cursor;; 8|9) echo antigravity;; esac; }
item_method() { case "$1" in 1) echo plugin;; 2) echo mcp;; 3) echo mcp;; 4) echo plugin;; 5) echo mcp;; 6) echo skills;; 7) echo mcp;; 8) echo skills;; 9) echo mcp;; esac; }
item_label()  {
  case "$1" in
    1) echo "Claude Code    (Plugin: skills + commands)";;
    2) echo "Claude Code    (MCP only)";;
    3) echo "Claude Desktop (MCP config)  [for skills, install the Plugin — item 1]";;
    4) echo "Codex          (Plugin: skills + prompts + AGENTS.md)";;
    5) echo "Codex          (MCP only)";;
    6) echo "Cursor         (Skills)";;
    7) echo "Cursor         (MCP only)";;
    8) echo "Antigravity    (Skills)";;
    9) echo "Antigravity    (MCP only)";;
  esac
}
DESKTOP_CFG=""
case "$(uname -s 2>/dev/null || echo unknown)" in
  Darwin) DESKTOP_CFG="$HOME/Library/Application Support/Claude/claude_desktop_config.json" ;;
  *)      DESKTOP_CFG="$HOME/.config/Claude/claude_desktop_config.json" ;;
esac
CURSOR_MCP="$HOME/.cursor/mcp.json"
CURSOR_SKILLS="$HOME/.cursor/skills"
GRAVITY_MCP="$HOME/.gemini/config/mcp_config.json"
GRAVITY_SKILLS="$HOME/.gemini/skills"
# Is the host present on the system? (probed once, cached in DET.)
_probe_detected() {
  case "$(item_host "$1")" in
    claude-code)    have claude && echo yes || echo no ;;
    claude-desktop) [ -e "$(dirname "$DESKTOP_CFG")" ] && echo yes || echo no ;;
    codex)          have codex && echo yes || echo no ;;
    cursor)         { have cursor || [ -d "$HOME/.cursor" ]; } && echo yes || echo no ;;
    antigravity)    { have antigravity || [ -d "$HOME/.gemini" ]; } && echo yes || echo no ;;
  esac
}

# Is THIS host×method already installed? File/dir checks only (fast, no CLI).
# Best-effort: config-based targets are exact; plugin/bundle installs that a host
# records elsewhere may under-detect (shown unchecked; re-install is idempotent).
_probe_installed() {
  case "$1" in
    1) { grep -qs 'yt-mem-ai' "$HOME/.claude/settings.json" 2>/dev/null || grep -qs 'yt-mem-ai' "$HOME/.claude.json" 2>/dev/null || [ -d "$HOME/.claude/plugins/cache/yt-mem-ai" ]; } && echo yes || echo no ;;  # claude-code plugin
    2) grep -qs 'yt-mem-ai' "$HOME/.claude.json" 2>/dev/null && echo yes || echo no ;;  # claude-code mcp (best-effort)
    3) grep -qs '"yt-mem-ai"' "$DESKTOP_CFG" 2>/dev/null && echo yes || echo no ;;       # claude-desktop mcp config
    4) [ -e "$HOME/.codex/skills/yt/SKILL.md" ] && echo yes || echo no ;;   # codex plugin = native skills
    5) grep -qs '^\[mcp_servers\.yt-mem-ai\]' "$HOME/.codex/config.toml" 2>/dev/null && echo yes || echo no ;;
    6) [ -e "$CURSOR_SKILLS/yt/SKILL.md" ] && echo yes || echo no ;;                     # cursor skills
    7) grep -qs 'yt-mem-ai' "$CURSOR_MCP" 2>/dev/null && echo yes || echo no ;;          # cursor mcp
    8) [ -e "$GRAVITY_SKILLS/yt/SKILL.md" ] && echo yes || echo no ;;                    # antigravity skills
    9) grep -qs 'yt-mem-ai' "$GRAVITY_MCP" 2>/dev/null && echo yes || echo no ;;         # antigravity mcp
  esac
}

# Cached membership (filled by compute_states before the picker runs).
DET=" "; INST=" "
item_detected() { case "$DET"  in *" $1 "*) echo yes;; *) echo no;; esac; }
item_installed(){ case "$INST" in *" $1 "*) echo yes;; *) echo no;; esac; }
compute_states() {
  for _i in $ITEM_IDS; do
    [ "$(_probe_detected "$_i")"  = yes ] && DET="$DET$_i "
    [ "$(_probe_installed "$_i")" = yes ] && INST="$INST$_i "
  done
  # Pre-check whatever is already installed so its box shows [x] ("remember").
  for _i in $ITEM_IDS; do case "$INST" in *" $_i "*) add_sel "$_i";; esac; done
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
    for _i in $ITEM_IDS; do
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
    --all-plugins) for i in 1 4 6 8; do add_sel "$i"; done; NONINTERACTIVE=1 ;;   # native skills installs
    --all-mcp)     for i in 2 3 5 7 9; do add_sel "$i"; done; NONINTERACTIVE=1 ;;
    --claude-code=*)    add_host_methods claude-code    "${arg#*=}" ;;
    --claude-desktop=*) add_host_methods claude-desktop "${arg#*=}" ;;
    --codex=*)          add_host_methods codex          "${arg#*=}" ;;
    --cursor=*)         add_host_methods cursor         "${arg#*=}" ;;
    --antigravity=*)    add_host_methods antigravity    "${arg#*=}" ;;
    --gravity=*)        add_host_methods antigravity    "${arg#*=}" ;;
    # legacy single-host positional → that host's native (skills/plugin) method
    claude-code)    add_sel 1; NONINTERACTIVE=1 ;;
    claude-desktop) add_sel 3; NONINTERACTIVE=1 ;;   # Desktop has only the MCP config here
    codex)          add_sel 4; NONINTERACTIVE=1 ;;
    cursor)         add_sel 6; NONINTERACTIVE=1 ;;
    antigravity|gravity) add_sel 8; NONINTERACTIVE=1 ;;
    *) die "unknown argument: $arg (try --help)" ;;
  esac
done

# No TTY (piped) and nothing selected → we can't show a checklist.
if [ "$NONINTERACTIVE" -eq 0 ] && [ ! -t 0 ]; then
  die "no selection and no TTY. Pass flags, e.g.: sh -s -- --codex=plugin --cursor=skills,mcp"
fi

# --------------------------------------------------------------------------- #
# interactive picker (portable numbered toggle; whiptail if available)
# --------------------------------------------------------------------------- #
picker_whiptail() {
  _args=""
  for i in $ITEM_IDS; do
    _on=off; [ "$(item_installed "$i")" = yes ] && _on=on   # pre-check installed
    _args="$_args $i \"$(item_label "$i")\" $_on"
  done
  _chosen=$(eval whiptail --title "'yt-mem-ai installer'" \
    --checklist "'Select targets (space toggles, enter confirms):'" 22 74 10 $_args \
    3>&1 1>&2 2>&3) || return 1
  SEL=" "                                                    # whiptail result is authoritative
  for c in $_chosen; do add_sel "$(printf '%s' "$c" | tr -d '"')"; done
}

picker_plain() {
  while :; do
    printf '\n  yt-mem-ai installer — select targets\n\n'
    for i in $ITEM_IDS; do
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
      a|A) for i in $ITEM_IDS; do [ "$(item_detected "$i")" = yes ] && add_sel "$i"; done ;;
      i|I) break ;;
      q|Q) msg "aborted."; exit 0 ;;
      *) : ;;
    esac
  done
}

# Arrow-key / space checkbox TUI (bash: works on macOS + Linux, no deps).
TUI_ROWS=12
tui_render() {
  _c=$1
  printf '  %syt-mem-ai installer%s\n' "$C_HEAD" "$C_RESET"
  printf '  %s↑/↓ move  ·  space toggle  ·  a all detected  ·  enter install  ·  q quit%s\n\n' "$C_DIM" "$C_RESET"
  for _i in $ITEM_IDS; do
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
          "[A") _cur=$(( _cur > 1 ? _cur - 1 : 9 )) ;;
          "[B") _cur=$(( _cur < 9 ? _cur + 1 : 1 )) ;;
        esac ;;
      k|K) _cur=$(( _cur > 1 ? _cur - 1 : 9 )) ;;
      j|J) _cur=$(( _cur < 9 ? _cur + 1 : 1 )) ;;
      " ") toggle "$_cur" ;;
      a|A) for _i in $ITEM_IDS; do [ "$(item_detected "$_i")" = yes ] && add_sel "$_i"; done ;;
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
for i in $ITEM_IDS; do
  if is_sel "$i"; then
    in_set "$i" "$INST" || INSTALL="$INSTALL$i "
  else
    in_set "$i" "$INST" && UNINSTALL="$UNINSTALL$i "
  fi
done
_any "$INSTALL" || _any "$UNINSTALL" || { msg "no changes."; exit 0; }

echo
msg "plan:"
for i in $ITEM_IDS; do in_set "$i" "$INSTALL"   && printf '   %s+ install%s %s\n' "$C_SEL" "$C_RESET" "$(item_label "$i")"; done
for i in $ITEM_IDS; do in_set "$i" "$UNINSTALL" && printf '   %s- remove %s %s\n' "$C_CUR" "$C_RESET" "$(item_label "$i")"; done

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
UVX=""; MCP_BIN=""

mcp_selected() { for _i in 2 3 5 7 9; do in_set "$_i" "$INSTALL" && return 0; done; return 1; }

# For any MCP target, install the server as a persistent, absolute-path binary.
# This avoids the two Claude-Desktop failure modes: (1) a heavy `uvx` cold start
# (torch/lancedb download) that times out the MCP handshake, and (2) a bare
# "uvx" command that the GUI app can't find on PATH.
ensure_yt_ai_mcp() {
  msg "installing the yt-ai-mcp server (uv tool install 'yt-mem-ai[mcp]') — first run pulls ML deps, please wait…"
  uv tool install --force "yt-mem-ai[mcp]" >/dev/null 2>&1 || uv tool install "yt-mem-ai[mcp]" || true
  MCP_BIN=$(command -v yt-ai-mcp 2>/dev/null || true)
  if [ -z "$MCP_BIN" ]; then
    for _d in "$(uv tool dir --bin 2>/dev/null || true)" "$HOME/.local/bin"; do
      [ -n "$_d" ] && [ -x "$_d/yt-ai-mcp" ] && { MCP_BIN="$_d/yt-ai-mcp"; break; }
    done
  fi
  if [ -n "$MCP_BIN" ]; then msg "server ready: $MCP_BIN"
  else warn "couldn't locate the yt-ai-mcp binary after install — MCP configs will fall back to uvx (slower cold start)."; fi
}

# Launch shape for MCP configs: prefer the installed binary (fast, absolute),
# else uvx. Sets MCP_CMD (string) + MCP_ARGS_JSON (JSON array literal).
mcp_cmd()       { [ -n "$MCP_BIN" ] && printf '%s' "$MCP_BIN" || printf '%s' "${UVX:-uvx}"; }
mcp_args_json() { [ -n "$MCP_BIN" ] && printf '[]' || printf '["--from", "yt-mem-ai[mcp]", "yt-ai-mcp"]'; }

# Only bootstrap uv + the data dir when we're actually installing something.
if _any "$INSTALL"; then
  ensure_uv
  UVX=$(command -v uvx)
  mkdir -p "$DATA_DIR/lance" "$DATA_DIR/logs" "$DATA_DIR/downloads"
  mcp_selected && ensure_yt_ai_mcp
fi

# merge one stdio MCP server into a JSON config file's mcpServers map.
# args: FILE  SERVER_NAME   (uses $UVX and $DATA_DIR from env)
json_merge_server() {
  _file=$1; _name=$2; _cmd=$(mcp_cmd); _args=$(mcp_args_json)
  mkdir -p "$(dirname "$_file")"
  if [ -n "$PY" ]; then
    YT_FILE="$_file" YT_NAME="$_name" YT_CMD="$_cmd" YT_ARGS="$_args" YT_DATA="$DATA_DIR" "$PY" - <<'PYEOF'
import json, os
f, name, cmd, args, data = (os.environ[k] for k in ("YT_FILE","YT_NAME","YT_CMD","YT_ARGS","YT_DATA"))
cfg = {}
if os.path.exists(f):
    try: cfg = json.load(open(f))
    except Exception: cfg = {}
cfg.setdefault("mcpServers", {})[name] = {
    "command": cmd,
    "args": json.loads(args),
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
      "command": "$_cmd",
      "args": $_args,
      "env": { "YT_STORE_PATH": "$DATA_DIR/lance", "YT_LOG_FILE": "$DATA_DIR/logs/common.jsonl", "YT_DOWNLOADS_DIR": "$DATA_DIR/downloads" }
    }
  }
}
EOF
    msg "wrote $_file"
  else
    warn "python3 not found and $_file already exists — add this server manually:"
    warn "  \"yt-mem-ai\": {\"command\": \"$_cmd\", \"args\": $_args}"
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
  if ! have claude; then
    warn "Claude Code: 'claude' not on PATH. Install the CLI, then: claude mcp add yt-mem-ai -- uvx --from 'yt-mem-ai[mcp]' yt-ai-mcp"
    return
  fi
  if [ -n "$MCP_BIN" ]; then
    claude mcp add yt-mem-ai \
      -e "YT_STORE_PATH=$DATA_DIR/lance" -e "YT_LOG_FILE=$DATA_DIR/logs/common.jsonl" \
      -e "YT_DOWNLOADS_DIR=$DATA_DIR/downloads" -- "$MCP_BIN"
  else
    claude mcp add yt-mem-ai \
      -e "YT_STORE_PATH=$DATA_DIR/lance" -e "YT_LOG_FILE=$DATA_DIR/logs/common.jsonl" \
      -e "YT_DOWNLOADS_DIR=$DATA_DIR/downloads" -- "$UVX" --from "yt-mem-ai[mcp]" yt-ai-mcp
  fi && msg "Claude Code: added MCP server 'yt-mem-ai'." \
     || warn "Claude Code: 'claude mcp add' failed — run it manually (see integrations/mcp/README.md)."
}

do_claude_code_plugin() {
  # Local checkout → the plugin dir; else the GitHub repo (root marketplace.json).
  _src=$(src_dir claude-code); [ -n "$_src" ] || _src="$REPO"
  if have claude; then
    claude plugin marketplace add "$_src" >/dev/null 2>&1 || true
    if claude plugin install yt-mem-ai@yt-mem-ai >/dev/null 2>&1; then
      msg "Claude Code: plugin installed (yt + yt-manager skills, /yt-* commands)."
      msg "(Unified plugin store — if your Claude Desktop shares ~/.claude it shows there too; else add it via Customize → Plugins.)"
    else
      warn "Claude Code: auto-install failed. Run inside Claude Code:"
      warn "  /plugin marketplace add $_src   →   /plugin install yt-mem-ai@yt-mem-ai"
    fi
  else
    msg "Plugin — 'claude' CLI not on PATH. In the app:"
    msg "  Claude Code:    /plugin marketplace add $_src ; /plugin install yt-mem-ai@yt-mem-ai"
    msg "  Claude Desktop: Customize → Plugins → Add marketplace → $_src → Install"
  fi
}

do_claude_desktop_mcp() {
  json_merge_server "$DESKTOP_CFG" "yt-mem-ai"
  msg "Claude Desktop: MCP server merged into $(basename "$DESKTOP_CFG"). Restart Claude Desktop."
  msg "(For the auto-triggering skills instead, install the Plugin — pick 'Claude Code (Plugin)', or Customize → Plugins in Desktop.)"
}

CODEX_CFG="$HOME/.codex/config.toml"
do_codex_mcp() {
  mkdir -p "$HOME/.codex"
  if [ -f "$CODEX_CFG" ] && grep -q '^\[mcp_servers\.yt-mem-ai\]' "$CODEX_CFG" 2>/dev/null; then
    msg "Codex: 'yt-mem-ai' already in config.toml (left as-is)."
  else
    cat >> "$CODEX_CFG" <<EOF

[mcp_servers.yt-mem-ai]
command = "$(mcp_cmd)"
args = $(mcp_args_json)

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

# shared: copy the yt + yt-manager SKILL.md skills into a host's skills dir
# (local checkout, else fetch each SKILL.md from GitHub).
install_yt_skills() {  # dest_skills_dir  local_integration_dir(may be empty)
  _dest=$1; _isrc=$2
  mkdir -p "$_dest"
  if [ -n "$_isrc" ] && [ -d "$_isrc/skills" ]; then
    cp -RL "$_isrc/skills/yt" "$_isrc/skills/yt-manager" "$_dest/" 2>/dev/null || true
  else
    for s in yt yt-manager; do
      mkdir -p "$_dest/$s"
      curl -LsSf "$RAW_ROOT/skills/$s/SKILL.md" -o "$_dest/$s/SKILL.md" 2>/dev/null || true
    done
  fi
}

do_cursor_skills() {
  install_yt_skills "$CURSOR_SKILLS" "$(src_dir cursor)"
  msg "Cursor: installed skills → ~/.cursor/skills/ (reload Cursor). Skills run the yt-ai CLI via uvx."
}
do_cursor_mcp() {
  json_merge_server "$CURSOR_MCP" "yt-mem-ai"
  msg "Cursor: MCP server merged into ~/.cursor/mcp.json (reload Cursor)."
}
do_antigravity_skills() {
  install_yt_skills "$GRAVITY_SKILLS" "$(src_dir antigravity)"
  msg "Antigravity: installed skills → ~/.gemini/skills/. Skills run the yt-ai CLI via uvx."
}
do_antigravity_mcp() {
  json_merge_server "$GRAVITY_MCP" "yt-mem-ai"
  msg "Antigravity: MCP server merged into ~/.gemini/config/mcp_config.json (restart Antigravity)."
}

# --------------------------------------------------------------------------- #
# per-target uninstallers
# --------------------------------------------------------------------------- #
undo_claude_code_plugin() {
  if have claude; then
    claude plugin uninstall yt-mem-ai@yt-mem-ai >/dev/null 2>&1 \
      && msg "Claude Code: plugin uninstalled." \
      || warn "Claude Code: uninstall failed — run: claude plugin uninstall yt-mem-ai@yt-mem-ai"
  else
    msg "Claude Code plugin — remove in-app: /plugin uninstall yt-mem-ai@yt-mem-ai"
  fi
}
undo_claude_code_mcp() {
  if have claude; then
    claude mcp remove yt-mem-ai >/dev/null 2>&1 && msg "Claude Code: removed MCP server 'yt-mem-ai'." \
      || warn "Claude Code: 'claude mcp remove yt-mem-ai' failed (maybe not present)."
  else warn "Claude Code: 'claude' not on PATH — run: claude mcp remove yt-mem-ai"; fi
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
undo_cursor_skills() {
  rm -rf "$CURSOR_SKILLS/yt" "$CURSOR_SKILLS/yt-manager" 2>/dev/null || true
  msg "Cursor: removed skills from ~/.cursor/skills/."
}
undo_cursor_mcp() {
  json_remove_server "$CURSOR_MCP" "yt-mem-ai"
  msg "Cursor: removed MCP server from ~/.cursor/mcp.json."
}
undo_antigravity_skills() {
  rm -rf "$GRAVITY_SKILLS/yt" "$GRAVITY_SKILLS/yt-manager" 2>/dev/null || true
  msg "Antigravity: removed skills from ~/.gemini/skills/."
}
undo_antigravity_mcp() {
  json_remove_server "$GRAVITY_MCP" "yt-mem-ai"
  msg "Antigravity: removed MCP server from ~/.gemini/config/mcp_config.json."
}

# --------------------------------------------------------------------------- #
# dispatch: removals first, then installs
# --------------------------------------------------------------------------- #
echo
for i in $ITEM_IDS; do
  in_set "$i" "$UNINSTALL" || continue
  case "$i" in
    1) undo_claude_code_plugin ;;   2) undo_claude_code_mcp ;;
    3) undo_claude_desktop_mcp ;;   4) undo_codex_plugin ;;
    5) undo_codex_mcp ;;            6) undo_cursor_skills ;;
    7) undo_cursor_mcp ;;           8) undo_antigravity_skills ;;
    9) undo_antigravity_mcp ;;
  esac
done
for i in $ITEM_IDS; do
  in_set "$i" "$INSTALL" || continue
  case "$i" in
    1) do_claude_code_plugin ;;     2) do_claude_code_mcp ;;
    3) do_claude_desktop_mcp ;;     4) do_codex_plugin ;;
    5) do_codex_mcp ;;              6) do_cursor_skills ;;
    7) do_cursor_mcp ;;             8) do_antigravity_skills ;;
    9) do_antigravity_mcp ;;
  esac
done

echo
_any "$INSTALL" && msg "done. Data dir: $DATA_DIR (override with YT_MEM_AI_HOME)."
_any "$INSTALL" && msg "Set proxy/cookies/embedding vars from chat with 'yt-ai config set', or in each host's config — see integrations/mcp/README.md."
_any "$UNINSTALL" && ! _any "$INSTALL" && msg "done — removed the selected integration(s)."
