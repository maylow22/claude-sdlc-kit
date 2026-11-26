---
name: feature-backlog-init
description: Sets up a versioned backlog (BACKLOG.md) in the project — the one command allowed to create the file. Use when the user invokes /feature-backlog-init or /feature:backlog-init.
argument-hint: nothing
---

Set up the project's backlog. This is the **only** place where `BACKLOG.md` gets created — every
other backlog command works with a file that already exists. The format of the file is described
by the **`backlog` skill**; load it before writing anything.

Initialization is a decision of the user's, never a side effect of some other task. If you were
not asked for it, do not run it.

## Steps

### 1. Is there already a backlog?

Look for `BACKLOG.md` in the repository root and for a file the project already keeps instead
(`TODO.md`, `serviceDesk.md`, `ISSUES.md`). If one exists, say which file it is and **stop** —
there is nothing to initialize. That file is the backlog; the skill's rules apply to it, keeping
its name, its layout and its existing ID prefix.

### 2. Is there a live tracker?

The backlog is meant for projects **without** a tracker of their own. Before creating anything,
check whether the project already has one:

- an Atlassian MCP connected and `.claude/jira/` in the repository, Jira keys in `git log`
  (`ABC-123` in commit subjects), a Jira link in the README
- GitHub Issues — `gh issue list` returns something, or `.github/ISSUE_TEMPLATE/` exists

If you find one, **say what you found and ask** (`AskUserQuestion`) whether to set the backlog up
anyway. Two reasonable outcomes, and the user picks:

- **No** — the tracker is where work belongs; create nothing and say tickets go to Jira / Issues.
- **Yes anyway** — some teams want a local backlog for items below the level of a tracker ticket
  (debt, a note for the next agent, a two-line finding). Then continue, and in step 3 write into
  the header **which of the two goes where**, so the next agent does not have to guess.

With no tracker found, continue without asking.

### 3. Create the file

`BACKLOG.md` in the repository root, with the header and the three priority sections, empty, and
the `<!-- last-id: BL-0 -->` marker at the end — the skill holds the exact shape. **In the
language the repo uses** (its commits, its README).

Do **not** create `BACKLOG.done.md` — the archive of closed tickets comes into being when the
first ticket closes, not before. An empty archive is just noise in the repository.

Check that the file is not ignored — `git check-ignore -v BACKLOG.md`. A backlog a fresh clone
does not know about is just a private note. Projects that have the whole `.claude/` in
`.gitignore` are the usual cause; the file belongs in the root, not in `.claude/`. If it comes
out ignored anyway, say so and offer an exception in `.gitignore`.

### 4. Write the convention into `CLAUDE.md`

If the project has its own `CLAUDE.md`, add a short paragraph: that tickets not being done now go
into `BACKLOG.md`, that a ticket is picked up with `/feature:start BL-<n>`, and — when step 2
found a tracker — what goes there instead. Without this paragraph the next agent will not see the
convention, and an empty backlog stays empty.

If the project has no `CLAUDE.md`, do not create one for this. Say so in one line.

### 5. Offer to fill it

The backlog's point is that things land in it. Ask whether to file the first tickets right away —
from what is already known about the project (findings from this conversation, `TODO`/`FIXME`
comments in the code, something the user has waved off as "later"). If they agree, each ticket
goes through `/feature:backlog-add`, one at a time.

**Do not commit.** Say in two lines what you created, and that from now on findings outside the
current task will be offered for the backlog.
