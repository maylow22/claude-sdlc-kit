# claude-sdlc-kit

A marketplace of personal plugins for [Claude Code](https://claude.com/claude-code) —
a live dashboard of running sessions, and a workflow that takes a feature from the task to
the PR. The plugins install and update through `claude plugin`.

## Who it is for

For a developer who works with Claude Code daily and wants two things:

- **to see what is going on** — how many sessions are running, how many tokens they burned,
  where they are in the context window and which subagents they spawned;
- **to have a procedure for a feature, not improvisation** — the plan gets reviewed against
  the code before anything is written, and the code goes through lint, review, documentation
  and a security review in isolated contexts.

Assumes macOS/Linux, `python3` (stdlib, no dependencies) and git. The workflow itself is
stack-neutral: it discovers the base branch, the test/lint/typecheck commands and the issue
tracker from the repo rather than assuming them.

## Installation

```bash
claude plugin marketplace add maylow22/claude-kit    # or locally: ~/Workspace/claude-kit
claude plugin install claude-monitor@claude-kit
claude plugin install feature@claude-kit
```

Restart Claude Code (or `/reload-plugins`), then `/claude-monitor:start`, `/feature:start`.

## Plugins

| Plugin | What it does |
|---|---|
| [claude-monitor](plugins/claude-monitor) | Live dashboard of every session on the machine — plan utilization, status, tokens, context occupancy, subagent tree. A second view is the backlog board of the projects the sessions sit in, with `copy` on the open ticket for the `/feature:start <id>` that takes it up. Starts itself at session start, serves on `http://127.0.0.1:8787/`. Safari's **Add to Dock** turns it into a standalone app, **Claudemon**, with its own icon. |
| [feature](plugins/feature) | `/feature:start` — the whole run of a feature: task → branch → plan → implementation → E2E → lint → review → docs → security → commit & PR. Which of the checking steps run is proposed per change and approved at the plan gate (`--fast`/`--full`); `--yolo` takes the workflow's own proposal at every approval gate instead of asking, up to the consultation — except dropping security, which still needs the user. Plus standalone `/feature:plan-review`, `/feature:commit`, `/feature:wiki`, and an opt-in backlog (`/feature:backlog-init` sets it up, then `/feature:backlog-add`, `/feature:backlog-list`, `/feature:backlog-groom`) in a versioned `BACKLOG.md` for projects without Jira — once it is set up, findings outside the task get offered for filing — `/feature:start BL-7` picks a ticket up and moves it to `BACKLOG.done.md` once its `Done when` is met. |

## The feature workflow at a glance

One `/feature:start` run, step by step — where each step runs, why there, and which of them
fan out into parallel lenses instead of a single agent. The steps are sequential; the
parallelism is inside a step, never across two.

| Step | Runs in | Why there | Fan-out | Always? |
|---|---|---|---|---|
| 1 · Task | main context | one thread from the task to the code; the user confirms the agent's summary | — | always · **gate** |
| 2 · Branch | main context | needs the base branch and the naming convention it just discovered | — | always |
| 3 · Plan | main context | the plan is the thread, not a deliverable to hand off | — | always |
| 3 · Plan review | `feature:plan-reviewer` | reviewing your own plan is not a review; a clean context has nothing to defend | **`feature:plan-review` workflow** — 3 lenses (step order · reuse · edge cases), every Blocking finding then refuted by an independent verifier | always |
| 3 · Gate | main context | the user approves the plan and which of the optional steps run, in one click | — | always · **gate** |
| 4 · Code | main context | the code comes out of the plan the same agent wrote | — | always |
| 5 · E2E | `feature:e2e-tester` | the author tests the path they built; a stranger tests the path the user walks — and the runner output stays out of the main window. Writes tests, never source | — | optional |
| 6 · Lint | `feature:linter` | formatter/lint/typecheck output is the longest and least interesting thing in the run. Gets no task at all — you can lint without knowing the intent | — | always |
| 7 · Review | `feature:reviewer` | does not know how the code came about, so nothing can talk it out of a finding; no `Edit` — it hands findings back | **`feature:code-review` workflow** — 3 lenses (bugs · simplify · scope vs. plan), every blocker and major refuted by an independent verifier | optional |
| 8 · Fixes | main context | only the agent that knows the code fixes it; what is out of scope goes to the backlog, not into the conversation | — | always |
| 9 · Docs | `feature:doc-writer` | writing docs is its own long job; may write, may not commit. Calls `/feature:wiki` so the wiki lands in its window | — | optional |
| 10 · Security | `feature:security-reviewer` | **dead last, after the docs** — only then is the diff complete, and docs are a security surface too. Gets the branches only, never the task: nothing may convince it a hole is the design | **`feature:security-review` workflow** — 3 lenses (input & access · exposure · docs), every critical and high gets a path to exploitation built | optional · not self-approvable |
| 11 · Consultation | main context | the findings, what was left undone and what went to the backlog, in one place | — | always · **gate** |
| 12 · Commit & PR | main context | `/feature:commit`; the PR only as a link, `gh` is not used | — | always · **gate** |

**Read it as:** the main context holds the thread — task, plan, code, fixes, decisions. Everything
that would either flood it with output (E2E, lint) or lose its independence by knowing the thread
(the three reviews, the docs) goes into a subagent. The checking agents get **at most the task, the
branch and the diff** — never how development went.

**Optional** steps are E2E, code review, documentation and security; the workflow proposes the
composition over the reviewed plan at the step-3 gate and re-checks it against the finished diff.
`--fast`/`--full` pre-set the proposal, `--yolo` answers the gates with it — except security, which
only the user can drop, and except a disqualifier (auth, secrets, untrusted input, endpoints,
dependencies, migrations, payments, CI/CD, `.claude/**`), where the workflow asks regardless.

The details (what the dashboard reads, how the workflow is split between the main context and
the subagents) are in each plugin's README.

## Language

The sources — commands, agents, code — are English. The conversation is not: the agents talk
to you in the language you write in, and `/feature:commit` writes the commit message in the
language the repo's history uses.

## Development

`claude plugin validate <path>` checks the manifest, `claude plugin details <name>` shows the
component inventory and token cost, `claude plugin tag` cuts a release tag `{name}--v{version}`.

For quick iteration without publishing, symlink the plugin into `~/.claude/skills/` — it
auto-loads as `<name>@skills-dir`.

### Versioning

Every PR that touches `plugins/<name>/` raises that plugin's `version` in
`plugins/<name>/.claude-plugin/plugin.json`. An install is cached per version —
`~/.claude/plugins/cache/<marketplace>/<plugin>/<version>` — so a change merged without a new
one never reaches anybody who already has the plugin: the marketplace metadata refreshes, the
files do not. `.github/workflows/plugin-version.yml` is the gate, and the same check runs
locally:

```bash
.github/scripts/check_plugin_versions.py main
```

After the merge an existing install picks the new version up with
`claude plugin update <plugin>@claude-kit`, applied on the next restart.
