# claude-monitor

A live dashboard of every Claude Code session running on the machine. Zero-dependency Python
(stdlib), serving a standalone HTML page that auto-refreshes every 3 s — click the interval in
the header to cycle it: 3 s → 10 s → 1 min → stop (a real stop, no timer at all).

```
# usually nothing — the dashboard starts itself at session start (SessionStart hook)
/claude-monitor:start          # → http://127.0.0.1:8787/
python3 tools/claude_monitor.py --port 8787 --open
tools/restart.sh [port]        # replace the running instance with a fresh one
tools/restart.sh --status      # who holds the port: ours | foreign | down
```

## Who is waiting on you

A session blocked on your input goes **to the top, ahead of the other cards**, gets an orange
frame with a pulse, a `needs you` pill and a line with the reason and how long it has been
waiting. The count of such sessions is in the KPIs and in the page `<title>`
(`(2) Claudemon`) — so you see it even on an inactive browser tab.

The reason comes from two sources:

| Source | What it knows | When |
|---|---|---|
| the session's `status` in the registry, and `waitingFor` from `claude agents --json` | that the session is waiting | always, even without the plugin |
| `Notification` hook | **why** — a tool permission (and which tool), an MCP dialog, 60 s idle | after restarting the session with the plugin |

The hook writes `~/.claude/monitor/notify/<sessionId>.json`; the dashboard treats it as valid
until the transcript moves past it — a user's answer means a write to the transcript, and that
is what ages the record out.

## Claudemon in the Dock

Safari turns the dashboard into a standalone app: open it and pick **File → Add to Dock**. The
app is called **Claudemon** and gets its own icon — a Claude burst with a pulse trace rising
into the gap between its lower rays, on the dashboard's own dark warm ground.

The name comes from the web app manifest, not from the `<title>`: the title carries the count
of sessions waiting on you (`(2) Claudemon`), which is exactly what you do not want engraved
under a Dock icon.

| Route | What it is for |
|---|---|
| `/manifest.webmanifest` | the app's name, its icons, `display: standalone`, the window's background |
| `/icon-180.png` | `apple-touch-icon` — what Safari falls back on without a manifest |
| `/icon-512.png`, `/icon-1024.png` | the Dock and Launchpad sizes |
| `/icon.svg`, `/icon-32.png` | the browser tab |

`127.0.0.1` counts as a **secure context**, so a manifest over plain HTTP is honoured here the
way it would be over HTTPS anywhere else — no certificate needed.

### Regenerating the artwork

`tools/make_icon.py` owns the geometry; `assets/icon.svg` and the PNGs are its output and are
committed, so nothing has to be built to run the dashboard. There is no SVG rasterizer to
depend on, which is why it takes two steps:

```
tools/make_icon.py svg                 # geometry -> assets/icon.svg
# render assets/icon.svg to a 1024x1024 PNG (any browser: open it at 1024 CSS px and shoot)
tools/make_icon.py png shot.png        # -> assets/icon-{1024,512,180,32}.png
```

The second step does what the SVG cannot do for itself: it cuts the square render to the Apple
squircle, lays the top rim light along that same curve, and box-filters the master down. The
corners come out **transparent**, so the icon looks right whether or not the system masks it
again on top.

## Jumping to the session

Every card carries a button with the name of the app the session is running in
(`↗ Cursor`, `↗ Terminal`, …) — it brings that window to the front. The page itself cannot
raise a native window, so the click goes to `POST /api/focus` and the server does the work.

The app is found by walking the parent chain of the session's pid until an `.app` turns up:

```
68114 claude → 67568 zsh → 65236 Cursor Helper: terminal pty-host → 64749 Cursor.app
```

How precisely it lands depends on the app:

| App | What it focuses | How |
|---|---|---|
| Terminal, iTerm2 | **the exact tab** | AppleScript — both publish the `tty` of every tab, and the session's tty comes from `ps` |
| Cursor, VS Code, Windsurf, Zed, … | **the window of that folder** | `open -a <app> <cwd>` — an editor keeps one window per open folder |
| anything else | the app, whichever window was last on top | `tell application … to activate` |

No Accessibility grant is needed anywhere (which is why `open -a` beats System Events for the
editors). Under `tmux` or over ssh no app owns the session any more — there the button is not
rendered at all.

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

Restarting is safe under concurrency: the stop always precedes the start, so when several
sessions start at once exactly one server survives, and each hook verifies the **port** rather
than its own pid.

### Stopping an instance another session started

The restart is what puts a new session's code in front of everybody watching, and it used to
matter a great deal more: while the session list still came from `claude agents --json`, an
instance left behind by a session that had ended went on answering for *that* session — one was
found reporting a session dead since the night before and missing the one typing at it. Reading
the registry instead (below) took that failure away; the restart now buys current code, not
correctness. Getting the old process to go is the hard part either way, and a signal does not
do it.

Claude Code confines a session to its **own process tree**. A monitor started by session A
cannot be killed by session B — `kill` answers `Operation not permitted` though both run as the
same user — and `ps` is refused outright, so nothing inside a hook can even look up what a pid
belongs to.

Neither end of the restart therefore touches the process table:

| Step | How |
|---|---|
| whose server is on the port | `GET /api/whoami` → `{"app": "claude-monitor", …}`; builds older than that route are recognized by the shape of `/api/state` |
| stopping it | `POST /api/quit` — the process handling the request is the one that has to go, so no signal ever crosses a tree boundary |
| the fallback | `kill` by `lsof -ti:<port> -sTCP:LISTEN`, for builds without `/api/quit` and for a server this session did start itself |
| confirming the new one | `GET /api/whoami` again — merely *listening* would be satisfied by anything that grabbed the port in the meantime |

`tools/restart.sh --status [port]` prints that verdict on its own: `ours`, `foreign` or `down`.
A port held by something that is **not** the dashboard is never killed — the restart exits `3`
and says whose it is.

### The hook does not report an untruth

A failed restart does not mean the dashboard is down, and saying so is exactly what this used to
get wrong: `ps` being unavailable read as "somebody else's process", the restart backed off, and
every new session opened with `Claude monitor is not running` while the dashboard had been
serving the whole time. The hook now asks the port who is on it **before** it reports, and has
three answers:

| Situation | What the session is told |
|---|---|
| a fresh instance answers | `Claude monitor: http://localhost:8787/` |
| the restart failed, ours still answers | `… is running at …, but could not be restarted (<reason>), so it may be serving older code and a stale session list` |
| nothing of ours on the port | `… is not running on port 8787 (<reason>) — run /claude-monitor:start` |

You stop it by hand with `tools/restart.sh --status` first and then either
`curl -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:8787/api/quit`, or
`kill $(lsof -ti:8787)` **from your own terminal** — which, unlike a session, is not confined to
somebody else's tree. It will not stop on its own; the next session start brings it back.

## Seeing every session, not just this one

The dashboard listed exactly one session — the one whose `SessionStart` hook had started it —
while half a dozen others were running. It is the same confinement that breaks the restart:
Claude Code holds a session inside its **own process tree**, and the liveness check behind
`claude agents --json` is a check on a process. From inside a session, `kill(pid, 0)` against
every *other* session answers `EPERM` whether that session is alive or not, so the listing
prunes them all and hands back the caller's own and nothing else.

Two things do reach across that boundary, and the session list is built out of them instead:

| What | Where |
|---|---|
| the sessions | `~/.claude/sessions/<pid>.json` — pid, `sessionId`, `cwd`, `kind`, `name`, `status` |
| whether one is still alive | a connection to its `messagingSocketPath` — a live session listens, a session that died leaves a socket file behind and it refuses |

Neither asks anything about a process, which is the whole point. `claude agents --json` is still
called, for the one field the registry files do not carry — `waitingFor` — and it is an overlay
on the list, not the list.

The status vocabulary is open-ended: `busy`, `idle`, `waiting` and `shell` have all turned up. A
session therefore counts as **working unless it is plainly not**, so a status nobody has seen
yet still lands on the right side of the sort and of the KPI count.

## What it shows

- **one KPI row** — it opens with plan utilization (5 h session, weekly, weekly model) as
  percent tiles with a thin bar, the active limit framed; the long label, the countdown to the
  reset and the age of the usage cache are in the tooltip. Then the counts and the few token numbers that matter; the
  rest is folded behind **show more**
- **which session this is** — the card is headed by the **session's own name** (`hx-anon`,
  `claude-sdlc-kit-c3`), because that is what tells two sessions in one repository apart. Under
  it the checkout: `<repo>:<branch>`, and a linked worktree on a line of its own as
  `wt:<worktree>` — the repository is the one the worktree belongs to, not the directory name
- **status** — needs you / busy / idle, pid, kind (interactive/background), model
- **tokens** — output, input, cache read/write, thinking; context window occupancy
- **folded away** — subagents, turns, input tokens, thinking, cache read/write, plan tier.
  Always visible instead: sessions, busy, need you, context total, output tokens and **cache
  hit** (the share of the input side served from the cache — what keeps a long session cheap)
- **theme** — dark, light or by the system, cycled with the button in the top right corner
  next to the version (◑ system · ☀ light · ☾ dark). The choice is stored, so it survives a
  reload; while it is on **system**, a system that flips repaints the page under you. Both
  palettes are one set of CSS variables, so a color is defined once per theme and nowhere else
- **version** — `vYYYYMMDD-commit` in the top right corner; the date is the **commit's**, so
  the same code always reports the same version (outside a git checkout only the file date)
- **subagent tree** — agentType, description, output tokens, how long ago it was active

## The backlog board

The second view, behind the `backlog` tab next to the title: the project's `BACKLOG.md` as a
list to scan on the left — id and title, grouped by priority in the order the file has them,
with the closed tickets from `BACKLOG.done.md` dimmed at the end — and the ticket you click open
on the right, in full. A ticket is several paragraphs of prose, so cards side by side turn into
a wall of text; one open at a time is what makes a list of fifteen readable. Tickets are still
added and closed by the `feature` plugin's commands — what the board adds is the command that
takes one up, without retyping its id into the right window.

More than one project with a backlog → a row of buttons above the list picks one, `name · open
count` each. Which project and which ticket are open live in the page, not in the DOM, so the
3 s repaint does not throw the selection away.

The board shows the projects that an **open session is sitting in** — the monitor does not go
looking around the disk. The file is searched for upwards from the session's `cwd` and never
outside the repository, because the backlog lives in the repository root and a session often
sits deeper.

Nothing in the parser is hardcoded to English: `##` is a priority, `###` a ticket, and a
`**Foo:** bar` line is a field whatever `Foo` says — the backlog is written in the language of
the repo, and headings and fields come out of the file as they are.

### Taking a ticket up

The open ticket carries a `copy` button in its top right corner, and a second one when there is
a window to raise:

| Button | What it does |
|---|---|
| `copy` | puts `/feature:start BL-7` on the clipboard — you paste it into a terminal yourself, nothing leaves the page |
| `↗ <app>` | raises the window of a session already sitting in that project — the same `POST /api/focus` the session cards use, and like them it is not rendered under `tmux` or over ssh |

The dashboard stays a **reader**. It never types into a running session and it never starts
one — launching a feature belongs in a terminal you are looking at, not in an HTTP request.
The clipboard is where the board stops and you take over.

A ticket somebody is already on **spins** in the list. The monitor works that out without any
agreement about field names: it compares the branch the project's worktree is on against the
values of the ticket's fields, and a ticket is live when one of them *is* that branch — not
merely mentions it, or a ticket warning you to keep `main` green would claim to be in progress.

The closed tickets are left out of that search: one cannot be in progress, and it moves to
`BACKLOG.done.md` verbatim — `Branch` line and all, so checking out a merged branch nobody
deleted would light the finished ticket up again.

The buttons report back **in place** — `✓ copied`, `✓`, or the error — which is more than the
session cards do, as those only ever show a failure. The board is repainted wholesale every
3 s, so the message lives in a page variable next to the selection, not in the DOM where the
next tick would eat it.

## Who may talk to the server

The server is bound to the loopback, and that on its own settles less than it looks: a page on
`evil.tld` whose name has been made to resolve to `127.0.0.1` stays on its own origin,
`http://evil.tld:<port>` — rebinding merely points that name at the loopback socket — so an
`Origin` check would not stop it and no CORS header of ours is ever consulted. The `Host` is
what gives it away, so every route, the page included, requires a `Host` of the dashboard's
own — `127.0.0.1:<port>` or `localhost:<port>`, and nothing else (on `--port 80` the bare
`127.0.0.1` and `localhost` too, as a browser leaves out the scheme's default port). That is
the check that breaks **DNS rebinding**, and it has to cover the reads.

Those reads are not a small matter. `/api/state` hands out the absolute path of every project
on the machine, the branch each one is on, session pids, and — for a session waiting on you —
why it is waiting and the last thing it said; `/api/backlog` adds the full prose of every
backlog found, which of its tickets are being worked on, and the pid and `cwd` of a session
sitting there. `POST /api/focus` and `POST /api/quit` are the routes that act on the machine
rather than reporting on it, and they add two legs: `Content-Type` has to be
`application/json`, which makes the request non-simple, so a cross-origin attempt needs a
preflight this server does not answer, and `Origin`/`Sec-Fetch-Site`, when present, has to be
same-origin. Anything else is a `403`.

`/api/quit` stops the server and is on those same guards — the most a page that got through
could do with it is take the dashboard down, which the next session start undoes, and it is a
good deal less than `/api/focus` already grants. `GET /api/whoami` gives up the app name, the
pid and the version, and exists so a restart can tell its own server from a stranger's without
the process table.

The gate authorizes **by origin, never by identity** — there is no token and no login. It asks
where a request comes from, which a *web page* cannot lie about; a program on the machine can.
Any other local account able to open a socket to the port reads the whole state and can raise
windows on your screen. The assumed deployment is a **single-user machine**; on a shared one, do
not run the dashboard (`CLAUDE_MONITOR_AUTOSTART=0`).

## Data sources

| What | From where |
|---|---|
| session list, status, `cwd`, `kind`, name | `~/.claude/sessions/<pid>.json` (liveness: a connection to the session's unix socket) |
| `waitingFor` | `claude agents --json` — answers for this server's own session only, so it is an overlay |
| tokens, model, effort | `~/.claude/projects/<slug>/<sessionId>.jsonl` → `.message.usage` |
| subagent tree | `<sessionId>/subagents/agent-*.meta.json` |
| git branch | `git -C <cwd> branch --show-current` (live — the transcript's copy tends to be stale) |
| repository + worktree | `git -C <cwd> rev-parse --show-toplevel --git-common-dir` — the common git dir is what a linked worktree shares with its repository |
| plan usage tiles | `~/.claude.json` → `cachedUsageUtilization` (the cache `/usage` fills) |
| restart + URL into the session | `hooks/session-start.sh` → `tools/restart.sh` (SessionStart hook) |
| the reason for waiting on the user | `hooks/notification.py` → `~/.claude/monitor/notify/<sessionId>.json` |
| the backlog board | `BACKLOG.md` + `BACKLOG.done.md` in the repository root of an open session's `cwd` (parsed only when the file changes) |
| which ticket is being worked on | `git branch --show-current` in each backlog project's root, matched against the ticket's field values (backticks stripped, compared whole) |
| the app hosting a session | `ps -Ao pid,ppid,tty,command` — one call per refresh, the parent chain is walked in memory; where the process table is refused, no app is found and the button is simply not rendered |

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
- Focus into an **editor** lands on the window of the session's `cwd`, not on the terminal
  panel inside it — AppleScript cannot reach into an editor's terminal tabs. Two sessions in
  the same folder therefore focus the same window.
- A branch belongs to the **worktree, not the session** — several sessions in one directory are
  always on the same branch, and a `checkout` in one switches the branch for all the others.
- The spinner marking a ticket as taken up needs the ticket to **carry its branch in a field**.
  `/feature:start` writes that line when it creates the branch; a ticket started by hand, or one
  filed before that was the habit, stays unmarked — the board just does not know.
- `claude agents --json` answers with **the caller's own session and no other**, however many
  are running — its liveness check is a process check, and those are refused across the tree
  boundary. Anything reading it for a machine-wide picture gets one row.
- A session may not signal, or even see, a process outside its **own tree**: `ps` comes back
  `operation not permitted` and `kill` `Operation not permitted`, same user or not. That is why
  the restart goes over HTTP — and why the `↗ <app>` button quietly disappears where the process
  table is refused, as the parent chain cannot be walked and no `.app` is ever found.
- The Dock icon is read **once**, when you add the app. Changing `assets/` afterwards does not
  reach an app already in the Dock — remove it and add it again. The icons are served with
  `max-age=86400`, so a browser tab wants a hard reload too.
- Every route, the page included, requires a `Host` of exactly **`127.0.0.1:<port>` or
  `localhost:<port>`** — on `--port 80` the bare `127.0.0.1` or `localhost` as well, because
  the browser omits the scheme's default port. That is what stops DNS rebinding, and it has no
  exceptions. Reaching the dashboard under any other name for the loopback (a `/etc/hosts`
  alias, the machine's own hostname, an ssh tunnel or proxy that passes its own `Host` through)
  gets a bare `403` rather than a page. Over ssh, forward it to **your own loopback only** —
  `ssh -L 127.0.0.1:8787:127.0.0.1:8787 <host>` — and open it as `localhost`. Never `-g`, never
  `GatewayPorts yes`, never `-L '*:8787:...'`: the forward satisfies the **only** access control
  this server has, and it authorizes by origin, not by identity. Whoever reaches the far end of
  a forward opened to the LAN reads every project path, branch, backlog and session `pid`/`cwd`
  on your machine, and gets an unauthenticated `POST /api/focus` with it. Take the tunnel down
  when you are done.
