# Workspace bootstrap (ai-tools harness)

Injected at session start by `harness/scripts/claude-bootstrap.sh` — the repo was just pulled, so this tree is current.

**Workspace map** — the `www` workspace is one tree seen from several places: the Mac hosts it at `~/www` (SMB share, and `~/www/ai-tools` is the git repo); the Windows PC maps the share at `M:\` and keeps its own clone of `ai-tools` at `C:\Users\isaac\www\ai-tools`; WSL2/Hermes mounts the share at `/mnt/www`.

**Orient before non-trivial work** on anything in this workspace: read `harness/context/CONTEXT.md` (the git-tracked context tree — the canonical, cross-machine source of truth) and drill into the relevant project/feature folder. Record durable outcomes back into the tree per its conventions when done.

**Context/memory writes flow through git.** On the PC, read and write repo content in the local clone, not on `M:`. Changes under `harness/context/` or `harness/memory/` are auto-committed and pushed by hooks; if you change them via Bash (hooks can't see that), run `harness/scripts/sync-memory.sh <repo-path>` or commit+push yourself. Every other machine only ever needs `git pull` to be current.

**Auto-memory** (`harness/memory/`) is shared by every Claude Code install on every machine. Keep it to thin pointers into the context tree plus preferences; tag machine-specific notes with the machine they apply to. Canonical project knowledge goes in the context tree, not in memory.

**Hard rule — restricted data:** never read, list, or follow symlinks into `~/ai-restricted/` (or any path resolving there, e.g. `budge/tmp/bank`, `budge/tmp/cc`). Real PII lives there, deliberately outside AI reach. If a task seems to need it, stop and ask; use synthetic samples instead.
