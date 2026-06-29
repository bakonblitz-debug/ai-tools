---
name: architect
description: >
  End-to-end planning pipeline that takes a rough idea to a vetted, task-broken implementation
  plan by running standalone skills in sequence: brainstorming (elicit intent and draft a
  spec), ouroboros (adversarially prove and certify that plan), then writing-plans (break the
  proven plan into tasks). A fourth jira-ticket phase (file the plan as a ticket) ships dormant
  in this build — enable it per the skill body if you have Jira.
  Use when you want the WHOLE cycle in one guided flow. Trigger on:
  full planning pipeline, take my idea to a proven task list, brainstorm then prove then break
  it down, run the whole elicit-prove-plan flow, end-to-end planning from idea to tasks.
  Do NOT
  trigger on a bare "plan X" / "design X" / "architect X" — for proving an existing plan use the
  ouroboros skill directly, and for intent elicitation alone use the brainstorming skill.
  Architect is a thin conductor that sequences these and gates between them; each skill it
  calls also works standalone without it.
---

# Architect — Idea → Proven Plan → Tasks

A conductor, not a coupler. Architect runs three core skills in order — plus a dormant fourth
(ticketing, disabled in this build) — and checks in with the user between them. It adds no
planning logic of its own and owns no shared file format — each skill writes its own native
artifact, and architect passes the path forward.

## Jira ticketing — DISABLED in this build

This personal build runs **without** Jira integration. Default behavior:
- **Skip the Step 0 ticket check** — do not ask whether a ticket exists, and use a **three-item**
  todo (Phases 1–3).
- **Skip Phase 4** — do not file a ticket; the pipeline ends at Phase 3 (the task list).

The ticket machinery below (the Step 0 ticket check and Phase 4) is kept as dormant,
ready-to-enable reference — good bones. If you move into an org with Atlassian/Jira, turn it on by
following the Step 0 ticket check and Phase 4 exactly as written. Until enabled, treat those two
sections as inert.

## Operating mode

Run in **default mode, not plan mode.** The pipeline produces several native planning artifacts —
brainstorming's spec under `docs/superpowers/specs/`, ouroboros's `PLAN.md`, and the task list —
and plan mode blocks any write outside the single plan file, so Phase 1 alone would stall.
Architect only ever writes *planning* artifacts, never source, so default mode is safe. Reserve
plan mode for the *implementation* the task list describes — not for the planning.

## Verbosity

Architect accepts a verbosity flag — `-q` / `-v` / `-vvv`, **default `-v`** — and forwards it to
the ouroboros call in Phase 2. So by default you see ouroboros's per-round digest and running
token ledger; `-q` gives a direct proven-plan return; `-vvv` shows full reasoning, grounding
citations, and the verifier transcript.

## Step 0 — Ticket check & track the pipeline

**First, ask the user once whether this work already has a Jira ticket** — e.g. "Is there an
existing Jira ticket for this, or should I file one at the end?" Record the answer; it sets the
Phase 4 gate:
- A ticket exists / is named → **read it first.** Fetch it via the Atlassian MCP (`getJiraIssue`)
  and pull its title, description, and any shared/attached files — that content is the starting
  input for the pipeline (Phase 1 refines what the ticket already states instead of eliciting
  cold), per the jira-ticket "the ticket is the plan/memory" principle. That ticket is also the
  home for the work → Phase 4 will NOT create a new one (it may update it, only if the user asks).
- None exists → do not create one now. Note it and **create it later, in Phase 4**, from the
  finished plan + task list.

Then create a todo with four items — "Phase 1: elicit", "Phase 2: prove", "Phase 3: tasks",
"Phase 4: file ticket" — and mark each in_progress/complete as you go, so the sequence survives
each sub-skill's own instructions and no phase is silently skipped. Mark Phase 4 skipped, not
complete, if a ticket was already provided.

## Resolving the sub-skills

Invoke each sub-skill by its **fully-qualified** name (bare names have failed to resolve). Use
whichever is installed in this environment:

- brainstorming → `superpowers:brainstorming`
- ouroboros → `bacon:ouroboros` (personal) or `ouroboros:ouroboros` (org marketplace)
- writing-plans → `superpowers:writing-plans`
- jira-ticket → `jira-ticket:jira-ticket` (only needed if Phase 4 fires)

If a required skill isn't installed, tell the user and stop — architect orchestrates these skills,
it does not reimplement them. The exception is jira-ticket: it is only needed when Phase 4 fires,
so if it is absent, run Phases 1–3 and tell the user the ticket step needs the jira-ticket skill
rather than hand-rolling ticket creation.

## Phase 1 — Elicit & draft (brainstorming)

Invoke the brainstorming skill on the user's idea — or, when Step 0 found an existing ticket, on
the ticket's title, description, and shared files as the seed, so elicitation refines what the
ticket already states rather than starting from nothing. Let it run its own flow — it elicits intent,
explores approaches, writes its design spec to its native
`docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`, and gets the user's approval. **Do not try
to redirect where it writes**; that path is part of the skill. When it finishes, note the spec
file path. Brainstorming's terminal step normally hands straight to writing-plans — here, *you*
(architect) take over instead and go to Phase 2, because the proving gate comes before tasks. Do
not proceed until the spec exists and the user has approved it.

## Phase 2 — Prove (ouroboros, the gate)

Invoke the ouroboros skill, pointing it at the approved spec file and forwarding the active
verbosity flag (default `-v`). Ouroboros ingests the design doc as its requirements source,
grounds every load-bearing claim, attacks assumptions, runs its cross-model verification, and
writes a `PLAN.md` with a `## Status` and `## Verification`. Gate on the `PLAN.md` `## Status`
(read the file, don't infer):

- `proven` / `CERTIFIED` → go to Phase 3.
- `provisional` → tell the user no foreign verifier certified it; proceed only on their ack.
- `deadlocked`, or any open `preference` questions remain → surface them to the user; once
  answered, re-run Phase 2. Never advance an unproven plan.

## Phase 3 — Break into tasks (writing-plans)

Invoke the writing-plans skill on the proven `PLAN.md` to produce the implementation task list.
Then go to Phase 4.

## Phase 4 — File as ticket (jira-ticket), if none was provided

Conditional gate, decided by the Step 0 ticket check:

- **A ticket WAS provided** (referenced when the session opened, or named by the user) → that
  ticket is the home for this work. Do **not** create a new one. Stop after Phase 3, or — only if
  the user asks — hand the proven `PLAN.md` + task list to jira-ticket to *update* that ticket.
  Mark the Phase 4 todo skipped.
- **No ticket was provided** → treat the session as planning for a new ticket. Invoke the
  jira-ticket skill, passing the proven `PLAN.md` and the Phase 3 task list, to author a parent
  issue holding the plan plus the gated subtasks. jira-ticket owns *how* the ticket is authored
  (self-contained; no local-path or internal-tooling-jargon dependence) and confirms the
  title/body with the user before the outward write. Architect only decides **whether** to file
  and forwards the artifacts.

Then **STOP.** Architect does not build, and does not invoke execution or feature-dev — those are
separate, optional steps the user takes when ready.

## What architect owns vs delegates

Owns: the phase sequence, the per-phase user checkpoints, passing artifact paths forward, the
verbosity flag, the `PLAN.md` status gate, and the ticket-presence gate (whether Phase 4 files a
new ticket). Delegates everything else — elicitation, proving, task breakdown, and ticket
authoring — to the four standalone skills, unchanged.
