---
description: Hands /feature:start over to Codex — opens a new cmux tab with an interactive Codex that runs the whole workflow there
argument-hint: <whatever /feature:start takes — issue key | URL | BL-<n> | description, plus its flags>
---

Run `/feature:start` in **Codex** instead of here: a new tab next to this session, with an
interactive Codex that walks every step of the workflow and asks its gates itself. This session
only launches it — it does not run the workflow, and it does not watch it.

If the argument is missing, **ask** what to implement — do not open an empty Codex.

## Steps

1. **Check, in parallel**, and stop with the missing piece named if any fails:
   - `cmux identify` succeeds — this session runs inside cmux. If not, do not launch anything;
     give the user the line to run in a terminal of their own (step 3's `cd … && codex …`).
   - `codex --version` succeeds.
   - `codex plugin list` lists `feature@<marketplace>` as installed — without it Codex has no
     `feature:start`. The install is in this plugin's README, section *In Codex*.
   - `git rev-parse --show-toplevel` — the repo root the run will work in.
2. **The working tree** — `git status --porcelain`. Codex will branch off and edit this same
   checkout, so say so if it is dirty; `/feature:start` itself stops on that in Codex.
3. **Open the tab** — the argument goes through unchanged, shell-quoted as one string:

   ```bash
   cmux new-surface --type terminal --focus true \
     --command "cd '<repo root>' && codex '\$feature:start <argument>'"
   cmux rename-tab --surface <surface ref from the output> "codex: <short task name>"
   ```

   `$feature:start` is Codex's explicit mention of the skill — keep the `$` out of reach of the
   shell. A flag meant for this command does not exist; every flag belongs to `/feature:start`.
4. **Report** in three lines: the tab (its `surface:` ref and title), the repo and the argument
   handed over, and that **this session keeps its hands off that checkout** until the Codex run
   is done — two agents editing one working tree overwrite each other. The first Codex run in a
   repo opens on a *Trust this folder?* prompt; that answer is the user's, so say it may be
   waiting in the tab and never answer it for them.

When the user comes back saying the Codex run is finished, the diff is theirs to have reviewed
here: offer `feature:reviewer` over it — a different model checking the other one's work is the
point of handing it over.
