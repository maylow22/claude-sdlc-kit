---
description: Runs the workflow for a new feature — branch, plan, implementation and E2E in the main context; plan review, lint, code review, security and docs in isolated subagents
argument-hint: <issue key | issue URL | task description> [--fast | --full]
---

Workflow for developing a new feature. The argument is required — either an **issue key**
(e.g. `IF-9`), an **issue URL** (e.g. `https://<your-org>.atlassian.net/browse/IF-9`) or a
**free-form description** of the task.

If the argument is missing, **ask** the user what to implement — do not continue without it.

Optional flags: **`--fast`** pre-sets the short composition of steps, **`--full`** the whole
workflow. Neither decides anything on its own — the composition is confirmed at the gate in
step 3 together with the plan.

## How the context is split

- **Main context (you)** — task, plan, implementation, E2E tests, fixing findings,
  consultation, commit and PR. All of this holds a single thread and you stay with it.
- **Isolated subagents (steps 3, 6, 7, 9 and 10)** — plan review, cleanup, code review,
  documentation and finally security. Each gets a **clean context** holding at most the task,
  the plan and the branch — never the course of development. They do not know how you arrived
  at the solution, what you weighed or what you threw away along the way; that is what makes
  their findings mean something. Each pulls its own diff.
- `feature:linter` and `feature:security-reviewer` get **only the branch**: cleanup does not
  need the task, and a security review must have nothing available to talk it into believing
  a hole is actually the design.
- **Do not write** explanations, defenses or "we already dealt with this" into a subagent's
  prompt. Whoever judges the code must not know the author's argument.
- Subagents **do not commit** and the reviewers **do not fix code** — you triage and fix the
  findings in steps 8 and 10. Documentation is written by the doc-writer, because that is work
  of its own, not a fix.
- **Security goes last**, after documentation — so it sees the docs in the diff too.
- Mechanical cleanup (formatter, lint, typecheck) is a subagent as well — its output tends to
  be the longest and least interesting thing in the whole workflow, so keep it out of the main
  context.

## The composition of steps (fast track)

A typo and a new endpoint do not deserve the same workflow. So the set of steps is not fixed:
in step 3 you propose, **together with the plan**, which of the checking steps actually run, and
the user confirms the composition at the same gate that approves the plan. One gate, two things
approved.

- **Always run, never up for discussion:** 1 task, 2 branch, 3 plan **including its review**,
  4 implementation, 6 lint, 11 consultation, 12 commit & PR. The review is what makes the plan
  worth approving, and mechanical cleanup is cheap enough not to be worth negotiating.
- **Up for the composition:** 5 E2E, 7 + 8 code review and its fixes, 9 documentation,
  10 security.

**Propose dropping a step only when all of this holds:**
- the change is small and local — a handful of files, no new module, no new dependency;
- there is no behavior a test would guard: copy, styling, a constant, a log message, comments,
  dead code, a version bump, renaming a local symbol;
- it touches no data model, no API contract, no migration;
- nothing the documentation describes changes for the user.

**Never dropped, whatever the flags say** — if the change touches authentication, authorization
or permissions · secrets, credentials or crypto · handling of untrusted input · file upload · a
new or changed endpoint · dependencies · migrations · payments · CI/CD, release or deploy
scripts. With `--fast` and one of these present, **name the disqualifier and ask** rather than
obeying.

Never skip a step silently and never skip one that was not in the table at the gate.

## Steps

### 1. The task
- Issue key or URL → fetch the detail through an Atlassian MCP server if one is configured
  (`getAccessibleAtlassianResources` to resolve the cloudId for the site in the URL — or the
  only site available — then `getJiraIssue` with `responseContentFormat: "markdown"`). Extract
  summary, description, status, assignee. If no Atlassian MCP is available, ask the user to
  paste the ticket content.
- Free-form description → use it as is. Ask the user for a short slug for the branch (e.g.
  `expand-details`).
- Summarize the task in 2–3 sentences and **wait for confirmation** before continuing. If
  anything is unclear, ask.

### 2. Feature branch
- Verify the working tree is clean (`git status`). If not, **stop** and ask the user.
- Determine the **base branch**: `develop` if the repo has it, otherwise the default branch
  (`git symbolic-ref refs/remotes/origin/HEAD`, typically `main`). Confirm it with the user if
  the repo has both and the choice is not obvious. That branch is `baseBranch` for the rest of
  the workflow.
- Switch to it and pull the latest state (`git fetch origin && git checkout <baseBranch> &&
  git pull --ff-only`).
- Create the branch `feature/<KEY>-<slug>` (e.g. `feature/IF-9-expand-details`). The slug is
  short, lowercase, hyphens instead of spaces, ASCII only. Without an issue key, just
  `feature/<slug>`. If the repo's history uses a different branch naming convention, follow
  that one instead.

### 3. The plan, its review — and the gate over the composition of steps
- Put together an **implementation plan** — brief steps (what/where/how), key files, risks.
  Write it to `.claude/plans/<branch-slug>.md` so both the review and the user have something
  to read.
- **Have it reviewed before you present it:** `/feature:plan-review .claude/plans/<slug>.md`,
  i.e. the `feature:plan-reviewer` agent with a clean context. It verifies the plan against
  the real code — that the named files and symbols exist, that the step order holds, that
  nothing already in the repo is being reinvented, and that the plan covers the task and
  nothing beyond it.
- **Fold blocking findings into the plan**, should-fix at your discretion (say what you left
  out and why).
- Present the user **only the reviewed plan** plus three lines on what the review found and
  what changed in the plan because of it. The first draft is not what gets approved.
- Right under it, propose the **composition of steps** (see the section above): a short table
  of step · run/skip · a one-line reason, and the resulting track — `FULL` or `FAST`. `--fast`
  and `--full` from the argument only pre-set the proposal; they do not replace the
  confirmation, and they do not override the disqualifiers.
- **Wait for explicit approval — of the plan and of the composition.** Ask with
  `AskUserQuestion`; the default answer is **one click on your own proposal**:
  - **✅ Approve the plan and the composition** — put the proposal itself in the `description`
    (`E2E skip · review skip · docs skip · security run`), so approving means not having to
    tick anything.
  - **🐢 Approve the plan, run the whole workflow** — the escape hatch to the full track.
  - **☑️ Approve the plan, adjust the steps** — only this one opens the checkbox list below.
  - Objections to the plan itself go through "Other".
- **The checkbox list** (only when the user picked "adjust the steps"): a second
  `AskUserQuestion` with `multiSelect: true`, one option per optional step — E2E · code review ·
  documentation · security. **What the user checks runs, what stays unchecked is dropped.** Put
  your recommendation in each label (`E2E — proposed: skip`) and the reason in the
  `description`. The tool **cannot pre-tick boxes**, which is exactly why the proposal is the
  one-click option above and the list is only the detour — do not open it by default.
- If the user wants changes, adjust the plan; on a substantial change run the review **again**
  (a new agent, not a continuation of the old one) — and propose the composition again, because
  a bigger plan may deserve more steps.

### 4. Implementation
- Implement the minimal change that solves the task, following the approved plan. No
  unrequested refactoring and no speculative abstractions.
- For a UI change, verify it in the browser (dev server + a manual pass).
- **Then check the agreed composition against the real diff.** It was proposed over the plan,
  not over the code. If the diff came out substantially bigger than the plan assumed, or it
  touches one of the disqualifiers, **put the dropped step back** and say so in one line.
  Putting a step back needs no approval — only dropping one does.

### 5. E2E tests
- **Skip the whole step if:**
  - the composition agreed at the gate dropped it, **or**
  - the project has no E2E setup (no e2e test directory, no runner config such as
    `playwright.config.*` / `cypress.config.*`, no e2e script in the project's manifest), **or**
  - this is a trivial fix (typo, one-line change, copy change, minor style fix, documentation).
- Otherwise: if the change **can be tested through the UI**, write or update a test covering
  the golden path, in the project's existing e2e location and style.
- Run the project's own e2e command and fix until it passes.
- If the change **cannot reasonably be tested through the UI** (pure tooling, infra,
  documentation), ask the user whether to skip the step.

### 6. Lint & format — isolated subagent
- Launch `feature:linter` (`baseBranch`, `branch`). It formats and lints **only the files in
  the diff**, fixes the mechanical parts and returns a short report — hundreds of lines of tool
  output stay with it.
- Do not send it the task. It does not need one for mechanical cleanup and has nothing to be
  swayed by.
- Whatever it returns under **Left for the author** you fix yourself — those are exactly the
  errors where knowing the intent matters. Then run the linter again, or verify the project's
  lint and typecheck commands yourself.
- **Skip** the step if the project has no formatter, no linter and no typecheck.

### 7. Code review — isolated subagent
**Skip** the step if the composition agreed at the gate dropped it — then step 8 has nothing to
triage either. Otherwise only run the reviewer on cleaned-up code, so the findings are not about
formatting.

Launch `feature:reviewer` (correctness + simplify lens). The prompt contains **only** this:
- `baseBranch` and `branch`
- the **task** confirmed in step 1 and the **approved plan** from step 3
- the instruction that it pulls its own diff: `git diff <baseBranch>...HEAD`

What does **not** belong in the prompt: what you tried and discarded, why you did something
this way, what the user already approved, or your summary of the implementation. Knowing that,
it would only confirm you.

**Do not handle security here** — that comes in step 10, so it sees the documentation too.

### 8. Fixing the findings (main context)
- **Triage** the findings: what you will fix, what is a false alarm (say why), what is out of
  scope (belongs in a ticket, not in this branch).
- Fix `blocker` and `major`. `minor` at your discretion.
- After the fixes, run the e2e command again (if step 5 was not skipped). Verify lint and
  typecheck yourself; if a lot piled up, rerun `feature:linter` instead.
- If the reviewer returned `CHANGES` and you disagree with a substantial part of it, do not
  argue with it in another round — take it to step 11 as a question for the user.

### 9. Documentation — isolated subagent
- Launch `feature:doc-writer` (`baseBranch`, `branch`, task). It sees the finished code, not
  the road to it.
- Runs **after the fixes**, so it does not document a state that is still going to change.
- **Skip it** if the composition agreed at the gate dropped it, or for a trivial change (typo,
  copy, style, purely internal refactoring with no behavior change) — just tell the user why.
- The doc-writer decides for itself about the wiki (`/feature:wiki`), the CHANGELOG and
  `docs/**`. Show its report to the user in step 11 — do not rewrite it afterwards.

### 10. Security — isolated subagent, dead last
Here, because now the diff is **complete including documentation** — and docs are a full
security surface: examples with a token, ENV values, internal URLs, an instruction that has the
reader disable a check or commit their `.env`.

- Launch `feature:security-reviewer` — pass **only** `baseBranch` and `branch`. Not the task:
  this is a solo check that should not be reasoning about what the feature was meant to do, and
  it pulls its own diff, so it sees the code after the fixes as well as what the doc-writer wrote.
- **Skip it** only when the composition agreed at the gate dropped it, or when **neither the
  code nor the documentation** touches a security surface — just tell the user why. The
  disqualifier list guards both: a diff that reaches a security surface gets this step back
  even if the gate dropped it.
- Fix the findings in the main context, with the same triage as step 8: `critical` and `high`
  always, `medium` and `low` at your discretion.
- If a fix touched documentation, rerun **`feature:doc-writer`** rather than hand-patching —
  docs are its job.
- If you reached into the code substantially over the security findings, run
  `feature:security-reviewer` **once more** with a clean context. What gets judged is the
  resulting diff, not the one it first received.

### 11. Consultation
- Summarize for the user:
  - what was implemented (briefly, no file listing)
  - new/updated tests
  - review and security results: both verdicts + which findings you fixed and which not (and why)
  - **which steps the composition dropped** and why, one line each — plus any you put back after
    seeing the diff
  - what the doc-writer wrote
  - what you did not do and why (if it is worth mentioning)
- **Wait** for feedback. If the user has comments, fix them and go back to step 6 (cleanup) and
  through the checking steps of the agreed composition again, security included — always run the
  reviewers **again with a clean context**, never as a continuation of the previous agent. If the
  fixes grew the change beyond what the gate assumed, put the dropped steps back (step 4 rule).

### 12. Commit & PR
- **Do not commit yourself.** Remind the user of the `/feature:commit` command.
- After the commit, ask whether to push the branch. If yes:
  - `git push -u origin <branch>`
  - Derive the host from `git remote get-url origin` and generate the URL for opening a PR
    against `<baseBranch>` (Bitbucket Server, GitHub, GitLab — depending on the URL). **Only
    show** that URL to the user — they create the PR themselves.
  - **Do not use `gh` or any other CLI to create PRs.** The PR is always created by the user
    through the generated link.

## Rules

- **Never** commit, push or create a PR without the user's explicit approval.
- **Never** `git add -A` or `.` — always specific files.
- **Never** `--no-verify`, `--amend`, `reset --hard`, force push.
- Always branch from a fresh `baseBranch`, not from another feature branch.
- If an E2E test fails repeatedly for a reason outside the task (a pre-existing bug), stop and ask.
- **Talk to the user in the language they write in.** These instructions are in English; the
  conversation does not have to be. Report where you are in the process briefly in your reply —
  no state file gets written anywhere.
- A step is only ever dropped by a composition **agreed at the gate**, never silently in the
  moment — and never one on the disqualifier list.
- Always launch the checking agents (linter, reviewers, doc-writer) **as a new subagent** with a
  clean context. Never send them the course of development and never let them continue an
  already running conversation — context isolation is the entire reason they are subagents.
