# Test-driven build — red, green, refactor

For building behavior I want pinned down by a test *before* it exists — new logic, a feature with real branching, or a bug I want to never see again. The point is fewer bugs by construction: the test states the intended behavior, then the code earns its way to green. The full discipline lives in the [`tdd` skill](../skills/tdd/SKILL.md); this is the copy-paste runbook.

## When to use / when not

- **Use it** for anything with real logic — calculations, validation, state changes, edge cases — and *always* for bug fixes (reproduce as a failing test first).
- **Skip the ceremony** for trivial behavior-free code (a getter, a constant), throwaway spikes (explore, then delete and TDD the real thing), and pure refactors already covered by existing tests (run those, don't add new ones).

If I can't state the next behavior as a single sentence ("returns an empty list when there are no orders"), I'm not ready to write the test yet — I scope the slice first.

## Opening prompt (Plan Mode)

```
Plan Mode. We're building this test-first (TDD). Feature/change:
<what it should do, from the user's point of view>.
In scope: <the slice I'm building now>.
Out of scope: <what I'm explicitly NOT doing yet>.

Before any code: map how this fits the existing codebase — real routes,
models, and patterns already in use (use Boost if available). Then give me
the list of behaviors to cover as a TEST LIST — one line per observable
behavior, including edge cases and error paths — ordered from simplest to
hardest. Plus the files you'd add/change and any open questions.
Don't write code or tests yet.
```

The test list *is* the plan: each line becomes one red→green→refactor lap. Ordering simplest-first keeps the early laps tight and lets the design emerge.

## Approve, then build the loop

```
Approved. Build it test-first, one behavior at a time:
1. Write ONE failing test for the next behavior on the list.
2. Run it and show me it fails for the RIGHT reason (the assertion or the
   missing code — not a typo or import error).
3. Write the simplest code that makes it pass. Run it — green.
4. Run the whole suite. Refactor while green if needed.
5. Next behavior. Repeat down the list.
Show me each red and each green. Don't write code ahead of the tests.
Stop before anything outside the agreed scope.
```

Insisting on seeing each test go red first is the whole game — a test that was never red can't be trusted.

## Bug-fix variant

```
Reproduce this bug as a FAILING test first: write a test asserting the
CORRECT behavior, run it, show me it fails (reproducing the bug). Only
then fix the code until that test goes green. Leave the test in as a
regression guard.
```

## Review follow-ups (Phase 3)

TDD reduces bugs; it doesn't replace the review pass.

```
Review the most recent uncommitted work:
- code review: structure, naming, error handling, and TEST QUALITY —
  do the tests assert behavior (not implementation), cover the edges,
  and would they actually fail if the behavior regressed?
- security: input validation, authz, anything user-controlled.
```

Then verify it actually runs — open the app and use the thing, don't just trust green tests.

## Common failure modes

- **Tests written after the code.** Quietly turns TDD into "tests that describe whatever the code happens to do." If code came first, the test no longer proves intent. Watch for it.
- **Never seeing red.** A test added straight to green may assert nothing. Always demand the failing run first.
- **Testing implementation, not behavior.** Brittle tests that break on every refactor — defeating the point. Assert outcomes and effects, not which method was called.
- **Steps too big.** A test that needs a whole subsystem to pass is a big-bang in disguise. Shrink the slice to one behavior.
- **Skipping the full-suite run.** New test green while three others silently broke. Run everything before "done."
