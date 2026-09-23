# claude-sdlc-kit

A Claude Code plugin marketplace. Two plugins under `plugins/` — `claude-monitor` (the live
session dashboard) and `feature` (the feature workflow). Both are `python3` stdlib and POSIX
shell: there is nothing to build and nothing to install.

## Touching a plugin means raising its version

An installed plugin is cached **per version** —
`~/.claude/plugins/cache/<marketplace>/<plugin>/<version>`. A change merged without a new
`version` in `plugins/<plugin>/.claude-plugin/plugin.json` reaches nobody who already has the
plugin: the marketplace metadata refreshes, the plugin files do not. That is not theoretical —
PR #1 merged that way, and installs stayed on the commit before it, without the `assets/` the
PR had added.

So **every PR that touches `plugins/<name>/` raises that plugin's `version`.** CI is the gate
(`.github/workflows/plugin-version.yml`); the same check runs locally before you open the PR:

```bash
.github/scripts/check_plugin_versions.py main   # compares commits — commit the bump first
```

Semver as the change deserves — a fix is a patch, a new route or view a minor. After the merge
an existing install takes it with `claude plugin update <plugin>@claude-kit`, which needs a
restart to apply.

## Language

Sources — commands, agents, code and comments — are **English**. Commit messages and PR
descriptions are **Czech**, which is what the repo's history uses. The conversation follows
whatever language the user writes in.

## Conventions

- **No dependencies.** `python3` stdlib and POSIX shell only, so a plugin runs wherever Claude
  Code runs.
- Detail belongs in the plugin's own `README.md`; the root `README.md` stays an overview.
- Work that is not being done now goes to `BACKLOG.md` (`/feature:backlog-add`), not into a
  comment in the code.
- A comment says **why**, not what — the surrounding code is written that way throughout.
