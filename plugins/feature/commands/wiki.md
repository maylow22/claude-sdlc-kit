---
description: Vygeneruje nebo aktualizuje technickou wiki projektu v docs/wiki/ podle LLM-wiki vzoru — stack si zjistí sám, nic nepředpokládá
argument-hint: "[--scope=full | --scope=incremental]"
---

Udržuj technickou wiki projektu v `docs/wiki/`. Cíl: aby budoucí AI session (i člověk)
získala orientaci v kódu bez procházení stromu souborů — a aby cross-referency už byly
hotové, ne dohledávané při každém dotazu.

Tenhle command je **jazykově i stackově neutrální**. Nic nepředpokládej o technologii,
struktuře adresářů ani doméně: všechno si zjisti z repa (fáze A) a podle toho se zařiď.
Když něco nenajdeš, tu část wiki **nezakládej** — prázdná stránka je horší než žádná.

## Tři vrstvy (LLM-wiki vzor)

| Vrstva | Co to je | Kdo ji vlastní |
|---|---|---|
| **raw** | kód repa, migrace, konfigurace, ADR, issue trackery | člověk; wiki do nich **nikdy** nezapisuje |
| **wiki** | `docs/wiki/**` | tenhle command — přepisuje ji, drží konzistentní |
| **schéma** | `CLAUDE.md`, `AGENTS.md`, `README.md`, konvence projektu | člověk; wiki se jimi řídí |

Z toho plyne jediné tvrdé pravidlo: **wiki je kompilát, ne pravda.** Nesmí obsahovat nic,
co není v kódu nebo ve schématu. Žádné domněnky, žádné „pravděpodobně", žádné best practices,
které v repu nikdo nedodržuje.

## Argumenty

- `--scope=full` (výchozí, i když `docs/wiki/` ještě neexistuje) — kompletní regenerace.
- `--scope=incremental` — jen to, co se změnilo od posledního běhu. Zdroj rozsahu je
  `Source commit` z posledního záznamu v `docs/wiki/log.md`:
  `git diff --name-only <ten commit>..HEAD`. Když log neexistuje nebo commit už v historii
  není, řekni to a degraduj na `full`.

## Fáze A — Schéma a rozvaha (sekvenčně, rychlé)

1. Přečti, co projekt o sobě říká: `README.md`, `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`,
   `docs/**` (existující dokumentace je schéma, ne konkurence).
2. Zjisti stack z manifestů, které v repu **skutečně jsou** — např. `package.json`,
   `pyproject.toml`/`requirements.txt`, `go.mod`, `Cargo.toml`, `pom.xml`/`build.gradle*`,
   `composer.json`, `Gemfile`, `*.csproj`, `mix.exs`, `Makefile`, `Dockerfile`,
   `docker-compose.*`, CI konfigurace. Z nich vyčti: jazyky, build a run příkazy, testy,
   linter, deploy jednotky.
3. Zmapuj tvar repa: `git ls-files | head -300`, počty souborů podle přípony, top-level
   adresáře. Monorepo (workspaces, `packages/*`, `apps/*`) poznáš tady — pak wiki dělej
   **po balíčcích**, ne jako jeden slepenec.
4. Pokud `docs/wiki/log.md` existuje, přečti poslední záznam (čas, commit, co se psalo).
5. Jazyk wiki: ten, kterým je psaná existující dokumentace projektu; když žádná není,
   **angličtina**. Doménové termíny **nepřekládej** — nech je v původním jazyce a vysvětli
   je v glosáři.
6. **Rozhodni sadu stránek** podle toho, co jsi našel (viz fáze D) a napiš si ji.
   Nemá vzniknout stránka na téma, které projekt nemá.

Když v repu není žádný zdrojový kód (prázdné repo, jen konfigurace), skonči s jednou větou
proč — wiki nemá z čeho vzniknout.

## Fáze B — Discovery (paralelní subagenti v JEDNÉ zprávě)

Spusť **3–5 `Explore` subagentů paralelně**. Každý dostane jednu optiku, vrátí strukturovanou
markdown zprávu do ~500 slov a **cituje `cesta/k/souboru:řádek`**. Zprávy nejsou wiki —
jsou vstup pro fázi D.

Optiky (uprav podle toho, co fáze A našla; u monorepa přidej agenta na balíček):

1. **Architektura a hranice** — entry pointy, deploy jednotky, procesní hranice, tok dat
   mezi nimi, konfigurace a ENV, externí služby a co se stane při jejich výpadku.
2. **Doménový model a kontrakty** — hlavní typy/entity a jejich vztahy, schémata DB
   a migrace, API kontrakty (routy, RPC, eventy), validace, serializace.
3. **Opakující se patterny a konvence** — jak se v tomhle repu dělá to, co se dělá pořád
   (přístup k datům, chyby, logování, autorizace, stav, i18n). Ke každému 1–2 ukázky
   do 6 řádků s citací. Zvlášť vypíchni, kde se kód od konvence odchyluje.
4. **Testy, build, CI** — jak se to spouští, testuje a nasazuje; co je pokryté a co ne.
5. **Pasti** — mrtvý kód, obcházení konvencí, TODO/FIXME hnízda, generovaný kód, věci,
   které v kódu vypadají jako chyba a jsou záměr (a naopak).

Brief každému agentovi piš **s konkrétními cestami z fáze A**, ne obecně. Zakaž jim
domýšlení: co nenajdou v kódu, nemají hlásit.

## Fáze C — Glosář (sekvenčně)

Vyber doménové termíny z výstupů fáze B a z názvů v kódu (typy, tabulky, routy, stavové
hodnoty). Termín → jednovětné vysvětlení → 1–2 místa v kódu. Ber jen slova, která **nejsou
pochopitelná z obecné znalosti** oboru: doménový žargon, zkratky, interní pojmy, názvy
stavů workflow. Obecné programátorské pojmy do glosáře nepatří.

## Fáze D — Syntéza (zapisuj v tomto pořadí)

Pořadí není libovolné — pozdější stránky odkazují na dřívější, `index.md` je až poslední.

1. `architecture.md` — hranice, entry pointy, tok dat, deploy jednotky, build a run příkazy.
   Tok dat popiš jedním ASCII diagramem nebo bulletovým flow, ne odstavcem prózy.
2. `concepts/<pattern>.md` — jedna stránka na pattern z optiky 3. Vždy: k čemu to je,
   jak se to v repu dělá, ukázka do 6 řádků s citací, kde jsou odchylky.
3. `entities/<jmeno>.md` — jedna stránka na věc, která je uzlem grafu: klíčový modul,
   dispatcher, doménová entita, tabulka, veřejné API. Ne na každý soubor v repu.
4. `domain-model.md` — entity a jejich vztahy z optiky 2 (jen když projekt doménový model má).
5. `testing.md` — jak se testuje a spouští; co je pokryté a co ne (z optiky 4).
6. `glossary.md` — tabulka z fáze C.
7. `gotchas.md` — z optiky 5 plus pasti ze schématu, každá jako plná věta s citací.
8. `index.md` — **poslední.** Dvě věty úvodu, pak katalog všech stránek s jednovětou anotací.
   Podle tohohle souboru se v wiki orientuje ten, kdo ji nikdy neviděl.
9. `log.md` — **append-only**, přidej záznam:

   ```
   ## [YYYY-MM-DD HH:MM] full | incremental

   - Zapsáno: <N> souborů — <výčet>
   - Source commit: <git rev-parse --short HEAD><pokud `git status --porcelain` není
     prázdný, připiš " + nezacommitované změny"; z workflow to tak běží vždy, wiki
     popisuje strom, ne commit>
   - Poznámky: <co je nového od posledního běhu; u prvního běhu "initial generation">
   ```

Sadu stránek ber jako doporučení, ne příkaz: **stránka bez obsahu se nezakládá** a naopak,
když má projekt něco výrazného mimo tenhle seznam, dej tomu stránku a zmiň ji v `index.md`.

U `--scope=incremental` přepisuj jen stránky, kterých se změněné soubory dotýkají, a vždy
`index.md` (anotace) a `log.md`. Nedotčené stránky nechej být — i když bys je napsal jinak.

## Fáze E — Lint

Projdi, co jsi zapsal, a ověř:

- každý relativní odkaz míří na existující soubor v `docs/wiki/`,
- na každou stránku vede odkaz z `index.md` (žádný sirotek),
- žádné dvě stránky netvrdí o téže věci něco jiného,
- každé tvrzení, které se dá ověřit, má citaci `cesta:řádek`, a ta cesta existuje,
- ukázky kódu odpovídají tomu, co je dnes v repu (u `incremental` hlavně ty nedotčené).

Nálezy **netiš přepsáním** — připoj je na konec posledního záznamu v `log.md` jako
`### Lint` s výčtem. Rozbité odkazy oprav, rozpory nahlas.

## Fáze F — Report uživateli (max 6 řádků)

- rozsah (`full` / `incremental`) a proč, pokud došlo k degradaci
- kolik stránek zapsáno, kolik nedotčeno
- kolik termínů v glosáři
- lint: rozbité odkazy, sirotci, rozpory (ideálně nuly)
- jedno doporučení, co dál (typicky kdy pustit znovu)

## Pravidla obsahu

- Wiki nesmí tvrdit nic, co není v kódu nebo ve schématu. **Nedoplňuj domněnky.**
- Každá stránka začíná `#` nadpisem, který odpovídá jejímu účelu.
- Cross-linkuj hojně relativními odkazy — hotové vazby jsou celý smysl wiki proti tomu,
  dohledávat je při každém dotazu znovu.
- Cituj kód jako `cesta/k/souboru:řádek`. Ukázky do 6 řádků, nikdy celé soubory.
- **Nikdy needituj zdrojový kód.** Wiki je výstup, kód je vstup.
- Soubory v `docs/wiki/`, které tenhle command neumí regenerovat (ruční poznámky, ADR),
  **nechej být** — přepisuj jen to, co sám píšeš.
- Bez emoji, bez zmínek o AI/Claude, bez `Co-Authored-By` v obsahu wiki.
- Necommituj. Commit řeší člověk (`/feature:commit`).
