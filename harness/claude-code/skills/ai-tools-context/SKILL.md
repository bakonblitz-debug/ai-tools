---
name: ai-tools-context
description: Load or update Isaac's personal ai-tools context tree (~/www/ai-tools) on demand. Use when Isaac says "load my ai-tools context", "check the context tree", or "update ai-tools context about what we worked on". For Claude Code installs (e.g. claude-simply) that keep their own session bootstrapping and only touch ai-tools when told to.
---

# ai-tools context — on-demand load/update

The `ai-tools` repo (`~/www/ai-tools` on the Mac) carries Isaac's cross-machine context tree at `harness/context/CONTEXT.md` — the canonical source of truth shared by all his Claude Code installs and Hermes. This skill straps a session to it **only when invoked**; do not bootstrap it automatically.

## Load (orient)

1. `git -C ~/www/ai-tools pull --rebase --autostash` (tolerate failure offline).
2. Read `~/www/ai-tools/harness/context/CONTEXT.md`, then drill into the project/feature folder relevant to the current task. Index conventions (checkboxes, leaf naming) are documented at the top of that file.

## Update ("update ai-tools context about what we worked on")

1. Write durable outcomes as leaf files under the right `harness/context/<project>/<feature>/` folder, named `<slug>-<epoch>-<yyyymmdd>.md` (plain prose: what happened, current status). Update parent `CONTEXT.md` index lines, reverting changed lines to `- [ ]` up the chain.
2. Commit + push via `bash ~/www/ai-tools/harness/scripts/sync-memory.sh ~/www/ai-tools` — other machines only ever `git pull`.

## Rules

- Commits to this repo use Isaac's **personal** identity (`isaacbacon1+github@gmail.com`); the repo has a local `user.email` override — never commit to it with `isaac@simplyphp.com`.
- Never read, list, or follow symlinks into `~/ai-restricted/` (or any path resolving there) — real PII, deliberately outside AI reach.
- Do not write work-confidential SimplyPHP material into this personal tree; record only what Isaac asks to record.
