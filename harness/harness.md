# Harness — Tiered AI-Delegation Pipeline (`ai-tools/harness`)

*Companion to `/mnt/www/.plans/harness/hermes-harness-2026-07-02.md` (the
unchanged 5-phase Orient/Ground/Plan/Build/Verify/Record doc) — this document
describes what runs *inside* that doc's Plan/Build phases when a task is big
enough to warrant more than one model's worth of reasoning. Small tasks still
just use the five phases directly.*

*Not a copy of `/mnt/www/safe-agentic-workflow/` (an 11-role SAFe
team-coordination template, left untouched, reference-only) or of any
employer Claude Code Team harness — this is an original, one-person,
tiered-model pipeline.*

---

## Two separate agent ecosystems — read this first

This design spans two runtimes that must not be conflated:

1. **Hermes' own skills** (`architect`, `ouroboros`, `git-conflict`, `tdd`,
   `handoff`, and the Hermes-bundled `claude-code` skill) — invoked by
   Hermes' native skill-loading mechanism, running on whichever local model
   is currently active.
2. **Claude Code's plugin skills** (`superpowers:brainstorming`,
   `superpowers:write-plan`) — these run inside a **separate `claude` CLI
   subprocess**: a child OS process with its own Claude Code session and its
   own OAuth/session state, spawned by Hermes' `terminal` tool. They are
   never invoked "from inside Hermes" the way `ouroboros` is.

Phases that cross this boundary (Research, Plan, Task-Decompose) construct a
prompt, shell out via the bundled `claude-code` skill's documented pattern,
and read back that subprocess's JSON result as plain text context for the
next phase. The Verify phase (ouroboros) never crosses this boundary — it
stays entirely native to Hermes, unchanged.

---

## Context Protocol — mandatory for every tier and every agent

The git-tracked context tree at `ai-tools/harness/context/CONTEXT.md`
(`/mnt/www/ai-tools/harness/context/` from Hermes) is the shared source of
truth for all AIs in this workspace — every Claude Code account, Hermes and
all its delegated tiers, and (via the `~/www/CONTEXT.md` distillation)
Claude Desktop. Its conventions (index format, issue-file naming,
Desktop-sync checkboxes) are documented in its own top file. Non-negotiable
rules for this pipeline:

- **Research tier** starts at the context tree and drills into the relevant
  project/feature folder *before* touching the codebase; its findings report
  must note anything that contradicts or extends what the tree says.
- **Plan and Task-Decompose tiers** receive the relevant context/ paths in
  their piped input; task specs cite them under Pattern References.
- **Orchestrator (`architect`)**, at task completion (after the Worker
  Output Gate passes), writes durable outcomes back into the right
  context/ folder — new facts, decisions, and discovered issues as
  `<slug>-<epoch>-<date>.md` leaf files or index updates, with changed
  index lines reverted to `- [ ]` up the chain. This is in addition to,
  not instead of, the 5-phase doc's Phase 5 (OpenViking trajectory).
- **Workers** don't write to context/ themselves (they implement against a
  spec); anything durable they surface flows back through the gate report.

This mirrors Hermes' Five Phases: Phase 0 (Orient) reads the tree, Phase 5
(Record) writes it — the tiers above are how the same obligation lands when
work is delegated instead of done inline.

---

## Tiers

| Tier | Model | Mechanism | Role |
|---|---|---|---|
| **Research** | `claude-fable-5`, personal OAuth | `claude` CLI subprocess (print mode) | Fact-gathering, codebase/doc investigation. Never makes the planning decision, just surfaces what's true. Output must be thorough enough that the Plan tier's single, one-shot invocation never needs to ask a clarifying question. |
| **Plan** | `claude-opus-4-8`, via subprocess invoking `superpowers:brainstorming` | `claude` CLI subprocess | Takes Research's findings, drafts the actual design decision. |
| **Verify** | Existing `ouroboros` skill, unchanged | Hermes-native (not a subprocess) | Adversarial debate loop (local `deepseek-r1:32b-65k` Proposer/Challenger) until stable, then cross-model certification. |
| **Task-Decompose** | `claude-sonnet-5`, via subprocess invoking `superpowers:write-plan` | `claude` CLI subprocess | Turns the ouroboros-hardened plan into task specs (`templates/`). Also re-invoked, fresh and stateless each time, to run the Worker Output Gate on every Worker result. |
| **Worker** | `devstral:65k` (code) / `gemma3:27b-65k` (non-code writing, tool-use, fallback) | Genuine Hermes `delegate_task`, `role="leaf"` | Implements against a spec; never plans its own approach. |
| **Orchestrator** | Existing `architect` skill, updated | Hermes-native, local top-level model | Sequences the tiers with checkpoints, same "conductor not coupler" philosophy. |

**Fallback chain** (every Claude-dependent tier — Research, Plan, Task-Decompose):
1. Named model unavailable/deprecated → fall back to Opus or higher (current frontier).
2. Anthropic entirely unreachable → fall back to `deepseek-r1:32b-65k`. **This
   fallback changes the mechanism, not just the model name**: it becomes an
   ordinary local `delegate_task` child (Hermes-native), not a `claude` CLI
   subprocess at all — there is no local equivalent of the subprocess
   boundary, so the fallback re-enters Hermes' own ecosystem entirely.

**Two separate Claude entry points, never conflated:** the personal OAuth
Pro/Max subscription (flat-rate, used freely by Research/Plan/Task-Decompose,
via the `claude` CLI) versus the pre-existing metered `localhost:4001`
Anthropic proxy (pay-per-token, keeps its "ask first, costs money" rule,
never a delegation default).

---

## Prerequisite: `superpowers` installed on Isaac's personal account, *inside WSL*

Confirmed this session: `claude plugin list` on the Windows side already
returns "No plugins installed" — only the marketplace is registered, not the
plugin itself, and that's the *Windows* side. The mechanism above needs the
`claude` CLI **and** the `superpowers` plugin installed inside the WSL
environment that actually runs Hermes (not just Windows), under whichever
account will invoke it (see the open design decision below — this determines
*which* account's `~/.claude` needs the plugin and the login).

```
npm install -g @anthropic-ai/claude-code   # if not already present in WSL
claude   # first run — completes browser OAuth login (personal account)
/plugin marketplace add obra/superpowers-marketplace
/plugin install superpowers@superpowers-marketplace
```

**This step is entirely manual — hand to Isaac.** The OAuth browser flow is
inherently interactive; no agent can complete `claude login` on his behalf.

---

## Credential Boundary Check — concrete mechanism

Confirmed from the bundled `claude-code` skill's own docs: `claude auth
status` returns identity information (`claude auth status` for a quick
human-readable check). Run before first use, and after any auth-adjacent
update:

```
claude auth status
```

Confirm it resolves to Isaac's *personal* account (`isaacbacon1@gmail.com`),
not his employer's Claude Code Team seat. If ambiguous, don't trust a cached
token — `claude login` again explicitly (interactive, hand to Isaac).

---

## OPEN DESIGN DECISION — hermes-uid airgap vs. `claude` CLI OAuth network access

**Not resolved by prior research — flag clearly, don't silently default.**
This project's standing rule (established via the Telegram/tinyproxy work) is:
*`hermes`'s uid must never touch the internet directly* — every existing
integration is a local relay/proxy bound to loopback or the WSL gateway IP.

Hermes' own `terminal` tool executes commands **as the `hermes` OS account**.
That means a naive implementation of the Research/Plan/Task-Decompose
subprocess calls — `terminal(command="claude -p ...")` — would be `hermes`-uid
traffic going straight to `api.anthropic.com`, which violates the airgap rule
as written. Two ways to resolve this, either is legitimate, but it needs an
explicit choice, not a silent default:

- **Option A (recommended) — matches existing precedent:** point the `claude`
  CLI's outbound traffic through the already-running local proxy (`tinyproxy`
  on `127.0.0.1:8889`, same one Telegram uses) via
  `HTTPS_PROXY=http://127.0.0.1:8889` set in the environment for these
  specific `terminal` calls. `hermes` still never touches the internet
  directly; the relay does. `claude login`'s one-time OAuth flow would then
  also need to happen as the `hermes` account (or its config copied in
  afterward) — a one-time, human-witnessed exception to the "never touch the
  internet directly" rule for the browser handshake specifically, same
  category as other narrow, verified exceptions already made this project.
- **Option B:** run these specific `claude` CLI calls under `zak`'s own
  account (the normal WSL user, which keeps unrestricted internet) instead
  of via Hermes' `terminal` tool as `hermes` — requires
  either a `terminal` tool user-switch capability (unconfirmed whether one
  exists) or moving this call outside Hermes' own process tree entirely.
  Avoids the airgap-exception question but is a bigger mechanical change.

**Recommendation:** Option A — reuses an already-verified, already-working
pattern instead of inventing a new mechanism. This is Isaac's decision to
make explicitly before Research/Plan/Task-Decompose go live; don't default
to it silently.

---

## The Plan/Task-Decompose subprocess mechanism — corrected, concrete

**Not ACP** (Claude Code doesn't speak it natively; the one real adapter
rejects OAuth Pro/Max tokens). **Not MCP** (Hermes' own engineers excluded
`delegate_task`-shaped work from MCP exposure — a stateless callback can't
drive a mid-loop agent). **Not a bespoke new Python wrapper** — Hermes
already ships this as the bundled `skills/autonomous-ai-agents/claude-code`
skill, confirmed present in the v0.18.0 install. The mechanism is: invoke
that skill (a Hermes-native skill, called by name — it is not a Claude Code
plugin skill, do not confuse the two), which documents exactly the
`terminal(command="claude -p '<prompt>' --output-format json ...")` pattern,
JSON result shape (`result`, `session_id`, `total_cost_usd`, `subtype`), and
`--resume <session-id>` follow-up mechanism this design needs.

**Concrete pattern:**

```
# Research
terminal(command="claude -p '<research directive>' --model <fable-model-id> \
  --output-format json --max-turns 20", timeout=180)
# → parse .result, write to /mnt/www/.plans/<slug>/research-findings.md

# Plan — front-load Research's output as piped context
terminal(command="cat /mnt/www/.plans/<slug>/research-findings.md | claude -p \
  '<plan directive: invoke superpowers:brainstorming on this input; do NOT ask \
  clarifying questions — make the best-supported assumption and flag it inline \
  as #PLAN_UNCERTAINTY instead>' --model <opus-model-id> --output-format json \
  --max-turns 30", workdir="/mnt/www/.plans/<slug>", timeout=300)
# → parse .result, write to /mnt/www/.plans/<slug>/design-draft.md
# → note .session_id in case a same-tier --resume follow-up is genuinely needed
```

**Why the front-loading requirement matters:** `superpowers:brainstorming`/
`write-plan` are normally interactive, elicitation-style skills that ask
clarifying questions back. A one-shot `-p` subprocess call cannot have that
back-and-forth. The fix is architectural, not a workaround: **the Research
tier's output contract is "thorough enough that Plan's single invocation
never needs to ask,"** and the Plan/Task-Decompose directive explicitly
instructs the subprocess to convert any would-be clarifying question into a
`#PLAN_UNCERTAINTY` tag instead of stalling — which is exactly what the
Worker Output Gate and escalation triggers already exist to catch downstream.
This reuses the hand-off-tag convention rather than inventing a second
mechanism for "things the model wasn't sure about."

**Trigger-phrase risk (still open, cannot verify until `superpowers` is
installed):** there's no confirmed `--skill <name>` CLI flag — trigger relies
on the subprocess's own natural-language description matching. Verify the
constructed directive's wording actually lands on `superpowers:brainstorming`/
`write-plan` once the plugin is installed; if it doesn't, the subprocess
still returns a result, just without that skill's structure — a silent
degradation to watch for, not a hard failure.

**Task-Decompose reading the templates directly:** rather than inlining
`task-spec-template.md`/`spike-template.md` content into the shell prompt
(escaping risk, token waste), set `workdir` so the subprocess can `Read` the
template files itself — the `claude` CLI subprocess has full file-tool
access, unlike a `delegate_task` leaf child.

---

## Model routing under a global-only `delegation:` block

Confirmed directly from Hermes source: `delegation:` has no per-role
schema — it's one global block, plus an optional single
`model`/`provider` override applied uniformly to *every* `delegate_task`
child. Multiple tiers in this pipeline need different local models
simultaneously (Worker = `devstral:65k`; ouroboros's internal
Proposer/Challenger = `deepseek-r1:32b-65k`; ouroboros's Phase 5 verifier =
`llama3.3:70b`). The only mechanism that reconciles this:

**Leave `delegation.model`/`provider` unset in config.yaml.** Per Hermes'
own docs, subagents use the same model as the parent when no override is
given — so each tier's model comes from an explicit `/model <name>` switch
on the parent, done immediately before that specific `delegate_task` call,
then switched back after. This is the same convention `architect`/`ouroboros`/
`tdd` already use (switch once before the whole skill runs) — applied here at
the granularity of "before this one delegate_task call" instead. Setting
`delegation.model` globally would silently override every tier uniformly and
break this.

---

## Flat star topology, not nested delegation

Every tier delegates as `role="leaf"`; none sub-delegate. The orchestrator
(`architect`, running on Hermes' local top-level loop) issues sibling
`delegate_task` calls in sequence, passing each tier's output forward as the
next tier's `context`. `max_spawn_depth` stays at its default of **1** —
nothing here needs grandchildren, and the hardware (24GB VRAM, models
14-42GB) can't usefully run nested parallelism anyway. `max_concurrent_
children: 1` makes this hardware reality explicit.

---

## Task-spec formats

See `templates/task-spec-template.md` and `templates/spike-template.md`
(verbatim, adapted from `safe-agentic-workflow`'s Method 1/Method 2, sized
for one agent).

**Decision rule — Spike vs. Full Spec:** default to Spike whenever uncertain.

- **Spike**: resolving a `#PLAN_UNCERTAINTY` the Plan tier flagged, or a
  small/low-risk/single-file change with an existing pattern already found
  in Research.
- **Full Spec**: multi-file/module change, new/changed interface or schema,
  anything on the compliance floor (Loi 25 > PIPEDA > GDPR > HIPAA > CCPA) or
  OWASP-relevant surface, or Research found no reusable pattern.

---

## Verify — Worker Output Gate & escalation

**Worker Output Gate** (Task-Decompose tier runs this routinely, via a
fresh stateless `claude` CLI subprocess call per Worker output, before
reporting "done"):

```markdown
- [ ] Every Acceptance Criteria checkbox met
- [ ] No secrets/credentials/API keys committed or logged
- [ ] Full test suite passes — TDD Red→Green→Refactor evidence present
- [ ] No dead/commented-out code
- [ ] No hardcoded values that should be config/constants
- [ ] Error handling covers realistic failure modes
- [ ] Relevant edge cases tested
- [ ] No PII in test fixtures or logs (compliance floor: Loi 25 > PIPEDA > GDPR > HIPAA > CCPA)
- [ ] Parameterized queries only
- [ ] OWASP Top 10 pass for anything touching input handling, auth, or storage
- [ ] Every #EXPORT_CRITICAL constraint respected
- [ ] Every #PLAN_UNCERTAINTY validated or explicitly flagged back
- [ ] Diff read end-to-end, not just test output skimmed
```

**Escalation triggers** (Task-Decompose → Plan tier; same set governs both
Worker-output verify and ouroboros Phase 5 convergence judgment):

```markdown
- [ ] Diff exceeds ~150 changed lines (starting point, adjust to codebase norms)
- [ ] Touches the compliance floor or OWASP Top 10 surface
- [ ] Any Gate Checklist item failed on Worker's first attempt
- [ ] A #PLAN_UNCERTAINTY or #PATH_DECISION still contested after Worker's attempt
- [ ] Worker expresses low confidence or contradicts a Pattern Reference without explaining why
```

**ouroboros Phase 5 default:** `llama3.3:70b` when the plan under test was
Plan-tier(Opus)-authored (preserves cross-model independence); becomes
Task-Decompose(Sonnet) for routine convergence judgment on locally-authored
plans (`deepseek-r1:32b-65k` standalone `architect` runs outside this
pipeline), escalating to Plan tier on the same trigger set above.
`llama3.3:70b` also stays available as an explicit fully-local, zero-cloud-
call opt-in regardless of plan authorship.

---

## `architect` — orchestrator (§5 rewrite, full content in `skills/architect/SKILL.md`)

Targeted rewrite, not a rebuild — same "conductor not coupler" philosophy.
Summary of what changed (full content lives in the skill file itself):

- Model-switch instruction: `deepseek-r1:32b-65k` (matches its existing
  ouroboros-loop role), not `deepseek-r1:14b`. Switch-back corrected from
  `qwen2.5:14b` to `gemma3:27b-65k` — the fleet's documented ambient default,
  since qwen models are explicitly banned elsewhere in this stack.
- Phase 1 (was: brainstorming) → Research (Fable subprocess) → Plan (Opus
  subprocess invoking `superpowers:brainstorming`).
- Phase 2 (ouroboros) → unchanged mechanically.
- Phase 3 (was: writing-plans) → Task-Decompose (Sonnet subprocess invoking
  `superpowers:write-plan`), producing task specs from `templates/`.
- New Phase 4 → Worker dispatch (one `delegate_task` per task spec, explicit
  model-switch before each call) + Worker Output Gate before marking done.
- Phase 5 (jira-ticket) stays dormant, renumbered from 4→5 to make room.

Full Spec ceremony applies to this rewrite itself, per the approved plan —
multi-file, behavior-changing edit to a skill Isaac actively relies on.

---

## Skill registration — corrected mechanism

**Not** per-skill symlinks under `~/.hermes/.hermes/skills/local/<name>` —
that path convention doesn't exist in Hermes 0.18.0. The real mechanism:
`skills.external_dirs:` in `config.yaml`, one entry (`/mnt/www/ai-tools/skills`),
recursively scanned for `SKILL.md` at any depth, merged live (no restart,
no caching gotcha), local-name-wins on collision. `ai-tools/harness/sync-
skills.sh`'s job is now: idempotent check-and-patch of that one config key,
not a copy or per-skill symlink loop.

**Location correction, found during implementation:** the approved plan put
this script at `~/.hermes/sync-skills.sh`, assuming that path was writable by
Isaac's normal WSL account `zak`. Verified false: `/home/zak/.hermes/` (the
whole tree, not just the nested `.hermes/.hermes/`) is owned by the `hermes`
service account, mode 755 — `zak` can traverse/read it but cannot write
into it (confirmed via a live `cp` attempt: Permission denied). The script
lives instead at `ai-tools/harness/sync-skills.sh` — writable by `zak`,
version-controlled with the rest of the harness. It edits a file inside
`hermes`'s locked home directory, so it must be *run* as (or via `sudo -u`)
the `hermes` account:

```
sudo -u hermes bash /mnt/www/ai-tools/harness/sync-skills.sh
```

Isaac runs this himself, an agent cannot execute it against the live install.

---

## Files touched

- `ai-tools/harness/README.md`, `harness.md`, `templates/task-spec-template.md`,
  `templates/spike-template.md`, `config/delegation.yaml` (all new)
- `.plans/harness/hermes-harness-2026-07-02.md` — one new "Harness Tiers"
  section appended after "Sync Instructions"; nothing else in that file touched
- `ai-tools/skills/architect/SKILL.md` — targeted rewrite
- `ai-tools/skills/git-conflict/SKILL.md` — real content, was a 14-line stub
- `ai-tools/harness/sync-skills.sh` — new, external_dirs-based, not symlink-based
  (relocated from the originally-planned `~/.hermes/sync-skills.sh` — that
  path turned out not to be writable by `zak`; see the Skill registration
  section above)
- `~/.hermes/.hermes/config.yaml` — NOT touched by this task; `delegation.yaml`
  is a reviewable sketch only, merged in by Isaac (via `hermes`) once reviewed

---

## What can be verified now vs. what's blocked

**Verifiable now (file-level, no live Hermes needed):**
- Every listed file exists at the specified path with the specified content
- This doc's cross-reference resolves (the appended section in
  `hermes-harness-2026-07-02.md` points at a `harness.md` that actually exists)
- `README.md`'s tree matches what was actually written
- `architect/SKILL.md` still reads as "conductor not coupler" — no planning
  logic invented inline, every phase still delegates to a named tier/skill
- `git-conflict/SKILL.md` has proper `---`-delimited frontmatter matching
  `architect`/`ouroboros`'s style (was previously malformed/missing)
- `sync-skills.sh` is idempotent by inspection (re-running its logic against
  a config.yaml that already has the entry is a documented no-op) and
  preserves existing comments (patches lines, doesn't round-trip through a
  full YAML parse+dump)
- Internal consistency: every model name/tier reference in this doc,
  `delegation.yaml`, and the `architect` rewrite agrees with the Model Fleet
  table in `hermes-harness-2026-07-02.md`

**Blocked pending the separate base-infra work (per the handoff's own scope fence):**
1. Credential Boundary Check (`claude auth status`) — needs `claude` CLI +
   `superpowers` actually installed and logged in inside WSL
2. `sync-skills.sh`'s actual execution against the live, locked `config.yaml`
   (needs Isaac, running as/via `hermes`)
3. A trivial Spike delegating to Worker (`devstral`) end-to-end
4. A full Research→Plan→Verify→Task-Decompose→Worker→Gate cycle, including
   confirming the gate catches a deliberately-introduced issue
5. The fallback chain (invalid model name → Opus; Anthropic unreachable →
   local)
6. `architect`'s rewritten phases actually calling the right tier at each
   step, live, and still gating correctly on `PLAN.md` status
7. The hermes-uid-airgap-vs-OAuth decision above — genuinely unresolved,
   needs Isaac's choice before Research/Plan/Task-Decompose go live at all
