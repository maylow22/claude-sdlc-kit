---
description: Runs the workflow for a new feature — branch, plan, implementation and E2E in the main context; plan review, lint, code review, security and docs in isolated subagents
argument-hint: <issue key | issue URL | task description>
---

Workflow for developing a new feature. The argument is required — either an **issue key**
(e.g. `IF-9`), an **issue URL** (e.g. `https://<your-org>.atlassian.net/browse/IF-9`) or a
**free-form description** of the task.

If the argument is missing, **ask** the user what to implement — do not continue without it.

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

### 3. The plan (and its review, before the user sees it)
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
- **Wait for explicit approval.** Do not proceed to implementation without it.
- If the user wants changes, adjust the plan; on a substantial change run the review **again**
  (a new agent, not a continuation of the old one).

### 4. Implementation
- Implement the minimal change that solves the task, following the approved plan. No
  unrequested refactoring and no speculative abstractions.
- For a UI change, verify it in the browser (dev server + a manual pass).

### 5. E2E tests
- **Skip the whole step if:**
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
Only run the reviewer on cleaned-up code, so the findings are not about formatting.

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
- **Skip it** for a trivial change (typo, copy, style, purely internal refactoring with no
  behavior change) — just tell the user why.
- The doc-writer decides for itself about the wiki (`/feature:wiki`), the CHANGELOG and
  `docs/**`. Show its report to the user in step 11 — do not rewrite it afterwards.

### 10. Security — isolated subagent, dead last
Here, because now the diff is **complete including documentation** — and docs are a full
security surface: examples with a token, ENV values, internal URLs, an instruction that has the
reader disable a check or commit their `.env`.

- Launch `feature:security-reviewer` — pass **only** `baseBranch` and `branch`. Not the task:
  this is a solo check that should not be reasoning about what the feature was meant to do, and
  it pulls its own diff, so it sees the code after the fixes as well as what the doc-writer wrote.
- **Skip it** only when **neither the code nor the documentation** touches a security surface —
  just tell the user why.
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
  - what the doc-writer wrote
  - what you did not do and why (if it is worth mentioning)
- **Wait** for feedback. If the user has comments, fix them and go back to step 6 (cleanup) and
  through the checking steps again, security included — always run the reviewers **again with a
  clean context**, never as a continuation of the previous agent.

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
- Always launch the checking agents (linter, reviewers, doc-writer) **as a new subagent** with a
  clean context. Never send them the course of development and never let them continue an
  already running conversation — context isolation is the entire reason they are subagents.
