# Task Spec: <slug>

**Tier chain:** Research (Fable) → Plan (Opus) → Verify/ouroboros → Task-Decompose (Sonnet) → Worker (<model>)
**Parent Plan:** /mnt/www/.plans/<slug>-YYYY-MM-DD.md | **Ceremony:** Full

## Goal
<one paragraph — what "done" means in plain language>

## Acceptance Criteria
- [ ] <testable condition>

## Pattern References
- Context: `/mnt/www/ai-tools/harness/context/<project>/<feature>/CONTEXT.md` — read before starting; durable outcomes get recorded back there at completion (orchestrator's job, per harness.md's Context Protocol)
- Follow: `<path/to/existing/file-or-utility>` — because <why this is the established convention>
- Do NOT reinvent: <thing that already exists elsewhere>

## Hand-off Tags
#PATH_DECISION: <why this approach was chosen over alternatives considered during planning>
#PLAN_UNCERTAINTY: <assumptions Worker must validate — if wrong, stop and ask, don't guess>
#EXPORT_CRITICAL: <non-negotiable constraints beyond the default floor (`coding-standards.md` always applies): things not to touch, task-specific hard limits>

## Context
<the minimal-but-sufficient facts Worker needs — Worker has zero conversation
history from any prior tier, this section IS the context, not a pointer to it>

## Ponytail
- **Stop at rung:** <which rung of the ladder this task should stop at, and why —
  e.g. "rung 3, stdlib `Intl.Collator` covers it; do not write a comparator">
- **Already exists, reuse it:** <named file/export the Worker must call instead of writing its own>
- **Do NOT build:** <the abstraction/config/interface a Worker typically reaches for here and must not>
- **Ceiling to mark:** <if a deliberate shortcut is correct, the `ponytail:` comment it must leave
  behind, naming the ceiling and the upgrade path>

## Out of Scope
<explicitly excluded work>
