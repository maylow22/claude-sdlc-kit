---
name: feature-plan-review
description: Adversarial review of an implementation plan against the real code — before any of it gets written. Use when the user invokes /feature-plan-review or /feature:plan-review.
argument-hint: "[path to the plan | empty = the plan from this session]"
---

Have an implementation plan adversarially picked apart **before** any code is written from it.
You do not review the plan yourself — that is what the isolated `feature:plan-reviewer` agent
with a clean context is for, verifying it against the real code rather than against your
argumentation. In Cursor that subagent is `plan-reviewer` and there is no `Workflow` tool,
so use the single-agent fallback in step 2.

## Which plan

- The argument is a file path (typically `.claude/plans/*.md`) → that plan gets reviewed.
- No argument → the plan from this session: the plan-mode output, or the approach we just
  agreed on. If there is no such plan, **ask** — do not invent one.

## Steps

1. **Run the review through the `Workflow` tool** — the script is `feature:plan-review`, which
   ships with this plugin (`workflows/plan-review.js`). These instructions are the explicit opt-in
   that tool asks for, so do not ask the user for it again, and do not review the plan yourself:

   ```
   Workflow({ name: 'feature:plan-review', args: { brief } })
   ```

   `brief` is the reviewer's whole prompt: the **task**, the **plan** (full text or its path) and
   `baseBranch`. Nothing else — not a word about why you settled on this approach, what you
   discarded or what the user already liked. The script fans `feature:plan-reviewer` out over
   three lenses (step order · reuse · edge cases) and then has an independent agent try to refute
   every **Blocking** finding, so what comes back is six agents' worth of work already filtered.
2. **A short, local plan does not need any of this**: a handful of files, no new module, no new
   dependency → launch a single `feature:plan-reviewer` through `Agent` and carry on with step 3.
   The same goes if the workflow is unavailable in this session — then launch the three lenses
   through `Agent` in a single message and merge the reports yourself, without the refutation round.
3. **Merge what comes back**: throw out the refuted findings, fold together what several lenses
   found as one, and order by severity. Then list them for the user: **Blocking** first, each with
   where it is and what the fix is.
4. Fold the **Blocking** findings into the plan. **Should-fix** at your discretion — write down
   what you did not fold in, with the reason. If the plan lives in a file, edit that file.
5. Show what changed in the plan (briefly, not a full diff), and **only then** hand this plan
   to the user for approval.

If the review finds nothing, that is a one-line result — do not inflate it.
