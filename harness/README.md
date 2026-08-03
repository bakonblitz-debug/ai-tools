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
- **The context tree** — the shared, git-tracked source of truth all agents
  orient from and write back to. It lives in a **separate private repo**
  (`/mnt/www/context/`), never in this public one: it accumulates real PII.
  Start at `/mnt/www/context/ORIENT.md`, then `/mnt/www/context/context/CONTEXT.md`.

  `harness/context/` and `harness/memory/` are the **in-repo access point** for
  agents scoped to `ai-tools` alone rather than the whole `www` tree — Cowork is
  the case that motivated it (see the context tree's
  `workspace/cowork-direct-access-*.md`; its folder is exposed over FUSE, so it
  cannot reach `../../context`). They are gitignored so the private tree never
  lands in this public repo.

  **Per-machine setup — required, and gitignored so it does not travel.** They are
  *relative* symlinks into the private repo. Relative, not absolute, so the same
  link resolves on the Mac (`~/www`), in WSL (`/mnt/www`) and on the PC (`M:\`):

  ```
  cd <repo>/harness && ln -s ../../context/context context && ln -s ../../context/memory memory
  ```

  Verify with `ls -l harness/context/CONTEXT.md` — it must resolve, and its date
  must match the live tree. If it is a real directory rather than a symlink, it is
  a stale copy: a frozen 2026-07-13 one was found here on 2026-08-03 still naming
  the old `BakonBlitz/ai-tools` repo and telling agents to commit as the retired,
  suspended `isaacbacon1+github@gmail.com`. A stale copy here is worse than nothing,
  because it produces exactly the identity mistake the hard rules forbid.

  **A symlink only works where the agent's confinement is conventional.** It does
  not cross an *enforced* boundary — a symlink out of a FUSE-exposed folder resolves
  outside the mount and fails. Hermes already has all of `/mnt/www` mounted, so it
  needs a pointer (`hermes-AGENTS.md`), not a symlink. Cowork is FUSE-confined, so
  whether this works for it is an empirical question: check that it can read
  `harness/context/CONTEXT.md` and see today's content before trusting it.
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
    ├── scripts/
    │   ├── claude-bootstrap.sh   — Claude Code SessionStart hook: pulls the
    │   │                           context repo, then prints its ORIENT.md so
    │   │                           the session starts oriented. Takes the
    │   │                           context-repo path as its one argument, and
    │   │                           REQUIRES an ORIENT.md at that repo's root —
    │   │                           without one it exits silently and every
    │   │                           session starts blind.
    │   ├── sync-memory.sh        — commit+push context/memory written via Bash
    │   └── plan-mindset.sh       — UserPromptSubmit hook, plan-tier only
    ├── hermes-AGENTS.md          — copy to ~/.hermes/.hermes/AGENTS.md. Hermes
    │                               has no SessionStart hook, so this is the only
    │                               file it reads every session; it does the
    │                               orienting by pointing.
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
