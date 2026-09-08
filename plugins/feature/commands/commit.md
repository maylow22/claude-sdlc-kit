---
description: Vytvoří git commit s českou hláškou shrnující změny
---

Vytvoř git commit s českou commit message popisující, o co v změnách šlo.

Postup:
1. Spusť paralelně:
   - `git status` (bez `-uall`)
   - `git diff` (staged i unstaged)
   - `git log --oneline -10` pro styl předchozích commitů
2. Analyzuj změny a navrhni stručnou českou commit message (1 řádek, ideálně do 72 znaků). Zaměř se na "proč" / "co se mění", ne na výpis souborů. Drž se tónu a stylu existujících commitů v repu (nepíšou velká písmena na začátku, bez tečky na konci, infinitiv/podstatné jméno).
3. Paralelně:
   - `git add` konkrétních relevantních souborů (nikdy `-A` ani `.`)
   - `git commit -m "<zpráva>"` přes HEREDOC, BEZ Co-Authored-By řádku a BEZ jakékoli zmínky o Claude
4. Pak `git status` pro ověření.

Pravidla:
- NIKDY necommituj soubory které vypadají jako tajemství (`.env`, credentials apod.)
- NIKDY nepoužívej `--no-verify` ani `--amend` pokud o to uživatel výslovně nepožádá
- NIKDY nepushuj
- Commit message je čistě v češtině, bez emoji, bez Co-Authored-By řádku
