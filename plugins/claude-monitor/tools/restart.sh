#!/usr/bin/env bash
# Restarts the dashboard: stops the instance on the port (if it is ours) and starts a
# fresh one detached, the same way the SessionStart hook does.
#
#   tools/restart.sh            # port 8787 (or CLAUDE_MONITOR_PORT)
#   tools/restart.sh 8788       # a different port
#   tools/restart.sh --status   # print who holds the port: ours | foreign | down
set -u

MODE="restart"
if [ "${1:-}" = "--status" ]; then
  MODE="status"
  shift
fi

PORT="${1:-${CLAUDE_MONITOR_PORT:-8787}}"
ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
URL="http://127.0.0.1:${PORT}/"

listening() {
  python3 -c "import socket,sys; sys.exit(0 if socket.socket().connect_ex(('127.0.0.1', $PORT))==0 else 1)" 2>/dev/null
}

# Who holds the port? The server is asked directly instead of the process table. `ps` is
# not dependable here: a process spawned by Claude Code can be denied it outright
# ("operation not permitted"), and a failed `ps` used to read as "somebody else's
# process" - so the restart backed off, the stale instance stayed up, and the session was
# told the monitor was down while it had been serving the whole time.
#
#   ours    - the dashboard answered for itself
#   foreign - something is on the port, but it is not ours to kill
#   down    - nothing is listening
identity() {
  listening || { echo down; return; }
  python3 - "$PORT" <<'PY'
import json
import sys
import urllib.request

port = sys.argv[1]


def get(path, timeout):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


try:
    if get("/api/whoami", 2).get("app") == "claude-monitor":
        print("ours")
        sys.exit(0)
except (OSError, ValueError):  # URLError and JSONDecodeError are subclasses of these
    pass

# Instances older than /api/whoami still answer /api/state, and that shape is ours alone.
# It costs a full state build, hence the longer timeout - it only runs the once, while an
# older instance is still the one being replaced.
try:
    if {"sessions", "totals", "now"} <= set(get("/api/state", 10)):
        print("ours")
        sys.exit(0)
except (OSError, ValueError):
    pass

print("foreign")
PY
}

if [ "$MODE" = "status" ]; then
  identity
  exit 0
fi

# Ask the monitor to stop itself. A restart almost always runs from a different session
# than the one that started the server, and Claude Code confines a session to its own
# process tree: kill() on a monitor another session spawned comes back "Operation not
# permitted" even though both run as the same user. Over the port it works regardless -
# the process handling the request is the one that has to go.
ask_to_stop() {
  python3 - "$PORT" <<'QUIT'
import json
import sys
import urllib.request

req = urllib.request.Request(
    f"http://127.0.0.1:{sys.argv[1]}/api/quit",
    data=b"{}",
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=5) as r:
        sys.exit(0 if json.load(r).get("ok") else 1)
except (OSError, ValueError):
    sys.exit(1)
QUIT
}

case "$(identity)" in
  ours)
    if ask_to_stop; then
      echo "asked the monitor on port ${PORT} to stop"
    else
      # builds older than /api/quit, and anything wedged: a signal still works when it is
      # this very session that started the server.
      # -sTCP:LISTEN matters: without it lsof also lists every *client* on the port, so an
      # open browser tab on the dashboard would look like another process holding it.
      for pid in $(lsof -ti:"$PORT" -sTCP:LISTEN 2>/dev/null); do
        if kill "$pid" 2>/dev/null; then
          echo "stopping monitor (pid $pid) on port ${PORT}"
        fi
      done
    fi
    ;;
  foreign)
    echo "port ${PORT} is held by a server that is not the Claude monitor - refusing to kill it" >&2
    exit 3
    ;;
esac

# wait for the port to be released, so the new instance does not die on a taken port
for _ in $(seq 20); do
  listening || break
  sleep 0.2
done

if listening; then
  echo "port ${PORT} is still held: the monitor there did not stop, and a session may not signal a process another session started - stop it from your own terminal" >&2
  exit 3
fi

nohup python3 "${ROOT}/tools/claude_monitor.py" --port "${PORT}" \
  >/dev/null 2>&1 < /dev/null &
disown 2>/dev/null || true

# `listening` alone would be satisfied by anything that grabbed the port in the meantime,
# so the new instance has to identify itself before this is called a success
for _ in $(seq 25); do
  if [ "$(identity)" = "ours" ]; then
    echo "Claude monitor running at ${URL}"
    exit 0
  fi
  sleep 0.2
done

echo "Claude monitor failed to start on port ${PORT}" >&2
exit 4
