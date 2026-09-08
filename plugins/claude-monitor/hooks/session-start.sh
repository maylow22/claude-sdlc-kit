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
URL="http://127.0.0.1:${PORT}/"

# additionalContext is a JSON string - keep messages free of quotes, backslashes and newlines
emit() {
  printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$1"
  exit 0
}

[ "${CLAUDE_MONITOR_AUTOSTART:-1}" = "0" ] && exit 0
command -v python3 >/dev/null 2>&1 || exit 0

# restart.sh kills the old instance, waits for the port and verifies the new one is up
if bash "${ROOT}/tools/restart.sh" "$PORT" >/dev/null 2>&1; then
  emit "Claude monitor restarted at ${URL} (live dashboard of all sessions on this machine)."
fi

emit "Claude monitor is not running on port ${PORT} - run /claude-monitor:start to see why."
