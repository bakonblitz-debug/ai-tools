# Workspace instructions

Copy to `~/.hermes/.hermes/AGENTS.md` on the WSL box. This is the **only** file I read every
session, so anything not reachable from here does not exist as far as turn 1 is concerned. Claude Code
gets its orientation injected by a `SessionStart` hook (`claude-bootstrap.sh` → `ORIENT.md`); I have no
such hook, so this file has to do that job by pointing.

Keep it short and keep the pointers at the top — earlier instructions carry more weight, and every
token here is spent on every session.

---

## 1. Orient before answering anything non-trivial

A question asked cold gets a cold answer. Before any substantive reply about this workspace, read:

1. `/mnt/www/context/ORIENT.md` — the workspace map and the sync rules. Start here.
2. `/mnt/www/context/context/CONTEXT.md` — the git-tracked context tree, canonical and cross-machine.
   Top index → per-project folders → feature folders → issue files. Drill into the relevant folder;
   do not read the whole tree.
3. `/mnt/www/CLAUDE.md` — the shared entrypoint both machines load.

**The context tree lives ONLY in `/mnt/www/context/`.** `ai-tools/harness/context/` and
`ai-tools/harness/memory/` are stale local shadows, gitignored, and carry no `CONTEXT.md` — anything
found there is months old. Do not read them and do not write to them.

Record durable outcomes back into the tree per its own conventions when a task finishes. Writes under
`/mnt/www/context/` need `ai-tools/harness/scripts/sync-memory.sh /mnt/www/context` afterwards, since
no hook of mine sees them.

## 2. Before writing code

Read `/mnt/www/ai-tools/harness/coding-standards.md` — the universal floor. Then load the drop-in for
whatever I am working in from `coding-standards.d/` (`php.md`, `frontend.md`, …). If there is no file
for that language the floor still applies in full.

**Every coding or project task goes through the `architect` skill — including small ones.** It
sequences: ground and plan → `ouroboros` at least once before any code → TDD with **one failing test
per lap** → review. Exempt: pure reads, one-line typo fixes with no behavioural change, and anything
he explicitly says to do without planning. If a step genuinely does not apply, say which and why —
never drop it silently.

A green typecheck is **not** a correctness verdict. It checks shape; the defects that matter here have
all been semantic. The acceptance test is the verdict, and it is authored by whoever owns the rule,
never by the worker implementing it.

## 3. Delegation

`devstral:65k` over the LAN, **one worker at a time**. **Never a qwen model as a worker** —
`config/delegation.yaml` forbids it (hallucinated tool calls); `skills/tdd/SKILL.md` still says to
switch to `qwen2.5:32b` and that line is stale.

Measured worker failure modes, worth naming in the spec up front because naming them prevents them:
**unrequested conjuncts** that silently shrink a match set, and **silent deletion** when asked to
extend a pattern. When a delegated lap fails, return a **mechanical diagnosis — why it broke** — never
just which test failed. Pass/fail cannot teach.

Do not delegate a task whose spec would be longer than its implementation. Delegate scaffolding and
boilerplate; keep the pure logic.

## 4. Hard rules

**Restricted data:** never read, list, or follow symlinks into `~/ai-restricted/` or any path
resolving there (e.g. `budge/tmp/bank`, `budge/tmp/cc`). Real PII, deliberately outside AI reach. If a
task seems to need it, stop and ask; use synthetic samples.

**One machine at a time.** The Mac and the PC share this tree and will collide on `index.lock` and
interleave auto-commits otherwise.

**Git identity** is the single global one; verify before committing. Retired identities must never
appear on a commit. Use the git CLI or `gh` — never a browser extension on GitHub.

**No `Co-Authored-By` trailers.** Git parses only the last contiguous paragraph as trailers, so a
blank line above them makes the whole ledger unreadable.

**Label the shell** in anything I hand him: `[WSL]`, `[PowerShell]`, `[Mac]`.

**Voice in shared docs:** I write as "I"; he is "he"/"his". Never his name or personal details.
