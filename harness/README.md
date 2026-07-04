# ai-tools/harness — Tiered AI-Delegation Pipeline

## What this is

This directory holds Isaac's original 5-tier delegation pipeline for Hermes:
**Research (Fable) → Plan (Opus) → Verify (ouroboros) → Task-Decompose
(Sonnet) → Worker (local `devstral:65k`)**, orchestrated by the `architect`
skill (`/mnt/www/ai-tools/skills/architect/SKILL.md`). It exists so that when
Hermes delegates work, the agent doing the work gets enough hand-off context
to produce a result as good as (or better than) a single agent working alone
with full context — the way Claude Code's own forked background research
agents do.

This is **not** a copy of `safe-agentic-workflow`'s 11-role SAFe-team
template, and not a copy of any employer Claude Code Team harness. It is a
one-person, tiered-model pipeline sized for Isaac's actual hardware and
actual workflow.

## Relation to other docs in this stack

- **`/mnt/www/ai-tools/harness/hermes-harness-2026-07-02.md`** — the
  pre-existing 5-phase (Orient/Ground/Plan/Build/Verify/Record) default
  operating mode for Hermes as an engineering collaborator. Unchanged by this
  work except for one short "Harness Tiers" cross-reference section appended
  at the end. It governs *every* non-trivial Hermes task; this pipeline is
  what runs *inside* its Plan/Build phases for tasks big enough to warrant
  the full tiered treatment. Small tasks still just use the five phases
  directly.
- **`/mnt/www/safe-agentic-workflow/`** — a cloned reference repo (11-role
  SAFe team-coordination template, Linear tickets, PR gates). Left untouched,
  read-only. A few portable ideas were mined from it into `harness.md`
  (hand-off tags, the Spike-vs-Full-Spec routing rule, the Worker Output Gate
  checklist shape) — not built on wholesale, since its actual problem
  (coordinating many humans) isn't Isaac's problem (tiered models, one person).

## Layout

```
/mnt/www/ai-tools/
├── skills/                       — existing, unchanged location
│   ├── architect/SKILL.md        — rewritten: now the tier orchestrator
│   ├── ouroboros/SKILL.md        — unchanged, reused as the Verify tier
│   ├── git-conflict/SKILL.md     — filled in (was a 14-line stub)
│   ├── tdd/, handoff/            — unchanged
│   └── second-brain/             — untouched, out of scope
└── harness/                      — this directory
    ├── README.md                 — this file
    ├── harness.md                — the actual tiered-delegation design
    ├── templates/
    │   ├── task-spec-template.md
    │   └── spike-template.md
    ├── config/
    │   └── delegation.yaml       — reviewable sketch, NOT live-applied
    └── sync-skills.sh            — registers ai-tools/skills with Hermes
                                     (relocated here from the originally-
                                     planned ~/.hermes/sync-skills.sh — that
                                     path isn't writable by isaac; see
                                     harness.md's Skill registration section)
```

## Where to start reading

Read `harness.md` next — it has the tier table, the corrected skill-
registration mechanism, the corrected Plan/Task-Decompose subprocess
mechanism, the Worker Output Gate, and the `architect` rewrite summary.

## Status

Documentation and skill-content complete. Live wiring (registering the
skills path in Hermes' `config.yaml`, installing `claude` CLI + `superpowers`
inside WSL, end-to-end pipeline run) is blocked on the separate,
still-in-progress base Hermes install — see `harness.md`'s "What can be
verified now vs. what's blocked" section.
