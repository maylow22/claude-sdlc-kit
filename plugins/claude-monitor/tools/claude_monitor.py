#!/usr/bin/env python3
"""Live dashboard of every Claude Code session running on this machine.

Data sources:
  - ~/.claude/sessions/<pid>.json    -> sessions, pid/cwd/kind/status (liveness: the
                                       session's unix socket accepts a connection)
  - `claude agents --json`           -> waitingFor, for this server's own session
  - ~/.claude/projects/*/<sid>.jsonl -> tokens, model, effort, git branch, activity
  - .../<sid>/subagents/agent-*      -> subagent tree (agentType, spawnDepth, tokens)
  - ~/.claude/monitor/notify/*.json  -> Notification hook: session is waiting on the user

Nothing is registered at start-up and no state is kept between requests: every /api/state
re-reads all of the above, so a session older than the server appears on the next poll
like any other. That the session list is read from the registry rather than taken from
`claude agents --json` is what makes this true at all - see registry().

Run:  python3 claude_monitor.py [--port 8787] [--open]
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import socket
import subprocess
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"
SESSIONS = Path.home() / ".claude" / "sessions"
CONFIG = Path.home() / ".claude.json"
NOTIFY = Path.home() / ".claude" / "monitor" / "notify"
SUBAGENT_ACTIVE_SEC = 60

# Safari's "Add to Dock" turns the dashboard into a standalone app, and takes its name
# and its icon from the manifest below - the <title> is no good for the name, it carries
# the count of sessions waiting on you. The artwork lives next to this script; see
# tools/make_icon.py.
APP_NAME = "Claudemon"
ASSETS = Path(__file__).resolve().parent.parent / "assets"
STATIC = {
    "/icon.svg": ("icon.svg", "image/svg+xml"),
    "/icon-32.png": ("icon-32.png", "image/png"),
    "/icon-180.png": ("icon-180.png", "image/png"),
    "/icon-512.png": ("icon-512.png", "image/png"),
    "/icon-1024.png": ("icon-1024.png", "image/png"),
}

# `claude agents --json` -> waitingFor
WAITING_LABELS = {"input needed": "waiting for your input"}
# Notification hook matchers (see hooks/notification.py)
NOTIFY_LABELS = {
    "permission_prompt": "waiting for tool permission",
    "idle_prompt": "waiting for a prompt",
    "elicitation_dialog": "MCP dialog waiting for input",
}

# Context window sizes (source: claude-api skill). The whole Claude 5 family is
# 1M, Haiku 4.5 only 200K. Careful: the transcript's `message.model` does NOT carry
# the [1m] suffix, so the 1M tier cannot be told apart from the log - hence 1M as
# the default for the 5 family. Claude Code may auto-compact earlier (see
# `claude --autocompact`).
CONTEXT_LIMITS = {
    "claude-haiku-4-5": 200_000,
}
DEFAULT_LIMIT = 1_000_000

# Fields from ~/.claude.json -> cachedUsageUtilization.utilization.limits
LIMIT_LABELS = {"session": "session (5 h)", "weekly_all": "week, all models",
                "weekly_scoped": "week"}
# the KPI tile is narrow - the long label only survives in the tooltip
SHORT_LABELS = {"session": "5 h", "weekly_all": "week all", "weekly_scoped": "week"}

_ORIGINS: set[str] = set()  # the `Host` values the page may carry, filled in by main()
_cache: dict[str, dict] = {}
_usage: dict = {"mtime": 0.0, "data": None}
_lock = threading.Lock()


def _fresh() -> dict:
    return {
        "offset": 0,
        "input": 0,
        "output": 0,
        "cache_read": 0,
        "cache_write": 0,
        "thinking": 0,
        "turns": 0,
        "context": 0,
        "model": None,
        "effort": None,
        "branch": None,
        "last_ts": None,
        "last_agent": None,
    }


AGENT_TEXT_MAX = 800


def agent_text(content) -> str:
    """Visible text of an assistant turn - thinking and tool_use blocks skipped."""
    if not isinstance(content, list):
        return ""
    txt = "\n".join(
        b.get("text", "")
        for b in content
        if isinstance(b, dict) and b.get("type") == "text"
    ).strip()
    return (txt[:AGENT_TEXT_MAX] + "\u2026") if len(txt) > AGENT_TEXT_MAX else txt


def scan(path: str) -> dict:
    """Read only the lines added since the last call and update the aggregates."""
    try:
        size = os.stat(path).st_size
    except OSError:
        return _fresh()

    c = _cache.get(path)
    if c is None or size < c["offset"]:  # new file or truncation
        c = _cache[path] = _fresh()
    if size == c["offset"]:
        return c

    with open(path, "rb") as f:
        f.seek(c["offset"])
        data = f.read()
    cut = data.rfind(b"\n")
    if cut == -1:
        return c
    c["offset"] += cut + 1

    for raw in data[:cut].split(b"\n"):
        if not raw:
            continue
        try:
            e = json.loads(raw)
        except ValueError:
            continue
        if e.get("timestamp"):
            c["last_ts"] = e["timestamp"]
        if e.get("gitBranch"):
            c["branch"] = e["gitBranch"]
        if e.get("effort"):
            c["effort"] = e["effort"]
        msg = e.get("message")
        if not isinstance(msg, dict):
            continue
        if e.get("type") == "assistant":
            # Turns that only think or call tools keep the previous reply. A subagent
            # transcript is all sidechain - its last reply is the report the
            # orchestrator gets, and that is where the verdict is read from.
            said = agent_text(msg.get("content"))
            if said:
                c["last_agent"] = {"text": said, "ts": e.get("timestamp")}
        u = msg.get("usage")
        if not isinstance(u, dict):
            continue
        inp = u.get("input_tokens", 0)
        cr = u.get("cache_read_input_tokens", 0)
        cw = u.get("cache_creation_input_tokens", 0)
        c["input"] += inp
        c["output"] += u.get("output_tokens", 0)
        c["cache_read"] += cr
        c["cache_write"] += cw
        c["thinking"] += (u.get("output_tokens_details") or {}).get("thinking_tokens", 0)
        c["turns"] += 1
        c["context"] = inp + cr + cw  # last turn = current window occupancy
        if msg.get("model"):
            c["model"] = msg["model"]
    return c


def read_notify(session_id: str, mtime: float) -> dict | None:
    """Notification hook record. Valid until the transcript moves past it - once the
    user answers, the transcript gets written to and the record goes stale."""
    try:
        rec = json.loads((NOTIFY / f"{session_id}.json").read_text())
    except (OSError, ValueError):
        return None
    return rec if rec.get("ts", 0) > mtime else None


def attention(session: dict, session_id: str, mtime: float) -> dict | None:
    """Is the session waiting on the user, and why? The Notification hook knows the
    reason more precisely (which tool wants permission); the CLI status works even
    without the hook."""
    rec = read_notify(session_id, mtime)
    # `idle_prompt` fires 60 s after the last transcript write - which a session busy
    # with its own subagents reaches without the user being asked anything (nothing is
    # written to the main transcript while a subagent runs, so the record never goes
    # stale either). The CLI knows the session is working; a permission or MCP dialog
    # happens mid-turn and stays valid while busy.
    if rec and rec.get("kind") == "idle_prompt" and session.get("status") == "busy":
        rec = None
    if rec:
        kind = rec.get("kind") or "?"
        return {
            "kind": kind,
            "label": NOTIFY_LABELS.get(kind, kind),
            "detail": rec.get("message") or "",
            "since": rec["ts"],
        }
    if session.get("status") == "waiting":
        wf = session.get("waitingFor") or ""
        return {
            "kind": "waiting",
            "label": WAITING_LABELS.get(wf, wf or "waiting for the user"),
            "detail": "",
            "since": mtime,
        }
    return None


def transcript(session_id: str) -> str | None:
    hits = glob.glob(str(PROJECTS / "*" / f"{session_id}.jsonl"))
    return hits[0] if hits else None


def subagents(transcript_path: str, session_id: str) -> list[dict]:
    d = Path(transcript_path).parent / session_id / "subagents"
    if not d.is_dir():
        return []
    now = time.time()
    out = []
    for meta_path in d.glob("agent-*.meta.json"):
        try:
            meta = json.loads(meta_path.read_text())
        except (OSError, ValueError):
            continue
        jsonl = str(meta_path).replace(".meta.json", ".jsonl")
        t = scan(jsonl) if os.path.exists(jsonl) else _fresh()
        try:
            mtime = os.stat(jsonl).st_mtime
        except OSError:
            mtime = meta_path.stat().st_mtime
        out.append(
            {
                "id": meta_path.name[len("agent-") : -len(".meta.json")],
                "type": meta.get("agentType") or "?",
                "desc": meta.get("description") or "",
                "depth": meta.get("spawnDepth", 1),
                "model": t["model"],
                "turns": t["turns"],
                "tokens": {k: t[k] for k in ("input", "output", "cache_read", "cache_write")},
                "mtime": mtime,
                "active": now - mtime < SUBAGENT_ACTIVE_SEC,
            }
        )
    out.sort(key=lambda a: a["mtime"], reverse=True)
    return out


def _parse_usage() -> dict | None:
    try:
        raw = json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        return None
    cu = raw.get("cachedUsageUtilization") or {}
    limits = []
    for lim in (cu.get("utilization") or {}).get("limits") or []:
        if not isinstance(lim, dict):
            continue
        kind = str(lim.get("kind") or "?")
        label = LIMIT_LABELS.get(kind, kind)
        short = SHORT_LABELS.get(kind, kind)
        model = ((lim.get("scope") or {}).get("model") or {}).get("display_name")
        limits.append(
            {
                "label": f"{label} {model}" if model else label,
                "short": (f"{short} {model}" if model else short),
                "percent": lim.get("percent") or 0,
                "severity": lim.get("severity") or "normal",
                "resetsAt": lim.get("resets_at"),
                "active": bool(lim.get("is_active")),
            }
        )
    if not limits:
        return None
    tier = (raw.get("oauthAccount") or {}).get("userRateLimitTier") or ""
    return {
        "plan": tier.replace("default_", "").replace("claude_", "").replace("_", " "),
        "fetchedAt": (cu.get("fetchedAtMs") or 0) / 1000,
        "limits": limits,
    }


def read_usage() -> dict | None:
    """Plan utilization (what /usage shows). Claude Code caches it in ~/.claude.json;
    we never query the API ourselves, so the number is only as fresh as the cache -
    which is why fetchedAt travels with it."""
    try:
        mtime = os.stat(CONFIG).st_mtime
    except OSError:
        return None
    if _usage["mtime"] != mtime:
        _usage["mtime"] = mtime
        _usage["data"] = _parse_usage()
    return _usage["data"]


def code_version() -> str:
    """vYYYYMMDD-commit of the checkout this script runs from - the date is the
    commit's, not today's, so the same code always reports the same version. The
    plugin can be installed outside git, then only the file date is known."""
    here = Path(__file__).resolve()
    try:
        r = subprocess.run(
            ["git", "-C", str(here.parent), "log", "-1",
             "--format=v%cd-%h", "--date=format:%Y%m%d"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return time.strftime("v%Y%m%d", time.localtime(here.stat().st_mtime))


def git_branch(cwd: str, cache: dict[str, str | None]) -> str | None:
    """Live branch of the working directory. A branch belongs to the worktree, not
    the session - the one recorded in the transcript is stale for idle sessions."""
    if cwd in cache:
        return cache[cwd]
    b = None
    try:
        r = subprocess.run(
            ["git", "-C", cwd, "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0:
            b = r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        pass
    cache[cwd] = b
    return b


# The hosts whose web address is a plain https://<host>/<owner>/<repo> of the remote, in
# every form git writes one. Nothing is guessed for a host that is not listed - a link that
# opens the wrong page is worse than a repository name that is not a link at all.
WEB_HOSTS = ("github.com", "bitbucket.org")
REMOTE_RE = re.compile(r"^(?:(?:https|ssh|git)://)?(?:[^@/]+@)?([^/:]+)[:/](.+?)(?:\.git)?/?$")
OWNER_REPO_RE = re.compile(r"[\w.-]+/[\w.-]+")


def web_url(remote: str) -> str | None:
    """https://<host>/<owner>/<repo> out of `git@github.com:owner/repo.git`,
    `https://bitbucket.org/team/repo.git` or `ssh://git@github.com/owner/repo`. The
    address is built from the host and the path, never passed through from the remote:
    whatever the config holds, what reaches the page is a URL this function composed."""
    m = REMOTE_RE.match(remote.strip())
    if not m:
        return None
    host, path = m.group(1).lower(), m.group(2)
    if host not in WEB_HOSTS or not OWNER_REPO_RE.fullmatch(path):
        return None
    return f"https://{host}/{path}"


def git_repo(
    cwd: str, cache: dict[str, tuple[str, str | None, str | None]]
) -> tuple[str, str | None, str | None]:
    """(repository, worktree) of the working directory. A linked worktree is a directory of
    its own - `claude-sdlc-kit-BL-11` beside `claude-sdlc-kit` - so the basename of the cwd
    names the checkout, not the repository; what the two share is the common git dir.

    That dir only names the repository when it is the repository's own `.git`: a submodule
    and a bare repo keep theirs elsewhere, and those are repositories in their own right, so
    their toplevel is the answer. Outside a repository there is only the directory.

    The third value is the web address of `origin`, where the host has one this knows."""
    if cwd in cache:
        return cache[cwd]
    repo, wt, url = os.path.basename(cwd) or "?", None, None
    try:
        r = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--path-format=absolute",
             "--show-toplevel", "--git-common-dir"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0:
            top, _, common = r.stdout.strip().partition("\n")
            root = os.path.dirname(common) if common.endswith("/.git") else top
            if root:
                repo = os.path.basename(root) or repo
                if os.path.realpath(top) != os.path.realpath(root):
                    wt = os.path.basename(top)
            # a worktree shares the config, so origin is the repository's either way
            r = subprocess.run(
                ["git", "-C", cwd, "config", "--get", "remote.origin.url"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if r.returncode == 0:
                url = web_url(r.stdout)
    except (OSError, subprocess.SubprocessError):
        pass
    cache[cwd] = (repo, wt, url)
    return repo, wt, url


# The .app that a process ultimately belongs to - "Cursor" out of
# /Applications/Cursor.app/Contents/MacOS/Cursor.
APP_RE = re.compile(r"/([^/]+)\.app/Contents/MacOS/")
MAX_ANCESTRY = 12


def proc_table() -> dict[int, tuple[int, str, str]]:
    """pid -> (ppid, tty, command) for every process; one ps call per tick."""
    try:
        r = subprocess.run(
            ["ps", "-Ao", "pid=,ppid=,tty=,command="],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    out: dict[int, tuple[int, str, str]] = {}
    for line in r.stdout.splitlines():
        f = line.split(None, 3)
        if len(f) < 4:
            continue
        try:
            out[int(f[0])] = (int(f[1]), f[2], f[3])
        except ValueError:
            continue
    return out


def host(pid: int | None, procs: dict) -> dict | None:
    """Which terminal window is this session sitting in? Walk the parent chain
    (claude -> zsh -> pty-host -> Cursor.app) until an .app turns up. Under tmux or
    over ssh nothing owns the session any more and there is nothing to focus."""
    if not pid:
        return None
    tty = (procs.get(pid) or (0, "", ""))[1]
    seen = 0
    while pid > 1 and seen < MAX_ANCESTRY:
        e = procs.get(pid)
        if not e:
            return None
        m = APP_RE.search(e[2])
        if m:
            return {"app": m.group(1), "tty": tty if tty not in ("??", "-") else ""}
        pid, seen = e[0], seen + 1
    return None


def _q(s: str) -> str:
    """AppleScript string literal."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


# An editor keeps one window per open folder, so `open -a <editor> <cwd>` lands on
# the very window the session runs in - and unlike System Events it needs no
# Accessibility grant. A terminal emulator would just open a new window instead.
EDITORS = {"Cursor", "Code", "VSCodium", "Windsurf", "Zed", "Positron"}


def tab_script(app: str, dev: str) -> str | None:
    """Terminal and iTerm publish the tty of every tab, so the exact tab can be
    raised - the only two apps where focus is precise rather than approximate."""
    if app == "Terminal":
        return f'''tell application "Terminal"
  activate
  repeat with w in windows
    repeat with t in tabs of w
      if tty of t is {_q(dev)} then
        set selected of t to true
        set index of w to 1
        return "tab"
      end if
    end repeat
  end repeat
end tell
return "app"'''
    if app.startswith("iTerm"):
        return f'''tell application {_q(app)}
  activate
  repeat with w in windows
    repeat with t in tabs of w
      repeat with s in sessions of t
        if tty of s is {_q(dev)} then
          select w
          select t
          select s
          return "tab"
        end if
      end repeat
    end repeat
  end repeat
end tell
return "app"'''
    return None


def _run(cmd: list[str]) -> tuple[bool, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    if r.returncode == 0:
        return True, r.stdout.strip()
    err = r.stderr.strip().splitlines()
    return False, err[-1] if err else "failed"


def focus(pid: int, cwd: str) -> dict:
    """Bring the terminal window this session runs in to the front."""
    h = host(pid, proc_table())
    if not h:
        return {"ok": False, "error": "no terminal app owns this session"}
    app = h["app"]
    script = tab_script(app, f"/dev/{h['tty']}") if h["tty"] else None
    if script:
        ok, out = _run(["osascript", "-e", script])
        scope = out or "app"
    elif app in EDITORS and cwd:
        # The only value from the request that ends up used as a path. No shell is
        # involved, but `open` reads an argument starting with a dash as a switch, so
        # it is matched against the directories the server itself listed as sessions.
        if cwd not in {s.get("cwd", "") for s in registry()}:
            return {"ok": False, "error": "unknown session directory"}
        ok, out = _run(["open", "-a", app, cwd])
        scope = "window"
    else:
        ok, out = _run(["osascript", "-e", f"tell application {_q(app)} to activate"])
        scope = "app"
    return {"ok": True, "app": app, "scope": scope} if ok else {"ok": False, "error": out}


def agents_json() -> list[dict]:
    """`claude agents --json`, which answers for the caller's own session only - see
    registry(). Kept for `waitingFor`, which the registry files do not carry."""
    try:
        raw = subprocess.run(
            ["claude", "agents", "--json"], capture_output=True, text=True, timeout=20
        )
        return json.loads(raw.stdout) if raw.returncode == 0 else []
    except (OSError, ValueError, subprocess.SubprocessError):
        return []


SOCKET_TIMEOUT = 0.25


def alive(path: str) -> bool:
    """Is a session still behind its messaging socket? A live one listens; a session that
    died leaves the socket file behind and it refuses the connection. Nothing about the
    process is asked, which is the point - see registry()."""
    if not path or not os.path.exists(path):
        return False
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(SOCKET_TIMEOUT)
    try:
        s.connect(path)
        return True
    except OSError:
        return False
    finally:
        s.close()


def registry() -> list[dict]:
    """Every session on the machine, read from ~/.claude/sessions/<pid>.json.

    `claude agents --json` is the obvious source and used to be the only one, but it
    answers with the caller's own session and nothing else: Claude Code confines a session
    to its own process tree, so the liveness check behind that listing comes back EPERM
    for every *other* session - live or not - and they are all pruned away. A dashboard
    started by a SessionStart hook therefore showed exactly one card, its own, while half
    a dozen sessions were running.

    The registry files are readable and the sockets accept a connection from inside that
    confinement, so this reads the one and tests the other. `waitingFor` is the single
    field the files do not carry; build_state() overlays it from the CLI where it can.
    """
    out = []
    for f in SESSIONS.glob("*.json"):
        try:
            s = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if s.get("sessionId") and alive(s.get("messagingSocketPath") or ""):
            out.append(s)
    # one pid, one session: a recycled pid can leave two files behind, and the fresher
    # record is the one that still means something
    best: dict[int, dict] = {}
    for s in out:
        cur = best.get(s.get("pid"))
        if not cur or s.get("updatedAt", 0) > cur.get("updatedAt", 0):
            best[s.get("pid")] = s
    return list(best.values())


IDLE_STATUS = {"idle", "waiting", None}


def working(status: str | None) -> bool:
    """The status vocabulary is open-ended - `busy`, `idle`, `waiting` and `shell` have all
    turned up - so a session is working unless it is plainly not, and a status nobody here
    has seen yet still lands on the right side of the sort and of the count."""
    return status not in IDLE_STATUS


def build_state() -> dict:
    sessions = []
    branches: dict[str, str | None] = {}
    repos: dict[str, tuple[str, str | None, str | None]] = {}
    procs = proc_table()
    # `waitingFor` only ever arrives for the session the server itself runs in, so it is
    # an overlay on the registry rather than the list itself
    waiting = {a.get("sessionId"): a for a in agents_json()}
    for s in registry():
        sid = s.get("sessionId", "")
        s = {**s, **{k: v for k, v in waiting.get(sid, {}).items() if v is not None}}
        path = transcript(sid)
        t = scan(path) if path else _fresh()
        limit = CONTEXT_LIMITS.get(t["model"] or "", DEFAULT_LIMIT)
        try:
            mtime = os.stat(path).st_mtime if path else 0
        except OSError:
            mtime = 0
        subs = subagents(path, sid) if path else []
        branch = git_branch(s.get("cwd", ""), branches) or t["branch"]
        repo, worktree, repo_url = git_repo(s.get("cwd", ""), repos)
        att = attention(s, sid, mtime)
        if att:  # only a waiting session shows what it last said
            att["lastAgent"] = t["last_agent"]
        sessions.append(
            {
                "name": s.get("name") or sid[:8],
                "sessionId": sid,
                "pid": s.get("pid"),
                "kind": s.get("kind"),
                "status": s.get("status"),
                "attention": att,
                "cwd": s.get("cwd", ""),
                "repo": repo,
                "repoUrl": repo_url,
                "worktree": worktree,
                "startedAt": s.get("startedAt"),
                "branch": branch,
                "model": t["model"],
                "effort": t["effort"],
                "turns": t["turns"],
                "context": t["context"],
                "contextLimit": limit,
                "tokens": {
                    k: t[k]
                    for k in ("input", "output", "cache_read", "cache_write", "thinking")
                },
                "mtime": mtime,
                "host": (host(s.get("pid"), procs) or {}).get("app"),
                "subagents": subs,
            }
        )

    sessions.sort(key=lambda s: (not s["attention"], not working(s["status"]), -s["mtime"]))
    totals = {
        "sessions": len(sessions),
        "waiting": sum(1 for s in sessions if s["attention"]),
        "busy": sum(1 for s in sessions if working(s["status"])),
        "subagents": sum(len(s["subagents"]) for s in sessions),
        "output": sum(s["tokens"]["output"] for s in sessions),
        "input": sum(s["tokens"]["input"] for s in sessions),
        "cache_read": sum(s["tokens"]["cache_read"] for s in sessions),
        "cache_write": sum(s["tokens"]["cache_write"] for s in sessions),
        "thinking": sum(s["tokens"]["thinking"] for s in sessions),
        "turns": sum(s["turns"] for s in sessions),
        "context": sum(s["context"] for s in sessions),
    }
    return {
        "now": time.time(),
        "usage": read_usage(),
        "sessions": sessions,
        "totals": totals,
    }


# --- The project backlog (the `feature` plugin's `backlog` skill describes the file) ---
# BACKLOG.md is prose, written for a human and for the model; the dashboard only reads
# it. The structure is small and fixed - `##` is the priority, `###` a ticket - but the
# words are not: the file is written in the language of the repo, so nothing here
# matches on a label. `**Foo:** bar` is a field whatever `Foo` happens to say.
TICKET_RE = re.compile(r"^###\s+([A-Za-z]{1,8}-\d+)\s*[-\u2013\u2014]\s*(.+?)\s*$")
FIELD_RE = re.compile(r"^\*\*(.+?):\*\*\s*(.*)$")
LAST_ID_RE = re.compile(r"<!--\s*last-id:\s*([^\s>]+)\s*-->")
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
RULE_RE = re.compile(r"^-{3,}$")
_backlog_cache: dict[str, tuple[float, dict]] = {}


def parse_backlog(text: str) -> dict:
    sections: list[dict] = []
    ticket: dict | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            sections.append({"title": line[3:].strip(), "tickets": []})
            ticket = None
            continue
        m = TICKET_RE.match(line)
        if m:
            if not sections:  # a ticket above any priority heading still has to land
                sections.append({"title": "", "tickets": []})
            ticket = {"id": m.group(1), "title": m.group(2), "fields": [], "body": []}
            sections[-1]["tickets"].append(ticket)
            continue
        if ticket is None:
            continue
        f = FIELD_RE.match(line.strip())
        if f:  # a field is a field wherever it sits - `Branch` is appended later
            ticket["fields"].append([f.group(1), f.group(2)])
            continue
        # `<!-- last-id -->` and a `---` rule belong to the file, not to the last
        # ticket that happens to stand above them. Blank lines stay - they are what
        # separates the paragraphs.
        line = COMMENT_RE.sub("", line)
        if not RULE_RE.match(line.strip()):
            ticket["body"].append(line)
    count = 0
    for sec in sections:
        for t in sec["tickets"]:
            t["body"] = "\n".join(t["body"]).strip()
            count += 1
    last = LAST_ID_RE.search(text)
    return {"sections": sections, "count": count,
            "lastId": last.group(1) if last else None}


def read_backlog(path: Path) -> dict | None:
    """Parsed only when the file has changed - the view is repainted every tick."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    hit = _backlog_cache.get(str(path))
    if not hit or hit[0] != mtime:
        try:
            data = parse_backlog(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            return None
        data["mtime"] = mtime
        hit = _backlog_cache[str(path)] = (mtime, data)
    return hit[1]


def backlog_root(cwd: str, cache: dict[str, str | None]) -> str | None:
    """The backlog lives in the repository root, which is not always the session's
    cwd - so walk up for it, but never out of the repository."""
    if cwd in cache:
        return cache[cwd]
    root, p = None, Path(cwd) if cwd else None
    while p and p != p.parent:
        if (p / "BACKLOG.md").is_file():
            root = str(p)
            break
        if (p / ".git").exists():
            break
        p = p.parent
    cache[cwd] = root
    return root


def live_tickets(open_: dict, branch: str | None) -> list[str]:
    """Ids of the open tickets somebody is sitting on right now - the ones carrying a field
    whose value *is* the branch the worktree is on (`**Branch:** feature/BL-7-x`, backticks
    allowed). Not a field that merely mentions it: `parse_backlog` calls every `**Foo:** bar`
    line a field, prose included, so a ticket warning that "merge do `main` must stay green"
    would otherwise claim to be in progress the moment anybody sits on `main`.

    The flag is returned beside the tickets, never written into them: `read_backlog` hands
    out the very dict it keeps in `_backlog_cache`, so a flag set once would outlive the
    branch - and mutating it would race the `json.dumps` the GET path runs under the lock.

    `BACKLOG.done.md` is deliberately not searched: a closed ticket cannot be in progress,
    and it keeps its `Branch` field when it moves to the archive - so a merged branch nobody
    has deleted yet would light up the ticket it finished."""
    if not branch:
        return []
    return [t["id"] for sec in open_["sections"] for t in sec["tickets"]
            if any(v.replace("`", "").strip() == branch for _, v in t["fields"])]


def build_backlog() -> dict:
    """Only projects that some open session is sitting in - the monitor knows nothing
    about a repository nobody has a session in, and does not go looking for one."""
    sessions = registry()
    cache: dict[str, str | None] = {}
    groups: dict[str, list[dict]] = {}
    for s in sessions:
        root = backlog_root(s.get("cwd", ""), cache)
        if root:  # grouped, not first-wins - a repo often has more than one session
            groups.setdefault(root, []).append(s)

    procs = proc_table() if groups else {}
    projects = []
    for root, group in groups.items():
        open_ = read_backlog(Path(root) / "BACKLOG.md")
        if not open_:
            continue
        done = read_backlog(Path(root) / "BACKLOG.done.md")
        # one branch per project, not per session: the sessions of a group share a root,
        # a root sits in one worktree, and a branch belongs to the worktree
        branch = git_branch(root, {})
        live = live_tickets(open_, branch)
        # any session a terminal app owns will do for the focus button - they are all in
        # the same directory. Under tmux or over ssh no app owns one, and there is none.
        pick = next(((s, h) for s in group if (h := host(s.get("pid"), procs))), None)
        projects.append({
            "name": os.path.basename(root) or root,
            "root": root,
            "open": open_,
            "done": done,
            "live": live,
            "session": {"pid": pick[0].get("pid"), "cwd": pick[0].get("cwd", ""),
                        "host": pick[1]["app"]} if pick else None,
        })
    return {
        "now": time.time(),
        "waiting": waiting_count(sessions),
        "projects": sorted(projects, key=lambda p: p["name"]),
    }


def waiting_count(sessions: list[dict]) -> int:
    """The `needs you` count without scanning a single transcript - the backlog view
    has no session cards, but the tab title still has to warn."""
    k = 0
    for s in sessions:
        sid = s.get("sessionId", "")
        path = transcript(sid)
        try:
            mtime = os.stat(path).st_mtime if path else 0
        except OSError:
            mtime = 0
        if attention(s, sid, mtime):
            k += 1
    return k


PAGE = r"""<!doctype html>
<meta charset="utf-8"><title>Claudemon</title>
<link rel="manifest" href="/manifest.webmanifest">
<link rel="icon" href="/icon.svg" type="image/svg+xml">
<link rel="icon" href="/icon-32.png" sizes="32x32" type="image/png">
<link rel="apple-touch-icon" href="/icon-180.png">
<meta name="application-name" content="Claudemon">
<meta name="apple-mobile-web-app-title" content="Claudemon">
<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#191817">
<meta name="theme-color" media="(prefers-color-scheme: light)" content="#f7f5f1">
<style>
/* Two palettes, one set of names. `data-theme` on the root always names the theme that
   is actually painted - "dark" or "light", never "system" - so which of the two the system
   asks for gets resolved once in JS instead of every palette being repeated here under a
   `prefers-color-scheme` block. Amber is the one color that needs two entries: `--att` is
   the fill and the border, `--att-ink` the same signal as text, which on a light card has
   to be dark enough to read. */
:root,:root[data-theme="dark"]{color-scheme:dark;
      --bg:#191817;--card:#232120;--fg:#f0eee9;--dim:#9a938a;--line:#35322f;
      --busy:#f0906a;--idle:#7cc292;--warn:#e0a94a;--bar:#d97757;--bar2:#3d3936;
      --max:#f2776b;--idle-bg:#1d1b1a;--idle-line:#2b2927;--idle-fg:#c9c2b8;
      --att:#ffb02e;--att-ink:#ffb02e;--att-fg:#191817;--att-bg:#3a2c12;
      --att-soft:rgba(255,176,46,.16);--att-soft2:rgba(255,176,46,.04)}
:root[data-theme="light"]{color-scheme:light;
      --bg:#f7f5f1;--card:#fff;--fg:#1f1d1b;--dim:#6b635a;--line:#e2ddd5;
      --busy:#c2410c;--idle:#2f7d54;--warn:#b07712;--bar:#b4451f;--bar2:#e8e2d9;
      --max:#d63f22;--idle-bg:#f2efe9;--idle-line:#e6e1d8;--idle-fg:#4b453d;
      --att:#e08600;--att-ink:#8a5200;--att-fg:#191817;--att-bg:#fdf1dc;
      --att-soft:rgba(224,134,0,.20);--att-soft2:rgba(224,134,0,.06)}
*{box-sizing:border-box}
[hidden]{display:none!important}  /* .kpis/.grid set display, which beats the UA rule */
body{margin:0;padding:18px;background:var(--bg);color:var(--fg);
     font:14px/1.45 ui-sans-serif,-apple-system,system-ui,sans-serif}
h1{font-size:16px;margin:0 0 2px;font-weight:650}
.sub{color:var(--dim);font-size:12px;margin-bottom:16px}
.iv{background:none;border:1px solid var(--line);border-radius:5px;color:var(--dim);
    font:inherit;padding:0 6px;cursor:pointer;font-variant-numeric:tabular-nums}
.iv:hover{border-color:var(--dim);color:var(--fg)}
.kpis{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px}
.kpi.plan{min-width:86px}
.kpi.plan.on{border-color:var(--busy)}
.kpi .bar{margin:6px 0 0}
.kpi.hot .bar>i{background:var(--warn)}
.kpi.max .bar>i{background:var(--max)}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 12px}
.kpis:not(.all) .kpi.more-only{display:none}
.more{background:none;border:1px dashed var(--line);border-radius:8px;color:var(--dim);
      padding:8px 12px;font:inherit;font-size:11px;text-transform:uppercase;
      letter-spacing:.04em;cursor:pointer;text-align:center}
.more i{display:block;font-size:19px;font-style:normal;line-height:1}
.more:hover{border-color:var(--dim);color:var(--fg)}
.kpi b{display:block;font-size:19px;font-variant-numeric:tabular-nums}
.kpi span{font-size:11px;color:var(--dim);text-transform:uppercase;letter-spacing:.04em}
.grid{display:grid;gap:10px;grid-template-columns:repeat(auto-fill,minmax(340px,1fr))}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.card.idle{background:var(--idle-bg);border-color:var(--idle-line);color:var(--dim)}
.card.idle .toks b,.card.idle h2{color:var(--idle-fg)}
.card.att{border:2px solid var(--att);padding:11px 13px;
          box-shadow:0 0 0 3px var(--att-soft),0 0 30px -6px var(--att);
          animation:pulse 1.8s ease-in-out infinite}
@keyframes pulse{50%{box-shadow:0 0 0 3px var(--att-soft2),0 0 8px -4px var(--att)}}
@media (prefers-reduced-motion:reduce){
  .card.att{animation:none}
  .spin{animation:none;border-top-color:currentColor}
}
.head{display:flex;align-items:baseline;gap:8px;margin-bottom:2px}
.head h2{font-size:14px;margin:0;font-weight:620;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.go{font-size:10px;padding:2px 7px;border-radius:99px;border:1px solid var(--line);
    background:none;color:var(--dim);font:inherit;font-size:10px;text-transform:uppercase;
    letter-spacing:.05em;font-weight:600;cursor:pointer;flex:none}
.go:hover{border-color:var(--busy);color:var(--busy)}
.go:disabled{opacity:.4;cursor:default}
.card.att .go{border-color:var(--att);color:var(--att-ink)}
.pill{font-size:10px;padding:2px 7px;border-radius:99px;border:1px solid currentColor;
      text-transform:uppercase;letter-spacing:.05em;font-weight:600}
.pill.busy{color:var(--busy)}.pill.idle{color:var(--idle)}
.spin{display:inline-block;vertical-align:-1px;width:8px;height:8px;margin-right:5px;
      border:1.5px solid currentColor;border-top-color:transparent;border-radius:99px;
      animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.pill.att{color:var(--att-fg);background:var(--att);border-color:var(--att)}
.att-row{background:var(--att-bg);border:1px solid var(--att);border-radius:7px;
         padding:6px 9px;margin:0 0 9px;font-size:12.5px;line-height:1.4}
.att-row b{color:var(--att-ink)}
.att-row .d{color:var(--dim);display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.att-row .say{margin-top:4px;color:var(--dim);cursor:pointer;overflow:hidden;
              display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.att-row .say::before{content:"\25be ";color:var(--att-ink)}
.att-row .say.open{display:block;white-space:pre-wrap}
.att-row .say.open::before{content:"\25b4 "}
.kpi.att b{color:var(--att-ink)}
.repo,.branch,.wt{font-size:12px;margin-bottom:1px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.repo,.branch{color:var(--fg);opacity:.75}
.repo{font-weight:460}
.repo a{color:inherit;text-decoration:none;border-bottom:1px dotted currentColor}
.repo a:hover{color:var(--busy);border-bottom-style:solid}
.branch{font-weight:620}
.wt{font-size:11.5px;color:var(--dim)}
.meta{color:var(--dim);font-size:12px;margin-bottom:9px}
.bar{height:5px;background:var(--bar2);border-radius:99px;overflow:hidden;margin:3px 0 5px}
.bar>i{display:block;height:100%;background:var(--bar)}
.toks{display:grid;grid-template-columns:1fr 1fr;gap:1px 12px;font-size:12px;color:var(--dim)}
.toks b{color:var(--fg);font-weight:550;font-variant-numeric:tabular-nums;float:right}
.subs{margin-top:10px;border-top:1px solid var(--line);padding-top:8px}
.subs>div{display:flex;gap:7px;align-items:baseline;font-size:12px;padding:2px 0}
.dot{width:6px;height:6px;border-radius:99px;background:var(--bar2);flex:none;margin-top:5px}
.dot.on{background:var(--busy)}
.sa-name{font-weight:550;white-space:nowrap}
.sa-desc{color:var(--dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}
.sa-tok{color:var(--dim);font-variant-numeric:tabular-nums;flex:none}
.corner{position:absolute;top:14px;right:18px;display:flex;align-items:center;gap:8px}
.ver{color:var(--dim);font-size:11px;font-variant-numeric:tabular-nums}
.th{background:none;border:1px solid var(--line);border-radius:5px;color:var(--dim);
    font:inherit;font-size:13px;line-height:1.3;padding:0 7px;cursor:pointer}
.th:hover{border-color:var(--dim);color:var(--fg)}
.tabs{display:inline-flex;gap:6px;margin-bottom:14px}
.tab{background:none;border:1px solid var(--line);border-radius:6px;color:var(--dim);
     font:inherit;font-size:12px;padding:3px 10px;cursor:pointer}
.tab:hover{border-color:var(--dim);color:var(--fg)}
.tab.on{border-color:var(--bar);color:var(--fg)}
/* the backlog: a list to scan on the left, one ticket open on the right - a ticket is
   several paragraphs of prose, so cards side by side turn into a wall of text */
.bl{display:grid;gap:16px;grid-template-columns:minmax(260px,360px) 1fr;align-items:start}
@media (max-width:820px){.bl{grid-template-columns:1fr}}
.bl .meta{margin-bottom:8px}
.grp{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--dim);
     font-weight:600;margin:12px 0 4px}
.grp:first-child{margin-top:0}
.tr{display:flex;gap:8px;padding:3px 7px;border-radius:6px;cursor:pointer;
    border:1px solid transparent}
.tr:hover{background:var(--card)}
.tr.on{background:var(--card);border-color:var(--bar)}
.tr.done{opacity:.5}
.tr .id{color:var(--bar);font-variant-numeric:tabular-nums;flex:none;font-size:12.5px}
.tr .ti{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px}
.tr .spin{color:var(--busy);flex:none;align-self:center;margin:0}
.tk{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;
    position:sticky;top:18px}
.tk-h{font-weight:600;font-size:15px;margin-bottom:6px;display:flex;align-items:baseline;gap:8px}
.tk-t{flex:1}
.tk-act{display:flex;gap:5px;flex:none}
.tk-id{color:var(--bar);font-variant-numeric:tabular-nums;margin-right:6px}
.tk-f{font-size:12.5px;color:var(--dim)}
.tk-f b{color:var(--fg);font-weight:550}
.tk-b{font-size:13px;color:var(--dim);margin-top:8px;max-width:78ch}
.tk-b p{margin:0 0 8px}
.tk-b pre{background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:8px 10px;
          overflow-x:auto;font-size:11.5px;margin:0 0 8px}
.tk-b code,.tk-f code{background:var(--bar2);border-radius:4px;padding:0 3px;font-size:11.5px}
.bl-none{color:var(--dim);font-size:13px}
</style>
<script>
// The root has to carry the theme before the first paint, otherwise a light-mode reload
// flashes the dark palette. The main script below owns the switch; this only repeats the
// one read it needs to get ahead of the stylesheet.
var _th;
try { _th = JSON.parse(localStorage.getItem("claude-monitor:theme")); } catch (e) {}
document.documentElement.dataset.theme = _th === "light" || _th === "dark" ? _th
  : matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
</script>
<div class="corner">
  <button class="th" onclick="cycleTheme()"></button>
  <span class="ver">__VERSION__</span>
</div>
<h1>Claudemon</h1>
<div class="sub" id="sub">loading…</div>
<div class="tabs">
  <button class="tab on" data-v="sessions" onclick="setView('sessions')">sessions</button>
  <button class="tab" data-v="backlog" onclick="setView('backlog')">backlog</button>
</div>
<div class="kpis" id="kpis"></div>
<div class="grid" id="grid"></div>
<div id="backlog" hidden></div>
<script>
const n = v => v >= 1e6 ? (v/1e6).toFixed(2)+"M" : v >= 1e3 ? Math.round(v/1e3)+"k" : String(v||0);
const dur = s => s < 60 ? Math.round(s)+" s" : s < 3600 ? Math.round(s/60)+" min"
  : s < 86400 ? (s/3600).toFixed(1)+" h" : (s/86400).toFixed(1)+" d";
const ago = (t, now) => dur(Math.max(0, now - t));
// quotes included: most of what goes through esc() lands in an attribute, and a repository
// path or a ticket title is allowed to contain one
const esc = s => (s||"").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",
  '"':"&quot;","'":"&#39;"}[c]));

function kpi(v, l, c){ return `<div class="kpi ${c||""}"><b>${v}</b><span>${l}</span></div>`; }

// Everything the user picks in the header or on the board lives in a plain variable,
// because both the grid and the board are rebuilt from `innerHTML` on every tick. That
// makes a reload - including the one the dashboard forces on itself after a server
// restart - throw the whole view away, so each of those variables is mirrored here.
// Storage can be denied outright (private windows, cookies off); a dashboard that
// forgets is better than one that does not paint.
const LS = "claude-monitor:";
function load(k, dflt){
  try { const v = localStorage.getItem(LS + k); return v === null ? dflt : JSON.parse(v); }
  catch (e) { return dflt; }
}
function save(k, v){ try { localStorage.setItem(LS + k, JSON.stringify(v)); } catch (e) {} }

// dark / light / by the system, cycled from the corner button. `data-theme` on the root
// is the theme being painted, the stored choice can also be "system" - so the media query
// is read here, and a system that flips while "system" is chosen repaints the page.
const THEMES = ["system", "light", "dark"];
const THEME_GLYPH = {system: "\u25d1", light: "\u2600", dark: "\u263d"};
let theme = load("theme", "system");
if(!THEMES.includes(theme)) theme = "system";  // an unknown value in storage
const sysLight = matchMedia("(prefers-color-scheme: light)");
function applyTheme(){
  const eff = theme === "system" ? (sysLight.matches ? "light" : "dark") : theme;
  document.documentElement.dataset.theme = eff;
  const b = document.querySelector(".th");
  b.textContent = THEME_GLYPH[theme];
  b.title = "theme: " + theme + (theme === "system" ? " (" + eff + ")" : "");
}
function cycleTheme(){
  theme = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
  save("theme", theme);
  applyTheme();
}
sysLight.addEventListener("change", () => { if(theme === "system") applyTheme(); });

// click the interval in the sub line to cycle it; like the KPI fold, the state has to
// live outside the DOM because the sub line is rewritten on every tick
const INTERVALS = [[3000, "3 s"], [10000, "10 s"], [60000, "1 min"], [0, "stop"]];
let ivIdx = load("iv", 0), timer = null;
if(!INTERVALS[ivIdx]) ivIdx = 0;  // the list may have been shorter when this was stored
function arm(){
  clearInterval(timer);
  const ms = INTERVALS[ivIdx][0];
  if(ms) timer = setInterval(tick, ms);  // "stop" is 0 - no timer, not a very long one
}
function cycleRefresh(){
  ivIdx = (ivIdx + 1) % INTERVALS.length;
  save("iv", ivIdx);
  arm();
  // tick() repaints the label too, but only once its fetch resolves - a click has to
  // answer immediately, so write it here as well
  document.querySelector(".iv").textContent = INTERVALS[ivIdx][1];
  tick();
}

// the KPI row is rebuilt every tick, so the fold state lives out here, not in the DOM
let kpisAll = load("kpis", false);
function toggleKpis(){
  kpisAll = !kpisAll;
  save("kpis", kpisAll);
  paintKpiFold();
}
function paintKpiFold(){
  const el = document.getElementById("kpis");
  el.classList.toggle("all", kpisAll);
  const b = el.querySelector(".more");
  if(b){
    b.querySelector("i").textContent = kpisAll ? "\u2190" : "\u2192";
    b.querySelector("span").textContent = kpisAll ? "show less" : "show more";
  }
}

// share of the input side served from the cache - what keeps a long session cheap
function hit(T){
  const all = T.cache_read + T.cache_write + T.input;
  return all ? Math.round(100 * T.cache_read / all) + "%" : "–";
}

// plan utilization as a KPI tile - the long label and the countdown are in the tooltip
function planKpis(u, now){
  if(!u) return "";
  return u.limits.map(l => {
    const p = Math.max(0, Math.min(100, l.percent));
    const cls = (p >= 90 || l.severity === "critical") ? "max"
              : (p >= 70 || l.severity === "warning") ? "hot" : "";
    const reset = l.resetsAt
      ? " · resets in " + dur(Math.max(0, Date.parse(l.resetsAt)/1000 - now)) : "";
    const age = " · from the Claude Code cache, " + ago(u.fetchedAt, now) + " old";
    return `<div class="kpi plan ${cls}${l.active ? " on" : ""}"`
      + ` title="${esc(l.label)}${reset}${age}">`
      + `<b>${Math.round(p)} %</b><span>${esc(l.short)}</span>`
      + `<div class="bar"><i style="width:${p}%"></i></div></div>`;
  }).join("");
}

// same reason as the KPI fold: the cards are rebuilt every tick
const expanded = new Set();  // sessions whose last agent message is unfolded
document.getElementById("grid").addEventListener("click", ev => {
  const go = ev.target.closest(".go");
  if(go){ focusSession(go); return; }
  const el = ev.target.closest(".say");
  if(!el) return;
  const sid = el.dataset.sid;
  expanded.has(sid) ? expanded.delete(sid) : expanded.add(sid);
  el.classList.toggle("open");
});

// The page has no way to raise a native window, so the server does it over
// AppleScript; the button reports back in place because the window that comes
// forward is not this one - the user is looking elsewhere by then.
async function focusSession(btn){
  const label = btn.innerHTML;
  btn.disabled = true;
  try {
    const r = await (await fetch("/api/focus", {method: "POST", headers: {
      "Content-Type": "application/json"}, body: JSON.stringify({
        pid: Number(btn.dataset.pid), cwd: btn.dataset.cwd})})).json();
    if(!r.ok) throw new Error(r.error || "failed");
  } catch (e) {
    btn.innerHTML = "\u2717 " + esc(String(e.message || e).slice(0, 40));
    btn.title = String(e.message || e);
    setTimeout(() => { btn.innerHTML = label; btn.disabled = false; }, 4000);
    return;
  }
  btn.disabled = false;
}

function card(s, now){
  const a = s.attention;
  const st = a ? "att" : s.status;
  const pct = s.contextLimit ? Math.min(100, 100*s.context/s.contextLimit) : 0;
  const t = s.tokens;
  const subs = s.subagents.map(a => `<div>
      <i class="dot ${a.active?"on":""}"></i>
      <span class="sa-name">${esc(a.type)}</span>
      <span class="sa-desc">${esc(a.desc)}</span>
      <span class="sa-tok">${n(a.tokens.output)} out · ${ago(a.mtime, now)}</span></div>`).join("");
  const said = a && a.lastAgent;
  const att = a ? `<div class="att-row">&#9203; <b>${esc(a.label)}</b> &middot; ${ago(a.since, now)}
      ${a.detail ? `<span class="d">${esc(a.detail)}</span>` : ""}
      ${said ? `<div class="say${expanded.has(s.sessionId) ? " open" : ""}"
        data-sid="${esc(s.sessionId)}" title="click to expand">${esc(said.text)}</div>` : ""
      }</div>` : "";
  return `<div class="card ${st}">
    <div class="head"><h2>${esc(s.name)}</h2>
      ${s.host ? `<button class="go" data-pid="${s.pid}" data-cwd="${esc(s.cwd)}"
        title="bring the ${esc(s.host)} window running this session to the front"
        >&#8599; ${esc(s.host)}</button>` : ""}
      <span class="pill ${st}">${st === "busy" ? '<i class="spin"></i>' : ""}${
        a ? "needs you" : st}</span></div>
    <div class="repo">${s.repoUrl
      ? `<a href="${esc(s.repoUrl)}" target="_blank" rel="noreferrer"
          title="${esc(s.repoUrl)}">${esc(s.repo)}</a>` : esc(s.repo)}</div>
    ${s.branch ? `<div class="branch">${esc(s.branch)}</div>` : ""}
    ${s.worktree ? `<div class="wt">wt:${esc(s.worktree)}</div>` : ""}
    <div class="meta">${esc(s.kind)}
      · pid ${s.pid} · ${esc(s.model||"?")}${s.effort?" / "+esc(s.effort):""}
      <br>${s.turns} turns · active ${ago(s.mtime, now)} ago</div>
    ${att}
    <div class="bar"><i style="width:${pct}%"></i></div>
    <div class="toks">
      <div>context <b>${n(s.context)} / ${n(s.contextLimit)}</b></div>
      <div>output <b>${n(t.output)}</b></div>
      <div>cache read <b>${n(t.cache_read)}</b></div>
      <div>cache write <b>${n(t.cache_write)}</b></div>
      <div>input <b>${n(t.input)}</b></div>
      <div>thinking <b>${n(t.thinking)}</b></div>
    </div>
    ${subs ? `<div class="subs">${subs}</div>` : ""}
  </div>`;
}

// The backlog is the same file the model reads - a ticket is prose, so render it as
// prose. No labels are hardcoded: whatever `**Foo:**` the file uses is what shows up.
const md = s => esc(s).replace(/`([^`]+)`/g, "<code>$1</code>")
                      .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");

// Line by line, because a ``` fence is not always surrounded by blank lines - and an
// inline-code regex let loose across one swallows the rest of the ticket.
function body(t){
  const out = [];
  let para = [], pre = null;
  const flush = () => { if(para.length){ out.push(`<p>${md(para.join(" "))}</p>`); para = []; } };
  for(const line of t.body.split("\n")){
    if(line.trimStart().startsWith("```")){
      if(pre === null){ flush(); pre = []; }
      else { out.push(`<pre>${esc(pre.join("\n"))}</pre>`); pre = null; }
      continue;
    }
    if(pre !== null) pre.push(line);
    else if(line.trim()) para.push(line.trim());
    else flush();
  }
  if(pre !== null) out.push(`<pre>${esc(pre.join("\n"))}</pre>`);  // unclosed fence
  flush();
  return out.join("");
}

// What a button last said - the board is repainted wholesale every tick, so a label
// written into the DOM would be gone before it is read. One slot: a second click replaces
// the message, and `key` (ticket+action) decides which button it is shown on.
let blFlash = null;  // {key, text, until}
async function flash(key, text, ms){
  const f = blFlash = {key, text, until: Infinity};
  await tick();  // the countdown starts when the label is painted, not when it is set -
  if(blFlash !== f) return;  // a slow /api/backlog would otherwise eat the whole message
  f.until = Date.now() + ms;
  setTimeout(tick, ms + 50);  // it has to expire even with auto-refresh stopped
}
const label = (key, dflt) =>
  blFlash && blFlash.key === key && Date.now() < blFlash.until ? esc(blFlash.text) : dflt;

function detail(t, p){
  const live = p.live.includes(t.id);
  const cmd = "/feature:start " + t.id;
  // every value an action needs rides on the button, the way the session cards carry
  // data-pid/data-cwd: a click is handled against the board that painted it, not against
  // whatever `blProj` has moved on to while a repaint was in flight
  const act = [`<button class="go" data-act="copy" data-id="${esc(t.id)}"
      data-cmd="${esc(cmd)}"
      title="copy ${esc(cmd)} to the clipboard">${label(t.id + ":copy", "copy")}</button>`];
  if(p.session) act.push(`<button class="go" data-act="focus" data-id="${esc(t.id)}"
      data-pid="${esc(String(p.session.pid))}" data-cwd="${esc(p.session.cwd)}"
      title="bring the ${esc(p.session.host)} window of this project to the front"
      >${label(t.id + ":focus", "\u2197 " + esc(p.session.host))}</button>`);
  return `<div class="tk"><div class="tk-h"><span class="tk-t">${
      live ? `<i class="spin" title="a session is running on this ticket"></i>` : ""}<span class="tk-id">${esc(t.id)}</span>${
      esc(t.title)}</span><span class="tk-act">${act.join("")}</span></div>`
    + t.fields.map(f => `<div class="tk-f"><b>${esc(f[0])}</b> ${md(f[1])}</div>`).join("")
    + (t.body ? `<div class="tk-b">${body(t)}</div>` : "")
    + `</div>`;
}

// which project and which ticket are open; the board is repainted on every tick, so
// neither can live in the DOM
let blProj = load("blProj", null), blSel = load("blSel", null);
// a stored project or ticket can be gone by the time it is read back - the session ended,
// the ticket was closed - so both are written through here and `board()` corrects them
function setProj(root){ blProj = root; save("blProj", root); setSel(null); }
function setSel(id){ blSel = id; save("blSel", id); }

function board(d){
  if(!d.projects.length) return `<div class="bl-none">No open session sits in a project
    with a <code>BACKLOG.md</code>. <code>/feature:backlog-init</code> sets one up.</div>`;
  let p = d.projects.find(x => x.root === blProj);
  if(!p){ p = d.projects[0]; setProj(p.root); }
  const groups = p.open.sections.map(s => [s.title, s.tickets, false]);
  if(p.done && p.done.count)  // closed tickets stay reachable, just dimmed and last
    groups.push(["closed", p.done.sections.flatMap(s => s.tickets), true]);
  const all = groups.flatMap(g => g[1]);
  if(!all.some(t => t.id === blSel)) setSel(all.length ? all[0].id : null);
  const picker = d.projects.length > 1
    ? `<div class="tabs">` + d.projects.map(x => `<button class="tab${
        x.root === blProj ? " on" : ""}" data-root="${esc(x.root)}" title="${esc(x.root)}">${
        esc(x.name)} &middot; ${x.open.count}</button>`).join("") + `</div>`
    : "";
  const list = groups.map(([title, ts, done]) => `<div class="grp">${esc(title)} &middot; ${
    ts.length}</div>` + ts.map(t => `<div class="tr${t.id === blSel ? " on" : ""}${
      done ? " done" : ""}" data-id="${esc(t.id)}" title="${esc(t.title)}"><span class="id">${esc(t.id)}</span>
      <span class="ti">${esc(t.title)}</span>${p.live.includes(t.id)
        ? `<i class="spin" title="a session is running on this ticket"></i>` : ""}</div>`).join("")).join("");
  const sel = all.find(t => t.id === blSel);
  return picker + `<div class="bl"><div><div class="meta">${p.open.count} open${
      p.open.lastId ? " &middot; last id " + esc(p.open.lastId) : ""} &middot; ${esc(p.root)}</div>
      ${list}</div><div>${sel ? detail(sel, p) : ""}</div></div>`;
}

document.getElementById("backlog").addEventListener("click", ev => {
  const act = ev.target.closest("button[data-act]");
  if(act){ boardAction(act); return; }
  const proj = ev.target.closest("button[data-root]");
  if(proj){ setProj(proj.dataset.root); tick(); return; }
  const row = ev.target.closest(".tr");
  if(row){ setSel(row.dataset.id); tick(); }
});

// The board's own handler; `focusSession` stays with the grid, because it reports into
// `btn.innerHTML` with a 4 s timer and the board throws that node away every 3 s.
// Everything here - success and failure alike - goes through `blFlash` instead.
async function boardAction(btn){
  const d = btn.dataset, id = d.id, what = d.act, key = id + ":" + what;
  if(what === "copy"){
    try {
      await navigator.clipboard.writeText(d.cmd);
      flash(key, "\u2713 copied", 2500);
    } catch (e) { flash(key, "\u2717 " + String(e.message || e).slice(0, 30), 4000); }
    return;
  }
  if(blFlash && blFlash.key === key && blFlash.until === Infinity) return;  // still in flight
  flash(key, "\u2026", 30000);
  try {
    const r = await (await fetch("/api/focus", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({pid: Number(d.pid), cwd: d.cwd})})).json();
    if(!r.ok) throw new Error(r.error || "failed");
    flash(key, "\u2713", 3000);
  } catch (e) { flash(key, "\u2717 " + String(e.message || e).slice(0, 30), 5000); }
}

// which view is painted; the sessions grid and the backlog never show at once - with
// eight sessions the board would be a scroll away, which is not a board
let view = load("view", "sessions");
if(view !== "backlog") view = "sessions";
function setView(v){
  view = v;
  save("view", v);
  // only the view tabs - the board's project picker shares the class and would lose its
  // own `on` until the next repaint three seconds later
  document.querySelectorAll(".tab[data-v]").forEach(b => b.classList.toggle("on", b.dataset.v === v));
  document.getElementById("kpis").hidden = v !== "sessions";
  document.getElementById("grid").hidden = v !== "sessions";
  document.getElementById("backlog").hidden = v !== "backlog";
  tick();
}

function stamp(){
  document.getElementById("sub").innerHTML =
    "updated " + new Date().toLocaleTimeString() + " · auto-refresh "
    + `<button class="iv" onclick="cycleRefresh()" title="click to change the interval">`
    + INTERVALS[ivIdx][1] + `</button>`;
}

async function tickBacklog(){
  const d = await (await fetch("/api/backlog")).json();
  stamp();
  document.getElementById("backlog").innerHTML = board(d);
  document.title = (d.waiting ? `(${d.waiting}) ` : "") + "Claudemon";
}

async function tick(){
  try {
    if(view === "backlog"){ await tickBacklog(); return; }
    const d = await (await fetch("/api/state")).json();
    const T = d.totals, now = d.now;
    const U = d.usage;
    stamp();
    document.getElementById("kpis").innerHTML =
      planKpis(U, now)
      + kpi(T.sessions, "sessions") + kpi(T.busy, "busy")
      + `<div class="kpi${T.waiting ? " att" : ""}"><b>${T.waiting}</b>`
      + `<span>need you</span></div>`
      + kpi(n(T.context), "context total")
      + kpi(n(T.output), "output tokens") + kpi(hit(T), "cache hit")
      + kpi(T.subagents, "subagents", "more-only")
      + kpi(T.turns, "turns", "more-only")
      + kpi(n(T.input), "input tokens", "more-only")
      + kpi(n(T.thinking), "thinking", "more-only")
      + kpi(n(T.cache_read), "cache read", "more-only")
      + kpi(n(T.cache_write), "cache write", "more-only")
      + (U ? kpi(esc(U.plan), "plan", "more-only") : "")
      + `<button class="more" onclick="toggleKpis()"><i>\u2192</i><span>show more</span></button>`;
    paintKpiFold();
    document.getElementById("grid").innerHTML = d.sessions.map(s => card(s, now)).join("");
    document.title = (T.waiting ? `(${T.waiting}) ` : "") + "Claudemon";
  } catch (e) {
    document.getElementById("sub").textContent = "connection to the server failed: " + e;
  }
}
applyTheme();  // the early script set the palette, this puts the choice on the button
setView(view);  // the markup ships with sessions open; a restored view has to take over
arm();
</script>
"""
VERSION = code_version()
PAGE = PAGE.replace("__VERSION__", VERSION)

# Before a restart replaces whatever holds the port it has to know the process is ours, and
# `ps` cannot be relied on to say so - a process spawned by Claude Code can be refused the
# process table outright ("operation not permitted"), which used to read as "somebody
# else's server" and made the restart back off. So the dashboard introduces itself on a
# route nothing else answers; see tools/restart.sh.
WHOAMI = json.dumps({"app": "claude-monitor", "pid": os.getpid(), "version": VERSION})

MANIFEST = json.dumps({
    "id": "/",
    "name": APP_NAME,
    "short_name": APP_NAME,
    "description": "Live dashboard of every Claude Code session on this machine.",
    "start_url": "/",
    "scope": "/",
    "display": "standalone",
    "background_color": "#191817",
    "theme_color": "#191817",
    "icons": [
        {"src": "/icon-180.png", "sizes": "180x180", "type": "image/png"},
        {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
        {"src": "/icon-1024.png", "sizes": "1024x1024", "type": "image/png"},
    ],
})


class Handler(BaseHTTPRequestHandler):
    def host_ok(self) -> bool:
        """The dashboard is bound to the loopback, which stops everything except DNS
        rebinding: a page on `evil.tld` stays on its own origin, but a short-TTL record
        re-points that name at 127.0.0.1, so the browser calls a fetch to it same-origin
        and hands over the reply without any CORS header of ours being consulted. The one
        thing that gives it away is the `Host` the browser still sends, and checking it has
        to cover the reads - the backlog prose, project paths and the last thing an agent
        said are all on the GET side."""
        return self.headers.get("Host") in _ORIGINS

    def do_GET(self):  # noqa: N802
        if not self.host_ok():
            self.send_error(403)
            return
        cache = "no-store"
        if self.path.startswith("/api/state"):
            with _lock:
                body = json.dumps(build_state()).encode()
            ctype = "application/json"
        elif self.path.startswith("/api/backlog"):
            with _lock:
                body = json.dumps(build_backlog()).encode()
            ctype = "application/json"
        elif self.path in ("/", "/index.html"):
            body, ctype = PAGE.encode(), "text/html; charset=utf-8"
        elif self.path == "/api/whoami":
            # deliberately free of locks and subprocesses: a restart probes this while the
            # server may be busy building state, and a slow answer would look like a
            # foreign process
            body, ctype = WHOAMI.encode(), "application/json"
        elif self.path == "/manifest.webmanifest":
            body, ctype = MANIFEST.encode(), "application/manifest+json"
            cache = "max-age=3600"
        elif self.path in STATIC:
            # an exact route per file, so nothing here can be talked into walking the disk
            name, ctype = STATIC[self.path]
            try:
                body = (ASSETS / name).read_bytes()
            except OSError:  # the script was copied out of the plugin without its artwork
                self.send_error(404)
                return
            cache = "max-age=86400"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def same_origin(self) -> bool:
        """`/api/focus` acts on the machine rather than reporting on it, so a page on some
        other site must not be able to reach it. `host_ok` already ran on the way in and is
        what defeats DNS rebinding; an `Origin` check alone does not. On top of it a POST
        must be JSON, which makes the request non-simple, so a cross-origin attempt needs a
        preflight and this server answers none - and `Origin`/`Sec-Fetch-Site`, when the
        browser sends them, must say same-origin."""
        if not self.host_ok():
            return False
        if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
            return False
        site = self.headers.get("Sec-Fetch-Site")
        if site and site != "same-origin":
            return False
        origin = self.headers.get("Origin")
        return not origin or origin in {f"http://{h}" for h in _ORIGINS}

    def do_POST(self):  # noqa: N802
        route = self.path.split("?")[0]
        if route not in ("/api/focus", "/api/quit"):
            self.send_error(404)
            return
        if not self.same_origin():
            self.send_error(403)
            return
        if route == "/api/quit":
            # A restart almost always runs from a different session than the one that
            # started the server, and Claude Code confines a session to its own process
            # tree - the same user gets "Operation not permitted" from kill() on a monitor
            # another session spawned. Serving its own stop is the way out: the process
            # that has to die is the one handling the request. The route is no wider than
            # /api/focus, which already drives AppleScript on the same guards.
            res = {"ok": True, "pid": os.getpid()}
        else:
            try:
                n = int(self.headers.get("Content-Length") or 0)
                req = json.loads(self.rfile.read(n) or b"{}")
                res = focus(int(req["pid"]), str(req.get("cwd") or ""))
            except (ValueError, KeyError, TypeError) as e:
                res = {"ok": False, "error": str(e)}
        body = json.dumps(res).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        if route == "/api/quit":
            # shutdown() blocks until serve_forever() has returned, so it can never run on
            # a thread that is still inside a request
            threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, *a):  # quiet
        pass


def main() -> None:
    ap = argparse.ArgumentParser(description="Live dashboard of Claude Code sessions")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--open", action="store_true", help="open a browser window")
    args = ap.parse_args()

    url = f"http://127.0.0.1:{args.port}/"
    _ORIGINS.update({f"127.0.0.1:{args.port}", f"localhost:{args.port}"})
    if args.port == 80:  # a browser leaves the port out when it is the scheme's default,
        _ORIGINS.update({"127.0.0.1", "localhost"})  # so `Host` arrives bare
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Claude monitor: {url}  (Ctrl-C to quit)")
    if args.open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        srv.server_close()  # hand the port back at once, a restart is waiting on it


if __name__ == "__main__":
    main()
