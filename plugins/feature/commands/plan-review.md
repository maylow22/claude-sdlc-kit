---
description: Adversarial review of an implementation plan against the real code — before any of it gets written
argument-hint: "[path to the plan | empty = the plan from this session]"
---

Have an implementation plan adversarially picked apart **before** any code is written from it.
You do not review the plan yourself — that is what the isolated `feature:plan-reviewer` agent
with a clean context is for, verifying it against the real code rather than against your
argumentation.

## Which plan

- The argument is a file path (typically `.claude/plans/*.md`) → that plan gets reviewed.
- No argument → the plan from this session: the plan-mode output, or the approach we just
  agreed on. If there is no such plan, **ask** — do not invent one.

## Steps

1. Launch the `feature:plan-reviewer` agent. Give it the **task**, the **plan** (full text or
   a file path) and `baseBranch`. Nothing else — not even why you settled on this approach.
2. For a large or risky plan, launch **2–3 agents in parallel in a single message**, each with
   a different lens: correctness and step order / reuse and simplicity / tests and edge cases.
   Then merge the findings and drop the duplicates.
3. List the findings for the user: **Blocking** first, each with where it is and what the fix is.
4. Fold the **Blocking** findings into the plan. **Should-fix** at your discretion — write down
   what you did not fold in, with the reason. If the plan lives in a file, edit that file.
5. Show what changed in the plan (briefly, not a full diff), and **only then** hand this plan
   to the user for approval.

If the review finds nothing, that is a one-line result — do not inflate it.
