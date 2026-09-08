---
description: Spustí workflow pro novou feature — branch, plán, implementace a E2E v hlavním kontextu, review plánu/lint/review kódu/bezpečnost/dokumentace v izolovaných subagentech
argument-hint: <Jira klíč | Jira URL | popis úkolu>
---

Workflow pro vývoj nové feature. Argument je povinný — buď **Jira klíč** (např. `IF-9`), **Jira URL** (`https://addsign.atlassian.net/browse/IF-9`) nebo **volný popis** úkolu v češtině.

Pokud argument chybí, **zeptej se** uživatele co implementovat — nepokračuj bez něj.

## Dělení kontextu

- **Hlavní kontext (ty)** — zadání, plán, implementace, E2E testy, opravy nálezů,
  konzultace, commit a PR. Tohle všechno drží jednu nit a ty u toho zůstáváš.
- **Izolované subagenty (kroky 3, 6, 7, 9 a 10)** — review plánu, úklid, review kódu,
  dokumentace a nakonec bezpečnost. Každý dostane **čistý kontext** a v něm nejvýš zadání,
  plán a branch — nikdy průběh vývoje. Nevědí, jak jsi se k řešení dopracoval, co jsi
  zvažoval ani co jsi po cestě zahodil, proto jejich nález něco znamená. Diff si každý
  vytáhne sám.
- `feature:linter` a `feature:security-reviewer` dostanou **jen branch**: úklid zadání
  nepotřebuje a security review se nemá čím nechat přesvědčit, že díra je vlastně záměr.
- Do promptu subagentům **nepiš** vysvětlení, obhajoby ani "tohle už jsme řešili".
  Kdo kód hodnotí, nesmí znát autorovu argumentaci.
- Subagenti sami **necommitují** a reviewery **neopravují kód** — nálezy triáduješ a opravuješ
  ty v krocích 8 a 10. Dokumentaci píše doc-writer, protože to je samostatná práce, ne oprava.
- **Bezpečnost jde jako poslední**, až po dokumentaci — aby v diffu viděla i docs.
- Mechanický úklid (formatter, lint, typecheck) je taky subagent — jeho výstup bývá
  nejdelší a nejméně zajímavý z celého workflow, tak ať nesedí v hlavním kontextu.

## Postup

### 1. Zadání
- Jira klíč nebo URL → načti detail přes MCP `mcp__claude_ai_Atlassian_Rovo__getJiraIssue` (cloudId = `addsign.atlassian.net`, `responseContentFormat: "markdown"`). Extrahuj summary, description, status, assignee.
- Volný popis → použij jak je. Zeptej se uživatele na krátký český slug pro branch (např. `rozbalit-informace`).
- Shrň zadání 2-3 větami a **počkej na potvrzení** než budeš pokračovat. Pokud je něco nejasné, zeptej se.

### 2. Feature branch
- Ověř že working tree je čistý (`git status`). Pokud ne, **stop** a zeptej se uživatele.
- Přepni se na `develop` a stáhni si nejnovější stav (`git fetch origin && git checkout develop && git pull --ff-only`).
- Vytvoř branch `feature/<KEY>-<slug>` (např. `feature/IF-9-rozbalit-informace`). Slug je krátký, lowercase, pomlčky místo mezer, bez diakritiky. Pokud Jira klíč chybí, použij jen `feature/<slug>`.

### 3. Plán (a jeho review, než ho uvidí uživatel)
- Sestav **plán implementace** — stručné kroky (co/kde/jak), klíčové soubory, rizika.
  Zapiš ho do `.claude/plans/<branch-slug>.md`, ať má review i uživatel co číst.
- **Nech ho zreviewovat, než ho předložíš:** `/feature:plan-review .claude/plans/<slug>.md`,
  tedy agent `feature:plan-reviewer` s čistým kontextem. Ověří plán proti skutečnému kódu —
  že jmenované soubory a symboly existují, že pořadí kroků drží, že se nevynalézá znovu,
  co v repu je, a že plán pokrývá zadání a nic navíc.
- Blokující nálezy **zapracuj do plánu**, should-fix podle úsudku (co ne, s důvodem).
- Uživateli předlož **až zreviewovaný plán** + tři řádky o tom, co review našlo a co se
  v plánu proto změnilo. Neschvaluje se první nástřel.
- **Počkej na výslovné odsouhlasení.** Bez souhlasu nepokračuj na implementaci.
- Pokud uživatel chce úpravy, plán uprav; při podstatné změně pusť review **znovu**
  (nový agent, ne pokračování toho starého).

### 4. Implementace
- Implementuj minimální změnu řešící zadání podle odsouhlaseného plánu. Žádné neporadené refaktoringy ani spekulativní abstrakce.
- Pokud jde o UI změnu, ověř ji v prohlížeči (dev server + manuální průchod).

### 5. E2E testy (Playwright)
- **Skip celý krok pokud:**
  - projekt nemá nastavené E2E testy (žádný `tests/e2e/`, žádný `playwright.config.*`, žádný skript `test:e2e` v `package.json`), **nebo**
  - jde o triviální opravu (překlep, jednořádková úprava, change copy, drobná oprava stylu, dokumentace).
- Jinak: pokud změna **lze otestovat přes UI**, napiš/aktualizuj test v `tests/e2e/` pokrývající zlatou cestu.
- Spusť `npm run test:e2e` a oprav dokud neprojde.
- Pokud změna **nelze rozumně otestovat přes UI** (čistě tooling, infra, dokumentace), zeptej se uživatele, jestli krok přeskočit.

### 6. Lint & formát — izolovaný subagent
- Spusť `feature:linter` (`baseBranch`, `branch`). Formátuje a lintuje **jen soubory z diffu**,
  opravuje mechaniky a vrací krátký report — stovky řádků výstupu z nástrojů zůstanou u něj.
- Zadání mu neposílej. Na mechanický úklid ho nepotřebuje a nemá se čím nechat ovlivnit.
- Co ti vrátí v sekci **Zbývá autorovi**, oprav sám — to jsou přesně ty chyby, u kterých je
  potřeba znát záměr. Pak pusť linter znovu, nebo si sám ověř `npm run lint` a `npm run tsc`.
- Krok **skipni**, pokud projekt nemá ani formatter, ani linter, ani typecheck.

### 7. Review kódu — izolovaný subagent
Reviewera pouštěj až na uklizený kód, ať nálezy nejsou o formátování.

Spusť `feature:reviewer` (correctness + simplify optika). Prompt obsahuje **jen** tohle:
- `baseBranch` (`develop`) a `branch`
- **zadání** potvrzené v kroku 1 a **odsouhlasený plán** z kroku 3
- pokyn, že diff si vytáhne sám: `git diff <baseBranch>...HEAD`

Do promptu **nepatří**: co jsi zkoušel a zahodil, proč jsi něco udělal takhle, co už
uživatel odsouhlasil, ani tvoje shrnutí implementace. Kdyby to znal, jen ti to potvrdí.

Bezpečnost tady **neřeš** — ta jde až v kroku 10, aby viděla i dokumentaci.

### 8. Opravy nálezů (hlavní kontext)
- Nálezy **roztřiď**: co opravíš, co je falešný poplach (napiš proč), co je mimo zadání
  (patří do ticketu, ne do téhle branche).
- Oprav `blocker` a `major`. `minor` podle úsudku.
- Po opravách znovu `npm run test:e2e` (pokud krok 5 nebyl skipnutý). Lint a typecheck si
  ověř sám; když se toho nasypalo hodně, pusť radši znovu `feature:linter`.
- Když reviewer vrátil `CHANGES` a ty s podstatnou částí nesouhlasíš, nehádej se s ním
  v dalším kole — vezmi to do kroku 12 jako otázku pro uživatele.

### 9. Dokumentace — izolovaný subagent
- Spusť `feature:doc-writer` (`baseBranch`, `branch`, zadání). Vidí hotový kód, ne cestu k němu.
- Běží **až po opravách**, aby nedokumentoval stav, který se ještě změní.
- **Skipni ho**, pokud jde o triviální změnu (překlep, copy, styl, čistě interní refaktoring
  beze změny chování) — jen napiš uživateli proč.
- Doc-writer si sám vyhodnotí wiki (`/feature:wiki`), CHANGELOG i `docs/**`. Jeho report
  ukaž uživateli v kroku 12 — nepřepisuj ho po něm.

### 10. Bezpečnost — izolovaný subagent, úplně na konci
Až tady, protože teď je diff **kompletní včetně dokumentace** — a docs jsou plnohodnotná
security plocha: příklady s tokenem, ENV hodnoty, interní URL, instrukce, podle které si
čtenář vypne kontrolu nebo si commitne `.env`.

- Spusť `feature:security-reviewer` — předej **jen** `baseBranch` a `branch`. Zadání ne:
  je to solo kontrola, která nemá řešit, co feature měla dělat, a diff si vytáhne sama,
  takže vidí kód po opravách i to, co zapsal doc-writer.
- **Skipni ho** jen když se security plochy nedotýká **ani kód, ani dokumentace** — jen
  napiš uživateli proč.
- Nálezy oprav v hlavním kontextu, stejnou triáží jako v kroku 8: `critical` a `high` vždy,
  `medium` a `low` podle úsudku.
- Když se oprava dotkla dokumentace, pusť **znovu `feature:doc-writer`**, ne ruční záplatu —
  docs má na starosti on.
- Když jsi na security nálezy sahal do kódu podstatně, pusť `feature:security-reviewer`
  **ještě raz** s čistým kontextem. Hodnotí se výsledný diff, ne ten, který mu přišel poprvé.

### 11. Konzultace
- Shrň uživateli:
  - co bylo implementováno (stručně, bez výpisu souborů)
  - nové/upravené testy
  - výsledky review a bezpečnosti: oba verdikty + co jsi z nálezů opravil a co ne (a proč)
  - co zapsal doc-writer
  - co jsi nedělal a proč (pokud to stojí za zmínku)
- **Počkej** na zpětnou vazbu. Pokud má uživatel připomínky, oprav je a vrať se na krok 6
  (úklid) a projdi kontrolní kroky znovu, včetně bezpečnosti —
  reviewery pouštěj vždy **znovu s čistým kontextem**, ne pokračováním předchozího agenta.

### 12. Commit & PR
- **Necommituj sám.** Připomeň uživateli command `/feature:commit` (vytvoří českou commit message bez emoji a bez Co-Authored-By).
- Po commitu se zeptej jestli pushnout branch. Pokud ano:
  - `git push -u origin <branch>`
  - Z `git remote get-url origin` odvoď hostera a vygeneruj URL pro vytvoření PR do `develop` (Bitbucket Server, GitHub, GitLab — podle URL). Tu URL **jen ukaž uživateli** — PR si vytvoří sám.
  - **Nepoužívej `gh` ani jiné CLI pro vytváření PR.** PR vždy vytváří uživatel ručně přes vygenerovaný odkaz.

## Pravidla

- **Nikdy** necommituj, nepushuj ani nevytvářej PR bez výslovného souhlasu uživatele.
- **Nikdy** `git add -A` ani `.` — vždy konkrétní soubory.
- **Nikdy** `--no-verify`, `--amend`, `reset --hard`, force push.
- Branch vždy z aktuálního `develop`, ne z `main` ani z jiné feature.
- Pokud E2E test selže opakovaně z důvodu mimo zadání (existující bug), zastav se a zeptej.
- Komunikace s uživatelem česky. Kde jsi v postupu, hlas krátce v odpovědi — žádný
  stavový soubor se nikam nezapisuje.
- Kontrolní agenty (linter, reviewery, doc-writer) spouštěj **vždy jako nový subagent** s čistým kontextem. Nikdy jim
  neposílej průběh vývoje ani je nenech pokračovat v už rozjeté konverzaci — izolace kontextu
  je celý důvod, proč jsou to subagenti.
