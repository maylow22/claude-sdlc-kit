# claude-kit

Vlastní Claude Code nástroje mimo [sdlc-kit](https://github.com/maylow22/sdlc-kit)
(ten zůstává zaměřený na `/sdlc`). Repo je zároveň **marketplace**, takže se pluginy
instalují a aktualizují přes `claude plugin`.

## Instalace

```bash
claude plugin marketplace add ~/Workspace/claude-kit     # lokálně
# nebo po pushnutí:  claude plugin marketplace add maylow22/claude-kit
claude plugin install claude-monitor@claude-kit
claude plugin install feature@claude-kit
```

Restart Claude Code (nebo `/reload-plugins`) a pak `/claude-monitor:start`, `/feature:start`.

## Pluginy

| Plugin | Co dělá |
|---|---|
| [claude-monitor](plugins/claude-monitor) | Live dashboard všech sessions — stav, tokeny, kontext, subagenti, průběh workflow |
| [feature](plugins/feature) | `/feature:start` workflow — vývoj a E2E v hlavním kontextu, review plánu i kódu, lint, bezpečnost a docs v izolovaných subagentech; plus `/feature:plan-review`, `/feature:commit`, `/feature:wiki` |

## Vývoj

`claude plugin validate <cesta>` ověří manifest, `claude plugin details <name>` ukáže
inventář komponent a token cost, `claude plugin tag` udělá release tag `{name}--v{version}`.

Pro rychlou iteraci bez publikování stačí plugin nasymlinkovat do `~/.claude/skills/`
— auto-loaduje se jako `<name>@skills-dir`.
