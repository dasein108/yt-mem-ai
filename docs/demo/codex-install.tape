# yt-mem-ai — record the "install skills for Codex" wizard as a GIF.
#
#   brew install vhs
#   vhs docs/demo/codex-install.tape      # → docs/demo/codex-install.gif
#
# Records the real one-liner. Runs against a throwaway HOME (/tmp/yt-demo) so it
# never touches your real ~/.codex, and points uv at your real cache/tool dirs so
# the CLI install doesn't stall the recording.

Output docs/demo/codex-install.gif

Set Shell bash
Set FontSize 13
Set Width 840
Set Height 520
Set Padding 18
Set TypingSpeed 35ms
Set Theme "Catppuccin Mocha"

# --- setup (not recorded) ---------------------------------------------------
Hide
Type "export HOME=/tmp/yt-demo; rm -rf $HOME; mkdir -p $HOME/.codex/skills"
Enter
Type "export UV_CACHE_DIR=/Users/dasein/.cache/uv YT_MEM_AI_HOME=$HOME/.yt-mem-ai"
Enter
Type "export UV_TOOL_DIR=/Users/dasein/.local/share/uv/tools UV_TOOL_BIN_DIR=/Users/dasein/.local/bin"
Enter
Type "cd /Users/dasein/dev/yt_summary && clear"
Enter
Show

# --- the demo ---------------------------------------------------------------
Copy "curl -LsSf https://raw.githubusercontent.com/dasein108/yt-mem-ai/main/install.sh | sh"
Paste
Sleep 700ms
Enter
Sleep 4s

# step 1/2 — "Plugin" is already selected
Enter
Sleep 1.5s

# step 2/2 — move down to Codex, tick it, apply
Down
Sleep 500ms
Down
Sleep 500ms
Space
Sleep 700ms
Enter

# installation output — long enough to show the Codex + "done" lines
Sleep 13s
