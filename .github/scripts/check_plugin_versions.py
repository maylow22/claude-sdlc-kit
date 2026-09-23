#!/usr/bin/env python3
"""Fail when a pull request changes a plugin but leaves its version alone.

An installed plugin is cached per version — `~/.claude/plugins/cache/<marketplace>/
<plugin>/<version>` — so merging a change that does not raise `version` reaches nobody who
already has it installed: the marketplace metadata refreshes, the plugin files do not. The
symptom is silent, which is why this is a gate rather than a note in a checklist.

    .github/scripts/check_plugin_versions.py <base-ref> [head-ref]
    .github/scripts/check_plugin_versions.py main          # locally, before opening the PR

It compares committed trees, the way CI sees them, so commit the bump before running it.
A plugin being added or removed is not a bump; both pass.
"""

from __future__ import annotations

import json
import subprocess
import sys

PLUGIN_JSON = ".claude-plugin/plugin.json"


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed:\n{r.stderr.strip()}")
    return r.stdout


def version_at(ref: str, plugin: str) -> str | None:
    """The plugin's declared version at a ref, or None when it has no manifest there."""
    r = subprocess.run(
        ["git", "show", f"{ref}:plugins/{plugin}/{PLUGIN_JSON}"],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return None
    try:
        return str(json.loads(r.stdout)["version"])
    except (ValueError, KeyError):
        return None


def parts(v: str) -> tuple:
    """`1.2.10` -> (1, 2, 10) so 1.2.10 sorts above 1.2.9. Anything that is not plain
    numbers falls back to the string, which still catches "did it change at all"."""
    bits = v.split(".")
    return tuple(int(b) for b in bits) if all(b.isdigit() for b in bits) else (v,)


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    base, head = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "HEAD")

    merge_base = git("merge-base", base, head).strip()
    changed = git("diff", "--name-only", merge_base, head).split()

    touched = sorted({p.split("/")[1] for p in changed if p.startswith("plugins/") and "/" in p[8:]})
    if not touched:
        print("no plugin files changed — nothing to check")
        return 0

    failures = []
    for plugin in touched:
        was, now = version_at(merge_base, plugin), version_at(head, plugin)
        if was is None or now is None:  # plugin added or removed, not a change to one
            print(f"  {plugin}: added or removed — skipped")
            continue
        if was == now:
            failures.append(f"{plugin}: changed, but version is still {now}")
        elif parts(now) <= parts(was):
            failures.append(f"{plugin}: version went {was} -> {now}, which is not forward")
        else:
            print(f"  {plugin}: {was} -> {now}")

    if failures:
        print("\nEvery plugin a PR touches needs its version raised in")
        print(f"plugins/<plugin>/{PLUGIN_JSON} — an install is cached per version, so")
        print("without a new one the change never reaches anybody who already has it.\n")
        for f in failures:
            print(f"  ✗ {f}")
        return 1

    print("\nevery changed plugin carries a new version")
    return 0


if __name__ == "__main__":
    sys.exit(main())
