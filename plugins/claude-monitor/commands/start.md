---
description: Spustí live dashboard všech běžících Claude sessions (port 8787)
argument-hint: "[port]"
---

Spusť monitor sessions na pozadí a vrať uživateli URL.

1. Zjisti, jestli už neběží: `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:${1:-8787}/`
   Pokud vrátí `200`, **nespouštěj druhou instanci** — jen oznam URL a skonči.
2. Jinak spusť na pozadí:
   `python3 "${CLAUDE_PLUGIN_ROOT}/tools/claude_monitor.py" --port ${1:-8787}`
3. Ověř, že odpovídá (`/api/state` vrací JSON), a vypiš uživateli URL
   `http://127.0.0.1:<port>/` plus počet nalezených sessions.

Zastavení: `kill $(lsof -ti:<port>)`.
