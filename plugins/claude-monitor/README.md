# claude-monitor

Live dashboard všech Claude Code sessions běžících na stroji. Zero-dep Python
(stdlib), servíruje samostatnou HTML stránku s auto-refreshem 3 s.

```
# obvykle nic — dashboard nastartuje sam pri startu session (SessionStart hook)
/claude-monitor:start          # → http://127.0.0.1:8787/
python3 tools/claude_monitor.py --port 8787 --open
```

## Autostart

`SessionStart` hook při každém startu session zkontroluje port 8787. Když tam nikdo
neposlouchá, spustí dashboard **odpojeně** (přežije konec session), a tak či tak pošle
jeho URL do kontextu session — takže se ho stačí zeptat, kde běží.

| Proměnná | Efekt |
|---|---|
| `CLAUDE_MONITOR_PORT=8788` | jiný port (hook i server) |
| `CLAUDE_MONITOR_AUTOSTART=0` | hook skončí tiše a nic nespustí |

Server je **singleton na stroj**, ne na session: druhá session ho už jen najde. Když dvě
odstartují naráz, druhý proces spadne na obsazený port a přežije jeden — do kontextu jde
v obou případech tatáž URL. Ukončíš ho `kill $(lsof -ti:8787)`; sám se neukončí.

## Co ukazuje

- **usage cockpit** — vytížení plánu (5h session, týdenní limit, týdenní limit modelu)
  s procenty a odpočtem do resetu; aktivní limit je zvýrazněný
- **stav** — busy / idle / blocked, pid, kind (interactive/background), projekt, živý git branch
- **tokeny** — output, input, cache read/write, thinking; obsazení kontextového okna
- **strom subagentů** — agentType, popis, output tokeny, jak dávno byl aktivní

## Zdroje dat

| Co | Odkud |
|---|---|
| seznam sessions, stav | `claude agents --json` |
| tokeny, model, effort | `~/.claude/projects/<slug>/<sessionId>.jsonl` → `.message.usage` |
| strom subagentů | `<sessionId>/subagents/agent-*.meta.json` |
| git branch | `git -C <cwd> branch --show-current` (živě — v transcriptu bývá zastaralý) |
| usage cockpit | `~/.claude.json` → `cachedUsageUtilization` (cache, kterou plní `/usage`) |
| autostart + URL do session | `hooks/session-start.sh` (SessionStart hook) |

Transcripty se čtou inkrementálně (pamatuje si offset), takže refresh je konstantně levný
i u vícemegabajtových souborů.

## Pasti

- Transcript v `message.model` **neuvádí sufix `[1m]`** — 1M tier z logu nerozlišíš.
  Kontextové limity jsou proto v `CONTEXT_LIMITS` na začátku skriptu (Claude 5 rodina 1M,
  Haiku 4.5 200K); Claude Code může auto-compactovat dřív.
- Usage se **nedotahuje z API** — čte se cache, kterou si zapisuje sám Claude Code.
  Stáří cache je proto vypsané v hlavičce; `/usage` v libovolné session ji obnoví.
- Branch je vlastnost **worktree, ne session** — víc sessions v jednom adresáři je vždy
  na téže větvi a `checkout` jedné přepne branch všem ostatním.
