# claude-kit

Marketplace vlastních pluginů pro [Claude Code](https://claude.com/claude-code) —
live dashboard běžících sessions a workflow pro vývoj feature od zadání po PR.
Pluginy se instalují a aktualizují přes `claude plugin`.

## Pro koho

Pro vývojáře, který s Claude Code pracuje denně a chce dvě věci:

- **vidět, co se děje** — kolik sessions běží, kolik spálily tokenů, kde jsou v kontextovém
  okně a jaké subagenty rozjely;
- **mít na feature postup, ne improvizaci** — plán se zreviewuje proti kódu, než se píše,
  a kód projde lintem, review, dokumentací a security review v izolovaných kontextech.

Předpokládá macOS/Linux, `python3` (stdlib, žádné závislosti) a git.
`/feature:start` navíc počítá s autorovým setupem (branch z `develop`, `npm run test:e2e`,
`tsc`, `lint`, Jira na `addsign.atlassian.net`) — jinde ho čeká úprava commandu.

## Instalace

```bash
claude plugin marketplace add maylow22/claude-kit    # nebo lokálně: ~/Workspace/claude-kit
claude plugin install claude-monitor@claude-kit
claude plugin install feature@claude-kit
```

Restart Claude Code (nebo `/reload-plugins`) a pak `/claude-monitor:start`, `/feature:start`.

## Pluginy

| Plugin | Co dělá |
|---|---|
| [claude-monitor](plugins/claude-monitor) | Live dashboard všech sessions na stroji — vytížení plánu, stav, tokeny, obsazení kontextu, strom subagentů. Startuje sám při startu session, servíruje na `http://127.0.0.1:8787/`. |
| [feature](plugins/feature) | `/feature:start` — celý průběh feature: zadání → branch → plán → implementace → E2E → lint → review → docs → bezpečnost → commit & PR. Plus samostatné `/feature:plan-review`, `/feature:commit`, `/feature:wiki`. |

Detaily (co dashboard čte, jak je workflow rozdělené mezi hlavní kontext a subagenty)
jsou v README jednotlivých pluginů.

## Vývoj

`claude plugin validate <cesta>` ověří manifest, `claude plugin details <name>` ukáže
inventář komponent a token cost, `claude plugin tag` udělá release tag `{name}--v{version}`.

Pro rychlou iteraci bez publikování stačí plugin nasymlinkovat do `~/.claude/skills/`
— auto-loaduje se jako `<name>@skills-dir`.
