---
description: Files a ticket in the project backlog (BACKLOG.md) — work that is not being done now
argument-hint: <what should be done | nothing = take it from the conversation>
---

File a ticket in the project's backlog. Follow the format and the rules of the **`backlog`
skill** — it is the single source of truth for the file, the fields and the numbering. Load it
before writing anything.

## What goes into the ticket

- **With an argument** — that is the subject. Do not extend it with anything the user did not
  say.
- **Without an argument** — take the subject from what was just discussed: the finding you hit,
  the thing the user waved off as "later", what a reviewer marked as out of scope. Name it in
  one sentence and **have it confirmed** before writing. If there is nothing in the conversation
  to reach for, ask what to file — do not invent a ticket.

## Steps

1. **Find the backlog.** `BACKLOG.md` in the repository root. If the project has a different live
   tracker (Jira, GitHub Issues, `TODO.md`), use that one and say so instead of creating a second
   file. **If no backlog exists, do not create one** — say the ticket in one sentence the way you
   would have written it, point at `/feature:backlog-init`, and stop. Setting a backlog up is the
   user's decision; this command only files into one that is already there.
2. **Check for a duplicate first.** Read the existing tickets. If the item is already there,
   **extend that ticket** — a second one about the same thing turns a backlog into noise.
3. **Verify the claim against the code** before describing an impact. A ticket built on an
   assumption about code you did not open wastes the time of whoever picks it up.
4. **Take the number** — run this from the repository root, with `F` set to the backlog file in
   use. It prints the ID for the new ticket and has already recorded it as taken:

   ```sh
   F=BACKLOG.md   # or the tracker file the project keeps
   export LC_ALL=C
   common=$(git rev-parse --path-format=absolute --git-common-dir) || exit 1
   case $common in */.git) root=${common%/.git} ;; *) root=$common ;; esac
   dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/projects/$(printf %s "$root" | sed 's/[^A-Za-z0-9]/-/g')"
   file="$dir/backlog-max-id"
   P=$(sed -n 's/.*last-id: \([A-Za-z][A-Za-z0-9]*\)-[0-9]*.*/\1/p' "$F" | tail -1); P=${P:-BL}
   n=$( {
     head -n 1 "$file" 2>/dev/null | tr -cd '0-9'; echo
     sed -n "s/.*last-id: $P-\([0-9]*\).*/\1/p" "$F"
     { for ref in $(git for-each-ref --format='%(refname)' refs/heads refs/remotes); do
         git show "$ref:$F" 2>/dev/null; git show "$ref:BACKLOG.done.md" 2>/dev/null
       done
       git worktree list --porcelain | sed -n 's/^worktree //p' | while IFS= read -r wt; do
         cat "$wt/$F" "$wt/BACKLOG.done.md" 2>/dev/null
       done
     } | grep -oE "$P-[0-9]+" | sed 's/.*-//' | grep -E '^[0-9]{1,6}$'
   } | sed 's/^0*//' | grep . | sort -n | tail -1 )
   n=$(( ${n:-0} + 1 ))
   mkdir -p "$dir" && printf '%s\n' "$n" > "$file.$$" && mv "$file.$$" "$file" \
     || echo "SHARED COUNTER NOT WRITTEN: $file" >&2
   echo "$P-$n"
   ```

   The next number is one above the highest of three: the shared counter, the marker in this
   checkout, and every `<prefix>-<n>` in the backlog and its archive on any branch and in any
   worktree (a couple of seconds on a repository with a hundred branches). The counter lives
   **outside git**, in the Claude Code project folder of the main checkout, so every worktree of
   the repository reads and raises the same number — the marker cannot do that, because each
   branch carries its own copy and two sessions on two branches would take the same number and
   collide only at the merge. The scan catches what the counter missed: a ticket filed by hand or
   by an older version of this command. The counter is written **before** the ticket, so the
   number is taken even if the filing stops halfway — a gap is harmless, a duplicate is not.
   Numbers longer than six digits are ignored, so one stray line on a pushed branch cannot push
   the counter out of reach; if the counter is ever wrong, it is a plain file — overwrite it with
   the right number.

   If the script prints `SHARED COUNTER NOT WRITTEN`, the ID it printed is still the highest
   number it saw plus one — file the ticket with it. If the script could not run at all (a refused
   permission, a sandbox), take the marker plus one. Either way **tell the user in one sentence**
   that the shared counter was not raised, so a collision later is not a surprise.
5. **Write the ticket** with that ID: a title that says what is wrong or missing, the area, the
   **impact** (what breaks if nobody does it), and a verifiable `Done when`. Add `Watch out` only
   if you know of a trap.
6. **Place it in a priority section** by impact, and raise the `last-id` marker to the new
   number — it stays the fallback for a clone that has no counter (another machine, a colleague).
7. **Do not commit.** Tell the user in two lines what you filed and where it landed — the ticket
   is a change to the working tree like any other and it is theirs to commit. If the tree is on a
   feature branch mid-workflow, say that the file will show up in that diff.

## Rules

- Whatever `/feature:backlog-add` gets asked for it files — but if it is genuinely a two-minute fix and
  the user is standing right there, say so in one sentence. They may want it now rather than in
  the backlog.
- **Never create the backlog file.** That belongs to `/feature:backlog-init` alone.
- **Never** file what is part of the current task instead of doing it.
- Touch no ticket other than the one you are filing (or extending).
