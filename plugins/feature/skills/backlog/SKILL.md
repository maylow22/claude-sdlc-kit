---
name: backlog
description: Keeps work that is not being done now in the project's versioned BACKLOG.md — both a finding you hit outside the current task and a feature you intend to build later. The backlog is opt-in: it exists in a project only once /feature:backlog-init has set it up, and where it is active, a finding gets offered for filing rather than only mentioned. Use when you run into a previous bug, stale documentation, a weakness, debt or an idea that does not belong in the current task — and whenever you catch yourself asking "should I fix this, or leave it?". Also on requests like "file a ticket", "add it to the backlog", "set up a backlog", "what is left to do", "go through the backlog".
metadata:
  version: 1.3.0
---

# Backlog

One versioned file per project holding **what is not being done now**. It covers two kinds of
ticket that behave the same way once written down:

- **A finding** — you were working on task A and hit problem B. Without a backlog there are only
  two bad moves: fix it in an unrelated branch (and grow the diff by something nobody asked for
  and nobody reviewed), or mention it in the reply and watch it die with the conversation.
- **Planned work** — something you intend to build, just not today. It waits here until
  `/feature:start BL-<n>` picks it up.

The third option, for both: **write it down and move on.**

## When to write

Write when the item is **outside the current task** and it would be a shame to lose it:

- an earlier bug or weakness you ran into along the way
- documentation that no longer matches the code
- debt that got in your way (dead code, duplication, a missing guard)
- an idea or a feature that deserves a decision of its own
- something outside the code — infrastructure, content, a third-party account

**Do not write** what is part of the current task (do that instead), what is purely about this
conversation ("still need to check it went through"), or what is already in the backlog — extend
the existing ticket rather than duplicating it.

**Do not write instead of fixing when the fix is the task.** The backlog is not where requested
work gets parked.

## Where

1. **`BACKLOG.md` in the repository root.** It must be **versioned** — a backlog a fresh clone
   does not know about is just a private note. Watch out for projects with the whole `.claude/`
   in `.gitignore`: there the file does **not** belong in `.claude/` unless an exception is added.
2. If the project already has a live tracker (Jira, GitHub Issues, `TODO.md`, an older
   `serviceDesk.md`), **use that one** and do not create this file — keep its filename, its
   section layout and its **existing ID prefix** (`SD-18` stays `SD-`), because renaming it would
   orphan every ticket already in it and every reference to one. Everything below then applies to
   that file. Ask when you are not sure which tracker is actually alive.
3. **If the file does not exist, do not create it** — offer `/feature:backlog-init` instead and
   wait. See the next section.

## An active backlog is opt-in

The backlog exists in a project only once someone has set it up. **`/feature:backlog-init` is the
only command that creates the file**; nothing else brings a backlog into a project that does not
have one — not a finding, not `/feature:backlog-add`, not the end of a `/feature:start` run.

**The active backlog is the file itself.** `BACKLOG.md` in the root (or the tracker file the
project already keeps) exists → the project has a backlog. Nothing exists → it does not, and the
right move is to offer the init in one sentence, not to create the file.

Two reasons for the switch. A `BACKLOG.md` that turns up in a diff unasked is noise for the
review, and a project that keeps its work in Jira does not want a second, parallel list of
tickets — that is the surest way to have both go stale. The backlog is meant for projects
**without** a tracker; with a tracker, work belongs there, unless the user has explicitly decided
during the init that they want both (then the header of the file says which goes where).

**What to do when a backlog is not active:**

- Say the finding in the reply — one sentence, as plainly as if the backlog existed.
- Add: "the project has no backlog; `/feature:backlog-init` sets one up." **Once per
  conversation**, not with every finding.
- If the project has Jira, offer a ticket there instead.

## Offering a finding when the backlog is active

With an active backlog, a finding outside the current task is **not a thing to mention in
passing**. Offer it:

- **At the end of the reply**, after the work itself — never mid-task, and never as a reason to
  stop what you are doing.
- **Name the finding in one sentence** with its impact ("`claude_monitor.py` polls once a second
  even when idle — with 8 sessions it keeps the CPU busy"), plus the priority you would file it
  at. One line each, several findings as a short list.
- **Ask whether to file them**, and write only what is approved. The write goes through
  `/feature:backlog-add`, with everything that entails — a duplicate check first, the claim
  verified against the code.
- **Never write without asking.** A backlog that fills up by itself is a backlog whose owner
  stops reading it. The one exception is an explicit standing instruction from the user in this
  conversation ("file everything you find").
- A **two-minute fix while the user is standing right there** is not a ticket. Say so — they may
  want it now.

The rules in "When to write" decide **what** counts as a finding worth offering. This section
decides only **how** it gets offered.

## The file

```markdown
# Backlog

Work that is not being done now. Priority is the order of the sections; a closed ticket moves to
`BACKLOG.done.md`. A ticket is picked up with `/feature:start BL-<n>`.

## High priority

### BL-3 — Monitor: switch polling to SSE
**Area:** performance · plugins/claude-monitor/tools/claude_monitor.py

The dashboard polls once a second even when nothing happens — with 8 open sessions it keeps
the CPU busy and the fan on. It grows linearly with the number of sessions.

**Done when:** the dashboard updates without polling and idle CPU stays under 1 %

## Medium priority

### BL-4 — ...

## Low priority

<!-- last-id: BL-4 -->
```

Two optional lines, only when they carry something:

- `**Watch out:** <a known trap — what this change invalidates elsewhere>` — write it into the
  ticket the moment you know it. That is where it gets looked for, not in a conversation log.
- `**Branch:** feature/BL-3-monitor-sse` — added by `/feature:start` when it picks the ticket
  up, so an open ticket does not look untouched.

**Write the file in the language the repo uses** (its commits, its README) — headings, fields and
text alike. The ID prefix `BL-` and the `<!-- last-id: BL-N -->` marker stay as they are in any
language: they are read by machine.

## Rules for a ticket

- **Priority is the position of the section**, not a field. Moving a ticket between sections is
  how priority changes.
- **One ticket is one thing** that can be closed. "Go through security" is not a ticket.
- **Always state the impact** — what breaks, or what is lost, if nobody does it. A ticket that
  only describes a state ("this function is long") never gets opened. One that says what goes
  wrong does.
- **`Done when` is a verifiable condition**, not a restatement of the title. Not "fix X" but the
  state in which it is fixed.
- **The file holds open items only.** A ticket that is finished, or that is going away for any
  other reason, **leaves `BACKLOG.md` and lands in `BACKLOG.done.md`** — see the next section.
  It is never crossed out in place and never left in a "Done" section: a backlog you have to read
  past finished items to use is a backlog nobody reads.
- **Numbers are never recycled.** Because closed tickets leave the file, the highest number in it
  is not enough — keep the `<!-- last-id: BL-N -->` marker at the end and raise it after every
  addition. The marker lives in `BACKLOG.md` and is never lowered, not even when the highest
  ticket moves to the archive.
- **The next number comes from a shared counter, not from the marker alone.** The marker is in
  git, so every branch has its own copy — two sessions on two branches would hand out the same
  number. `/feature:backlog-add` takes it from `backlog-max-id`, one number in the Claude Code
  project folder of the main checkout, which all worktrees of the repository share, and raises
  both. The counter is never lowered either; the marker stays as the fallback for a clone that
  has no counter.

## Closing a ticket — `BACKLOG.done.md`

A ticket never just disappears. It moves, verbatim, to **`BACKLOG.done.md`** in the repository
root — the same directory, the same versioning as `BACKLOG.md`.

This applies to **every** way a ticket leaves the backlog, not just success: done, no longer
relevant, merged into another one, dropped by decision. What differs is a single added line
saying why.

### How to move it

1. **Cut the whole ticket** out of `BACKLOG.md` — heading, `Area`, description, `Done when`, all
   of it. No trace stays behind: no strikethrough, no "(done)" in the title, no "Done" section.
2. **Paste it at the top** of `BACKLOG.done.md`, under the header. Newest first, so the file reads
   as a history without scrolling to the bottom.
3. **Add a `Closed` line** right under the heading, before everything else:

   `**Closed:** 2026-09-18 · done · commit 8c48187`

   The date from `date +%F` (never guessed), then one of `done` / `stale` / `duplicate of BL-4` /
   `dropped`, and where relevant the evidence: a commit, a branch, one clause of reasoning. For
   `done` this is what makes the entry worth keeping — six months later the question is *what
   closed it*, and the answer is in that line.
4. **Leave the `<!-- last-id: BL-N -->` marker in `BACKLOG.md`** where it is. The archive has no
   marker of its own.

If `BACKLOG.done.md` does not exist yet, create it when the first ticket closes — header only,
no empty sections. It is not set up in advance by the init.

```markdown
# Backlog — closed

Tickets that have left BACKLOG.md. Newest first. Nothing here is work waiting to be done.

### BL-3 — Monitor: switch polling to SSE
**Closed:** 2026-09-18 · done · commit 8c48187
**Area:** performance · plugins/claude-monitor/tools/claude_monitor.py

The dashboard polls once a second even when nothing happens — with 8 open sessions it keeps
the CPU busy and the fan on. It grows linearly with the number of sessions.

**Done when:** the dashboard updates without polling and idle CPU stays under 1 %
```

### What the archive is not

- **It is not a second backlog.** Nothing in it is waiting for anyone. `/feature:backlog-list`
  never reads it, `/feature:backlog-groom` never grooms it, and `/feature:start` never picks a
  ticket out of it. Read it only when someone asks what happened to a ticket, or asks what got
  done.
- **It is not a place to park work.** A ticket that is still open does not go there to make the
  backlog look tidier. When a ticket stops being worth doing, that is `dropped` and it needs a
  reason in the `Closed` line.
- **It is not trimmed.** The archive grows and that is fine — nobody reads it front to back. Do
  not "clean it up", do not split it by year unless the user asks.
- **A ticket does come back** if it turns out it was closed too early: move it back to
  `BACKLOG.md`, drop the `Closed` line, and **keep its original number**. Numbers are not
  recycled, and reusing the old one is what keeps the archive entry and the reopened ticket
  legible as the same thing.

## Rules of conduct

- **Writing to the backlog does not replace telling the user.** Always say what you found and
  that you filed it. They may well decide they want it now.
- **Do not change other people's priorities** unasked. File new ones where their impact puts them.
- **Do not close a ticket you have not verified.** Only something that meets its own
  `Done when` gets closed as `done` — anything else leaves with an honest reason in the `Closed`
  line, not with `done`.
- On "what is left" or "go through the backlog", **read the file and summarize it** by priority —
  do not recite it verbatim.
