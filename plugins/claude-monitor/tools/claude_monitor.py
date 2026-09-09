#!/usr/bin/env python3
"""Live dashboard of every Claude Code session running on this machine.

Data sources:
  - `claude agents --json`           -> sessions, pid/cwd/kind/status/waitingFor
  - ~/.claude/projects/*/<sid>.jsonl -> tokens, model, effort, git branch, activity
  - .../<sid>/subagents/agent-*      -> subagent tree (agentType, spawnDepth, tokens)
  - ~/.claude/monitor/notify/*.json  -> Notification hook: session is waiting on the user

Run:  python3 claude_monitor.py [--port 8787] [--open]
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"
CONFIG = Path.home() / ".claude.json"
NOTIFY = Path.home() / ".claude" / "monitor" / "notify"
SUBAGENT_ACTIVE_SEC = 60

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
        if e.get("type") == "assistant" and not e.get("isSidechain"):
            # Turns that only think or call tools keep the previous reply.
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


def agents_json() -> list[dict]:
    try:
        raw = subprocess.run(
            ["claude", "agents", "--json"], capture_output=True, text=True, timeout=20
        )
        return json.loads(raw.stdout) if raw.returncode == 0 else []
    except (OSError, ValueError, subprocess.SubprocessError):
        return []


def build_state() -> dict:
    sessions = []
    branches: dict[str, str | None] = {}
    for s in agents_json():
        sid = s.get("sessionId", "")
        path = transcript(sid)
        t = scan(path) if path else _fresh()
        limit = CONTEXT_LIMITS.get(t["model"] or "", DEFAULT_LIMIT)
        try:
            mtime = os.stat(path).st_mtime if path else 0
        except OSError:
            mtime = 0
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
                "project": os.path.basename(s.get("cwd", "")) or "?",
                "startedAt": s.get("startedAt"),
                "branch": git_branch(s.get("cwd", ""), branches) or t["branch"],
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
                "subagents": subagents(path, sid) if path else [],
            }
        )

    sessions.sort(key=lambda s: (not s["attention"], s["status"] != "busy", -s["mtime"]))
    totals = {
        "sessions": len(sessions),
        "waiting": sum(1 for s in sessions if s["attention"]),
        "busy": sum(1 for s in sessions if s["status"] == "busy"),
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


PAGE = r"""<!doctype html>
<meta charset="utf-8"><title>Claude agents</title>
<style>
:root{--bg:#191817;--card:#232120;--fg:#f0eee9;--dim:#9a938a;--line:#35322f;
      --busy:#f0906a;--idle:#7cc292;--warn:#e0a94a;--bar:#d97757;--bar2:#3d3936;
      --att:#ffb02e}
*{box-sizing:border-box}
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
.kpi.max .bar>i{background:#f2776b}
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
.card.idle{background:#1d1b1a;border-color:#2b2927;color:var(--dim)}
.card.idle .toks b,.card.idle h2{color:#c9c2b8}
.card.att{border:2px solid var(--att);padding:11px 13px;
          box-shadow:0 0 0 3px rgba(255,176,46,.16),0 0 30px -6px var(--att);
          animation:pulse 1.8s ease-in-out infinite}
@keyframes pulse{50%{box-shadow:0 0 0 3px rgba(255,176,46,.04),0 0 8px -4px var(--att)}}
@media (prefers-reduced-motion:reduce){
  .card.att{animation:none}
  .spin{animation:none;border-top-color:currentColor}
}
.head{display:flex;align-items:baseline;gap:8px;margin-bottom:2px}
.head h2{font-size:14px;margin:0;font-weight:620;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pill{font-size:10px;padding:2px 7px;border-radius:99px;border:1px solid currentColor;
      text-transform:uppercase;letter-spacing:.05em;font-weight:600}
.pill.busy{color:var(--busy)}.pill.idle{color:var(--idle)}
.spin{display:inline-block;vertical-align:-1px;width:8px;height:8px;margin-right:5px;
      border:1.5px solid currentColor;border-top-color:transparent;border-radius:99px;
      animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.pill.att{color:#191817;background:var(--att);border-color:var(--att)}
.att-row{background:#3a2c12;border:1px solid var(--att);border-radius:7px;
         padding:6px 9px;margin:0 0 9px;font-size:12.5px;line-height:1.4}
.att-row b{color:var(--att)}
.att-row .d{color:var(--dim);display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.att-row .say{margin-top:4px;color:var(--dim);cursor:pointer;overflow:hidden;
              display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.att-row .say::before{content:"\25be ";color:var(--att)}
.att-row .say.open{display:block;white-space:pre-wrap}
.att-row .say.open::before{content:"\25b4 "}
.kpi.att b{color:var(--att)}
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
.ver{position:absolute;top:18px;right:18px;color:var(--dim);font-size:11px;
     font-variant-numeric:tabular-nums}
</style>
<div class="ver">__VERSION__</div>
<h1>Claude agents dashboard</h1>
<div class="sub" id="sub">loading…</div>
<div class="kpis" id="kpis"></div>
<div class="grid" id="grid"></div>
<script>
const n = v => v >= 1e6 ? (v/1e6).toFixed(2)+"M" : v >= 1e3 ? Math.round(v/1e3)+"k" : String(v||0);
const dur = s => s < 60 ? Math.round(s)+" s" : s < 3600 ? Math.round(s/60)+" min"
  : s < 86400 ? (s/3600).toFixed(1)+" h" : (s/86400).toFixed(1)+" d";
const ago = (t, now) => dur(Math.max(0, now - t));
const esc = s => (s||"").replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));

function kpi(v, l, c){ return `<div class="kpi ${c||""}"><b>${v}</b><span>${l}</span></div>`; }

// click the interval in the sub line to cycle it; like the KPI fold, the state has to
// live outside the DOM because the sub line is rewritten on every tick
const INTERVALS = [[3000, "3 s"], [10000, "10 s"], [60000, "1 min"], [0, "stop"]];
let ivIdx = 0, timer = null;
function arm(){
  clearInterval(timer);
  const ms = INTERVALS[ivIdx][0];
  if(ms) timer = setInterval(tick, ms);  // "stop" is 0 - no timer, not a very long one
}
function cycleRefresh(){
  ivIdx = (ivIdx + 1) % INTERVALS.length;
  arm();
  // tick() repaints the label too, but only once its fetch resolves - a click has to
  // answer immediately, so write it here as well
  document.querySelector(".iv").textContent = INTERVALS[ivIdx][1];
  tick();
}

// the KPI row is rebuilt every tick, so the fold state lives out here, not in the DOM
let kpisAll = false;
function toggleKpis(){
  kpisAll = !kpisAll;
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
  const el = ev.target.closest(".say");
  if(!el) return;
  const sid = el.dataset.sid;
  expanded.has(sid) ? expanded.delete(sid) : expanded.add(sid);
  el.classList.toggle("open");
});

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
      <span class="pill ${st}">${st === "busy" ? '<i class="spin"></i>' : ""}${
        a ? "needs you" : st}</span></div>
    <div class="meta">${esc(s.project)}${s.branch?" · "+esc(s.branch):""} · ${esc(s.kind)}
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

async function tick(){
  try {
    const d = await (await fetch("/api/state")).json();
    const T = d.totals, now = d.now;
    const U = d.usage;
    document.getElementById("sub").innerHTML =
      "updated " + new Date().toLocaleTimeString() + " · auto-refresh "
      + `<button class="iv" onclick="cycleRefresh()" title="click to change the interval">`
      + INTERVALS[ivIdx][1] + `</button>`;
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
    document.title = (T.waiting ? `(${T.waiting}) ` : "") + "Claude agents";
  } catch (e) {
    document.getElementById("sub").textContent = "connection to the server failed: " + e;
  }
}
tick(); arm();
</script>
"""
PAGE = PAGE.replace("__VERSION__", code_version())


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.startswith("/api/state"):
            with _lock:
                body = json.dumps(build_state()).encode()
            ctype = "application/json"
        elif self.path in ("/", "/index.html"):
            body, ctype = PAGE.encode(), "text/html; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # quiet
        pass


def main() -> None:
    ap = argparse.ArgumentParser(description="Live dashboard of Claude Code sessions")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--open", action="store_true", help="open a browser window")
    args = ap.parse_args()

    url = f"http://127.0.0.1:{args.port}/"
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Claude monitor: {url}  (Ctrl-C to quit)")
    if args.open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
