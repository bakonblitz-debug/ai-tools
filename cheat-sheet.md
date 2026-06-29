# Cheat Sheet

One-page reference. Read [the README](README.md) first; this is for after.

## The loop

```
Plan  →  Build  →  Review  →  Ship
```

- **Plan** — Plan Mode on (Shift+Tab ×2). Agent writes a plan, waits for approval.
- **Build** — implement against the plan, run + write tests, read the diff.
- **Review** — separate code-review + security pass on the finished change.
- **Ship** — run the app and confirm it works, commit, push.

## Reflexes

| When | Do |
|------|-----|
| Task is non-trivial or I'm guessing | Plan Mode first |
| Plan carries real risk / hidden assumptions / a wrong call is expensive | Stress-test it with the `ouroboros` adversarial planning loop |
| Task is one line and I know exactly what | Just do it — skip the ceremony |
| Building real logic or fixing a bug | Test-first: red → green → refactor (`tdd` skill) |
| Fixing a bug | Reproduce it as a *failing test first*, then fix to green |
| Code looks plausible but off | "Where is this defined? Show me the source." |
| Done writing | "Review the most recent uncommitted work for bugs and security." |
| Session is getting long / drifting | Start a fresh session |
| Working on a Laravel project | Make sure Boost MCP is connected |
| Unrelated new task | New session, don't pile it on |

## Keys & commands

- **Plan Mode**: <kbd>Shift</kbd>+<kbd>Tab</kbd> twice (until it says *Plan Mode*)
- `/code-review` — review the current diff
- `/security-review` — security pass on pending changes
- `/usage` — my plan/billing usage
- `/context` — how full *this session's* context window is (different from `/usage`)
- `/model` — switch model tier mid-session

## Models at a glance

- **Opus** — planning, architecture, gnarly debugging
- **Sonnet** — daily build driver
- **Haiku** — fast, cheap, parallel grunt work

See [models.md](models.md). `/context` ≠ `/usage`: one is session-window fullness, the other is plan/billing.

## Token discipline (the whole point)

- One job per agent. Don't plan + build + review in one prompt.
- Load only the files the task needs.
- Keep `CLAUDE.md` short; important stuff near the top.
- Let Boost feed real routes/models instead of the agent grepping for them.
- Fresh session for unrelated work — context doesn't get better as it grows.
