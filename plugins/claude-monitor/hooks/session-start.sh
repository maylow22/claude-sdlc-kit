#!/usr/bin/env bash
# SessionStart: dashboard je singleton na stroj. Pokud uz jede, jen posleme URL do
# kontextu session; jinak ho nastartujeme odpojene, aby prezil konec tehle session.
#
# CLAUDE_MONITOR_PORT=8788  jiny port
# CLAUDE_MONITOR_AUTOSTART=0  vypne autostart (hook skonci tise)
set -u

PORT="${CLAUDE_MONITOR_PORT:-8787}"
URL="http://127.0.0.1:${PORT}/"

# additionalContext je JSON string - drz zpravy bez uvozovek, zpetnych lomitek a novych radku
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
  emit "Claude monitor bezi na ${URL} (live dashboard vsech sessions na tomhle stroji)."
fi

nohup python3 "${CLAUDE_PLUGIN_ROOT}/tools/claude_monitor.py" --port "${PORT}" \
  >/dev/null 2>&1 < /dev/null &
disown 2>/dev/null || true

# server nabiha do desitek ms; kratce pockej, at do kontextu nejde nepravda
for _ in 1 2 3 4 5 6 7 8 9 10; do
  listening && emit "Claude monitor nastartovan na ${URL} (live dashboard vsech sessions na tomhle stroji)."
  sleep 0.2
done

emit "Claude monitor se na portu ${PORT} nepodarilo nastartovat - zkus /claude-monitor:start rucne."
