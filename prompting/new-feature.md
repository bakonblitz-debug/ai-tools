# New feature — scoped

For a feature I can describe in a sentence or two with a clear boundary. If I can't say what's *out* of scope, I'm not ready to prompt — I plan the scope first.

## Opening prompt (Plan Mode)

```
Plan Mode. Feature: <what it does, from the user's point of view>.
In scope: <the slice I'm building now>.
Out of scope: <what I'm explicitly NOT doing yet>.
Constraints: <stack conventions, existing patterns to follow, perf/UX limits>.

Before proposing anything, map how this fits the existing codebase —
real routes, models, and patterns already in use (use Boost if available).
Then give me: the approach, the files you'd add/change, the data/schema
changes if any, the test plan, and any open questions you need me to answer.
Don't write code yet.
```

On Laravel projects, Boost makes this plan reflect the *actual* app — real relationships and migrations — instead of a plausible-sounding guess. That's most of the value of planning in Plan Mode.

## Approve, then build

Once the plan looks right:

```
Approved. Implement it against the plan. Follow existing conventions in
the files you touch. Write tests for the new behaviour. Run the suite.
Stop and show me the diff before doing anything outside the agreed scope.
```

## Review follow-ups (Phase 3)

```
Review the most recent uncommitted work:
- code review: structure, naming, error handling, test coverage, conventions
- security: authz on new routes, input validation, anything user-controlled
```

Then verify it actually runs — open the app and use the feature, don't just trust green tests.

## Common failure modes

- **Silent scope creep.** It builds the adjacent thing I didn't ask for. The explicit "out of scope" line and "stop before anything outside scope" are there to prevent this.
- **Convention drift.** New code that works but isn't how the rest of the project does it. Point it at a similar existing file: *"Follow the pattern in X."*
- **Skipped authz.** New routes/endpoints that forget the permission check the rest of the app enforces. Always call it out in the security follow-up.
- **Tests that assert nothing.** Green tests that don't actually exercise the new behaviour. Read them.
