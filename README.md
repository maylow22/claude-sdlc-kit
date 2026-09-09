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
| [claude-monitor](plugins/claude-monitor) | Live dashboard of every session on the machine — plan utilization, status, tokens, context occupancy, subagent tree. Starts itself at session start, serves on `http://127.0.0.1:8787/`. |
| [feature](plugins/feature) | `/feature:start` — the whole run of a feature: task → branch → plan → implementation → E2E → lint → review → docs → security → commit & PR. Plus standalone `/feature:plan-review`, `/feature:commit`, `/feature:wiki`. |

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
