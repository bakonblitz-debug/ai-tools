# ai-tools — Tiered AI-Delegation Pipeline

> Paths below are written as `<workspace>/…`. The real root is `~/www` (Mac/Linux),
> `/mnt/www` (WSL2), or `M:\` (Windows) — see `detect_root()` in
> `scripts/session-todo.sh`.

## Start here, if you just cloned this

Most of what is in this repo is not tied to any of the machinery below. In rough order of
usefulness to someone who is not him:

| Want | Read |
|---|---|
| The rules every language obeys | `coding-standards.md`, plus the drop-in for your stack in `coding-standards.d/` |
| Copy-paste runbooks per situation | `prompting/` — bug fix, new feature, TDD, scoped refactor |
| The skills | `skills/` — `architect` sequences the others; `ouroboros`, `tdd`, `handoff` each stand alone |
| To wire it into Claude Code | `python3 scripts/install.py` (`--dry-run` first). It merges into your `settings.json`, backs it up, and prints the undo |
| To check what works on your machine | `bash scripts/health-check.sh` — anything you do not have reports SKIP, not FAIL |

The delegation pipeline described below needs a local model runner and a private context repo.
**Neither is required for any of the above.** If you do not have them, the pipeline section is
background reading, not a prerequisite.

## What this is

His original 5-tier delegation pipeline for Hermes: **Research (Fable) →
Plan (Opus) → Verify (ouroboros) → Task-Decompose (Sonnet) → Worker (local
`devstral:65k`)**, orchestrated by the `architect` skill
(`<workspace>/ai-tools/skills/architect/SKILL.md`). The point: when Hermes
delegates work, whoever picks it up should get enough hand-off context to do
the job as well as a single agent holding the full picture would — the way
Claude Code's own forked background research agents do.

This is not a copy of `safe-agentic-workflow`'s 11-role SAFe-team template,
and not a copy of any employer Claude Code Team harness. It's a one-person,
tiered-model pipeline sized for his actual hardware and workflow.

## Relation to other docs in this stack

- **A private Hermes operating note, not in this repo** — the 5-phase
  (Orient/Ground/Plan/Build/Verify/Record) default operating mode for Hermes
  as an engineering collaborator. It governs
  *every* non-trivial Hermes task; the pipeline here is what runs *inside*
  its Plan/Build phases when a task is big enough to warrant the full tiered
  treatment. Small tasks just use the five phases directly.
- **`coding-standards.md`** (this directory) — the canonical security,
  privacy, and development floor. Every tier works to it, and so does every
  agent outside the pipeline.
- **The context tree** — the shared, git-tracked source of truth all agents
  orient from and write back to. It lives in a **separate private repo**
  (`<workspace>/context/`), never in this public one: it accumulates real PII.
  Start at `<workspace>/context/ORIENT.md`, then `<workspace>/context/context/CONTEXT.md`.

  Agents read it at `<workspace>/context/`. The in-repo `harness/context` and
  `harness/memory` symlinks (meant for a FUSE-confined Cowork that could only see
  `ai-tools`) were removed on 2026-10-27: no script used them and Cowork access
  was never verified. Recreate them only if that need is proven.
- **`<workspace>/other/reference/safe-agentic-workflow/`** — a cloned reference repo (11-role
  SAFe team-coordination template, Linear tickets, PR gates). Read-only. A
  few portable ideas were mined from it into `harness.md` (hand-off tags,
  the Spike-vs-Full-Spec routing rule, the Worker Output Gate checklist
  shape). It wasn't adopted wholesale because its actual problem —
  coordinating many humans — isn't his problem.

## Layout

Standard Claude Code marketplace shape: the plugin under `plugins/`, everything else beside it.

```
<workspace>/ai-tools/
├── .claude-plugin/marketplace.json   — the `ai-tools` marketplace; lists one plugin
├── plugins/bacon/                    — the plugin (skills are invoked as bacon:*)
│   ├── .claude-plugin/plugin.json
│   └── skills/                       — architect, ouroboros, tdd, handoff, git-conflict,
│                                       second-brain, context-query, ai-tools-context
├── scripts/                          — hooks and tools: claude-bootstrap.sh, session-todo.sh,
│                                       health-check.sh, install.py, sync-memory.sh, …
├── bin/now                           — on PATH via ~/.zshenv
├── config/delegation.yaml            — who does which tier
├── templates/                        — spike and task-spec templates, launchd example
├── docs/                             — this file, harness.md, coding-standards(.d),
│                                       context-and-memory.md, prompting/, setup, glossary
├── .env.example                      — every machine-local key; the real .env is gitignored
└── README.md
```

## Where to start reading

[`harness-map.md`](harness-map.md) for what runs today: every file, what fires it, what
it touches, and why it is built this way. Open `harness-map.html` in a browser for the
clickable version.

For the July 2026 design history, `harness.md`. It has the tier table, the corrected skill-registration
mechanism, the corrected Plan/Task-Decompose subprocess mechanism, the
Worker Output Gate, and the `architect` rewrite summary.

## Status

**The Claude Code side is live and running** — hooks, the session digest, the health checks,
the standards and the skills are all in daily use. `scripts/health-check.sh` is the acceptance
test for that half; `scripts/clone-test.sh` checks that a fresh clone works for someone who is
not him.

**The Hermes delegation pipeline is partially wired.** The base install was redone 2026-09-04;
skills registration and an end-to-end tiered run are still outstanding. See "What can be
verified now vs. what's blocked" in `harness.md`. Nothing in the Claude Code half depends on it.
