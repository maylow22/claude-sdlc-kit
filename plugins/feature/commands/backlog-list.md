---
name: feature-backlog-list
description: Overview of the project backlog — open tickets by priority, what is in progress and what to pick up next. Use when the user invokes /feature-backlog-list or /feature:backlog-list.
argument-hint: [word to filter by | nothing = everything]
---

Show what is waiting in the project's backlog. The format of the file is described by the
**`backlog` skill**.

## Steps

1. **Read `BACKLOG.md`** in the repository root. If it does not exist, say in one line that the
   project has no backlog and offer `/feature:backlog-init` — do not create an empty file. If the
   project has a different live tracker, read that one.
2. With an argument, **filter** the tickets by it (area, file, a word in the title) and say what
   you filtered by.
3. **Summarize by priority, do not recite.** One line per ticket: number, title and the impact
   compressed into a clause. High priority in full; medium and low may be summarized in a single
   line each once there are more than about five. At the end, the count per section.
4. **Mark what is already running** — tickets with a `Branch` line. Check whether the branch
   still exists (`git branch --list`, `git branch -r --list`): a ticket pointing at a branch that
   is gone is either finished (close it) or abandoned (clear the line). Say which, do not fix it
   here — that is what `/feature:backlog-groom` is for.
5. **Close with a recommendation**: which ticket to pick up next and why, plus the command
   `/feature:start BL-<n>`. One sentence, not a ranking of all of them.

**Do not read `BACKLOG.done.md`.** The archive holds closed tickets; nothing in it is waiting for
anyone, and mixing it in is what makes a backlog unreadable. Reach for it only when the user asks
what happened to a ticket, or what has been done.

Do not modify the file. This is a read-only command.
