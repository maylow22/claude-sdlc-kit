---
description: Starts the live dashboard of all running Claude sessions (port 8787)
argument-hint: "[port]"
---

Start the session monitor in the background and give the user its URL. It is usually already
running — the plugin's `SessionStart` hook starts it; this command is for the case where it was
disabled (`CLAUDE_MONITOR_AUTOSTART=0`), somebody stopped it, or the hook reported that it could
not be restarted.

1. Ask who holds the port — never judge that by a bare `200`, which any local server would give:
   `bash "${CLAUDE_PLUGIN_ROOT}/tools/restart.sh" --status ${1:-8787}`
   - `ours` → the dashboard is already up. **Do not start a second instance**; report the URL and
     stop. Only if the user wants it on current code, run step 2 to replace it.
   - `foreign` → something else is on that port. Say so and stop — suggest another port
     (`/claude-monitor:start 8788`) rather than taking it.
   - `down` → nothing there; go to step 2.
2. Start (or replace) it: `bash "${CLAUDE_PLUGIN_ROOT}/tools/restart.sh" ${1:-8787}`
   It stops the old instance over `POST /api/quit` — a signal does not work across sessions —
   waits for the port and confirms the new one answers for itself. Exit `3` means the port is
   held by something it will not touch, `4` that the server did not come up.
3. Report the URL `http://127.0.0.1:<port>/` and the number of sessions
   (`curl -s http://127.0.0.1:<port>/api/state`). If step 2 failed, tell the user what it
   printed — do not claim the dashboard is down when `--status` still says `ours`.

To stop it: `curl -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:<port>/api/quit`
(or `kill $(lsof -ti:<port>)` from the user's own terminal — a session cannot signal a process
outside its own tree).
