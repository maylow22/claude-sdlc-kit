#!/usr/bin/env bash
# SessionStart: the dashboard is a singleton per machine. If it is already up we only
# push its URL into the session context; otherwise we start it detached so it survives
# the end of this session.
#
# CLAUDE_MONITOR_PORT=8788     different port
# CLAUDE_MONITOR_AUTOSTART=0   disables autostart (the hook exits quietly)
set -u

PORT="${CLAUDE_MONITOR_PORT:-8787}"
URL="http://127.0.0.1:${PORT}/"

# additionalContext is a JSON string - keep messages free of quotes, backslashes and newlines
emit() {
  printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$1"
  exit 0
}

listening() {
  python3 -c "import socket,sys; sys.exit(0 if socket.socket().connect_ex(('127.0.0.1', $PORT))==0 else 1)" 2>/dev/null
}

[ "${CLAUDE_MONITOR_AUTOSTART:-1}" = "0" ] && exit 0
command -v python3 >/dev/null 2>&1 || exit 0

if listening; then
  emit "Claude monitor is running at ${URL} (live dashboard of all sessions on this machine)."
fi

nohup python3 "${CLAUDE_PLUGIN_ROOT}/tools/claude_monitor.py" --port "${PORT}" \
  >/dev/null 2>&1 < /dev/null &
disown 2>/dev/null || true

# the server comes up in tens of ms; wait briefly so we do not report an untruth
for _ in 1 2 3 4 5 6 7 8 9 10; do
  listening && emit "Claude monitor started at ${URL} (live dashboard of all sessions on this machine)."
  sleep 0.2
done

emit "Claude monitor failed to start on port ${PORT} - try /claude-monitor:start manually."
