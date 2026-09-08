---
description: Adversariální review implementačního plánu proti skutečnému kódu — než se začne psát
argument-hint: "[cesta k plánu | prázdné = plán z této session]"
---

Nech implementační plán adversariálně proklepnout **předtím**, než se z něj začne psát kód.
Sám plán nereviduješ — na to je izolovaný agent `feature:plan-reviewer` s čistým kontextem,
který ho ověřuje proti reálnému kódu, ne proti tvé argumentaci.

## Který plán

- Argument je cesta k souboru (typicky `.claude/plans/*.md`) → reviduje se ten plán.
- Bez argumentu → plán z téhle session: výstup plan mode, nebo postup, na kterém jsme se
  právě shodli. Když žádný takový plán není, **zeptej se** — nevymýšlej si ho.

## Postup

1. Spusť agenta `feature:plan-reviewer`. Předej mu **zadání**, **plán** (celý text, nebo
   cestu k souboru) a `baseBranch`. Nic dalšího — ani proč jsi se pro daný postup rozhodl.
2. U velkého nebo rizikového plánu spusť **v jedné zprávě 2–3 agenty paralelně**, každého
   s jinou optikou: správnost a pořadí kroků / reuse a jednoduchost / testy a hraniční
   případy. Nálezy pak slož a zduplikované zahoď.
3. Nálezy vypiš uživateli: **Blocking** první, u každého kde to je a jaká je oprava.
4. **Blocking** nálezy zapracuj do plánu. **Should-fix** podle úsudku — co nezapracuješ,
   napiš i s důvodem. Pokud plán žije v souboru, uprav ten soubor.
5. Ukaž, co se v plánu změnilo (stručně, ne celý diff), a **teprve tenhle plán** dej
   uživateli k odsouhlasení.

Když review nic nenajde, je to jednořádkový výsledek — nenafukuj ho.
