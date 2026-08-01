#!/bin/sh
# yt-mem-ai — one installer (POSIX sh).
#
# Two steps:
#   1. what to install   Plugin (skills + yt-ai CLI)  |  MCP (typed tools)
#   2. where             Claude Code · Claude Desktop · Codex · Cursor · Antigravity
#
# Anything that can't be automated (Claude Desktop plugins live on your Claude
# account; a host whose CLI isn't on PATH) prints a bright WARNING with the exact
# manual steps instead of failing silently.
#
#   sh install.sh                            # interactive wizard
#   sh install.sh --plugin --codex --cursor  # non-interactive
#   sh install.sh --all                      # every method × every host
#   curl -LsSf …/install.sh | sh             # no TTY → bootstraps the CLI only
#
# Flags: --plugin --mcp | --claude-code --claude-desktop --codex --cursor
#        --antigravity (alias --gravity) | --all --all-hosts --all-methods
#        -y/--yes  --bootstrap  -h/--help
set -eu

REPO="dasein108/yt-mem-ai"
RAW_ROOT="${YT_INSTALL_RAW_ROOT:-https://raw.githubusercontent.com/${REPO}/main}"
RAW="${RAW_ROOT}/integrations"
DATA_DIR="${YT_MEM_AI_HOME:-$HOME/.yt-mem-ai}"

# --------------------------------------------------------------------------- #
# ui
# --------------------------------------------------------------------------- #
msg()  { printf '%s\n' "yt-mem-ai: $*"; }
warn() { printf '%s\n' "yt-mem-ai: $*" >&2; }
die()  { warn "$*"; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

if [ -t 1 ]; then
  C_RESET=$(printf '\033[0m');   C_HEAD=$(printf '\033[1;36m')
  C_SEL=$(printf '\033[1;32m');  C_DIM=$(printf '\033[2m')
  C_CUR=$(printf '\033[1;33m');  C_WARN=$(printf '\033[1;91m')
  C_KEY=$(printf '\033[1;97m')
else
  C_RESET=; C_HEAD=; C_SEL=; C_DIM=; C_CUR=; C_WARN=; C_KEY=
fi
ESC=$(printf '\033')

# Terminal width: every menu row is truncated to fit, because a wrapped row
# would occupy two physical lines and the redraw (cursor-up by N rows) would
# smear the screen.
COLS=$(tput cols 2>/dev/null || echo 80)
case "$COLS" in ''|*[!0-9]*) COLS=80 ;; esac
[ "$COLS" -lt 30 ] && COLS=80
# row <color> <plain text> — erase the line first so leftovers can't show through
# Menu text is deliberately ASCII: cut works on bytes on some platforms, and a
# half-written multi-byte character would corrupt the line.
row() { printf '\033[2K%s%s%s\n' "$1" "$(printf '%s' "$2" | cut -c1-$((COLS - 1)))" "$C_RESET"; }

# Bright, impossible-to-miss warning block: headline then indented steps.
warnbox() {
  _head=$1; shift
  printf '\n%s  ⚠  %s%s\n' "$C_WARN" "$_head" "$C_RESET" >&2
  for _l in "$@"; do printf '%s     %s%s\n' "$C_KEY" "$_l" "$C_RESET" >&2; done
  printf '\n' >&2
}

# Where does this script live (empty when piped through curl)?
SCRIPT_DIR=""; ENTRY_PATH=""
case "${0:-}" in
  */*) SCRIPT_DIR=$(cd "$(dirname "$0")" 2>/dev/null && pwd || true) ;;
  # `sh install.sh` from the checkout root: $0 carries no directory part.
  *)   [ -f "./integrations/claude-code/.claude-plugin/plugin.json" ] && SCRIPT_DIR=$(pwd) || true ;;
esac
[ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/$(basename "${0:-install.sh}")" ] \
  && ENTRY_PATH="$SCRIPT_DIR/$(basename "$0")" || true
LOCAL_MODE=0
[ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/integrations/claude-code/.claude-plugin/plugin.json" ] && LOCAL_MODE=1
ING="$SCRIPT_DIR/integrations"        # only meaningful when LOCAL_MODE=1

# --------------------------------------------------------------------------- #
# hosts, methods, paths
# --------------------------------------------------------------------------- #
case "$(uname -s 2>/dev/null || echo unknown)" in
  Darwin) DESKTOP_CFG="$HOME/Library/Application Support/Claude/claude_desktop_config.json" ;;
  *)      DESKTOP_CFG="$HOME/.config/Claude/claude_desktop_config.json" ;;
esac
PY=$(command -v python3 2>/dev/null || true)
CODEX_CFG="$HOME/.codex/config.toml"
CODEX_SKILLS="$HOME/.codex/skills"
CURSOR_MCP="$HOME/.cursor/mcp.json"
CURSOR_SKILLS="$HOME/.cursor/skills"
GRAVITY_MCP="$HOME/.gemini/config/mcp_config.json"
GRAVITY_SKILLS="$HOME/.gemini/skills"

METHODS="plugin mcp"
HOSTS="claude-code claude-desktop codex cursor antigravity"

method_label() {
  case "$1" in
    plugin) echo "Plugin  - yt/yt-agent skills + the yt-ai CLI";;
    mcp)    echo "MCP     - yt-ai-mcp server (typed tools)";;
  esac
}
host_label() {
  case "$1" in
    claude-code)    echo "Claude Code   ";;
    claude-desktop) echo "Claude Desktop";;
    codex)          echo "Codex          (CLI + IDE)";;
    cursor)         echo "Cursor        ";;
    antigravity)    echo "Antigravity   ";;
  esac
}
host_detected() {
  case "$1" in
    claude-code)    have claude ;;
    claude-desktop) [ -e "$(dirname "$DESKTOP_CFG")" ] ;;
    codex)          have codex || [ -d "$HOME/.codex" ] ;;
    cursor)         have cursor || [ -d "$HOME/.cursor" ] ;;
    antigravity)    have antigravity || [ -d "$HOME/.gemini" ] ;;
  esac
}

# Does this JSON config actually register the MCP server? A plain grep would
# match unrelated mentions of the name (Claude Code stores a githubRepoPaths
# entry for a yt-mem-ai checkout, which made "MCP" look installed after a plugin
# install), so look the key up inside an mcpServers map — including the
# project-scoped maps Claude Code writes under "projects".
json_has_server() {  # file
  [ -f "$1" ] || return 1
  if [ -n "$PY" ]; then
    YT_FILE="$1" "$PY" - <<'PYEOF' >/dev/null 2>&1
import json, os, sys
try:
    cfg = json.load(open(os.environ["YT_FILE"]))
except Exception:
    sys.exit(1)
def has(node):
    if isinstance(node, dict):
        if isinstance(node.get("mcpServers"), dict) and "yt-mem-ai" in node["mcpServers"]:
            return True
        return any(has(v) for v in node.values())
    if isinstance(node, list):
        return any(has(v) for v in node)
    return False
sys.exit(0 if has(cfg) else 1)
PYEOF
  else
    grep -qs '"yt-mem-ai"[[:space:]]*:' "$1" 2>/dev/null
  fi
}
# Claude Code enables plugins by "<plugin>@<marketplace>" in settings.json.
# (extraKnownMarketplaces can mention yt-mem-ai without the plugin installed.)
claude_plugin_installed() {
  grep -qs '"yt-mem-ai@yt-mem-ai"' "$HOME/.claude/settings.json" 2>/dev/null \
    || [ -d "$HOME/.claude/plugins/cache/yt-mem-ai" ]
}

# Is this method×host pair already installed? File checks only (fast, no CLI).
pair_installed() {  # method host
  case "$1:$2" in
    plugin:claude-code)    claude_plugin_installed ;;
    # Claude Desktop plugins live on your Claude account, not on disk — nothing
    # local to probe, install, or remove. Always "not installed"; we print steps.
    plugin:claude-desktop) return 1 ;;
    plugin:codex)          [ -e "$CODEX_SKILLS/yt/SKILL.md" ] ;;
    plugin:cursor)         [ -e "$CURSOR_SKILLS/yt/SKILL.md" ] ;;
    plugin:antigravity)    [ -e "$GRAVITY_SKILLS/yt/SKILL.md" ] ;;
    mcp:claude-code)       json_has_server "$HOME/.claude.json" ;;
    mcp:claude-desktop)    json_has_server "$DESKTOP_CFG" ;;
    mcp:codex)             grep -qs '^\[mcp_servers\.yt-mem-ai\]' "$CODEX_CFG" 2>/dev/null ;;
    mcp:cursor)            json_has_server "$CURSOR_MCP" ;;
    mcp:antigravity)       json_has_server "$GRAVITY_MCP" ;;
    *) return 1 ;;
  esac
}
pair_label() { printf '%s / %s' "$(printf '%s' "$1" | tr 'a-z' 'A-Z')" "$(host_label "$2")"; }

# --------------------------------------------------------------------------- #
# set helpers (space-delimited strings; dash/bash-3 safe, no arrays)
# --------------------------------------------------------------------------- #
in_set()  { case " $2 " in *" $1 "*) return 0;; esac; return 1; }
add_to()  { # var-name value
  eval "_cur=\$$1"
  in_set "$2" "$_cur" || eval "$1=\"\$$1 \$2 \""
}
del_from() { eval "$1=\$(printf '%s' \" \$$1 \" | sed \"s/ \$2 / /g\")"; }
_any()    { [ -n "$(printf '%s' "$1" | tr -d ' ')" ]; }

# --------------------------------------------------------------------------- #
# flags
# --------------------------------------------------------------------------- #
SEL_M=" "; SEL_H=" "
ASSUME_YES=0; NONINTERACTIVE=0; FORCE_BOOTSTRAP=0
usage() {
  cat <<EOF
yt-mem-ai installer

  sh install.sh                             two-step wizard (what → where)
  sh install.sh --plugin --codex --cursor   non-interactive
  sh install.sh --all                       every method × every host

What:  --plugin (skills + yt-ai CLI)   --mcp (yt-ai-mcp server)   --all-methods
Where: --claude-code  --claude-desktop  --codex  --cursor  --antigravity (--gravity)
       --all-hosts
Other: --all  -y/--yes  --bootstrap (just install the CLI)  -h/--help
EOF
  exit 0
}
for arg in "$@"; do
  case "$arg" in
    -h|--help) usage ;;
    -y|--yes) ASSUME_YES=1 ;;
    --bootstrap) FORCE_BOOTSTRAP=1 ;;
    --plugin|--skills|--plugin=*) add_to SEL_M plugin; NONINTERACTIVE=1 ;;
    --mcp|--mcp=*)                add_to SEL_M mcp;    NONINTERACTIVE=1 ;;
    --all-methods) SEL_M=" plugin mcp "; NONINTERACTIVE=1 ;;
    --all-hosts)   SEL_H=" $HOSTS ";     NONINTERACTIVE=1 ;;
    --all) SEL_M=" plugin mcp "; SEL_H=" $HOSTS "; NONINTERACTIVE=1 ;;
    --claude-code|--claude-code=*)       add_to SEL_H claude-code;    NONINTERACTIVE=1 ;;
    --claude-desktop|--claude-desktop=*) add_to SEL_H claude-desktop; NONINTERACTIVE=1 ;;
    --codex|--codex=*)                   add_to SEL_H codex;          NONINTERACTIVE=1 ;;
    --cursor|--cursor=*)                 add_to SEL_H cursor;         NONINTERACTIVE=1 ;;
    --antigravity|--antigravity=*|--gravity|--gravity=*) add_to SEL_H antigravity; NONINTERACTIVE=1 ;;
    *) die "unknown argument: $arg (try --help)" ;;
  esac
done
# Hosts named but no method → skills, the recommended path.
[ "$NONINTERACTIVE" -eq 1 ] && ! _any "$SEL_M" && SEL_M=" plugin "
[ "$NONINTERACTIVE" -eq 1 ] && ! _any "$SEL_H" && SEL_H=" $HOSTS "

# --------------------------------------------------------------------------- #
# uv + payload bootstrap
# --------------------------------------------------------------------------- #
UVX=""; MCP_BIN=""; YT_BIN=""

ensure_uv() {
  if ! have uv; then
    msg "installing uv (provides Python + uvx)…"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
  fi
  have uvx || die "uvx not on PATH after installing uv (add ~/.local/bin to PATH and re-run)."
  UVX=$(command -v uvx)
}
_find_bin() {  # name → absolute path or empty
  _p=$(command -v "$1" 2>/dev/null || true)
  if [ -z "$_p" ]; then
    for _d in "$(uv tool dir --bin 2>/dev/null || true)" "$HOME/.local/bin"; do
      [ -n "$_d" ] && [ -x "$_d/$1" ] && { _p="$_d/$1"; break; }
    done
  fi
  printf '%s' "$_p"
}
# Skills shell out to the CLI → install it as a real binary (uvx stays a fallback).
ensure_yt_ai_cli() {
  msg "installing the yt-ai CLI (uv tool install yt-mem-ai) — first run pulls ML deps, please wait…"
  uv tool install --force yt-mem-ai >/dev/null 2>&1 || uv tool install yt-mem-ai || true
  YT_BIN=$(_find_bin yt-ai)
  if [ -n "$YT_BIN" ]; then msg "CLI ready: $YT_BIN (skills also work via 'uvx yt-mem-ai')."
  else warn "couldn't locate the yt-ai binary — skills fall back to 'uvx yt-mem-ai' (slower first run)."; fi
}
# MCP hosts get an absolute binary: no uvx cold start to time out the handshake,
# and no bare "uvx" a GUI app can't find on PATH.
ensure_yt_ai_mcp() {
  msg "installing the yt-ai-mcp server (uv tool install 'yt-mem-ai[mcp]') — first run pulls ML deps, please wait…"
  uv tool install --force "yt-mem-ai[mcp]" >/dev/null 2>&1 || uv tool install "yt-mem-ai[mcp]" || true
  MCP_BIN=$(_find_bin yt-ai-mcp)
  if [ -n "$MCP_BIN" ]; then msg "server ready: $MCP_BIN"
  else warn "couldn't locate the yt-ai-mcp binary — MCP configs fall back to uvx (slower cold start)."; fi
}
mcp_cmd()       { [ -n "$MCP_BIN" ] && printf '%s' "$MCP_BIN" || printf '%s' "${UVX:-uvx}"; }
mcp_args_json() { [ -n "$MCP_BIN" ] && printf '[]' || printf '["--from", "yt-mem-ai[mcp]", "yt-ai-mcp"]'; }

# `curl … | sh` with no flags: the shell is reading THIS script from stdin, so we
# can't just point stdin at the terminal (that would truncate the script). Grab a
# copy on disk and re-exec it with the real terminal attached — that's what makes
# the one-line install interactive.
if [ "$FORCE_BOOTSTRAP" -eq 0 ] && [ "$NONINTERACTIVE" -eq 0 ] \
   && [ ! -t 0 ] && [ -t 1 ] && [ -r /dev/tty ] && [ -z "${YT_INSTALL_REEXEC:-}" ]; then
  _self=$(mktemp "${TMPDIR:-/tmp}/yt-mem-ai-install.XXXXXX") || _self=""
  if [ -n "$_self" ] && curl -LsSf "$RAW_ROOT/install.sh" -o "$_self" 2>/dev/null && [ -s "$_self" ]; then
    YT_INSTALL_REEXEC=1 export YT_INSTALL_REEXEC
    sh "$_self" "$@" < /dev/tty; _rc=$?
    rm -f "$_self"
    exit "$_rc"
  fi
  [ -n "$_self" ] && rm -f "$_self"
  warn "couldn't fetch the installer for interactive mode — installing the CLI only."
fi

# No terminal at all (CI, or the re-exec above failed) → just make the CLI available.
if [ "$FORCE_BOOTSTRAP" -eq 1 ] || { [ "$NONINTERACTIVE" -eq 0 ] && [ ! -t 0 ]; }; then
  ensure_uv
  ensure_yt_ai_cli
  echo
  msg "ready:  yt-ai --help    (or: uvx yt-mem-ai --help)"
  msg "to wire up hosts (skills and/or MCP):"
  msg "  curl -LsSf $RAW_ROOT/install.sh -o install.sh && sh install.sh"
  msg "  or in one shot:  curl -LsSf $RAW_ROOT/install.sh | sh -s -- --mcp --claude-desktop"
  exit 0
fi

# --------------------------------------------------------------------------- #
# checkbox screens
#   pick_screen <title> <hint> <items> <label-fn> <status-fn>   in/out: PICK
# --------------------------------------------------------------------------- #
PICK=" "
pick_render() {  # title hint items label-fn status-fn cursor
  _t=$1; _hint=$2; _items=$3; _lf=$4; _sf=$5; _c=$6
  row "$C_HEAD" "  $_t"
  row "$C_DIM"  "  $_hint"
  row "" ""
  for _it in $_items; do
    if in_set "$_it" "$PICK"; then _box="[x]"; else _box="[ ]"; fi
    _lab="$($_lf "$_it")"
    _st="$($_sf "$_it")"
    [ -n "$_st" ] && _lab="$_lab $_st"
    if [ "$_it" = "$_c" ]; then row "$C_CUR" "  > $_box $_lab"
    elif in_set "$_it" "$PICK"; then row "$C_SEL" "    $_box $_lab"
    else row "" "    $_box $_lab"; fi
  done
}
pick_screen() {
  _t=$1; _hint=$2; _items=$3; _lf=$4; _sf=$5
  _rows=3; for _x in $_items; do _rows=$((_rows + 1)); done
  if [ -z "${BASH_VERSION:-}" ] || [ ! -t 0 ] || [ ! -t 1 ]; then
    pick_plain "$_t" "$_hint" "$_items" "$_lf" "$_sf"; return
  fi
  _cur=$(printf '%s' "$_items" | cut -d' ' -f1)
  _first=1
  printf '\033[?25l'
  trap 'printf "\033[?25h\n"' EXIT
  trap 'printf "\033[?25h\n"; exit 130' INT
  while :; do
    if [ "$_first" = 1 ]; then _first=0; else printf '\033[%dA' "$_rows"; fi
    pick_render "$_t" "$_hint" "$_items" "$_lf" "$_sf" "$_cur"
    if ! IFS= read -rsn1 _k 2>/dev/null; then
      trap - EXIT INT; printf '\033[?25h\n'; msg "aborted."; exit 0
    fi
    case "$_k" in
      "$ESC")
        IFS= read -rsn2 -t 1 _r 2>/dev/null || _r=""
        case "$_r" in
          "[A") _cur=$(_neighbour "$_items" "$_cur" up) ;;
          "[B") _cur=$(_neighbour "$_items" "$_cur" down) ;;
        esac ;;
      k|K) _cur=$(_neighbour "$_items" "$_cur" up) ;;
      j|J) _cur=$(_neighbour "$_items" "$_cur" down) ;;
      " ") if in_set "$_cur" "$PICK"; then del_from PICK "$_cur"; else add_to PICK "$_cur"; fi ;;
      a|A) for _it in $_items; do add_to PICK "$_it"; done ;;
      n|N) PICK=" " ;;
      q|Q) trap - EXIT INT; printf '\033[?25h\n'; msg "aborted."; exit 0 ;;
      "")  break ;;
    esac
  done
  trap - EXIT INT
  printf '\033[?25h'
}
_neighbour() {  # items current up|down
  _items=$1; _c=$2; _dir=$3; _prev=""; _first=""; _take=0; _res=""
  for _it in $_items; do
    [ -z "$_first" ] && _first=$_it
    if [ "$_take" = 1 ]; then _res=$_it; _take=0; fi
    if [ "$_it" = "$_c" ]; then
      if [ "$_dir" = up ]; then _res=$_prev; else _take=1; fi
    fi
    _prev=$_it
  done
  if [ -z "$_res" ]; then
    [ "$_dir" = up ] && _res=$_prev || _res=$_first
  fi
  printf '%s' "$_res"
}
pick_plain() {  # numbered fallback (no bash / no cursor addressing)
  _t=$1; _hint=$2; _items=$3; _lf=$4; _sf=$5
  while :; do
    printf '\n  %s\n  %s\n\n' "$_t" "$_hint"
    _n=0
    for _it in $_items; do
      _n=$((_n + 1)); _m=" "; in_set "$_it" "$PICK" && _m="x"
      printf '   [%s] %s) %s %s\n' "$_m" "$_n" "$($_lf "$_it")" "$($_sf "$_it")"
    done
    printf '\n   number = toggle, "a" = all, "n" = none, enter = continue, "q" = quit: '
    read -r _ans || _ans=q
    case "$_ans" in
      "") break ;;
      a|A) for _it in $_items; do add_to PICK "$_it"; done ;;
      n|N) PICK=" " ;;
      q|Q) msg "aborted."; exit 0 ;;
      [0-9]*)
        _n=0
        for _it in $_items; do
          _n=$((_n + 1))
          if [ "$_n" = "$_ans" ]; then
            if in_set "$_it" "$PICK"; then del_from PICK "$_it"; else add_to PICK "$_it"; fi
          fi
        done ;;
      *) : ;;
    esac
  done
}

# status suffixes shown in the pickers
host_status() {
  _out=""
  for _m in $SEL_M_FINAL; do if pair_installed "$_m" "$1"; then _out="$_out $_m"; fi; done
  if [ -n "$_out" ]; then printf '(installed)'
  elif ! host_detected "$1"; then printf '(not detected)'; fi
  return 0
}

# --------------------------------------------------------------------------- #
# step 1: single choice (a radio list, not checkboxes) → CHOICE holds the
# chosen method (" plugin " or " mcp "). Want both? Run the installer twice, or
# pass --all-methods.
# --------------------------------------------------------------------------- #
CHOICE=" "
CHOICES="plugin mcp"
choice_status() {
  for _h in $HOSTS; do if pair_installed "$1" "$_h"; then printf '(installed)'; return 0; fi; done
  return 0
}

choose_method() {
  _title="yt-mem-ai - step 1/2: what to install"
  _hint="up/down move - enter select - q quit"
  if [ -z "${BASH_VERSION:-}" ] || [ ! -t 0 ] || [ ! -t 1 ]; then
    while :; do
      printf '\n  %s\n\n' "$_title"
      _n=0
      for _c in $CHOICES; do
        _n=$((_n + 1)); printf '   %s) %s %s\n' "$_n" "$(method_label "$_c")" "$(choice_status "$_c")"
      done
      printf '\n   Choose [1-2] (q to quit): '
      read -r _a || _a=q
      case "$_a" in
        1) CHOICE=" plugin "; return 0 ;;
        2) CHOICE=" mcp ";    return 0 ;;
        q|Q) msg "aborted."; exit 0 ;;
        *) : ;;
      esac
    done
  fi
  _cur=plugin; _first=1; _rows=5
  printf '\033[?25l'
  trap 'printf "\033[?25h\n"' EXIT
  trap 'printf "\033[?25h\n"; exit 130' INT
  while :; do
    if [ "$_first" = 1 ]; then _first=0; else printf '\033[%dA' "$_rows"; fi
    row "$C_HEAD" "  $_title"
    row "$C_DIM"  "  $_hint"
    row "" ""
    for _c in $CHOICES; do
      _lab="$(method_label "$_c") $(choice_status "$_c")"
      if [ "$_c" = "$_cur" ]; then row "$C_CUR" "  > $_lab"
      else row "" "    $_lab"; fi
    done
    if ! IFS= read -rsn1 _k 2>/dev/null; then
      trap - EXIT INT; printf '\033[?25h\n'; msg "aborted."; exit 0
    fi
    case "$_k" in
      "$ESC")
        IFS= read -rsn2 -t 1 _r 2>/dev/null || _r=""
        case "$_r" in
          "[A") _cur=$(_neighbour "$CHOICES" "$_cur" up) ;;
          "[B") _cur=$(_neighbour "$CHOICES" "$_cur" down) ;;
        esac ;;
      k|K) _cur=$(_neighbour "$CHOICES" "$_cur" up) ;;
      j|J) _cur=$(_neighbour "$CHOICES" "$_cur" down) ;;
      1) _cur=plugin ;;  2) _cur=mcp ;;
      q|Q) trap - EXIT INT; printf '\033[?25h\n'; msg "aborted."; exit 0 ;;
      "")  break ;;
    esac
  done
  trap - EXIT INT
  # Collapse this screen so step 2 replaces it instead of stacking below it.
  printf '\033[%dA\033[J\033[?25h' "$_rows"
  CHOICE=" $_cur "
}

# --------------------------------------------------------------------------- #
# step 1 (what) → step 2 (where)
# --------------------------------------------------------------------------- #
SEL_M_FINAL=""
if [ "$NONINTERACTIVE" -eq 0 ]; then
  choose_method                             # single choice — no checkboxes here
  SEL_M="$CHOICE"
  SEL_M_FINAL=$(printf '%s' "$SEL_M")

  PICK=" "
  for _h in $HOSTS; do
    for _m in $SEL_M; do
      if pair_installed "$_m" "$_h"; then add_to PICK "$_h"; break; fi
    done
  done
  _for=$(printf '%s' "$SEL_M" | tr -s ' ' | sed 's/^ //; s/ $//')
  pick_screen "yt-mem-ai - step 2/2: where ($_for)" \
    "space toggle - a all - n none - enter apply - q quit (untick = remove)" \
    "$HOSTS" host_label host_status
  SEL_H="$PICK"
fi
SEL_M_FINAL="$SEL_M"

# --------------------------------------------------------------------------- #
# diff → plan.  Scope is the SELECTED methods only: a method you didn't tick is
# never touched, so picking "plugin" can't wipe your MCP configs. Flag runs are
# additive — only the wizard (where installed targets show pre-ticked) removes.
# --------------------------------------------------------------------------- #
INSTALL=" "; UNINSTALL=" "
for m in $SEL_M; do
  for h in $HOSTS; do
    if in_set "$h" "$SEL_H"; then
      if ! pair_installed "$m" "$h"; then INSTALL="$INSTALL$m:$h "; fi
    elif [ "$NONINTERACTIVE" -eq 0 ]; then
      if pair_installed "$m" "$h"; then UNINSTALL="$UNINSTALL$m:$h "; fi
    fi
  done
done
_any "$INSTALL" || _any "$UNINSTALL" || { msg "no changes."; exit 0; }

echo
msg "plan:"
for p in $INSTALL;   do printf '   %s+ install%s %s\n' "$C_SEL" "$C_RESET" "$(pair_label "${p%%:*}" "${p#*:}")"; done
for p in $UNINSTALL; do printf '   %s- remove %s %s\n' "$C_CUR" "$C_RESET" "$(pair_label "${p%%:*}" "${p#*:}")"; done

if _any "$UNINSTALL" && [ "$ASSUME_YES" -eq 0 ] && [ -t 0 ]; then
  printf '\nApply this plan (includes removals)? [y/N] '; read -r ok || ok=n
  case "$ok" in y*|Y*) : ;; *) msg "aborted."; exit 0 ;; esac
elif ! _any "$UNINSTALL" && [ "$ASSUME_YES" -eq 0 ] && [ "$NONINTERACTIVE" -eq 1 ] && [ -t 0 ]; then
  printf '\nProceed? [Y/n] '; read -r ok || ok=n
  case "$ok" in n*|N*) msg "aborted."; exit 0 ;; esac
fi

# --------------------------------------------------------------------------- #
# preflight
# --------------------------------------------------------------------------- #
_need_plugin=0; _need_mcp=0
for p in $INSTALL; do
  case "${p%%:*}" in plugin) _need_plugin=1 ;; mcp) _need_mcp=1 ;; esac
done
if _any "$INSTALL"; then
  ensure_uv
  mkdir -p "$DATA_DIR/lance" "$DATA_DIR/logs" "$DATA_DIR/downloads"
  [ "$_need_plugin" = 1 ] && ensure_yt_ai_cli
  [ "$_need_mcp" = 1 ] && ensure_yt_ai_mcp
fi

# --------------------------------------------------------------------------- #
# config writers
# --------------------------------------------------------------------------- #
json_merge_server() {  # file name
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
    warnbox "python3 not found and $_file already exists — add the server by hand:" \
      "\"yt-mem-ai\": { \"command\": \"$_cmd\", \"args\": $_args }"
  fi
}
json_remove_server() {  # file name
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
    warnbox "python3 not found — remove \"$_name\" from $_file by hand."
  fi
}
toml_remove_yt() {
  _file=$1
  [ -f "$_file" ] || return 0
  awk '
    /^[[:space:]]*\[/ { skip = ($0 ~ /^[[:space:]]*\[mcp_servers\.yt-mem-ai([].]|$)/) ? 1 : 0 }
    skip != 1 { print }
  ' "$_file" > "$_file.tmp" 2>/dev/null && mv "$_file.tmp" "$_file"
}

# copy the canonical yt + yt-agent SKILL.md into a host's skills dir.
# Returns non-zero (and warns) if a skill file didn't land — a silent empty
# SKILL.md would look installed but do nothing.
install_yt_skills() {  # dest_dir  [local_integration_subdir]
  _dest=$1; _sub=${2:-}
  mkdir -p "$_dest"
  if [ "$LOCAL_MODE" = 1 ] && [ -n "$_sub" ] && [ -d "$ING/$_sub/skills" ]; then
    cp -RL "$ING/$_sub/skills/yt" "$ING/$_sub/skills/yt-agent" "$_dest/" 2>/dev/null || true
  elif [ "$LOCAL_MODE" = 1 ] && [ -d "$SCRIPT_DIR/skills" ]; then
    cp -RL "$SCRIPT_DIR/skills/yt" "$SCRIPT_DIR/skills/yt-agent" "$_dest/" 2>/dev/null || true
  else
    for s in yt yt-agent; do
      mkdir -p "$_dest/$s"
      curl -LsSf "$RAW_ROOT/skills/$s/SKILL.md" -o "$_dest/$s/SKILL.md" 2>/dev/null || true
    done
  fi
  for s in yt yt-agent; do
    if [ ! -s "$_dest/$s/SKILL.md" ]; then
      rm -rf "$_dest/$s" 2>/dev/null || true
      warnbox "couldn't fetch the '$s' skill (no network, or GitHub unreachable)." \
        "Copy it by hand from a checkout:  cp -R skills/$s $_dest/" \
        "or download:  curl -LsSf $RAW_ROOT/skills/$s/SKILL.md -o $_dest/$s/SKILL.md"
      return 1
    fi
  done
  return 0
}

# --------------------------------------------------------------------------- #
# per-pair install / uninstall
# --------------------------------------------------------------------------- #
CODEX_PROMPTS="yt-summarize yt-highlights yt-qa yt-presentation yt-digest yt-review yt-group yt-config yt-setup"

host_missing_warning() {  # host — bright note when the app isn't on this machine
  host_detected "$1" && return 0
  case "$1" in
    claude-code)    warnbox "Claude Code not found on PATH." \
                      "Install it:  npm i -g @anthropic-ai/claude-code   (or see claude.com/product/claude-code)" \
                      "Then re-run this installer." ;;
    claude-desktop) warnbox "Claude Desktop config dir not found — is the app installed?" \
                      "Get it: https://claude.ai/download   Config lands at:" "$DESKTOP_CFG" ;;
    codex)          warnbox "Codex not detected (~/.codex missing)." \
                      "Files are written anyway — Codex will pick them up once installed." ;;
    cursor)         warnbox "Cursor not detected (~/.cursor missing)." \
                      "Files are written anyway — Cursor will pick them up once installed." ;;
    antigravity)    warnbox "Antigravity not detected (~/.gemini missing)." \
                      "Files are written anyway — Antigravity will pick them up once installed." ;;
  esac
}

install_pair() {  # method host
  case "$1:$2" in
    plugin:claude-code)
      _src="$REPO"; [ "$LOCAL_MODE" = 1 ] && _src="$ING/claude-code"
      if have claude; then
        claude plugin marketplace add "$_src" >/dev/null 2>&1 || true
        if claude plugin install yt-mem-ai@yt-mem-ai >/dev/null 2>&1; then
          msg "Claude Code: plugin installed (yt + yt-agent skills, /yt-* commands) → ~/.claude/plugins."
        else
          warnbox "Claude Code: automatic plugin install failed. Run these inside Claude Code:" \
            "/plugin marketplace add $_src" \
            "/plugin install yt-mem-ai@yt-mem-ai"
        fi
      else
        warnbox "Claude Code: the 'claude' CLI isn't on PATH, so the plugin can't be installed for you." \
          "Inside Claude Code run:" \
          "/plugin marketplace add $_src" \
          "/plugin install yt-mem-ai@yt-mem-ai"
      fi ;;

    plugin:claude-desktop)
      warnbox "Claude Desktop plugins live on your Claude ACCOUNT, not on disk — no script can install them." \
        "Do this in the app (one minute):" \
        "Customize (left sidebar) → Plugins → Personal plugins → +" \
        "→ Add marketplace → Add from a repository" \
        "→ https://github.com/$REPO → Add → Install 'yt-mem-ai'" \
        "Uninstall the same way. Prefer typed tools? Re-run and tick MCP for Claude Desktop." ;;

    plugin:codex)
      mkdir -p "$CODEX_SKILLS" "$HOME/.codex/prompts"
      if install_yt_skills "$CODEX_SKILLS" codex; then
        if [ "$LOCAL_MODE" = 1 ] && [ -d "$ING/codex/prompts" ]; then
          cp "$ING/codex"/prompts/*.md "$HOME/.codex/prompts/" 2>/dev/null || true
          cp "$ING/codex/AGENTS.md" "$HOME/.codex/AGENTS.md" 2>/dev/null || true
        else
          for p in $CODEX_PROMPTS; do
            curl -LsSf "$RAW/codex/prompts/$p.md" -o "$HOME/.codex/prompts/$p.md" 2>/dev/null || true
          done
          curl -LsSf "$RAW/codex/AGENTS.md" -o "$HOME/.codex/AGENTS.md" 2>/dev/null || true
        fi
        msg "Codex: skills + prompts + ~/.codex/AGENTS.md installed (CLI and IDE share ~/.codex)."
      fi ;;

    plugin:cursor)
      install_yt_skills "$CURSOR_SKILLS" cursor \
        && msg "Cursor: skills installed → ~/.cursor/skills/ (reload Cursor)." ;;

    plugin:antigravity)
      install_yt_skills "$GRAVITY_SKILLS" antigravity \
        && msg "Antigravity: skills installed → ~/.gemini/skills/ (restart Antigravity)." ;;

    mcp:claude-code)
      if have claude; then
        if [ -n "$MCP_BIN" ]; then
          claude mcp add -s user yt-mem-ai -e "YT_STORE_PATH=$DATA_DIR/lance" \
            -e "YT_LOG_FILE=$DATA_DIR/logs/common.jsonl" -e "YT_DOWNLOADS_DIR=$DATA_DIR/downloads" \
            -- "$MCP_BIN" >/dev/null 2>&1
        else
          claude mcp add -s user yt-mem-ai -e "YT_STORE_PATH=$DATA_DIR/lance" \
            -e "YT_LOG_FILE=$DATA_DIR/logs/common.jsonl" -e "YT_DOWNLOADS_DIR=$DATA_DIR/downloads" \
            -- "$UVX" --from "yt-mem-ai[mcp]" yt-ai-mcp >/dev/null 2>&1
        fi && msg "Claude Code: added MCP server 'yt-mem-ai'." \
           || warnbox "Claude Code: 'claude mcp add' failed. Run it yourself:" \
                "claude mcp add yt-mem-ai -- ${MCP_BIN:-uvx --from 'yt-mem-ai[mcp]' yt-ai-mcp}"
      else
        warnbox "Claude Code: the 'claude' CLI isn't on PATH." \
          "After installing it, run:" \
          "claude mcp add yt-mem-ai -- ${MCP_BIN:-uvx --from 'yt-mem-ai[mcp]' yt-ai-mcp}"
      fi ;;

    mcp:claude-desktop)
      json_merge_server "$DESKTOP_CFG" "yt-mem-ai"
      msg "Claude Desktop: MCP server merged into $(basename "$DESKTOP_CFG") — restart the app." ;;

    mcp:codex)
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
        msg "Codex: MCP server appended to $CODEX_CFG."
      fi ;;

    mcp:cursor)
      json_merge_server "$CURSOR_MCP" "yt-mem-ai"
      msg "Cursor: MCP server merged into ~/.cursor/mcp.json (reload Cursor)." ;;

    mcp:antigravity)
      json_merge_server "$GRAVITY_MCP" "yt-mem-ai"
      msg "Antigravity: MCP server merged into ~/.gemini/config/mcp_config.json (restart Antigravity)." ;;
  esac
}

uninstall_pair() {  # method host
  case "$1:$2" in
    plugin:claude-code)
      if have claude; then
        claude plugin uninstall yt-mem-ai@yt-mem-ai >/dev/null 2>&1 \
          && msg "Claude Code: plugin uninstalled." \
          || warnbox "Claude Code: uninstall failed. Run: claude plugin uninstall yt-mem-ai@yt-mem-ai"
      else
        warnbox "Claude Code: 'claude' not on PATH — remove it in-app:" "/plugin uninstall yt-mem-ai@yt-mem-ai"
      fi ;;
    plugin:claude-desktop)
      warnbox "Claude Desktop: remove it in the app — Customize → Plugins → yt-mem-ai → Uninstall." ;;
    plugin:codex)
      rm -rf "$CODEX_SKILLS/yt" "$CODEX_SKILLS/yt-agent" 2>/dev/null || true
      for p in $CODEX_PROMPTS; do rm -f "$HOME/.codex/prompts/$p.md" 2>/dev/null || true; done
      msg "Codex: skills + prompts removed. (~/.codex/AGENTS.md left alone — delete it by hand if it's ours.)" ;;
    plugin:cursor)
      rm -rf "$CURSOR_SKILLS/yt" "$CURSOR_SKILLS/yt-agent" 2>/dev/null || true
      msg "Cursor: skills removed from ~/.cursor/skills/." ;;
    plugin:antigravity)
      rm -rf "$GRAVITY_SKILLS/yt" "$GRAVITY_SKILLS/yt-agent" 2>/dev/null || true
      msg "Antigravity: skills removed from ~/.gemini/skills/." ;;
    mcp:claude-code)
      if have claude; then
        { claude mcp remove -s user yt-mem-ai >/dev/null 2>&1 || claude mcp remove yt-mem-ai >/dev/null 2>&1; } && msg "Claude Code: MCP server removed." \
          || warnbox "Claude Code: 'claude mcp remove yt-mem-ai' failed (maybe not present)."
      else warnbox "Claude Code: 'claude' not on PATH — run: claude mcp remove yt-mem-ai"; fi ;;
    mcp:claude-desktop)
      json_remove_server "$DESKTOP_CFG" "yt-mem-ai"
      msg "Claude Desktop: MCP server removed — restart the app." ;;
    mcp:codex)
      toml_remove_yt "$CODEX_CFG"; msg "Codex: MCP server removed from config.toml." ;;
    mcp:cursor)
      json_remove_server "$CURSOR_MCP" "yt-mem-ai"; msg "Cursor: MCP server removed." ;;
    mcp:antigravity)
      json_remove_server "$GRAVITY_MCP" "yt-mem-ai"; msg "Antigravity: MCP server removed." ;;
  esac
}

# --------------------------------------------------------------------------- #
# apply: removals first, then installs
# --------------------------------------------------------------------------- #
echo
for p in $UNINSTALL; do uninstall_pair "${p%%:*}" "${p#*:}" || true; done
_warned=" "
for p in $INSTALL; do
  _h=${p#*:}
  in_set "$_h" "$_warned" || { host_missing_warning "$_h"; _warned="$_warned$_h "; }
  install_pair "${p%%:*}" "$_h" || true
done

echo
if _any "$INSTALL"; then
  msg "done. Data dir: $DATA_DIR (override with YT_MEM_AI_HOME)."
  msg "Configure any time:  yt-ai config set <KEY> <VALUE>   (yt-ai config list shows everything)"
  in_set plugin "$SEL_M" && msg "Try it: ask your assistant — summarize 'https://youtu.be/…'" || true
fi
_any "$UNINSTALL" && ! _any "$INSTALL" && msg "done — removed the selected integration(s)." || true
exit 0
