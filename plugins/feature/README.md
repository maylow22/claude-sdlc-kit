# feature

A workflow for taking one feature from the task to the PR. Three commands, one namespace.
No state file and no tracking of its own — you see the progress in the terminal and the
subagents in [claude-monitor](../claude-monitor).

| Command | What it does |
|---|---|
| `/feature:start <issue key \| URL \| description> [--fast\|--full]` | the whole run: task → branch → plan → implementation → E2E → lint → review → fixes → docs → consultation → commit & PR. Which of the checking steps actually run is decided at the plan gate |
| `/feature:plan-review [path to plan]` | adversarial review of the plan against the real code, before anything gets written |
| `/feature:commit` | git commit, no emoji and no Co-Authored-By, in the language of the repo's history |
| `/feature:wiki [--scope=full\|incremental]` | the project wiki in `docs/wiki/` following the LLM-wiki pattern — discovers the stack itself |

`/feature:start` calls `/feature:commit` and `/feature:wiki` itself (the wiki through the
doc-writer); you run them standalone when the workflow is not running.

## How the context is split

The **main agent** holds the core of the workflow, because it needs one thread from the task
to the code:

| Step | Where it runs |
|---|---|
| 1 Task · 2 Branch | main context |
| 3 Plan — drafting and folding in findings | main context |
| 3 Plan — review | `feature:plan-reviewer` (clean context) |
| 4 Implementation · 5 E2E | main context |
| 6 Lint & format | `feature:linter` (clean context) |
| 7 Code review | `feature:reviewer` (clean context) |
| 8 Fixing findings | main context |
| 9 Documentation | `feature:doc-writer` (clean context) |
| 10 Security | `feature:security-reviewer` (clean context, sees the docs too) |
| 11 Consultation · 12 Commit & PR | main context |

Mechanical cleanup is a subagent for the same reason, even though it judges nothing: the output
of the formatter, the linter and the typechecker is the longest and least interesting thing in
the entire workflow. Which is why it does not get the task at all — you can lint without knowing
the intent.

Security is deliberately the **last step**, not parallel to the code review: only after the
documentation is the diff complete, and docs are a full security surface — an example with a
token, an internal URL, or an instruction that has the reader turn verification off is a finding
just as much as a hole in the code.

The checking agents get **at most the task, the branch and the diff** — never the course of
development. They do not know what you weighed, what you discarded or what the user already
approved, so they have nothing to latch onto and their findings carry weight. `feature:linter`
and `feature:security-reviewer` do not even get the task: cleanup does not need it, and a
security review must have nothing available to talk it into believing a hole is the design. The
reviewers also lack `Edit`: they hand findings back, and the main agent, which knows the code,
fixes them. The doc-writer may write (documentation is work, not a fix) but does not commit.

On a second round (the user has comments) the agents are launched **from scratch again**, not as
a continuation — otherwise they would pull the context back in.

A command carries the **recipe**, an agent is a **context boundary** — they are not competing
options. That is why `/feature:wiki` is a command: a person runs it directly (and it runs in
their context), while from the workflow `feature:doc-writer` calls it, so the work lands in its
window instead. Which is also why the doc-writer has `Agent` — so phase B can spawn its discovery
subagents.

## The agents

| Agent | Context | Tools | Output |
|---|---|---|---|
| `feature:plan-reviewer` | task, plan | read-only | verdict + Blocking/Should-fix findings against the real code |
| `feature:linter` | branch + diff only | + Edit | what the formatter/lint/typecheck fixed and what is left for the author |
| `feature:reviewer` | task, plan, diff | read-only + Skill | PASS/CHANGES verdict + findings by severity |
| `feature:security-reviewer` | branch + diff only (code **and** docs) | read-only + Skill | verdict + findings with a path to exploitation |
| `feature:doc-writer` | task, diff | + Write/Edit | what it wrote, what it did not and why, wiki status |

## The composition of steps

A typo and a new endpoint do not deserve the same workflow, so the set of steps is not fixed.
Together with the reviewed plan, `/feature:start` proposes at the **gate in step 3** which of
the checking steps will run — a table of step · run/skip · reason — and the user approves the
plan and the composition in **one click on the proposal**. The full track is the second option,
and only the third one ("adjust the steps") opens a checkbox list of the four optional steps,
where what is ticked runs. The dialog cannot come pre-ticked, so the pre-filled answer is the
first option, not a checked box.

Up for the composition are **E2E, code review, documentation and security**. The task, the
branch, the plan **including its review**, the implementation, lint, the consultation and the
commit always run. `--fast` and `--full` only pre-set the proposal; the confirmation still
happens at the gate.

A step is never dropped when the change touches authentication, authorization or permissions,
secrets, credentials or crypto, untrusted input, file upload, a new or changed endpoint,
dependencies, migrations, payments, or CI/CD and release scripts — with `--fast` the workflow
names the disqualifier and asks instead of obeying. And because the composition is proposed over
the plan rather than the diff, it gets re-checked once the code is written: a change that came
out bigger than planned gets the dropped steps back, which needs no approval — only dropping
one does.

## The gates that wait for you

The task, the **reviewed** plan together with the composition of steps, the consultation,
commit & push. Without explicit approval the workflow does not commit, does not push and does
not create a PR (the PR is only generated as a link — `gh` is not used).

## What it discovers, and what it does not

`/feature:start` reads the project rather than assuming it: the base branch (`develop` if the
repo has one, otherwise the default branch), the e2e/lint/typecheck commands from the manifests
that are actually there, the branch naming convention from the history, and the issue detail
through an Atlassian MCP server if one is configured. Where it finds nothing, it skips the step
and says so.

`/feature:wiki` is stack-neutral the same way — it works out the language, build, tests and the
shape of the repo from the manifests and `git ls-files`, decides the page set from what the
project actually has, and does not create a page with no content. It holds the three layers of
the LLM-wiki pattern: code is the raw source (it never writes into it), `docs/wiki/**` is its
own, and `CLAUDE.md`/`AGENTS.md`/`README.md` is the schema it obeys. `index.md` is the catalog,
`log.md` an append-only history, and `--scope=incremental` rewrites only the pages touched by
the diff since the last entry in the log.
