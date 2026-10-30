---
name: architect
description: >
  Conductor for any code change, small ones included: new project, add a feature, fix a bug, refactor, change behaviour, "build X", "plan X", "design X". Runs brainstorming → ouroboros → writing-plans → subagent build → verification. Skips only pure reads, one-line typo edits, or "skip planning".
---

# Architect — conductor for every code change

Paths: `<workspace>` is `~/www` (Mac), `/mnt/www` (WSL2) or `M:\` (Windows). Every artifact lives in
`<workspace>/.plans/<slug>/` (design.md, PLAN.md, plan.md) — never `docs/superpowers/` in a repo.
This skill sequences other skills and owns no logic of its own. It runs in a coding-mode session
(bacon-dev enabled, opened in the project). Exempt: pure reads, one-line typo/format edits with no
behaviour change, or when he says to skip planning. Say which step you skip and why; never skip silently.

## The pipeline (check in with him only between phases)

1. **Ground.** Read the code and the project's `.plans/`. If the change has a GitHub issue, read it
   (`gh issue view`); if it has none and the work is more than a small fix, file one at the end.
2. **Design — `superpowers:brainstorming`.** Output goes to `.plans/<slug>/design.md`. Ask him only
   intent, product and scope questions. Engineering choices (stack, structure, patterns) I decide and
   record in the design as "Decision (mine, <date>)" — never ask him to adjudicate engineering.
3. **Gate: his approval of the design.** One gate. Nothing is built before it.
4. **Prove — `bacon-dev:ouroboros`.** Ingest design.md as its requirements; do not re-ask him
   anything the design already answers. At least one adversarial round. Output `.plans/<slug>/PLAN.md`.
   If ouroboros finds a flaw that changes intent or scope, bring it to him; engineering flaws I fix.
5. **Plan — `superpowers:writing-plans`.** Format from that skill, saved as `.plans/<slug>/plan.md`.
   The proven PLAN.md is the input; plan.md is its step list.
6. **Build — `superpowers:subagent-driven-development`** on his tiers: Sonnet interprets the plan
   and reviews, Haiku codes. Use the cheapest model whose error rate fits the role; rework tokens
   count against a cheaper model. **Never qwen**, never a local model. Every step is test-first per
   the TDD rule in `docs/coding-standards.md` (method: `superpowers:test-driven-development`).
   Commit each step on the branch; squash before any push. No attribution trailers in commits.
7. **Verify — `superpowers:verification-before-completion`.** Run the real checks and show evidence;
   a green typecheck is not a verdict. An acceptance test is authored by whoever owns the rule, never
   by the worker.
8. **Finish — `superpowers:finishing-a-development-branch`.** Show the options menu. **Never run
   push, merge or PR creation myself** — the public push is his.

## Rules

- **Worktree per session.** Commits happen in this session's own worktree and branch, one per
  feature/request, never the shared checkout or another session's branch (no asking).
- **Out-of-scope finds** go to `bacon-dev:handoff` as a plan in `.plans/`, not into the diff.
- **Concurrent edits conflict** → `bacon-dev:git-conflict`.
- **Tracker is GitHub issues via the `gh` CLI.** Never drive github.com in a browser, not even once.
  If `gh` is unavailable, write the issue text and say it was not filed.
- **Delegation:** don't delegate a task whose spec is longer than its implementation. A failed
  attempt returns a mechanical diagnosis, not a verdict.
- **Superpowers vs this skill.** The approved settlements: his CLAUDE.md outranks any skill;
  design/plan artifacts go to `.plans/` not the repo; one approval gate; test-first for non-trivial
  logic, trivial one-liners exempt; worktree creation needs no asking; finishing never pushes. If a
  superpowers instruction conflicts with this skill in a way not listed here, **stop and bring it to
  him** — do not pick a side silently.
