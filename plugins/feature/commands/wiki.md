---
description: Generuje technickou wiki pro AI orientaci v kódu projektu (Karpathy-style LLM wiki). Píše do docs/wiki/.
argument-hint: [--scope=full]
---

Vygeneruj technickou wiki pro aktuální projekt v `docs/wiki/`. Cílem je, aby budoucí AI sezení (i lidé) získali okamžitou orientaci v kódu bez nutnosti procházet strom souborů.

Wiki je _kompilát_ podle Karpathyho LLM-wiki vzoru:
- **raw zdroj** = kód projektu (immutable),
- **wiki** = `docs/wiki/` (LLM ji vlastní a přepisuje),
- **schéma** = `CLAUDE.md` a `AGENTS.md` (konvence projektu).

Argumenty:
- `--scope=full` (výchozí) — kompletní regenerace všech souborů wiki.
- `--scope=incremental` — TODO(incremental): zatím neimplementováno, vyhraď arg pro budoucí použití (post-edit agent řízený `git diff`). Pokud bude předáno v této verzi, vypiš upozornění a degraduj na `full`.

Veškerý obsah wiki piš **anglicky**. České doménové termíny (CPZ, vyúčtování, schválení, kontrola, výplata, …) v textu **zachovej v češtině** a vysvětli je v `glossary.md`.

## Pipeline

### Fáze A — Načti schéma (sekvenčně, rychlé)

1. Přečti `CLAUDE.md`, `AGENTS.md`, `package.json`, `vite.config.js`, `federationExposes.ts` (pokud existují).
2. Pokud existuje `docs/wiki/log.md`, přečti poslední entry — využij časové razítko pro nový log entry.
3. Ověř, že `src/` existuje. Pokud ne, ukonči s jasnou hláškou „Cannot generate wiki: no `src/` directory in current working directory.“
4. Vytvoř adresáře `docs/wiki/`, `docs/wiki/concepts/`, `docs/wiki/entities/` pokud chybí.

### Fáze B — Discovery (paralelně, 3 Explore subagenti v JEDNÉ zprávě)

Spusť tři Explore subagenty paralelně. Každý vrátí strukturovanou markdown zprávu pod ~500 slov. Zprávy NEPUBLIKUJ jako wiki — slouží jen jako vstup pro fázi D.

**Agent 1 — Architektura a entry pointy**
- Brief: „Map the project's entry points and federation surfaces. Cover `federationExposes.ts`, `vite.config.js` (federation plugin config), `src/main.tsx`, `src/App.tsx`, `src/components/Form.tsx` (extract the COMPLETE `formName → component path` mapping — read the file fully), `src/components/Page.tsx`, `src/components/List.tsx`. For each, report: purpose, exported symbols, how federationContext flows in. Output as numbered list with file paths."

**Agent 2 — Katalog task formulářů**
- Brief: „List every file under `src/components/taskForms/travelorder/`, `taskForms/subforms/`, `taskForms/detail/`, `taskForms/schemas/`. For each: filename, derived formName (from Form.tsx mapping if listed there, otherwise from filename), one-line purpose (read the file's top comments/JSDoc and the form's title), workflow stage (zadání / schválení / kontrola / vyúčtování / výplata). Output as Markdown table sorted by workflow stage."

**Agent 3 — Patterns, hooks, schemas, gotchas**
- Brief: „Profile recurring patterns: (a) every file in `src/hooks/` — purpose, API endpoint hit (if any), return shape; (b) every file in `src/components/taskForms/schemas/` — which yup objects it exports and what they validate; (c) recurring patterns from `CLAUDE.md` plus grep usages across `src/` of: `FormFieldCN`, `federationContext.apiClient`, `handleErrors`, `useWatch`, `useDraftManager`, `yupResolver`. Output sectioned by: hooks / schemas / form-pattern / api-pattern / state-and-data / validation / error-handling. Quote 1-2 concise representative snippets per pattern (≤6 lines each) with file:line citations."

### Fáze C — Sběr doménových termínů (sekvenčně)

5. Grep české doménové termíny z výstupů Agenta 2 + 3 a z `src/components/constants.ts`, `src/travelorderTypes.ts`. Sestav glosář: termín (CZ) → krátké anglické vysvětlení → kde použito (1–2 file paths).
   - Cíl pokrýt minimálně: CPZ, vyúčtování, schválení, kontrola, návrh, vyplata zálohy, vrácení zálohy, kontrola nákladů, kontrola OMV, doplnění návrhu, rozhodnutí.

### Fáze D — Syntéza (zapiš soubory)

Piš v tomto pořadí (později generované soubory mohou odkazovat na ty dřívější):

6. `docs/wiki/architecture.md` — z Agenta 1. Sekce: Module Federation, Entry points, Form dispatch (krátký diagram v ASCII nebo bullet flow: Page → Form → lazy(taskForms/...)), Build/dev commands (z `package.json`).
7. `docs/wiki/task-forms.md` — z Agenta 2. Hlavní tabulka `| formName | file | stage | purpose |` seřazená podle workflow stage. Pod tabulkou krátký narrative odstavec na každý stage.
8. `docs/wiki/concepts/form-pattern.md` — FormFieldCN snippet, povinný `data-cy` na `FormItem` a `FormLabel`, tabulka výchozích hodnot (z CLAUDE.md), Checkbox výjimka.
9. `docs/wiki/concepts/api-pattern.md` — `federationContext.apiClient` flow, příklad volání, `handleErrors(err, emitter)` na chyby.
10. `docs/wiki/concepts/state-and-data.md` — react-hook-form + `useWatch` (s pravidlem fallback hodnoty), `useDraftManager`, zustand pokud existuje (jinak explicitně „no zustand stores“).
11. `docs/wiki/concepts/validation.md` — yup + `yupResolver`, kde žijí schémata, `undefined` vs `null` pro file upload.
12. `docs/wiki/concepts/error-handling.md` — `handleErrors`, toast flow z emitteru.
13. `docs/wiki/entities/Form.tsx.md` — jak funguje dispatcher, kompletní mapping (zdroj: Agent 1), Suspense fallback.
14. `docs/wiki/entities/hooks.md` — jedna sekce na každý hook z `src/hooks/`.
15. `docs/wiki/entities/schemas.md` — výpis exportů z `taskForms/schemas/*`.
16. `docs/wiki/entities/shared-lib.md` — výčet komponent z `@addsign/moje-agenda-shared-lib` použitých v projektu (extrahuj importy z grepu).
17. `docs/wiki/glossary.md` — tabulka z fáze C.
18. `docs/wiki/gotchas.md` — sekce „Known Gotchas“ z `CLAUDE.md` přepsaná do plné věty + cokoli dalšího, co subagenti označili jako past.
19. `docs/wiki/index.md` — **píš až jako poslední**. Krátký intro odstavec (1–2 věty), pak seznam odkazů na všechny ostatní soubory s jednovětou anotací u každého.
20. Append do `docs/wiki/log.md` (vytvoř pokud neexistuje) entry:

   ```
   ## [YYYY-MM-DD HH:MM] full | wiki-generate

   - Files written: <N>
     - architecture.md, task-forms.md, …
   - Source commit: <output of `git rev-parse HEAD`>
   - Notes: <anything notable — e.g. „2 new task forms detected since last run: X, Y"; pokud první run, napiš „initial generation"」>
   ```

### Fáze E — Lint

21. Projdi všechny zapsané soubory a ověř, že každý relativní odkaz (`./concepts/...`, `./entities/...`, `../index.md`, …) odkazuje na existující soubor v `docs/wiki/`.
22. Pokud najdeš broken link, **neopravuj cíleně tichým přepsáním** — připoj na konec posledního log entry sekci `### Broken links` se seznamem.

### Fáze F — Report uživateli (max 5 řádků)

Vypiš:
- počet zapsaných souborů,
- broken links count (ideálně 0),
- počet doménových termínů v glosáři,
- 1 doporučení na další krok (např. „rerun po větším refactoru; pro post-edit automatizaci přidat --scope=incremental").

## Pravidla obsahu

- Anglický jazyk pro veškerý prozaický text wiki. České doménové termíny zůstávají v češtině.
- Každý soubor začíná H1 nadpisem odpovídajícím účelu souboru.
- Cross-linkuj liberálně mezi wiki soubory pomocí relativních odkazů.
- Cituj zdrojový kód jako `path/to/file.tsx:LINE` (nevkládej dlouhé bloky, max 6 řádků na ukázku).
- Wiki nesmí obsahovat fakta, která nejsou v kódu / `CLAUDE.md` / `AGENTS.md`. Nedoplňuj domněnky.
- Nesmaž soubory, které v `docs/wiki/` najdeš a které tento command neumí regenerovat (např. ručně přidané poznámky). Přepiš jen ty, které sám zapisuješ.
- Nepřidávej Co-Authored-By, emoji ani zmínky o Claude/AI v obsahu wiki.

## Volání command z jiného agenta (budoucnost)

Tento command je navržen tak, aby ho v budoucnu mohl volat post-edit agent (např. ze Stop hooku). V té fázi se přidá větev `--scope=incremental`, která místo plné regenerace přečte `git diff` od posledního log entry a aktualizuje pouze dotčené soubory. Strukturu workflow zachovej.
