#!/usr/bin/env bash
# Restarts the dashboard: kills the instance on the port (if it is ours) and starts a
# fresh one detached, the same way the SessionStart hook does.
#
#   tools/restart.sh          # port 8787 (or CLAUDE_MONITOR_PORT)
#   tools/restart.sh 8788     # a different port
set -u

PORT="${1:-${CLAUDE_MONITOR_PORT:-8787}}"
ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
URL="http://127.0.0.1:${PORT}/"

listening() {
  python3 -c "import socket,sys; sys.exit(0 if socket.socket().connect_ex(('127.0.0.1', $PORT))==0 else 1)" 2>/dev/null
}

# Only kill our own process - somebody else's server on the same port is not ours to stop.
# -sTCP:LISTEN matters: without it lsof also lists every *client* on the port, so an open
# browser tab on the dashboard would look like a foreign process holding it.
for pid in $(lsof -ti:"$PORT" -sTCP:LISTEN 2>/dev/null); do
  if ps -o command= -p "$pid" | grep -q claude_monitor.py; then
    echo "stopping monitor (pid $pid) on port ${PORT}"
    kill "$pid"
  else
    echo "port ${PORT} is held by pid $pid, which is not claude_monitor.py - refusing to kill it" >&2
    exit 1
  fi
done

# wait for the port to be released, so the new instance does not die on a taken port
for _ in $(seq 20); do
  listening || break
  sleep 0.2
done

nohup python3 "${ROOT}/tools/claude_monitor.py" --port "${PORT}" \
  >/dev/null 2>&1 < /dev/null &
disown 2>/dev/null || true

for _ in $(seq 20); do
  if listening; then
    echo "Claude monitor running at ${URL}"
    exit 0
  fi
  sleep 0.2
done

echo "Claude monitor failed to start on port ${PORT}" >&2
exit 1
