---
name: architect
description: >
  "new project", "add a feature", "fix a bug", "refactor", "change behaviour", "build X", "plan X", "design X". Conductor for any code change, small ones included: runs brainstorming → ouroboros → writing-plans → subagent build → verification. Skips only pure reads, one-line typo edits, or "skip planning".
---

# Architect — conductor for every code change

Every artifact lives in `<repo>/.plans/<slug>/` (design.md, PLAN.md, plan.md), unless the user's
CLAUDE.md names another plans folder; never `docs/superpowers/` in a repo. This skill sequences other
skills and owns no logic of its own. It needs the **superpowers** plugin (brainstorming, writing-plans,
subagent-driven-development, test-driven-development, verification-before-completion,
finishing-a-development-branch) and dev-loop's own `ouroboros`, `handoff` and `git-conflict`.

Exempt: pure reads, one-line typo/format edits with no behaviour change, or when the user says to skip
planning. Say which step you skip and why; never skip silently.

## The pipeline (check in with the user only between phases)

1. **Ground.** Read the code and the repo's plans folder. If the change has a GitHub issue, read it
   (`gh issue view`); if it has none and the work is more than a small fix, file one at the end.
2. **Design — `superpowers:brainstorming`.** Output goes to `.plans/<slug>/design.md`. Ask the user
   only intent, product and scope questions. Engineering choices (stack, structure, patterns) are
   yours: decide and record each in the design as "Decision (<date>): … because …".
3. **Gate: the user's approval of the design.** One gate. Nothing is built before it.
4. **Prove — `dev-loop:ouroboros`.** Ingest design.md as its requirements; do not re-ask anything the
   design already answers. At least one adversarial round. Output `.plans/<slug>/PLAN.md`. A flaw that
   changes intent or scope goes back to the user; engineering flaws you fix.
5. **Plan — `superpowers:writing-plans`.** Format from that skill, saved as `.plans/<slug>/plan.md`.
   The proven PLAN.md is the input; plan.md is its step list.
6. **Build — `superpowers:subagent-driven-development`.** A stronger model interprets the plan and
   reviews; a cheaper one writes the code. Use the cheapest model whose error rate fits the role;
   rework counts against a cheaper model. Every step is test-first
   (`superpowers:test-driven-development`). Commit each step on the branch.
7. **Verify — `superpowers:verification-before-completion`.** Run the real checks and show evidence;
   a green typecheck is not a verdict. An acceptance test is written by whoever owns the rule, never by
   the worker that implements it.
8. **Finish — `superpowers:finishing-a-development-branch`.** Show the options menu. Push, merge and
   PR creation are the user's call: do them only when asked.

## Rules

- **Worktree per session.** Commits happen in this session's own worktree and branch, one per
  feature/request, never the shared checkout or another session's branch.
- **Out-of-scope finds** go to `dev-loop:handoff` as a plan, not into the diff.
- **Concurrent edits conflict** → `dev-loop:git-conflict`.
- **Tracker is GitHub issues via the `gh` CLI.** If `gh` is unavailable, write the issue text and say
  it was not filed.
- **Delegation:** don't delegate a task whose spec is longer than its implementation. A failed
  attempt returns a mechanical diagnosis, not a verdict.
- **Superpowers vs this skill.** The settled points: the user's CLAUDE.md outranks any skill;
  design/plan artifacts go to the plans folder, not the repo; one approval gate; test-first for
  non-trivial logic, trivial one-liners exempt; creating a worktree needs no asking; finishing never
  pushes unasked. If a superpowers instruction conflicts with this skill in a way not listed here,
  **stop and bring it to the user**; do not pick a side silently.
