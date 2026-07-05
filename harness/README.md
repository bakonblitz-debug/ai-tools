# ai-tools/harness — Tiered AI-Delegation Pipeline

## What this is

His original 5-tier delegation pipeline for Hermes: **Research (Fable) →
Plan (Opus) → Verify (ouroboros) → Task-Decompose (Sonnet) → Worker (local
`devstral:65k`)**, orchestrated by the `architect` skill
(`/mnt/www/ai-tools/skills/architect/SKILL.md`). The point: when Hermes
delegates work, whoever picks it up should get enough hand-off context to do
the job as well as a single agent holding the full picture would — the way
Claude Code's own forked background research agents do.

This is not a copy of `safe-agentic-workflow`'s 11-role SAFe-team template,
and not a copy of any employer Claude Code Team harness. It's a one-person,
tiered-model pipeline sized for his actual hardware and workflow.

## Relation to other docs in this stack

- **`hermes-harness-2026-07-02.md`** (this directory, deliberately kept out
  of git) — the 5-phase (Orient/Ground/Plan/Build/Verify/Record) default
  operating mode for Hermes as an engineering collaborator. It governs
  *every* non-trivial Hermes task; the pipeline here is what runs *inside*
  its Plan/Build phases when a task is big enough to warrant the full tiered
  treatment. Small tasks just use the five phases directly.
- **`coding-standards.md`** (this directory) — the canonical security,
  privacy, and development floor. Every tier works to it, and so does every
  agent outside the pipeline.
- **`context/`** (this directory) — the shared, git-tracked context tree all
  agents orient from and write back to. Start at `context/CONTEXT.md`.
- **`/mnt/www/safe-agentic-workflow/`** — a cloned reference repo (11-role
  SAFe team-coordination template, Linear tickets, PR gates). Read-only. A
  few portable ideas were mined from it into `harness.md` (hand-off tags,
  the Spike-vs-Full-Spec routing rule, the Worker Output Gate checklist
  shape). It wasn't adopted wholesale because its actual problem —
  coordinating many humans — isn't his problem.

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
    ├── coding-standards.md       — canonical security/privacy/dev floor
    ├── hermes-harness-2026-07-02.md — Hermes' 5-phase operating mode (gitignored)
    ├── context/                  — shared context tree (see context/CONTEXT.md)
    ├── templates/
    │   ├── task-spec-template.md
    │   └── spike-template.md
    ├── config/
    │   └── delegation.yaml       — reviewable sketch, NOT live-applied
    └── sync-skills.sh            — registers ai-tools/skills with Hermes
                                     (lives here because ~/.hermes isn't
                                     writable by the normal WSL user; see
                                     harness.md's Skill registration section)
```

## Where to start reading

`harness.md`. It has the tier table, the corrected skill-registration
mechanism, the corrected Plan/Task-Decompose subprocess mechanism, the
Worker Output Gate, and the `architect` rewrite summary.

## Status

Documentation and skill content are complete. Live wiring — registering the
skills path in Hermes' `config.yaml`, installing `claude` CLI + `superpowers`
inside WSL, an end-to-end pipeline run — is blocked on the separate,
still-in-progress base Hermes install. See "What can be verified now vs.
what's blocked" in `harness.md`.
