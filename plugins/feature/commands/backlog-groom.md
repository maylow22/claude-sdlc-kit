---
description: Maintenance of the project backlog — verifies tickets against the real code, proposes closing what is done into BACKLOG.done.md, merging duplicates and fixing what cannot be picked up
argument-hint: [BL-<n> ... | nothing = the whole backlog]
---

Go through the backlog and confront it with the state of the repository. A backlog nobody prunes
fills up with tickets that were finished long ago, and then nobody reads it. The format of the
file is described by the **`backlog` skill**.

With an argument, groom only the listed tickets. Without one, all of them.

## Steps

### 1. Read and verify

Read `BACKLOG.md` and for each ticket **check the actual code** — read the files it names, search
for the symbols, look at `git log` for the area. Decide on evidence, never on a guess about how
it probably turned out. For each ticket, one verdict:

- **done** — the `Done when` condition is met in the current code. Say what proves it (a file, a
  commit, a symbol).
- **duplicate** — it overlaps another ticket. Name which one and what the merged one should say.
- **stale** — the code it was about is gone, or the problem no longer exists for another reason.
- **unpickable** — it has no impact stated, or the `Done when` cannot be verified. It needs a
  rewrite, not a closure; propose the wording.
- **wrong priority** — the impact does not match the section it sits in. Propose the move and
  state what changed.
- **ok** — leave it alone.

Tickets with a `Branch` line: check whether the branch exists. Gone plus the condition met means
**done**; gone with the condition unmet means an abandoned attempt — propose clearing the line.

### 2. Present it and wait

Show a table — ticket · verdict · one line of reasoning — and **ask for approval before changing
anything**. `AskUserQuestion`, the default being to apply everything you propose; the second
option closes only the finished tickets; the third leaves the file untouched. Anything you are
not sure about goes into the table as **ok** with a note, not as a closure.

### 3. Apply

Only what was approved:

- **move finished and stale tickets to `BACKLOG.done.md`** — cut them out whole and paste them at
  the top of the archive with a `**Closed:** <date> · done|stale · <evidence>` line; the skill
  describes the file. Never delete a ticket outright, and never leave it crossed out in place.
- merge duplicates into one ticket; the one that loses moves to the archive as
  `duplicate of BL-<n>`
- rewrite unpickable ones and move mispriced ones — those stay in `BACKLOG.md`
- **never lower the `<!-- last-id: BL-N -->` marker** (nor the shared `backlog-max-id` counter
  `/feature:backlog-add` keeps), even when the highest ticket leaves — numbers are not recycled

Then say in three lines what changed, how many tickets are left and how many moved to the
archive. **Do not commit** — leave both files in the working tree for the user.

## Rules

- **Never close a ticket you have not verified in the code.** "It is probably done" is not a
  verdict. A ticket you are unsure about stays in `BACKLOG.md`.
- **Do not groom the archive.** `BACKLOG.done.md` is history — nothing in it gets rewritten,
  merged or trimmed.
- Do not rewrite the wording of tickets that are fine. This is maintenance, not an editorial pass.
- Do not file new tickets here. Anything you discover while grooming goes through `/feature:backlog-add`
  and only after you have told the user.
