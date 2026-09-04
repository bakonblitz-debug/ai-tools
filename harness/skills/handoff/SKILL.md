---
name: handoff
description: >
  Use this skill whenever, in the middle of analyzing or working on a task, you
  notice something out of scope that deserves its own work — a latent bug, a
  missing test or edge case, a refactor opportunity, a small adjacent feature, a
  questionable pattern, a TODO worth doing. Instead of fixing it inline (scope
  creep, an unreviewable diff) or silently dropping it, hand it off: write a
  focused plan-of-work .md and delegate it to a subagent. Trigger this even when
  the user did NOT ask for the side fix — the whole point is to catch the tangent
  yourself and keep the current task sharp. Reach for it on cues like "while I was
  in here I noticed…", "this is unrelated but…", "that's broken too", "we should
  also…", or any moment you feel the pull to fork off the main task.
---

# Handoff

## Why this exists

This playbook rests on one idea: **a coding agent does its best work when it has
one clear job and just enough context to do it.** Mid-task tangents are the enemy
of that. When you're implementing a feature and you spot an unrelated bug, you have
three options, and two of them are bad:

- **Fix it inline** → scope creep. The diff now mixes two concerns, it's harder to
  review, and "implement feature" quietly became "implement feature *and* fix this
  other thing." The user reads the diff; a mixed diff wastes their time and hides
  risk.
- **Drop it** → the observation is lost. You were the one agent in the best
  position to notice it, and now nobody acts on it.
- **Hand it off** → capture the tangent as a written plan, keep working the main
  task, and let a *separate* focused agent deal with it. This is the good option,
  and it's what this skill is for.

Handing off is the "one job per agent" principle turned into a concrete move.

## When to hand off — and when not to

**Hand off** when the issue is real but lives *outside the scope* of the task you're
on: a latent bug in code you happened to read, a missing test, an edge case nobody
handles, a refactor that would help but isn't required, a small adjacent feature, a
pattern that smells wrong.

**Don't hand off** when:
- The issue *is* part of the current task — just do it. Handoff is for tangents,
  not for the work you were asked to do.
- It's a trivial one-liner already under your cursor — fixing it in place is
  cheaper than the ceremony of a handoff. Use judgment; don't bureaucratize.
- It *blocks* the current task — then it isn't a side issue. Surface it, stop, and
  resolve the blocker with the user. Don't fork off something you're waiting on.

When unsure, lean toward handing off rather than fixing inline — protecting the
current task's focus is the higher-order goal.

## The procedure

1. **Name it, don't fork silently.** Tell the user in one sentence what you noticed
   and that you want to hand it off. They should never discover a fork after the
   fact.
2. **Write the handoff plan** to the **workspace share**, at `<root>/.plans/handoff-<slug>.md`
   — `~/www/.plans/` on the Mac, `M:\.plans\` on the PC, `/mnt/www/.plans/` from
   WSL/Hermes. `<slug>` is a short kebab-case summary (e.g.
   `handoff-null-account-export.md`). Use the template below — it *is* the plan of
   work the subagent will execute.

   **Not `~/.claude/plans/`.** That directory is machine-local, and the `SessionStart`
   digest (`harness/scripts/session-todo.sh`) runs on the Mac over ssh — so a handoff
   written there from the PC never resurfaces anywhere, which defeats the entire point
   of parking it. The share is visible from all three systems. The digest reads both
   locations and dedups by filename, so an older plan in `~/.claude/plans/` still shows
   up; new ones belong on the share.
3. **Surface it and ask.** Show the user the plan path and a one-line summary, then
   ask whether to spawn the subagent now, hand it off later, or skip. **Wait for the
   go-ahead** — do not spawn unprompted. (The user works in plan mode and reads
   diffs; they decide when a second agent starts touching code.)
4. **On approval, spawn the subagent** (the Agent tool) whose entire job is that one
   plan. Point it at the `.md` and give it only the context it needs — its value
   comes from a small, focused context, so don't dump the whole conversation into
   it.
5. **Return to the primary task.** The tangent is now someone else's job. Do not let
   it expand the scope of what you were doing.

## The handoff plan template

The `.md` is the artifact — it has to stand on its own, because the subagent reads
it cold without your conversation. Reuse this exact structure every time; it mirrors
the playbook's plan anatomy (scope boundaries, files, tests, open questions):

```markdown
# Handoff: <title>

## Context
The task I was doing when I noticed this — enough background for a cold reader.

## The issue
What's off, concretely, with `file:line` references so the subagent can find it.

## Why it's out of scope
Why I'm handing this off instead of fixing it inline — what it's tangential to.

## Scope
What the subagent should do, and explicitly what it should NOT touch. Boundaries
keep the handoff from becoming its own scope-creep.

## Suggested approach
Optional: files likely to change, patterns or utilities already in the codebase to
reuse, anything I already figured out. Don't over-prescribe — leave room for the
subagent to plan.

## Verification
How to confirm the fix works: which tests to run, what to check by running the app.

## Status
open
```

Keep the plan tight. A cold reader — human or agent — should be able to pick it up
and know exactly what to do and where the edges are.
