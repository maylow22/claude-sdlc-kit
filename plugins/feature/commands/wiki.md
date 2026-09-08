---
description: Generates or updates the project's technical wiki in docs/wiki/ following the LLM-wiki pattern — discovers the stack itself, assumes nothing
argument-hint: "[--scope=full | --scope=incremental]"
---

Maintain the project's technical wiki in `docs/wiki/`. The goal: a future AI session (or a
human) gets oriented in the code without walking the file tree — and the cross-references are
already made, not looked up again on every question.

This command is **language- and stack-neutral**. Assume nothing about the technology, the
directory layout or the domain: find all of it in the repo (phase A) and act accordingly. If
you cannot find something, **do not create** that part of the wiki — an empty page is worse
than no page.

## Three layers (the LLM-wiki pattern)

| Layer | What it is | Who owns it |
|---|---|---|
| **raw** | the repo's code, migrations, configuration, ADRs, issue trackers | humans; the wiki **never** writes into them |
| **wiki** | `docs/wiki/**` | this command — it rewrites it and keeps it consistent |
| **schema** | `CLAUDE.md`, `AGENTS.md`, `README.md`, project conventions | humans; the wiki obeys them |

From which follows the one hard rule: **the wiki is a compilation, not the truth.** It must
contain nothing that is not in the code or in the schema. No guesses, no "probably", no best
practices nobody in the repo follows.

## Arguments

- `--scope=full` (the default, and also when `docs/wiki/` does not exist yet) — full regeneration.
- `--scope=incremental` — only what changed since the last run. The range comes from the
  `Source commit` of the last entry in `docs/wiki/log.md`:
  `git diff --name-only <that commit>..HEAD`. If the log does not exist or the commit is no
  longer in history, say so and degrade to `full`.

## Phase A — Schema and reconnaissance (sequential, fast)

1. Read what the project says about itself: `README.md`, `CLAUDE.md`, `AGENTS.md`,
   `CONTRIBUTING.md`, `docs/**` (existing documentation is schema, not competition).
2. Determine the stack from the manifests that are **actually** in the repo — e.g.
   `package.json`, `pyproject.toml`/`requirements.txt`, `go.mod`, `Cargo.toml`,
   `pom.xml`/`build.gradle*`, `composer.json`, `Gemfile`, `*.csproj`, `mix.exs`, `Makefile`,
   `Dockerfile`, `docker-compose.*`, CI configuration. From them read off: languages, build and
   run commands, tests, linter, deploy units.
3. Map the shape of the repo: `git ls-files | head -300`, file counts by extension, top-level
   directories. A monorepo (workspaces, `packages/*`, `apps/*`) shows up here — then do the wiki
   **per package**, not as one lump.
4. If `docs/wiki/log.md` exists, read the last entry (time, commit, what was written).
5. Wiki language: whatever the project's existing documentation is written in; if there is
   none, **English**. **Do not translate domain terms** — leave them in the original language
   and explain them in the glossary.
6. **Decide the set of pages** based on what you found (see phase D) and write it down. No page
   should exist for a topic the project does not have.

If the repo contains no source code at all (empty repo, configuration only), stop with one
sentence saying why — there is nothing for a wiki to be made of.

## Phase B — Discovery (parallel subagents in ONE message)

Launch **3–5 `Explore` subagents in parallel**. Each gets one lens, returns a structured
markdown report of up to ~500 words and **cites `path/to/file:line`**. The reports are not the
wiki — they are input for phase D.

The lenses (adjust to what phase A found; for a monorepo add an agent per package):

1. **Architecture and boundaries** — entry points, deploy units, process boundaries, data flow
   between them, configuration and ENV, external services and what happens when they go down.
2. **Domain model and contracts** — the main types/entities and their relationships, DB schemas
   and migrations, API contracts (routes, RPC, events), validation, serialization.
3. **Recurring patterns and conventions** — how this repo does the things it does constantly
   (data access, errors, logging, authorization, state, i18n). For each, 1–2 examples of up to
   6 lines with a citation. Call out especially where the code departs from the convention.
4. **Tests, build, CI** — how it is run, tested and deployed; what is covered and what is not.
5. **Traps** — dead code, convention workarounds, TODO/FIXME nests, generated code, things that
   look like bugs in the code but are intentional (and the reverse).

Write each agent's brief **with concrete paths from phase A**, not in general terms. Forbid
them to fill in gaps: what they cannot find in the code, they must not report.

## Phase C — Glossary (sequential)

Pick the domain terms out of the phase B output and out of names in the code (types, tables,
routes, state values). Term → one-sentence explanation → 1–2 places in the code. Take only
words that are **not understandable from general knowledge** of the field: domain jargon,
abbreviations, internal concepts, names of workflow states. General programming terms do not
belong in the glossary.

## Phase D — Synthesis (write in this order)

The order is not arbitrary — later pages link to earlier ones, and `index.md` comes last.

1. `architecture.md` — boundaries, entry points, data flow, deploy units, build and run commands.
   Describe the data flow with a single ASCII diagram or a bulleted flow, not a paragraph of prose.
2. `concepts/<pattern>.md` — one page per pattern from lens 3. Always: what it is for, how the
   repo does it, an example of up to 6 lines with a citation, where the deviations are.
3. `entities/<name>.md` — one page per thing that is a node in the graph: a key module, a
   dispatcher, a domain entity, a table, a public API. Not per file in the repo.
4. `domain-model.md` — entities and their relationships from lens 2 (only if the project has a
   domain model).
5. `testing.md` — how it is tested and run; what is covered and what is not (from lens 4).
6. `glossary.md` — the table from phase C.
7. `gotchas.md` — from lens 5 plus the traps in the schema, each as a full sentence with a citation.
8. `index.md` — **last.** Two sentences of introduction, then a catalog of every page with a
   one-sentence annotation. This file is how someone who has never seen the wiki finds their way.
9. `log.md` — **append-only**, add an entry:

   ```
   ## [YYYY-MM-DD HH:MM] full | incremental

   - Written: <N> files — <list>
   - Source commit: <git rev-parse --short HEAD><if `git status --porcelain` is not
     empty, append " + uncommitted changes"; from the workflow it always runs that way,
     the wiki describes the tree, not the commit>
   - Notes: <what is new since the last run; on the first run "initial generation">
   ```

Treat the page set as a recommendation, not an order: **a page with no content does not get
created**, and conversely, when the project has something notable outside this list, give it a
page and mention it in `index.md`.

With `--scope=incremental`, rewrite only the pages the changed files touch, plus always
`index.md` (annotations) and `log.md`. Leave the untouched pages alone — even if you would
write them differently.

## Phase E — Lint

Go over what you wrote and verify:

- every relative link points at a file that exists in `docs/wiki/`,
- every page is linked from `index.md` (no orphans),
- no two pages claim different things about the same subject,
- every verifiable claim has a `path:line` citation, and that path exists,
- the code examples match what is in the repo today (with `incremental`, especially the
  untouched ones).

**Do not silence findings by rewriting** — append them to the end of the last entry in `log.md`
as `### Lint` with a list. Fix broken links, report contradictions.

## Phase F — Report to the user (max 6 lines)

- scope (`full` / `incremental`) and why, if it degraded
- how many pages written, how many untouched
- how many terms in the glossary
- lint: broken links, orphans, contradictions (ideally zeroes)
- one recommendation for what is next (typically when to run it again)

## Content rules

- The wiki must not claim anything that is not in the code or the schema. **Do not fill in guesses.**
- Every page starts with a `#` heading matching its purpose.
- Cross-link generously with relative links — the finished connections are the entire point of
  a wiki over looking them up again on every question.
- Cite code as `path/to/file:line`. Examples up to 6 lines, never whole files.
- **Never edit source code.** The wiki is the output, the code is the input.
- Files in `docs/wiki/` that this command cannot regenerate (hand-written notes, ADRs) are to be
  **left alone** — rewrite only what you write yourself.
- No emoji, no mentions of AI/Claude, no `Co-Authored-By` in the wiki content.
- Do not commit. Commits are the human's business (`/feature:commit`).
