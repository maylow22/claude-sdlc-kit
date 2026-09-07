# claude-monitor

Live dashboard všech Claude Code sessions běžících na stroji. Zero-dep Python
(stdlib), servíruje samostatnou HTML stránku s auto-refreshem 3 s.

```
/claude-monitor:start          # → http://127.0.0.1:8787/
python3 tools/claude_monitor.py --port 8787 --open
```

## Co ukazuje

- **stav** — busy / idle / blocked, pid, kind (interactive/background), projekt, živý git branch
- **tokeny** — output, input, cache read/write, thinking; obsazení kontextového okna
- **strom subagentů** — agentType, popis, output tokeny, jak dávno byl aktivní
- **průběh workflow** — volitelný pruh kroků, viz níže

## Zdroje dat

| Co | Odkud |
|---|---|
| seznam sessions, stav | `claude agents --json` |
| tokeny, model, effort | `~/.claude/projects/<slug>/<sessionId>.jsonl` → `.message.usage` |
| strom subagentů | `<sessionId>/subagents/agent-*.meta.json` |
| git branch | `git -C <cwd> branch --show-current` (živě — v transcriptu bývá zastaralý) |
| průběh workflow | `~/.claude/flow/<sessionId>.json` (zapisuje si sám agent) |

Transcripty se čtou inkrementálně (pamatuje si offset), takže refresh je konstantně levný
i u vícemegabajtových souborů.

## Průběh workflow (volitelné)

Jakýkoli command/skill může hlásit svůj postup — zapíše
`~/.claude/flow/$CLAUDE_CODE_SESSION_ID.json`:

```json
{
  "flow": "git-feature",
  "task": "IF-9 — rozbalit informace",
  "steps": [
    {"name": "4 Implementace", "status": "done"},
    {"name": "5 E2E testy", "status": "running", "note": "3/7 testů"},
    {"name": "6 Review", "status": "wait", "note": "čeká na odsouhlasení"}
  ]
}
```

`status`: `todo` | `running` | `wait` | `done` | `skip` | `fail`.
`wait` = blokován na uživateli (jantarově) — z dashboardu poznáš, že session nedře,
ale čeká na tebe.

## Pasti

- Transcript v `message.model` **neuvádí sufix `[1m]`** — 1M tier z logu nerozlišíš.
  Kontextové limity jsou proto v `CONTEXT_LIMITS` na začátku skriptu (Claude 5 rodina 1M,
  Haiku 4.5 200K); Claude Code může auto-compactovat dřív.
- Branch je vlastnost **worktree, ne session** — víc sessions v jednom adresáři je vždy
  na téže větvi a `checkout` jedné přepne branch všem ostatním.
