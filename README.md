# claude-kit

Vlastní Claude Code nástroje mimo [sdlc-kit](https://github.com/maylow22/sdlc-kit)
(ten zůstává zaměřený na `/sdlc`). Repo je zároveň **marketplace**, takže se pluginy
instalují a aktualizují přes `claude plugin`.

## Instalace

```bash
claude plugin marketplace add ~/Workspace/claude-kit     # lokálně
# nebo po pushnutí:  claude plugin marketplace add maylow22/claude-kit
claude plugin install claude-monitor@claude-kit
```

Restart Claude Code (nebo `/reload-plugins`) a pak `/claude-monitor:start`.

## Pluginy

| Plugin | Co dělá |
|---|---|
| [claude-monitor](plugins/claude-monitor) | Live dashboard všech sessions — stav, tokeny, kontext, subagenti, průběh workflow |

## Vývoj

`claude plugin validate <cesta>` ověří manifest, `claude plugin details <name>` ukáže
inventář komponent a token cost, `claude plugin tag` udělá release tag `{name}--v{version}`.

Pro rychlou iteraci bez publikování stačí plugin nasymlinkovat do `~/.claude/skills/`
— auto-loaduje se jako `<name>@skills-dir`.
