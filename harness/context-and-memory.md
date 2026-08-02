# Context & memory: a separate, private repo

This harness keeps your Claude **memory** and **context** in a *separate
directory you own* — never inside this `ai-tools` repo. Wired through three
settings in `~/.claude/settings.json`:

| setting | points at |
|---|---|
| `SessionStart` → `scripts/claude-bootstrap.sh <context-dir>` | pulls the context dir (if it's a git repo) + prints its `ORIENT.md` |
| `PostToolUse` / `Stop` → `scripts/sync-memory.sh <context-dir>` | commits + pushes changes under `memory/` and `context/` |
| `autoMemoryDirectory` | `<context-dir>/memory` |

Expected layout of `<context-dir>`:

```
<context-dir>/
  memory/      # auto-memory (thin pointers + preferences)
  context/     # canonical context tree (context/CONTEXT.md is the index)
  ORIENT.md    # session-start orientation, printed by the bootstrap hook
```

## Git is optional — but keep it PRIVATE if you use it

Forking/cloning `ai-tools`? A git repo for your context dir is **not
mandatory**: without git the scripts no-op cleanly and memory still works
**locally on that machine**. To make it **persist and sync across machines**,
make `<context-dir>` a git repo — and make that repo **private**.

Memory and context accumulate real PII (machine IPs, emails, project names,
personal notes). **Never put them in a public repo.** `ai-tools` is deliberately
generic and carries none of it; your personal layer lives in your own private
context repo.

## Example wiring

```jsonc
// ~/.claude/settings.json
"hooks": {
  "SessionStart": [{ "hooks": [{ "type": "command",
    "command": "bash ~/www/ai-tools/harness/scripts/claude-bootstrap.sh ~/www/context" }] }],
  "PostToolUse":  [{ "matcher": "Write|Edit", "hooks": [{ "type": "command",
    "command": "bash ~/www/ai-tools/harness/scripts/sync-memory.sh ~/www/context", "async": true }] }],
  "Stop":         [{ "hooks": [{ "type": "command",
    "command": "bash ~/www/ai-tools/harness/scripts/sync-memory.sh ~/www/context", "async": true }] }]
},
"autoMemoryDirectory": "~/www/context/memory"
```
