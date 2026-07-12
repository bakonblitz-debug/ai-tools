# Bug fix — reproducible

For a bug I **can reproduce** and whose surface I roughly know: a stack trace, a failing test, a specific route or function that misbehaves.

**Not** for: a vague "it's slow sometimes" or a report I can't reproduce — that's investigation, not a fix. Don't let the agent start changing code before the bug is pinned down.

## Opening prompt (Plan Mode)

```
Plan Mode. Bug: <what happens> vs <what should happen>.
Reproduce: <steps / failing test / route + payload>.
<paste the stack trace or error if I have one>

Find the root cause first — don't propose a fix until you can point to the
exact line(s) responsible and explain why it fails. Then propose the
smallest change that fixes the cause (not the symptom), and a test that
fails before the fix and passes after. List any files you'd touch.
```

The key instruction is **root cause before fix**. Agents love to patch the symptom — wrap the thing in a null check and move on. I make it show me the cause first.

## After it implements

```
Add the failing-then-passing test if you haven't. Run the suite.
Then review the change for correctness bugs and any security impact.
```

## Triage the result

- **Must-fix** — the fix doesn't actually address the root cause, or it breaks another path.
- **Should-fix** — adjacent smell the fix revealed; ticket it unless it's a one-liner.
- **Note** — "this whole area is fragile"; log it for a future refactor pass.

## Common failure modes

- **Symptom patching.** A null check that hides the crash without fixing why the value was null. Ask: *"Why was it null in the first place?"*
- **Scope creep.** The agent "improves" surrounding code while fixing one bug. Keep the diff to the bug; refactors are a separate task.
- **No regression test.** A fix without a test that would have caught the bug means it can silently come back. Don't skip it.
- **Hallucinated cause.** It confidently blames a method or column that doesn't exist. Verify against the real code before believing the diagnosis.
