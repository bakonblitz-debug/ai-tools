# Prompting guides

Copy-paste runbooks for the scenarios that come up most. The [main workflow](../README.md) says *what* happens in each phase; these say *how to prompt*.

Each guide follows the same shape:
1. **When to use / when not** — so I pick the right one.
2. **Opening prompt** — copy-paste ready, used in Plan Mode.
3. **Review follow-ups** — the prompts that kick off Phase 3.
4. **Common failure modes** — how it tends to go wrong.

## Index

| Scenario | Guide |
|----------|-------|
| Getting oriented on a codebase (mine or inherited) | [`project-intake.md`](project-intake.md) |
| Fixing a reproducible bug | [`bug-fix.md`](bug-fix.md) |
| Building a scoped new feature | [`new-feature.md`](new-feature.md) |
| Building behaviour test-first (red-green-refactor) | [`tdd.md`](tdd.md) |
| Behaviour-preserving cleanup of one area | [`scoped-refactor.md`](scoped-refactor.md) |
| Running review on demand | [`review-triggers.md`](review-triggers.md) |

I add a guide *after* I've done the scenario once and learned what the prompt should actually say. A template I haven't pressure-tested isn't worth keeping.
