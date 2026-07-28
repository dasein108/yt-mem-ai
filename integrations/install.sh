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
    1) echo "Claude Code    (Plugin: skills + commands + MCP)";;
    2) echo "Claude Code    (MCP only)";;
    3) echo "Claude Desktop (Bundle .mcpb)";;
    4) echo "Claude Desktop (MCP config)";;
    5) echo "Codex          (Plugin: skills + MCP + prompts + AGENTS.md)";;
    6) echo "Codex          (MCP only)";;
    7) echo "Gemini CLI     (Extension: MCP + commands)";;
    8) echo "Gemini CLI     (MCP only)";;
  esac
}
DESKTOP_CFG=""
case "$(uname -s 2>/dev/null || echo unknown)" in
  Darwin) DESKTOP_CFG="$HOME/Library/Application Support/Claude/claude_desktop_config.json" ;;
  *)      DESKTOP_CFG="$HOME/.config/Claude/claude_desktop_config.json" ;;
esac
item_detected() {
  case "$(item_host "$1")" in
    claude-code)    have claude && echo yes || echo no ;;
    claude-desktop) [ -e "$(dirname "$DESKTOP_CFG")" ] && echo yes || echo no ;;
    codex)          have codex && echo yes || echo no ;;
    gemini)         have gemini && echo yes || echo no ;;
  esac
}

# --------------------------------------------------------------------------- #
# selection state (space-delimited item ids; dash/bash-3 safe, no arrays)
# --------------------------------------------------------------------------- #
SEL=" "
is_sel()  { case "$SEL" in *" $1 "*) return 0;; esac; return 1; }
add_sel() { is_sel "$1" || SEL="$SEL$1 "; }
toggle()  { if is_sel "$1"; then SEL=$(printf '%s' "$SEL" | sed "s/ $1 / /"); else SEL="$SEL$1 "; fi; }

# --------------------------------------------------------------------------- #
# argument parsing → selection + mode
# --------------------------------------------------------------------------- #
ASSUME_YES=0
NONINTERACTIVE=0
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
    _on=off; [ "$(item_detected "$i")" = yes ] && _on=on
    _args="$_args $i \"$(item_label "$i")\" $_on"
  done
  _chosen=$(eval whiptail --title "'yt-mem-ai installer'" \
    --checklist "'Select targets (space toggles, enter confirms):'" 20 74 8 $_args \
    3>&1 1>&2 2>&3) || return 1
  for c in $_chosen; do add_sel "$(printf '%s' "$c" | tr -d '"')"; done
}

picker_plain() {
  while :; do
    printf '\n  yt-mem-ai installer — select targets\n\n'
    for i in 1 2 3 4 5 6 7 8; do
      mark=" "; is_sel "$i" && mark="X"
      det=""; [ "$(item_detected "$i")" = no ] && det="  (not detected)"
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

if [ "$NONINTERACTIVE" -eq 0 ]; then
  if have whiptail && [ -t 0 ]; then
    picker_whiptail || picker_plain
  else
    picker_plain
  fi
fi

# normalize + guard
SEL=$(printf '%s' "$SEL" | tr -s ' ')
[ "$SEL" != " " ] && [ -n "$(printf '%s' "$SEL" | tr -d ' ')" ] || die "nothing selected."

echo
msg "will install:"
for i in 1 2 3 4 5 6 7 8; do is_sel "$i" && printf '   - %s\n' "$(item_label "$i")"; done
if [ "$ASSUME_YES" -eq 0 ] && [ -t 0 ]; then
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
ensure_uv
UVX=$(command -v uvx)
mkdir -p "$DATA_DIR/lance" "$DATA_DIR/logs" "$DATA_DIR/downloads"

PY=$(command -v python3 2>/dev/null || true)

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
  msg "(This bundles the yt + yt-manager skills, /yt-* commands, and the MCP server.)"
}

do_claude_desktop_mcp() {
  json_merge_server "$DESKTOP_CFG" "yt-mem-ai"
  msg "Claude Desktop: MCP server merged into $(basename "$DESKTOP_CFG"). Restart Claude Desktop."
}

do_claude_desktop_plugin() {
  _src=$(src_dir claude-desktop)
  if [ -z "$_src" ]; then
    warn "Claude Desktop bundle needs the repo checkout. Clone it and re-run, or use --claude-desktop=mcp."
    return
  fi
  if ! have mcpb; then
    warn "Claude Desktop bundle needs the mcpb CLI: npm install -g @anthropic-ai/mcpb — then re-run, or use --claude-desktop=mcp."
    return
  fi
  ( cd "$_src" && sh build.sh )
  _out="$_src/yt-mem-ai.mcpb"
  if have open; then open "$_out" && msg "Claude Desktop: opened $_out to install."; else msg "Built $_out — open it in Claude Desktop → Settings → Extensions."; fi
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
  do_codex_mcp
  # Native SKILL.md skills — Codex loads them from the User scope ~/.codex/skills/
  # (v0.117.0+). This is the reliable, non-interactive install; the full
  # .codex-plugin/ manifest is also available for the /plugins marketplace browser.
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
  msg "Codex: installed skills (yt, yt-manager) + prompts + ~/.codex/AGENTS.md."
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
# dispatch
# --------------------------------------------------------------------------- #
echo
for i in 1 2 3 4 5 6 7 8; do
  is_sel "$i" || continue
  case "$i" in
    1) do_claude_code_plugin ;;
    2) do_claude_code_mcp ;;
    3) do_claude_desktop_plugin ;;
    4) do_claude_desktop_mcp ;;
    5) do_codex_plugin ;;
    6) do_codex_mcp ;;
    7) do_gemini_extension ;;
    8) do_gemini_mcp ;;
  esac
done

echo
msg "done. Data dir: $DATA_DIR (override with YT_MEM_AI_HOME)."
msg "Set proxy/cookies/embedding vars in each host's config or .env — see integrations/mcp/README.md."
