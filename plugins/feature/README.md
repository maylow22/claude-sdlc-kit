# feature

Workflow pro vývoj jedné feature od zadání po PR. Tři commandy, jeden namespace.
Žádný stavový soubor ani vlastní tracking — postup vidíš v terminálu, subagenty
v [claude-monitoru](../claude-monitor).

| Command | Co dělá |
|---|---|
| `/feature:start <Jira klíč \| URL \| popis>` | celý průběh: zadání → branch → plán → implementace → E2E → lint → review → opravy → docs → konzultace → commit & PR |
| `/feature:plan-review [cesta k plánu]` | adversariální review plánu proti skutečnému kódu, než se začne psát |
| `/feature:commit` | git commit s českou hláškou, bez emoji a bez Co-Authored-By |
| `/feature:wiki [--scope=full\|incremental]` | wiki projektu v `docs/wiki/` podle LLM-wiki vzoru — stack si zjistí sám |

`/feature:start` si `/feature:commit` i `/feature:wiki` volá sám (wiki přes doc-writera);
samostatně je pustíš, když workflow neběží.

## Dělení kontextu

Jádro workflow drží **hlavní agent**, protože potřebuje jednu nit od zadání ke kódu:

| Krok | Kde běží |
|---|---|
| 1 Zadání · 2 Branch | hlavní kontext |
| 3 Plán — sestavení a zapracování nálezů | hlavní kontext |
| 3 Plán — review | `feature:plan-reviewer` (čistý kontext) |
| 4 Implementace · 5 E2E | hlavní kontext |
| 6 Lint & formát | `feature:linter` (čistý kontext) |
| 7 Review kódu | `feature:reviewer` (čistý kontext) |
| 8 Opravy nálezů | hlavní kontext |
| 9 Dokumentace | `feature:doc-writer` (čistý kontext) |
| 10 Bezpečnost | `feature:security-reviewer` (čistý kontext, vidí i docs) |
| 11 Konzultace · 12 Commit & PR | hlavní kontext |

Mechanický úklid je subagent ze stejného důvodu, i když nic nehodnotí: výstup formatteru,
eslintu a `tsc` je nejdelší a nejméně zajímavá věc v celém workflow. Zadání proto vůbec
nedostane — lintovat se dá bez znalosti záměru.

Bezpečnost je záměrně **poslední krok**, ne paralelní s review kódu: teprve po dokumentaci
je diff kompletní, a docs jsou plnohodnotná security plocha — příklad s tokenem, interní URL
nebo návod, podle kterého si čtenář vypne verifikaci, je nález stejně jako díra v kódu.

Kontrolní agenti dostanou **nejvýš zadání, branch a diff** — nikdy průběh vývoje. Nevědí, co
jsi zvažoval, co zahodil ani co už uživatel odsouhlasil, takže se nemají čeho chytit a jejich
nález má váhu. `feature:linter` a `feature:security-reviewer` nedostanou ani zadání: úklid ho
nepotřebuje a security review se nemá čím nechat přesvědčit, že díra je vlastně záměr. Reviewery navíc chybí `Edit`: nálezy vracejí, opravuje je hlavní agent, který
kód zná. Doc-writer psát smí (dokumentace je práce, ne oprava), ale necommituje.

Při dalším kole (uživatel má připomínky) se agenti spouštějí **znovu od nuly**, ne jako
pokračování — jinak by si kontext natáhli zpátky.

Command nese **recept**, agent je **hranice kontextu** — nejsou to konkurenční varianty.
`/feature:wiki` je proto command: člověk si ho pustí přímo (a běží v jeho kontextu), z workflow
ho volá `feature:doc-writer`, takže tam ta práce padne do jeho okna. Proto má doc-writer
`Agent` — aby mu fáze B rozjela discovery subagenty.

## Agenti

| Agent | Kontext | Nástroje | Výstup |
|---|---|---|---|
| `feature:plan-reviewer` | zadání, plán | read-only | verdikt + nálezy Blocking/Should-fix proti reálnému kódu |
| `feature:linter` | jen branch + diff | + Edit | co formatter/lint/tsc opravily a co zbylo autorovi |
| `feature:reviewer` | zadání, plán, diff | read-only + Skill | verdikt PASS/CHANGES + nálezy dle závažnosti |
| `feature:security-reviewer` | jen branch + diff (kód **i** docs) | read-only + Skill | verdikt + nálezy s cestou ke zneužití |
| `feature:doc-writer` | zadání, diff | + Write/Edit | co zapsal, co ne a proč, stav wiki |

## Brány, na kterých se čeká na tebe

Zadání, **zreviewovaný** plán, konzultace, commit & push. Bez výslovného souhlasu workflow necommituje,
nepushuje ani nevytváří PR (PR se jen vygeneruje jako odkaz — `gh` se nepoužívá).

## Konvence napevno

Workflow počítá s autorovým setupem: branch z `develop`, `npm run test:e2e` / `tsc` /
`lint`, Jira na `addsign.atlassian.net`.

`/feature:wiki` je naopak **stackově neutrální** — jazyk, build, testy i tvar repa si zjistí
z manifestů a `git ls-files`, sadu stránek určí podle toho, co v projektu opravdu je, a stránku
bez obsahu nezakládá. Drží tři vrstvy LLM-wiki vzoru: kód je raw zdroj (nikdy do něj nezapisuje),
`docs/wiki/**` vlastní, `CLAUDE.md`/`AGENTS.md`/`README.md` je schéma, kterým se řídí.
`index.md` je katalog, `log.md` append-only historie, a `--scope=incremental` přepíše jen
stránky dotčené diffem od posledního záznamu v logu.
