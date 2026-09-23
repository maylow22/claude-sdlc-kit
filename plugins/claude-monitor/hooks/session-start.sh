#!/usr/bin/env bash
# SessionStart: restart the dashboard so every new session runs the current code, then
# push its URL into the session context. The server is a singleton per machine, so this
# also replaces the instance the other sessions are watching - it comes back in well
# under a second and the browser polls every 3 s.
#
# CLAUDE_MONITOR_PORT=8788     different port
# CLAUDE_MONITOR_AUTOSTART=0   disables autostart (the hook exits quietly)
set -u

PORT="${CLAUDE_MONITOR_PORT:-8787}"
ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
URL="http://localhost:${PORT}/"

# additionalContext goes to the model, systemMessage is printed to the user - both are JSON
# strings, so keep messages free of quotes, backslashes and newlines
emit() {
  printf '{"systemMessage":"%s","hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$2" "$1"
  exit 0
}

# whatever restart.sh reports goes into a hand-built JSON string, so strip what would
# break it and keep the line short enough to read in a terminal
clean() {
  printf '%s' "$1" | tr -d '"\\' | tr '\n' ' ' | cut -c1-160
}

[ "${CLAUDE_MONITOR_AUTOSTART:-1}" = "0" ] && exit 0
command -v python3 >/dev/null 2>&1 || exit 0

# restart.sh stops the old instance, waits for the port and verifies the new one answers
# for itself
out=$(bash "${ROOT}/tools/restart.sh" "$PORT" 2>&1)
if [ $? -eq 0 ]; then
  emit "Claude monitor restarted at ${URL} (live dashboard of all sessions on this machine)." "Claude monitor: ${URL}"
fi

# The restart failing does not mean the dashboard is down, and saying so was the old bug:
# a refused stop leaves the previous instance serving happily. Ask the port who is on it
# before reporting anything.
why=$(clean "$(printf '%s' "$out" | tail -n 1)")
if [ "$(bash "${ROOT}/tools/restart.sh" --status "$PORT" 2>/dev/null)" = "ours" ]; then
  emit "Claude monitor is running at ${URL} but could not be restarted (${why}), so it may be serving older code and a stale session list." "Claude monitor: ${URL} (running, but the restart failed: ${why})"
fi

emit "Claude monitor is not running on port ${PORT} (${why}) - run /claude-monitor:start to see why." "Claude monitor is not running on port ${PORT} (${why}) - run /claude-monitor:start to see why."
