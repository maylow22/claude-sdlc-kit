#!/usr/bin/env python3
"""Notification hook: records that this session is waiting on the user.

Claude Code fires Notification with a permission_prompt / idle_prompt /
elicitation_dialog matcher. The matcher is not in the payload, so we take the
kind as an argument.

Writes ~/.claude/monitor/notify/<sessionId>.json; the dashboard treats the file
as valid until the transcript moves past it (a user answer = a write to the
transcript, i.e. mtime > ts => the record is stale).
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
