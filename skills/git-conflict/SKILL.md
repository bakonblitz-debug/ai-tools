---
name: git-conflict
description: >
  Resolve git conflicts that arise when multiple agents (or multiple isolated
  worktrees/branches) make concurrent changes to the same project files. Use
  when `git status` shows unmerged paths, a merge/rebase stops with conflict
  markers, or a PR shows a conflicting-files warning. Trigger on: merge
  conflict, rebase conflict, conflicting changes, resolve conflicts, worktrees
  diverged, two agents touched the same file. Not for ordinary code review —
  only for actual unmerged/conflicted git state.
---

# Git Conflict — Cross-Agent Conflict Resolution

> **Model:** Switch to `deepseek-r1:32b-65k` before starting
> (`/model deepseek-r1:32b-65k`). Conflict resolution is a judgment call about
> two divergent intents, not mechanical text merging — treat it with the same
> model tier as ouroboros/architect, not the default coding model.
> Switch back to `gemma3:27b-65k` when complete.

## When to use

Multiple agents (parallel Hermes sessions, isolated Claude Code worktrees, or
a human and an agent) made concurrent changes to the same file(s) or
diverging branches, and git now reports unmerged paths — mid-merge,
mid-rebase, or a PR showing conflicting files. Do not invoke this
speculatively; only once git itself has actually stopped with a real
conflict.

## Why this exists

A conflict marker is git's honest admission that it can't tell which intent
should win — that's a judgment call, not a mechanical merge. Blindly taking
"ours" or "theirs" silently discards one side's actual work; that is the most
common way cross-agent conflict resolution introduces a regression nobody
notices until later. This skill's job is to make the judgment call
*explicit*: state which side's change wins, why, and what (if anything) had
to be manually reconciled from both.

## Procedure

### 1. Identify the conflict

```bash
git status                              # lists unmerged paths
git diff --name-only --diff-filter=U    # just the conflicted file list
```

Read each conflicted file in full — don't just look at the `<<<<<<<` hunks in
isolation; a conflict marker only shows where *lines* collide, not why each
side made the change.

### 2. Understand both sides before touching anything

For each conflicted file:

```bash
git log --oneline -5 -- <file>                           # recent history, current branch
git show :2:<file>                                        # "ours"
git show :3:<file>                                        # "theirs"
git log --oneline <merge-base>..<theirs-branch> -- <file> # what the other side was doing
```

State, in one sentence each, what each side was trying to accomplish. If
either side's intent isn't clear from the commit messages/diff alone, that is
itself a signal to escalate (§4) rather than guess.

### 3. Resolve — reconcile intents, don't just pick a side

- Two sides touching genuinely different concerns in the same hunk (e.g. one
  added error handling, the other renamed a variable) → merge both changes by
  hand into one coherent version. This is the common case and the whole
  reason "just take theirs" is wrong.
- Two sides making **the same fix in different ways** → pick the version that
  better matches the codebase's existing patterns (see `hermes-harness-
  2026-07-02.md`'s "existing patterns → follow them" rule), and note why the
  other approach wasn't used.
- Two sides **genuinely incompatible** (same behavior, opposite requirements)
  → this is a requirements conflict, not a merge conflict. Do not resolve it
  silently; escalate (§4).
- Remove every conflict marker (`<<<<<<<`, `=======`, `>>>>>>>`) — a leftover
  marker is a silent syntax-breaking bug in almost every language.
- Tag the resolution as a commit-message note (not in the code), using the
  hand-off convention from `ai-tools/harness/harness.md`:
  `#PATH_DECISION: kept <ours|theirs|merged> because <reason>` — makes the
  judgment call auditable later, same as Task-Decompose specs.

### 4. Escalate instead of guessing, when:

- The two sides' intents are incompatible, not just differently-expressed
- Resolution would touch the compliance floor (Loi 25 > PIPEDA > GDPR > HIPAA
  > CCPA) or OWASP-relevant surface (auth, input handling, storage) — same
  bar as the harness's Worker Output Gate escalation triggers
- You cannot state, in one sentence, what either side was trying to do
- The conflict spans more than ~150 changed lines across more than one file
  (same threshold used elsewhere in the harness's escalation triggers)

When escalating: stop, do not commit a half-resolved merge, and report the
crux plainly, mirroring ouroboros's `DEADLOCK` format:

```
CONFLICT: <file(s)> — <one-line statement of what's incompatible>
OURS: <what this branch's change accomplishes>
THEIRS: <what the incoming change accomplishes>
WHAT WOULD RESOLVE IT: <the decision or fact needed>
```

### 5. Verify before committing the resolution

- Full test suite green — not just "the conflict markers are gone"
- Read the merged diff end-to-end once more — does it contain both sides'
  intended behavior, or did one silently get dropped during the by-hand merge?
- `git add <file>` only after both checks above, never before
- Continue the merge/rebase (`git merge --continue` / `git rebase --continue`)
  only once every conflicted file has passed steps 3-5

### 6. Worktree-specific note

When the conflict originates from isolated Claude Code worktrees
(`.claude/worktrees/<name>`, `claude -w <name>`) rather than a plain branch
merge, the same procedure applies — the worktree is just where each side's
changes physically live before the merge. Resolve at the point the
worktrees' branches are merged back (`git merge <worktree-branch>`), not by
editing files inside both worktrees separately; editing both sides is how
the same conflict re-appears at the next merge.

## What this skill owns vs. delegates

Owns: identifying real (not speculative) conflicts, understanding both sides'
intent before editing, the reconcile-vs-pick-a-side judgment call, the
escalation gate, and post-resolution verification. Delegates: the actual test
run to whatever test command the project already uses, and any
requirements-level disagreement that escalation surfaces — that goes to the
human or the Plan tier; this skill does not resolve requirements conflicts
itself.
