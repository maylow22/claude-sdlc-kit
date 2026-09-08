#!/usr/bin/env python3
"""Notification hook: zapise, ze tahle session ceka na uzivatele.

Claude Code posila Notification s matcherem permission_prompt / idle_prompt /
elicitation_dialog. Matcher v payloadu neni, takze druh dostaneme argumentem.

Zapisuje ~/.claude/monitor/notify/<sessionId>.json; dashboard soubor bere jako
platny, dokud transcript nepokrocil dal (odpoved uzivatele = zapis do transcriptu,
tj. mtime > ts => zaznam je zastaraly).
"""

import json
import os
import sys
import time

DIR = os.path.expanduser("~/.claude/monitor/notify")


def main() -> None:
    kind = sys.argv[1] if len(sys.argv) > 1 else "notification"
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    sid = payload.get("session_id") or ""
    if not sid or "/" in sid or sid.startswith("."):
        return
    rec = {"kind": kind, "message": payload.get("message") or "", "ts": time.time()}
    tmp = os.path.join(DIR, f".{sid}.tmp")
    try:
        os.makedirs(DIR, exist_ok=True)
        with open(tmp, "w") as f:
            json.dump(rec, f)
        os.replace(tmp, os.path.join(DIR, f"{sid}.json"))
    except OSError:
        pass


main()
