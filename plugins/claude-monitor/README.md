# claude-monitor

A live dashboard of every Claude Code session running on the machine. Zero-dependency Python
(stdlib), serving a standalone HTML page that auto-refreshes every 3 s.

```
# usually nothing — the dashboard starts itself at session start (SessionStart hook)
/claude-monitor:start          # → http://127.0.0.1:8787/
python3 tools/claude_monitor.py --port 8787 --open
```

## Who is waiting on you

A session blocked on your input goes **to the top, ahead of the other cards**, gets an orange
frame with a pulse, a `needs you` pill and a line with the reason and how long it has been
waiting. The count of such sessions is in the KPIs and in the page `<title>`
(`(2) Claude agents`) — so you see it even on an inactive browser tab.

The reason comes from two sources:

| Source | What it knows | When |
|---|---|---|
| `claude agents --json` → `status: waiting` | that the session is waiting (`waitingFor`) | always, even without the plugin |
| `Notification` hook | **why** — a tool permission (and which tool), an MCP dialog, 60 s idle | after restarting the session with the plugin |

The hook writes `~/.claude/monitor/notify/<sessionId>.json`; the dashboard treats it as valid
until the transcript moves past it — a user's answer means a write to the transcript, and that
is what ages the record out.

## Autostart

The `SessionStart` hook checks port 8787 on every session start. If nobody is listening it
starts the dashboard **detached** (surviving the end of the session), and either way it pushes
the URL into the session context — so you can just ask the session where it is running.

| Variable | Effect |
|---|---|
| `CLAUDE_MONITOR_PORT=8788` | a different port (hook and server alike) |
| `CLAUDE_MONITOR_AUTOSTART=0` | the hook exits quietly and starts nothing |

The server is a **singleton per machine**, not per session: a second session merely finds it.
When two start at once, the second process dies on the taken port and one survives — either way
the same URL goes into the context. You stop it with `kill $(lsof -ti:8787)`; it will not stop
on its own.

## What it shows

- **usage cockpit** — plan utilization (5 h session, weekly limit, weekly model limit) with
  percentages and a countdown to the reset; the active limit is highlighted
- **status** — needs you / busy / idle, pid, kind (interactive/background), project, live git branch
- **tokens** — output, input, cache read/write, thinking; context window occupancy
- **subagent tree** — agentType, description, output tokens, how long ago it was active

## Data sources

| What | From where |
|---|---|
| session list, status, `waitingFor` | `claude agents --json` |
| tokens, model, effort | `~/.claude/projects/<slug>/<sessionId>.jsonl` → `.message.usage` |
| subagent tree | `<sessionId>/subagents/agent-*.meta.json` |
| git branch | `git -C <cwd> branch --show-current` (live — the transcript's copy tends to be stale) |
| usage cockpit | `~/.claude.json` → `cachedUsageUtilization` (the cache `/usage` fills) |
| autostart + URL into the session | `hooks/session-start.sh` (SessionStart hook) |
| the reason for waiting on the user | `hooks/notification.py` → `~/.claude/monitor/notify/<sessionId>.json` |

Transcripts are read incrementally (the offset is remembered), so a refresh costs the same
whether the file is small or several megabytes.

## Traps

- The transcript's `message.model` **does not carry the `[1m]` suffix** — you cannot tell the
  1M tier from the log. The context limits therefore live in `CONTEXT_LIMITS` at the top of the
  script (Claude 5 family 1M, Haiku 4.5 200K); Claude Code may auto-compact earlier.
- Usage is **not fetched from the API** — it reads the cache Claude Code writes itself. The age
  of the cache is printed in the header; `/usage` in any session refreshes it.
- A `Notification` hook record is only invalidated by a write to the transcript. After you
  approve a permission, though, nothing is written to the transcript until the tool finishes —
  so for a long command "waiting for tool permission" can hang around for a while after you
  clicked through. The `waiting` status from the CLI does not suffer from this.
- A branch belongs to the **worktree, not the session** — several sessions in one directory are
  always on the same branch, and a `checkout` in one switches the branch for all the others.
