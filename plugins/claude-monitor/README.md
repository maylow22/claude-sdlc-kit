# claude-monitor

Live dashboard všech Claude Code sessions běžících na stroji. Zero-dep Python
(stdlib), servíruje samostatnou HTML stránku s auto-refreshem 3 s.

```
/claude-monitor:start          # → http://127.0.0.1:8787/
python3 tools/claude_monitor.py --port 8787 --open
```

## Co ukazuje

- **usage cockpit** — vytížení plánu (5h session, týdenní limit, týdenní limit modelu)
  s procenty a odpočtem do resetu; aktivní limit je zvýrazněný
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
| usage cockpit | `~/.claude.json` → `cachedUsageUtilization` (cache, kterou plní `/usage`) |

Transcripty se čtou inkrementálně (pamatuje si offset), takže refresh je konstantně levný
i u vícemegabajtových souborů.

## Průběh workflow (volitelné)

Jakýkoli command/skill může hlásit svůj postup — v tomto kitu to dělá plugin
[feature](../feature) (`/feature:start`) — zapíše
`~/.claude/flow/$CLAUDE_CODE_SESSION_ID.json`:

```json
{
  "flow": "feature",
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

## Vývoj

Plugin se instaluje jako **kopie** do `~/.claude/plugins/cache/claude-kit/claude-monitor/<verze>/`,
takže změny v repu se samy neprojeví. Místo reinstalace stačí kopii nahradit symlinkem
(uděláno, dokud se nezmění verze v `plugin.json`):

```bash
cd ~/.claude/plugins/cache/claude-kit/claude-monitor
rm -rf 0.1.0 && ln -s ~/Workspace/claude-kit/plugins/claude-monitor 0.1.0
```

Jednorázově bez instalace: `claude --plugin-dir ~/Workspace/claude-kit/plugins/claude-monitor`.

Server drží HTML v paměti, takže po editaci je stejně potřeba restart:
`kill $(lsof -ti:8787)` a spustit znovu.

## Pasti

- Transcript v `message.model` **neuvádí sufix `[1m]`** — 1M tier z logu nerozlišíš.
  Kontextové limity jsou proto v `CONTEXT_LIMITS` na začátku skriptu (Claude 5 rodina 1M,
  Haiku 4.5 200K); Claude Code může auto-compactovat dřív.
- Usage se **nedotahuje z API** — čte se cache, kterou si zapisuje sám Claude Code.
  Stáří cache je proto vypsané v hlavičce; `/usage` v libovolné session ji obnoví.
- Branch je vlastnost **worktree, ne session** — víc sessions v jednom adresáři je vždy
  na téže větvi a `checkout` jedné přepne branch všem ostatním.
