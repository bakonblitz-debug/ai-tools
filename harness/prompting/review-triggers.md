# Review triggers

The prompts that kick off Phase 3. Review runs as a **separate pass on the finished change** — never folded into the prompt that wrote the code. A reviewer that wrote the code is a bad reviewer.

## The default pass

After the build is done and tests are green:

```
Review the most recent uncommitted work as two separate passes:
1. Code review — correctness bugs, structure, naming, error handling,
   test coverage, and adherence to this project's conventions.
2. Security — injection surfaces, auth/authz on any new routes, input
   validation, secrets handling, dependency risk, framework misconfig.
Report findings separately. Don't fix anything yet — just report.
```

"Report, don't fix yet" keeps me in control of triage. I decide what's worth changing before code moves.

## Built-in commands

- `/code-review` — reviews the current diff for bugs and cleanups. Effort scales: lower = fewer high-confidence findings, higher = broader coverage.
- `/security-review` — a security pass on pending changes.

If a skill doesn't auto-trigger, invoke it by name: *"Use the security-review skill on this diff."*

## Triage every finding

| Bucket | Meaning | Action |
|--------|---------|--------|
| **Must-fix** | Correctness or security defect | Blocks the commit — loop back to Build |
| **Should-fix** | Real but not blocking | Fix now if cheap, else write it down |
| **Note** | Worth knowing, not worth doing now | Log it for a future pass |

## When to run extra passes

- Touched auth, payments, or anything user-controlled → always a security pass, no exceptions.
- Touched a query or a hot path → ask specifically about N+1s and indexes.
- Touched user-facing copy or UI → a quick accessibility/clarity look.

## Common failure modes

- **Review folded into generation.** Asking the same prompt to "build it and make sure it's secure" — it'll grade its own homework. Separate pass, always.
- **Rubber-stamp.** A review that finds nothing on a non-trivial change is suspicious. Push: *"Assume there's at least one bug here — where is it?"*
- **Fixing before triaging.** Letting the agent rewrite on every finding before I've decided what matters. Report first, then I choose.
