---
description: Starts the live dashboard of all running Claude sessions (port 8787)
argument-hint: "[port]"
---

Start the session monitor in the background and give the user its URL. It is usually already
running — the plugin's `SessionStart` hook starts it; this command is for the case where it was
disabled (`CLAUDE_MONITOR_AUTOSTART=0`) or somebody killed it.

1. Check whether it is already up: `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:${1:-8787}/`
   If it returns `200`, **do not start a second instance** — just report the URL and stop.
2. Otherwise start it in the background:
   `python3 "${CLAUDE_PLUGIN_ROOT}/tools/claude_monitor.py" --port ${1:-8787}`
3. Verify it responds (`/api/state` returns JSON) and print the user the URL
   `http://127.0.0.1:<port>/` plus the number of sessions found.

To stop it: `kill $(lsof -ti:<port>)`.
