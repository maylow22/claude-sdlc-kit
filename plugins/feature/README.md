# feature

Workflow pro vývoj jedné feature od zadání po PR. Tři commandy, jeden namespace.
Žádný stavový soubor ani vlastní tracking — postup vidíš v terminálu, subagenty
v [claude-monitoru](../claude-monitor).

| Command | Co dělá |
|---|---|
| `/feature:start <Jira klíč \| URL \| popis>` | celý průběh: zadání → branch → plán → implementace → E2E → lint → review → opravy → docs → konzultace → commit & PR |
| `/feature:commit` | git commit s českou hláškou, bez emoji a bez Co-Authored-By |
| `/feature:wiki` | regenerace `docs/wiki/` (Karpathy-style LLM wiki) |

`/feature:start` si `/feature:commit` i `/feature:wiki` volá sám (wiki přes doc-writera);
samostatně je pustíš, když workflow neběží.

## Dělení kontextu

Jádro workflow drží **hlavní agent**, protože potřebuje jednu nit od zadání ke kódu:

| Krok | Kde běží |
|---|---|
| 1 Zadání · 2 Branch · 3 Plán · 4 Implementace · 5 E2E | hlavní kontext |
| 6 Lint & formát | `feature:linter` (čistý kontext) |
| 7 Review + bezpečnost | `feature:reviewer` + `feature:security-reviewer` (paralelně, čistý kontext) |
| 8 Opravy nálezů | hlavní kontext |
| 9 Dokumentace | `feature:doc-writer` (čistý kontext) |
| 10 Konzultace · 11 Commit & PR | hlavní kontext |

Mechanický úklid je subagent ze stejného důvodu, i když nic nehodnotí: výstup formatteru,
eslintu a `tsc` je nejdelší a nejméně zajímavá věc v celém workflow. Zadání proto vůbec
nedostane — lintovat se dá bez znalosti záměru.

Kontrolní agenti dostanou **jen zadání, branch a diff** — ne průběh vývoje. Nevědí, co jsi
zvažoval, co zahodil ani co už uživatel odsouhlasil, takže se nemají čeho chytit a jejich
nález má váhu. Reviewery navíc chybí `Edit`: nálezy vracejí, opravuje je hlavní agent, který
kód zná. Doc-writer psát smí (dokumentace je práce, ne oprava), ale necommituje.

Při dalším kole (uživatel má připomínky) se agenti spouštějí **znovu od nuly**, ne jako
pokračování — jinak by si kontext natáhli zpátky.

## Agenti

| Agent | Kontext | Nástroje | Výstup |
|---|---|---|---|
| `feature:linter` | jen branch + diff | + Edit | co formatter/lint/tsc opravily a co zbylo autorovi |
| `feature:reviewer` | zadání, plán, diff | read-only + Skill | verdikt PASS/CHANGES + nálezy dle závažnosti |
| `feature:security-reviewer` | zadání, diff | read-only + Skill | verdikt + nálezy s cestou ke zneužití |
| `feature:doc-writer` | zadání, diff | + Write/Edit | co zapsal, co ne a proč, stav wiki |

## Brány, na kterých se čeká na tebe

Zadání, plán, konzultace, commit & push. Bez výslovného souhlasu workflow necommituje,
nepushuje ani nevytváří PR (PR se jen vygeneruje jako odkaz — `gh` se nepoužívá).

## Konvence napevno

Commandy počítají s autorovým setupem: branch z `develop`, `npm run test:e2e` / `tsc` /
`lint`, Jira na `addsign.atlassian.net`. `/feature:wiki` je navíc psaná pro strukturu
projektu moje-agenda (`src/components/taskForms/**`) — v jiném projektu ji ber jako šablonu.
