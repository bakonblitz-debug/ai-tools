---
name: handoff
description: >
  "While I was in here I noticed…", "unrelated but…", "that's broken too", "we should also…": out-of-scope bug, missing test, refactor or TODO found mid-task. Write a focused plan in .plans/ and delegate it instead of fixing inline.
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
2. **Write the handoff plan** to `<plans>/handoff-<slug>.md`. `<plans>` is the folder
   the user's CLAUDE.md names for plans (for example a folder shared between machines),
   else `.plans/` at the repo root. `<slug>` is a short kebab-case summary (e.g.
   `handoff-null-account-export.md`). Use the template below — it *is* the plan of
   work the subagent will execute.

   Prefer a folder that the next session will look at. A plan in a machine-local
   folder that no later session reads is a dropped observation with extra steps.

   **The status goes under a `## Status` heading, nothing else.** Tools that list open
   handoffs read the state from the first non-blank line after `## Status`: `open`,
   optionally followed by ` — <short status text>`, or the word done to close it. A
   status line placed anywhere else (for example straight under the title) is not
   read. Keep the heading even when you update the status later.
3. **Check that it surfaces.** If the user's setup has a command that lists open
   handoffs (a session-start digest, a todo script; their CLAUDE.md names it), run it
   and confirm the new file is listed with its `open` text. Otherwise re-read the file
   and confirm the `## Status` heading and line. Never tell the user that a later
   session will pick it up until you have seen that it will.
4. **Surface it and ask.** Show the user the plan path and a one-line summary, then
   ask whether to spawn the subagent now, hand it off later, or skip. **Wait for the
   go-ahead** — do not spawn unprompted. (The user works in plan mode and reads
   diffs; they decide when a second agent starts touching code.)
5. **On approval, spawn the subagent** (the Agent tool) whose entire job is that one
   plan. Point it at the `.md` and give it only the context it needs — its value
   comes from a small, focused context, so don't dump the whole conversation into
   it.
6. **Return to the primary task.** The tangent is now someone else's job. Do not let
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
open — <one line: where it stands, what is next>
```

The `## Status` section is required (see step 2); the other sections can be short
for a handoff that is notes rather than a coding task, but they keep their headings.

Keep the plan tight. A cold reader — human or agent — should be able to pick it up
and know exactly what to do and where the edges are.
