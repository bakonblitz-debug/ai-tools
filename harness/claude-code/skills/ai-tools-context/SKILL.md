---
name: ai-tools-context
description: Load or update the shared context tree paired with the ai-tools repo (<workspace>/ai-tools). Use when he says "load my ai-tools context", "check the context tree", or "update ai-tools context about what we worked on". For Claude Code installs (e.g. claude-simply) that keep their own session bootstrapping and only touch this context when told to.
---

# ai-tools context — on-demand load/update

> Paths below are written as `<workspace>/…`. The real root is `~/www` (Mac/Linux),
> `/mnt/www` (WSL2), or `M:\` (Windows) — see `detect_root()` in
> `harness/scripts/session-todo.sh`.

The shared, git-tracked context tree lives in a separate private repo at
`<workspace>/context/context/CONTEXT.md` — the canonical source of truth shared by
all his Claude Code installs and Hermes. (`<workspace>/ai-tools/harness/context/` is
only a gitignored, per-machine symlink into it, not a copy — see `ai-tools/harness/README.md`.)
This skill straps a session to it **only when invoked**; do not bootstrap it automatically.

## Load (orient)

1. `git -C <workspace>/context pull --rebase --autostash` (tolerate failure offline).
2. Read `<workspace>/context/context/CONTEXT.md`, then drill into the project/feature folder relevant to the current task. Index conventions (checkboxes, leaf naming) are documented at the top of that file.

## Update ("update ai-tools context about what we worked on")

1. Write durable outcomes as leaf files under the right `context/context/<project>/<feature>/` folder, named `<slug>-<epoch>-<yyyymmdd>.md` (plain prose: what happened, current status). Update parent `CONTEXT.md` index lines, reverting changed lines to `- [ ]` up the chain.
2. Commit + push via `bash <workspace>/ai-tools/harness/scripts/sync-memory.sh <workspace>/context` — other machines only ever `git pull`.

## Rules

- Commits use the single global git identity; verify `git config user.email` before committing — retired identities must never be used.
- Never read, list, or follow symlinks into `~/ai-restricted/` (or any path resolving there) — real PII, deliberately outside AI reach.
- Do not write work-confidential client/employer material into this personal tree; record only what he asks to record.
