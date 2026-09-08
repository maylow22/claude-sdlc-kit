# claude-monitor

A live dashboard of every Claude Code session running on the machine. Zero-dependency Python
(stdlib), serving a standalone HTML page that auto-refreshes every 3 s — click the interval in
the header to cycle it: 3 s → 10 s → 1 min → stop (a real stop, no timer at all).

```
# usually nothing — the dashboard starts itself at session start (SessionStart hook)
/claude-monitor:start          # → http://127.0.0.1:8787/
python3 tools/claude_monitor.py --port 8787 --open
tools/restart.sh [port]        # kill the running instance and start a fresh one
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

The `SessionStart` hook **restarts** the dashboard on every session start — so a new session
always runs the current code — and pushes its URL into the session context, so you can just ask
the session where it is running. The new instance is **detached** and survives the end of the
session. The whole hook takes ~0.3 s.

| Variable | Effect |
|---|---|
| `CLAUDE_MONITOR_PORT=8788` | a different port (hook and server alike) |
| `CLAUDE_MONITOR_AUTOSTART=0` | the hook exits quietly and starts nothing |

The server is a **singleton per machine**, not per session — so a session start replaces the
instance the *other* sessions are watching. That costs them nothing visible: it is back in well
under a second and the browser polls every 3 s. What is lost are the in-memory transcript
offsets, so the first refresh after a restart re-reads every transcript from the beginning
(the totals come out the same, it is just not the cheap incremental read).

Restarting is safe under concurrency: the kill always precedes the start, so when several
sessions start at once exactly one server survives, and each hook verifies the **port** rather
than its own pid — nobody reports an untruth. `tools/restart.sh` refuses to kill a process on
the port that is not `claude_monitor.py`; the hook then reports that the dashboard is not
running instead of stealing somebody else's port.

You stop it with `kill $(lsof -ti:8787)`; it will not stop on its own — but the next session
start brings it back.

## What it shows

- **one KPI row** — it opens with plan utilization (5 h session, weekly, weekly model) as
  percent tiles with a thin bar, the active limit framed; the long label, the countdown to the
  reset and the age of the usage cache are in the tooltip. Then the counts and the few token numbers that matter; the
  rest is folded behind **show more**
- **status** — needs you / busy / idle, pid, kind (interactive/background), project, live git branch
- **tokens** — output, input, cache read/write, thinking; context window occupancy
- **folded away** — subagents, turns, input tokens, thinking, cache read/write, plan tier.
  Always visible instead: sessions, busy, need you, context total, output tokens and **cache
  hit** (the share of the input side served from the cache — what keeps a long session cheap)
- **version** — `vYYYYMMDD-commit` in the top right corner; the date is the **commit's**, so
  the same code always reports the same version (outside a git checkout only the file date)
- **subagent tree** — agentType, description, output tokens, how long ago it was active

## Data sources

| What | From where |
|---|---|
| session list, status, `waitingFor` | `claude agents --json` |
| tokens, model, effort | `~/.claude/projects/<slug>/<sessionId>.jsonl` → `.message.usage` |
| subagent tree | `<sessionId>/subagents/agent-*.meta.json` |
| git branch | `git -C <cwd> branch --show-current` (live — the transcript's copy tends to be stale) |
| plan usage tiles | `~/.claude.json` → `cachedUsageUtilization` (the cache `/usage` fills) |
| restart + URL into the session | `hooks/session-start.sh` → `tools/restart.sh` (SessionStart hook) |
| the reason for waiting on the user | `hooks/notification.py` → `~/.claude/monitor/notify/<sessionId>.json` |

Transcripts are read incrementally (the offset is remembered), so a refresh costs the same
whether the file is small or several megabytes.

## Traps

- The transcript's `message.model` **does not carry the `[1m]` suffix** — you cannot tell the
  1M tier from the log. The context limits therefore live in `CONTEXT_LIMITS` at the top of the
  script (Claude 5 family 1M, Haiku 4.5 200K); Claude Code may auto-compact earlier.
- Usage is **not fetched from the API** — it reads the cache Claude Code writes itself. The age
  of the cache is in the tooltip of the plan tiles; `/usage` in any session refreshes it.
- A `Notification` hook record is only invalidated by a write to the transcript. After you
  approve a permission, though, nothing is written to the transcript until the tool finishes —
  so for a long command "waiting for tool permission" can hang around for a while after you
  clicked through. The `waiting` status from the CLI does not suffer from this.
- A branch belongs to the **worktree, not the session** — several sessions in one directory are
  always on the same branch, and a `checkout` in one switches the branch for all the others.
