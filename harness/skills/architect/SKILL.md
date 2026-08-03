---
name: architect
description: >
  THE default entry point for any coding or project work — ours or a client's. Takes an idea or a
  change request through Ground → Plan → ouroboros (adversarial challenge, at least one round) →
  Task-Decompose → TDD implementation, gating between each. Use it for creating a new project,
  changing an existing one, adding a feature, fixing a bug, refactoring, or altering behaviour —
  **including small changes**; the size of the diff does not lower the bar, and "it's just a small
  fix" is exactly where unreviewed assumptions ship. Trigger on: new project, start a project, set
  up a repo, build X, add a feature, implement X, change X, update the app, modify behaviour, fix
  this bug, refactor X, plan X, design X, architect X, take my idea to a task list, full planning
  pipeline. Prefer this over answering a build/change request directly. The only things that skip
  it are pure reads (explain this, what does X do, find where Y happens), one-line typo and
  formatting edits with no behavioural change, and work the user has explicitly told you to do
  without planning. If a step genuinely does not apply, say which one and why — do not silently
  drop it. Each tier also works standalone; architect is the conductor that sequences and gates.
---

# Architect — Idea → Proven Plan → Tasks → Shipped Work

## Current wiring — read this before running the pipeline

**Corrected 2026-08-02.** The tier table below still describes the original five-tier design. Two of
those tiers cannot run as written on this install, so the pipeline that actually executes today is:

| Tier | Original | Actual today |
|---|---|---|
| Research | Fable via `claude` CLI subprocess | **Shelved 2026-07-05** — Claude subprocess tiers were dropped in favour of Claude Code planning directly and handing work over as files on the share |
| Plan | Opus subprocess → `superpowers:brainstorming` | **`superpowers` is disabled.** Plan directly, or use the intake questions in `ouroboros`'s Requirements section |
| **ouroboros** | adversarial prove + certify | **Works. Mandatory — at least one round.** |
| Task-Decompose | Sonnet subprocess → `superpowers:write-plan` | **`superpowers` is disabled.** Decompose directly into `templates/task-spec-template.md` |
| Worker | local `devstral:65k` via `delegate_task` | **Works** — or reach Ollama directly over the LAN when the `hermes` CLI is not available |

**Non-negotiable regardless of tier availability:** ouroboros runs at least once before code is
written, and implementation is TDD with **one failing test per lap** (`coding-standards.md`). If a tier
is unavailable, do that tier's job inline and say so — never skip the gate because its tool is missing.

**Do not switch the worker to any qwen model.** `config/delegation.yaml` forbids it (hallucinated tool
calls). Note `skills/tdd/SKILL.md` currently says to switch to `qwen2.5:32b`; that is stale and the
delegation config wins.


> **Model:** Switch to `deepseek-r1:32b-65k` before starting (`/model deepseek-r1:32b-65k`) —
> matches this skill's existing ouroboros-loop role; it is the fleet's planning/architecture/
> judgment-call model (see `/mnt/www/ai-tools/harness/hermes-harness-2026-07-02.md`'s Model Fleet
> table), which is what this skill's own sequencing/gating decisions need.
> Switch back to `gemma3:27b-65k` when complete (the fleet's documented ambient default — NOT
> `qwen2.5:14b`, which this build's harness doc explicitly bans: "Never use qwen models — they
> hallucinate tool calls." The previous version of this instruction predated that documented
> constraint; corrected here for internal consistency — flag if this should be reverted.)

A conductor, not a coupler. Architect runs a tiered delegation pipeline in order — plus a dormant
final phase (ticketing, disabled in this build) — and checks in with the user between phases. It
adds no planning logic of its own and owns no shared file format — each tier writes its own native
artifact, and architect passes the path forward.

## Two separate agent ecosystems in this pipeline — do not conflate

This skill spans two entirely different runtimes, and it matters which one you're in at each step:

1. **Hermes' own skills** — `architect` (this skill), `ouroboros`, `git-conflict`, `tdd`,
   `handoff`, and the Hermes-bundled `claude-code` skill. These are invoked the normal way, by
   Hermes' own skill-loading mechanism, running on whatever local model you've switched to.
2. **Claude Code's plugin skills** (`superpowers:brainstorming`, `superpowers:write-plan`) —
   these do **not** run inside Hermes at all. They run inside a completely separate `claude` CLI
   subprocess (a child OS process, its own Claude Code session, its own OAuth/session state),
   which Hermes spawns via its `terminal` tool per the bundled `claude-code` skill's print-mode
   guidance, and which his personal Anthropic account must have `superpowers` installed on
   (see harness.md's Prerequisite section) for those two skill names to resolve at all.

Phases 1 and 3 below cross this boundary — Hermes (you, running locally) constructs a prompt,
shells out via `claude-code`, and reads back that subprocess's final JSON result. Phase 2
(ouroboros) does not cross it — it stays entirely inside Hermes' own skill ecosystem, unchanged.

## Jira ticketing — DISABLED in this build

This personal build runs **without** Jira integration. Default behavior:
- **Skip the Step 0 ticket check** — do not ask whether a ticket exists, and use a **five-item**
  todo (Phases 1–5, see below — was three/four items before the tier split).
- **Skip the final ticketing phase** — do not file a ticket; the pipeline ends once Worker tasks
  are built and gated.

The ticket machinery below (the Step 0 ticket check and the final phase) is kept as dormant,
ready-to-enable reference — good bones. If you move into an org with Atlassian/Jira, turn it on by
following the Step 0 ticket check and that final phase exactly as written. Until enabled, treat
those two sections as inert.

## Operating mode

Run in **default mode, not plan mode.** The pipeline produces several native planning artifacts —
Research findings, the Plan tier's design draft, ouroboros's `PLAN.md`, and the task specs — and
plan mode blocks any write outside a single plan file, so Phase 1 alone would stall. Architect only
ever writes *planning* artifacts itself (Worker is where source gets written, and Worker runs as
its own delegate_task child, not as this skill's own context), so default mode is safe. Reserve
plan mode for direct human-driven implementation sessions, not for this pipeline.

## Verbosity

Architect accepts a verbosity flag — `-q` / `-v` / `-vvv`, **default `-v`** — and forwards it to
the ouroboros call in Phase 2. So by default you see ouroboros's per-round digest and running
token ledger; `-q` gives a direct proven-plan return; `-vvv` shows full reasoning, grounding
citations, and the verifier transcript.

## Step 0 — Ticket check & track the pipeline

**First, ask the user once whether this work already has a Jira ticket** — e.g. "Is there an
existing Jira ticket for this, or should I file one at the end?" Record the answer; it sets the
final-phase gate:
- A ticket exists / is named → **read it first.** Fetch it via the Atlassian MCP (`getJiraIssue`)
  and pull its title, description, and any shared/attached files — that content is the starting
  input for Phase 1's Research sub-phase instead of eliciting cold. That ticket is also the home
  for the work → the final phase will NOT create a new one (it may update it, only if the user asks).
- None exists → do not create one now. Note it and **create it later, in the final phase**, from
  the finished plan + task specs.

Then create a todo with five items — "Phase 1: research & plan", "Phase 2: prove (ouroboros)",
"Phase 3: decompose into task specs", "Phase 4: build & gate each task", "Phase 5: file ticket" —
and mark each in_progress/complete as you go, so the sequence survives each phase's own instructions
and no phase is silently skipped. Mark Phase 5 skipped, not complete, if a ticket was already
provided.

## Resolving the tiers

Invoke each tier by its **fully-qualified** name where one exists (bare names have failed to
resolve for Hermes-native skills before). Use whichever is installed in this environment:

- ouroboros → `bacon:ouroboros` (personal) or `ouroboros:ouroboros` (org marketplace) — Hermes-
  native, unchanged, invoked the normal way.
- claude-code → `claude-code` (Hermes-bundled — this is a Hermes skill, not a Claude Code plugin;
  invoke it directly by name). Its job is only to remind you of the `claude -p ...` invocation
  pattern — Research/Plan/Task-Decompose don't "invoke a skill" for their actual work so much as
  follow this skill's documented shell-out pattern via the `terminal` tool.
- Inside the subprocess this spawns: `superpowers:brainstorming` (Plan tier) and
  `superpowers:write-plan` (Task-Decompose tier) — these are Claude Code plugin skills, resolved
  by that separate process's own plugin auto-trigger matching (natural-language description match,
  not a confirmed `--skill` flag). Construct the prompt so its wording matches what each skill's
  own description says it triggers on (see harness.md's prompt-construction guidance) — if the
  wording doesn't land, the subprocess just reasons directly instead, which is a silent
  degradation, not a hard failure. Verify this once `superpowers` is actually installed, against
  the installed plugin's real trigger phrasing.
- jira-ticket → `jira-ticket:jira-ticket` (only needed if the final phase fires).

If a required tier's underlying mechanism isn't installed (e.g. `claude` CLI missing, or
`superpowers` not installed on his personal account), tell the user and stop — architect
orchestrates these tiers, it does not reimplement them. The exception is jira-ticket: it is only
needed when the final phase fires, so if it is absent, run Phases 1–4 and tell the user the ticket
step needs the jira-ticket skill rather than hand-rolling ticket creation.

## Phase 1 — Research (Fable) → Plan (Opus)

Two sub-phases, both crossing into the separate `claude` CLI subprocess ecosystem (see "Two
separate agent ecosystems" above). Full detail — exact shell invocation, JSON parsing, fallback
chain, front-loading requirement — lives in `/mnt/www/ai-tools/harness/harness.md`'s "Plan /
Task-Decompose mechanism" section; summary here:

**1a. Research.** Shell out via `terminal` (per the `claude-code` skill's print-mode pattern) to
`claude -p "<research directive>" --model <fable-model-id> --output-format json --max-turns <N>`
— or, when Step 0 found an existing ticket, seed the directive with the ticket's title/description/
shared files instead of starting cold. This subprocess just gathers and reports facts — codebase
reads, doc lookups, "does this already exist" — it never makes the design decision. Its output
must be **thorough enough that Phase 1b's single invocation never needs to ask a clarifying
question** — front-load everything Plan will need, because this subprocess is one-shot, not a
back-and-forth conversation. Write the parsed `result` field to
`/mnt/www/.plans/<slug>/research-findings.md`. Apply the fallback chain (harness.md) if Fable is
unavailable or Anthropic is unreachable entirely — note that the second fallback (Anthropic
unreachable) changes the *mechanism*, not just the model: it becomes a plain local `delegate_task`
child running `deepseek-r1:32b-65k`, not a `claude` CLI subprocess at all.

**1b. Plan.** Pipe the research-findings file as context into a second subprocess call:
`cat /mnt/www/.plans/<slug>/research-findings.md | claude -p "<plan directive — instructs the
subprocess to invoke superpowers:brainstorming on this input, and explicitly: 'do not ask
clarifying questions — if something is genuinely uncertain, make the best-supported assumption
and flag it inline as #PLAN_UNCERTAINTY instead'>" --model <opus-model-id> --output-format json
--max-turns <N>`. Write the parsed result to `/mnt/www/.plans/<slug>/design-draft.md`. Record the
`session_id` in case a same-tier follow-up is needed (`--resume <id>`) — but prefer getting the
directive right the first time over relying on follow-up turns, since each turn is a fresh billed
subprocess call.

Do not proceed to Phase 2 until `design-draft.md` exists and the user has approved it (present it,
same checkpoint discipline the old brainstorming-in-Hermes flow used).

## Phase 2 — Prove (ouroboros, the gate) — UNCHANGED

Invoke the ouroboros skill, pointing it at `design-draft.md` and forwarding the active verbosity
flag (default `-v`). Ouroboros ingests the design doc as its requirements source, grounds every
load-bearing claim, attacks assumptions, runs its cross-model verification, and writes a `PLAN.md`
with a `## Status` and `## Verification`. Gate on the `PLAN.md` `## Status` (read the file, don't
infer):

- `proven` / `CERTIFIED` → go to Phase 3.
- `provisional` → tell the user no foreign verifier certified it; proceed only on their ack.
- `deadlocked`, or any open `preference` questions remain → surface them to the user; once
  answered, re-run Phase 2. Never advance an unproven plan.

Since Phase 1b was Opus-authored, ouroboros's Phase 5 verifier should default to `llama3.3:70b`
(preserves genuine cross-model independence — Opus judging its own plan would be a weaker check).

## Phase 3 — Break into task specs (Task-Decompose, Sonnet)

Shell out via the same `claude` CLI subprocess mechanism as Phase 1, this time pointed at the
ouroboros-certified `PLAN.md`: `cat <PLAN.md path> | claude -p "<decompose directive — instructs
the subprocess to invoke superpowers:write-plan on this input, producing task specs using the
templates at /mnt/www/ai-tools/harness/templates/task-spec-template.md and spike-template.md
(the subprocess has its own file-read tools — point it at the paths rather than inlining the
templates into this prompt), applying the Spike-vs-Full-Spec decision rule from harness.md>"
--model <sonnet-model-id> --output-format json --max-turns <N>`. Write each resulting task spec to
its own file under `/mnt/www/.plans/<slug>/tasks/`. Task creation is meant to be cheap and
mechanical here — ouroboros already did the hard adversarial work upstream, per his framing.

## Phase 4 — Build (Worker, local) & gate — NEW

For each task spec produced in Phase 3:

1. Switch the active model to `devstral:65k` (or `gemma3:27b-65k` for non-code writing/tool-use
   tasks) **immediately before** the `delegate_task` call — children inherit whichever model the
   parent is actively running at spawn time when `delegation.model`/`provider` are left unset in
   config.yaml (they are, deliberately — see `delegation.yaml`'s comments). This is the same
   explicit-switch-before-delegating pattern this skill and ouroboros already use for their own
   single-model needs, just applied per `delegate_task` call.
2. Issue one `delegate_task(goal=..., context=<the full task spec file content>, role="leaf",
   toolsets=["terminal","file"])` call per task spec — never batch multiple task specs into one
   call, since each Worker needs to start with **zero conversation history**, per the task-spec
   template's own framing ("this section IS the context, not a pointer to it").
3. Switch back to `deepseek-r1:32b-65k` once the Worker fan-out for this task is done.
4. Run the **Worker Output Gate** (harness.md's Verify section, full checklist) via a fresh
   Task-Decompose (Sonnet) subprocess call — same claude CLI mechanism as Phase 3, given the
   Worker's diff/output plus the gate checklist plus the original task spec as context — before
   marking the task done. Escalate to Phase 1b (Plan tier) on any of harness.md's escalation
   triggers (diff too large, compliance/OWASP surface touched, a gate item failed, a
   `#PLAN_UNCERTAINTY`/`#PATH_DECISION` still contested, Worker expressed low confidence).

Then go to Phase 5.

## Phase 5 — File as ticket (jira-ticket), if none was provided

Conditional gate, decided by the Step 0 ticket check:

- **A ticket WAS provided** (referenced when the session opened, or named by the user) → that
  ticket is the home for this work. Do **not** create a new one. Stop after Phase 4, or — only if
  the user asks — hand the proven `PLAN.md` + task specs + build results to jira-ticket to *update*
  that ticket. Mark the Phase 5 todo skipped.
- **No ticket was provided** → treat the session as planning for a new ticket. Invoke the
  jira-ticket skill, passing the proven `PLAN.md`, the Phase 3 task specs, and the Phase 4 build/
  gate results, to author a parent issue holding the plan plus the completed subtasks. jira-ticket
  owns *how* the ticket is authored (self-contained; no local-path or internal-tooling-jargon
  dependence) and confirms the title/body with the user before the outward write. Architect only
  decides **whether** to file and forwards the artifacts.

Then **STOP.**

## What architect owns vs delegates

Owns: the phase sequence, the per-phase user checkpoints, passing artifact paths forward, the
verbosity flag, the `PLAN.md` status gate, the ticket-presence gate, the explicit model-switch
before each Worker `delegate_task` call, and the Worker Output Gate's escalation decision. Delegates
everything else — research, elicitation/design, proving, task breakdown, actual implementation,
and ticket authoring — to the tiers/skills themselves, unchanged in their own internal logic.
