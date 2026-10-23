# flow-status

A [mod](https://code.claude.com/docs/en/plugins/mods/overview): one status line under the
prompt with the topic the session is working on and the step of the feature flow it stands at.

```
◆ Levé menu konverzace  │  ▸ implementace 4/12
```

## Where the line comes from

- **The topic** is a few words the model names through the tool `mcp__flow-status__update`.
  Until it does, a feature branch stands in for it (`git branch --show-current`, refreshed
  after every turn); `main`, `master` and `develop` say nothing about the topic and are left out.
- **The step** is one of the steps of `/feature:start` in its order — `analyza`, `plan`,
  `plan-review`, `implementace`, `e2e`, `lint`, `code-review`, `opravy`, `dokumentace`,
  `security`, `konzultace`, `commit` — shown as `n/12`, and `hotovo` once the task is done.
  - The steps the `feature` plugin runs in subagents and skills (plan review, E2E, lint, code
    review, docs, security) are read off the `Agent` and `Skill` calls of the main loop, so the
    model does not have to report them. A `Skill` call of `feature:start` starts a new topic.
  - The steps done in the main context (analysis, plan, implementation, fixes, consultation,
    commit) the model reports through the tool.

The tool is allowed without a permission prompt: reporting a step is not worth one.

## Why the instructions live in the tool's description

The model learns when to call the tool from its description alone, and the tool is listed up
front (`isDeferred: false`) rather than behind ToolSearch. A `prompt.compose` section would be
the natural place, but a security plugin may skip that hook — the tool list is always sent.

## Limits

- `/feature:start` typed as a slash command expands in place and makes no `Skill` call; the
  model reports `analyza` itself then.
- How the line is drawn (dimmed, beside the engine's own notices) is up to Claude Code.
- The state is the module's own: a reload of the module (an edit while it is loaded from a
  folder) starts the line over.

## Development

```bash
claude plugin validate plugins/flow-status
cd plugins/flow-status && claude plugin test .
```
