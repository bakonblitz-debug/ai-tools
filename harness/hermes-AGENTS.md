# Workspace instructions

> ## ⚠ THIS FILE IS NOT LOADED. Editing it changes nothing.
>
> Verified 2026-09-03 by probing a live session's `system_prompt`: unique strings from this file
> (`One machine at a time`, `Label the shell`) are **absent**. Hermes discovers context files
> **cwd-only** and only under the names `AGENTS.md` / `CLAUDE.md` / `.cursorrules`
> (`agent/prompt_builder.py:build_context_files_prompt`). The cwd is `/mnt/www`, which has no
> `AGENTS.md` — so a copy or symlink at `~/.hermes/.hermes/AGENTS.md` is never read.
>
> What Hermes actually loads: **`SOUL.md`** (→ `local-ai-setup/SOUL.md`, git-tracked, no sudo) and
> **`/mnt/www/CLAUDE.md`** (the cwd context file). Put instructions in those.
>
> Rules below that reach Hermes nowhere else — one machine at a time, label the shell, git identity,
> no `Co-Authored-By` trailers, doc voice — need folding into `SOUL.md`, budget permitting. It is
> already 25.7 KB of a 32.8 KB prompt against a 24k window.
>
> Same class of trap as the August `platform_toolsets` finding: a carefully maintained file that
> nothing reads. Kept as the staging copy for that fold, not as a live config.

Symlinked to `~/.hermes/.hermes/AGENTS.md` on the WSL box (inert — see above). Claude Code
gets its orientation injected by a `SessionStart` hook (`claude-bootstrap.sh` → `ORIENT.md`); I have no
such hook, so this file has to do that job by pointing.

Keep it short and keep the pointers at the top — earlier instructions carry more weight, and every
token here is spent on every session.

---

## 1. Answer the question that was asked

**Reading is not answering.** A turn spent orienting and then stopping is a failed turn, and it is my
most common failure: measured 2026-09-03, ten trials out of ten of a one-line question were lost to
reading context files and summarising them instead of replying.

So: if the question can be answered directly, or with one tool call, I do that and stop. A literal
instruction — "reply with exactly X", "list the filenames", "answer in one line" — **is** the whole
task. I do it and stop, and I do not infer a larger job from the surrounding context.

Orient only before substantive work on this workspace: planning, building, changing code, or a
question about past decisions I cannot answer by looking directly. Then read only as far as I need:

1. `/mnt/www/context/context/CONTEXT.md` — the git-tracked context tree, canonical and cross-machine.
   Note the **doubled `context`**: `/mnt/www/context` is the repo, `/mnt/www/context/context` is the
   tree. `/mnt/www/context/CONTEXT.md` does not exist and I keep reaching for it by mistake.
   Top index → per-project folders → feature folders → issue files. Drill into the relevant folder;
   do not read the whole tree.
2. `/mnt/www/context/ORIENT.md` — the workspace map and the sync rules, if step 1 was not enough.
3. `/mnt/www/CLAUDE.md` — the shared entrypoint both machines load, if I am about to change code.

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

`devstral:24k` over the LAN, **one worker at a time**. The 24k variant is deliberate — 65k needs a
10.27 GB KV cache on top of 14 GB of weights, more than the card has, and silently runs partly on
CPU. **Never a qwen model as a worker** —
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
