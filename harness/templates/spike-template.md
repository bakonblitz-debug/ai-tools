# Task Spec: <slug> (Spike)

> Paths below are written as `<workspace>/…`. The real root is `~/www` (Mac/Linux),
> `/mnt/www` (WSL2), or `M:\` (Windows) — see `detect_root()` in
> `harness/scripts/session-todo.sh`.

**Time-Box:** <e.g. 1 Worker iteration, ~10 min — if unresolved, escalate to Plan tier rather than extend>
**Delegated to:** Worker (<model>)

## Question to Answer
<the single question this spike must resolve — often literally a #PLAN_UNCERTAINTY>

**Context:** `<workspace>/ai-tools/harness/context/<project>/<feature>/CONTEXT.md` — check first; the answer gets recorded back there at completion (orchestrator's job, per harness.md's Context Protocol).

## Expected Outcomes
- <an answer, a recommendation, a small proof-of-concept — not necessarily working code>
- Escalation note: if the answer implies multi-file/interface-level work, STOP and
  report back — this becomes a Full Spec, don't keep building.

## Hand-off Tags
#EXPORT_CRITICAL: <constraints that apply even to throwaway/exploratory work — `coding-standards.md` is the default floor here too>
