---
name: ouroboros
description: >
  Produce a rigorously stress-tested implementation or architecture plan through an adversarial
  two-agent loop that refines a plan until both agents agree it's complete, then certifies it with
  an independent cross-model verifier. Use this whenever the user asks to "plan", "design",
  "architect", or "think through" any non-trivial change before writing code — and especially when
  they say ouroboros, want a "proven plan", want a plan challenged/stress-tested, or are about to
  start work where a wrong assumption would be expensive. Trigger on: plan, design, architect,
  stress-test, prove this plan, challenge my approach, premortem, what could go wrong, de-risk.
  Runs standalone, and automatically upgrades when the Superpowers brainstorming skill (or an
  existing design doc) is present by ingesting its requirements instead of re-eliciting them.
  Prefer this over answering a planning request directly whenever the task has real risk, hidden
  assumptions, or more than one reasonable approach. Distinct from brainstorming (which elicits
  intent from the user) — ouroboros owns the gate that grounds, attacks, and certifies the plan.
---

# Ouroboros — Adversarial Planning Loop

Two isolated agents refine a single plan by attacking it until neither has anything left to add, fix, or challenge and both agree it is sound. The converged plan is then handed to an independent verifier — ideally a *different model* — that certifies it before it is called proven. The plan is the snake's body; each round eats the previous round's debate and leaves only the refined artifact.

## What this produces

A single plan document (`PLAN.md`) where every load-bearing claim is tagged `[verified]` or `[assumed]`, every open question is resolved (by grounding or by the human), every surfaced risk has an explicit disposition (mitigated or accepted-and-documented), and a verification verdict is recorded at the end. Nothing else from the debate survives — rebuttals and superseded drafts are discarded on purpose.

## Why it's built this way

The cheap failure mode of any "two agents debate" design is **false consensus**: two instances of the same model share training priors, so they can agree confidently on something wrong. Agreement therefore measures convergence, not correctness. This skill treats agreement as the *stop condition* for the loop, and a separate cross-model check as the thing that earns the word "proven." Do not collapse the two. A loop that ends on agreement alone, with no foreign verifier, is provisional — say so in the output.

The same false-consensus risk is why the skill never lets the loop **invent requirements**. Questions of user intent are routed to the human, never resolved by agreement (see Requirements intake).

## Token & freshness discipline (≤5% per session)

The constraint that keeps each call cheap is the same one that keeps it fresh and honest. A bloated context blows the budget, anchors the agent on stale framings, *and* drives hallucination — models confabulate more when reasoning over long, self-referential context full of their own prior guesses. Small, fresh, and grounded are one design, not three.

**The plan file is the only memory.** `PLAN.md` on disk is the entire persistent state. No agent holds history in context. Each round spawns *fresh* subagents that read the file, do one job, write back, and terminate. Ephemeral workers plus externalized state is what keeps every context tiny and every answer un-anchored.

**Minimal payload per call.** A subagent receives only: the current `PLAN.md`, the single challenge or question it is answering, and the specific grounded facts it needs. Never the debate transcript, never prior rounds, never the other agent's reasoning. Carrying history is the number-one budget leak and the number-one source of rut-stuck answers.

**Spend the budget on verifying, not remembering.** Trim history to zero before trimming grounding. A cap set so tight the agent can't afford to read the real code pushes it to *assume* instead of *verify* — which defeats the whole anti-hallucination point. If grounding genuinely doesn't fit 5%, the task is too big for one plan: split it, don't starve the checks.

**Targeted retrieval only.** Ground claims with surgical reads — grep the symbol, read the one function or line range, fetch the one doc section. Never read a whole file or repo into context. Bulk reads are where the budget dies. This applies to requirements intake too: explore for *questions*, not for a full mental model of the codebase.

**Token ledger + hard ceiling.** Track tokens per role per round in the workspace. If either role nears 5% of its session window, stop and escalate — do not silently truncate. Truncation manufactures exactly the half-remembered context that causes hallucination.

## Verbosity / visibility

Controls how much of the working is surfaced to the user. **Default is `-v`.** Verbosity never changes the protocol or the convergence/verification gates — it only changes what is *shown*. The token figures come from the ledger above; verbosity just surfaces it.

- **quiet** (`-q`, off) — direct return only: the final `PLAN.md` (Status, Approach, Claims, Risks, Questions, Verification). None of the debate.
- **`-v`** (default) — also surface a per-round digest: each round, the Challenger's objection (`SEVERITY` + one-line `CLAIM`), the Proposer's disposition (mitigated / accepted / rejected + reason), any new `## Questions`, and the running token ledger (per role this round + cumulative).
- **`-vvv`** — full visibility: the complete Challenger output each round (all four fields), the Proposer's rewrite rationale, every grounding citation (`file:line` / doc / run), the full per-role/per-round token ledger, and the verifier's verdict transcript.

## Requirements intake — the integration seam

A plan can only be as right as the requirements it's built on. Before the adversarial loop can attack anything, the requirements must be on the table and grounded. **The integration with brainstorming lives entirely here, and entirely as data** — a `## Questions` block in `PLAN.md` — not as a hard call into another skill. That decoupling is what lets ouroboros run by itself yet get sharper when brainstorming is installed.

### Two kinds of question

Every open question is exactly one of:

- **`preference`** — only the user can answer it (success metric, desired behavior, scope, trade-off priority). Guessing it *fabricates a requirement*. These go to the human.
- **`verifiable`** — reality can answer it (does this API exist? is that endpoint rate-limited? does the current schema allow this?). These get grounded against code/docs/a spike.

### The one rule that makes triage safe

> A question may be marked **resolved by grounding** only if the grounding subagent returns **hard evidence** — a `file:line`, a doc section, or run output. No citation → it falls through to the human queue, regardless of how it was classified.

This makes misclassification harmless. If a `preference` question is wrongly tagged `verifiable`, grounding finds nothing to cite and it ends up asked anyway. The system can waste a little effort; it can **never** confabulate a requirement.

### Where questions come from (graceful degradation)

Questions can be populated from any of three sources — all flow into the same `## Questions` block and through the same triage. Ouroboros owns the gate; brainstorming is just the best available *source*.

1. **An existing design doc** (preferred). If a Superpowers brainstorming spec exists (e.g. `docs/superpowers/specs/*-design.md`) or the user points at one, ingest its decisions as `[user-stated]` facts and its open items as questions. **Do not re-elicit what's already settled there.**
2. **The brainstorming skill, live.** If that skill is available and no spec exists yet, invoke it to generate the clarifying-question set (it is better at Socratic elicitation than this skill is), then take ownership of the answers: triage them here rather than firing every one at the user.
3. **Built-in minimal elicitation** (fallback). If neither is present, a single `Elicitor` subagent explores project context *surgically* and writes the clarifying questions itself. Degraded relative to brainstorming, but fully standalone.

In all three cases the **human only ever sees the `preference` residue** — the `verifiable` ones are answered by grounding first. That is the entire point of the merge: spend the user's attention on judgment calls, not on "go read the code."

### Questions surface mid-loop too

The Challenger's premortem (Phase 3) routinely exposes a hidden `preference` question ("what should happen when the token expires mid-request?"). When it does, the Challenger does **not** argue it internally — it appends it to `## Questions` as `open/preference` and lets it block convergence the same way an `[assumed]` claim does. This is a second human-escalation channel alongside `DEADLOCK`: *deadlock* = "we can't resolve this by reasoning"; *open preference* = "only you can decide this." Batch them when you ask.

## The two roles

Run each as a **separate subagent** so neither inherits the other's reasoning. Independence is the whole point; a single agent wearing two hats will rationalize its own plan.

**Proposer** — owns the plan. Each round it does not defend; it *regenerates* the plan, folding in every challenge the Challenger raised that it accepts, and recording the ones it rejects with a one-line reason. It never appends a rebuttal section — it rewrites the artifact.

**Challenger** — owns the attack. Each round it must surface its single strongest *load-bearing* objection, in the structured format below. It may declare "nothing left" only with a written justification for why no material risk remains. It attacks **assumptions**, not step ordering or naming. When an assumption is really an unstated user preference, it files a question instead of an objection.

## Convergence condition

The loop exits when **all** are true in the same round:

1. The `## Questions` block has no `open/*` entries (every question resolved by grounding or by the human), AND
2. No load-bearing claim is still `[assumed]`, AND
3. The Challenger declares "nothing left" with justification, AND
4. The Proposer makes no change to the plan in response.

A no-change round following an empty challenge, with all questions and claims settled, is the signal — not one side going quiet. If anything still moves the plan, run another round.

## The protocol

### Phase 0 — Requirements intake

Populate `## Questions` from the best available source (design doc → live brainstorming → built-in elicitation). Triage each into `verifiable` / `preference`. Ground the verifiable ones; queue the preference ones for the human and ask them (batch independent questions into one prompt; ask one-at-a-time only when a later question depends on an earlier answer). Record answers as `[user-stated]` facts. Do not proceed to a plan while any `preference` question is unanswered.

### Phase 1 — Independent starts (optional, for high-stakes plans)

Generate **3 cold-start plans** in parallel subagents, each given a different optimization bias (e.g. simplicity / robustness / speed-to-ship). Where the three diverge is a free map of the real decisions; where they agree across independent starts is a far stronger signal than agreement within one debate. Merge into one seed plan before entering the loop. Skip for small, well-bounded tasks.

### Phase 2 — Grounding

Before any debate, the Proposer must **check claims against reality** rather than reasoning in a vacuum. Read the actual code, grep for the assumption, run a throwaway spike, fetch the real API/library docs. This is where most precision comes from — one verified fact beats ten rounds of argument. Tag each load-bearing claim:

- `[verified]` — checked against the codebase, a doc, or a run this session
- `[assumed]` — believed but unchecked

**The loop may not exit while any load-bearing claim is still `[assumed]`.** That tag, not "we agree," is the real definition of a solid plan.

### Phase 3 — Premortem attack

The Challenger runs a mandatory premortem: *"Assume this plan shipped and caused an incident six weeks later. Write the postmortem."* Then work backward from each failure to the assumption that caused it. This surfaces silent premises that step-by-step review never touches — which is exactly where plans are actually wrong. Premises that turn out to be user-intent questions get filed into `## Questions`, not argued.

Challenger output format (keeps it tight and load-bearing):

```
SEVERITY: blocking | major | minor
CLAIM: the specific plan element being challenged
WHY IT BREAKS: the concrete failure path, ideally as a premortem trace
SUGGESTED FIX: what would resolve it (or "open question" if genuinely unresolved)
```

### Phase 4 — Regenerate, don't append

The Proposer rewrites `PLAN.md` absorbing accepted challenges. Each surfaced risk must end the round in one of two states:

- **mitigated** — the plan changed to remove it
- **accepted-and-documented** — known, consciously kept, with a stated reason

"No more objections" is the wrong bar; "every risk has an explicit disposition" is the right one. The output then carries its own rationale and its rejected alternatives — what a precise plan looks like.

### Phase 5 — Cross-model verification (the certification gate)

Once the loop converges, hand the final plan to an **independent verifier** through the seam below. This is the step that makes agreement trustworthy. Until it's wired to a real foreign model, the plan is `provisional`, and the output must say so.

The verifier receives the converged plan and the risk dispositions, *not* the debate transcript, and returns one of:

- `CERTIFIED` — no load-bearing objection
- `REJECTED` — with specific objections, which re-enter the loop as fresh Challenger input

#### The verification seam

Keep verification behind one configurable command so the foreign model is a drop-in, not a refactor. Define it once:

```
VERIFIER_CMD = "<external model invocation>"   # e.g. a Gemini / GPT CLI call
```

Today, stub it: if `VERIFIER_CMD` is unset, run the verification prompt as one more **fresh, context-isolated Claude subagent** that has seen only the final plan — better than nothing, but mark the result `provisional (same-model verifier)`. When the real command is set, pipe the plan to it and parse the verdict. The rest of the protocol does not change. That isolation — verifier sees the artifact, never the reasoning — is what stops it from rubber-stamping a truce.

Verifier prompt (model-agnostic):

```
You are an independent reviewer. You did not write this plan and have not
seen the discussion that produced it. Judge only the plan and its stated
risk dispositions. Find the strongest load-bearing reason it would fail in
practice. If none exists, output CERTIFIED. Otherwise output REJECTED with
specific, concrete objections.
```

## Severity gate

Bar `minor` objections (taste, naming, micro-optimizations) from blocking convergence. They can be noted, but an unbounded loop will manufacture infinite small objections and never terminate. Only `blocking` and `major` keep the loop alive.

## Deadlock escalation

If the same `blocking`/`major` objection survives **two full rounds** unresolved, stop. That is not something to grind on — it is a genuine judgment call or a missing fact. Escalate to the human with the crux stated cleanly:

```
DEADLOCK: <one-line statement of the disagreement>
PROPOSER POSITION: ...
CHALLENGER POSITION: ...
WHAT WOULD RESOLVE IT: <the fact or decision needed>
```

Forcing internal resolution here just fabricates a conclusion, which is worse than an honest crux.

## Output: PLAN.md structure

```
# Plan: <task>
## Status: proven | provisional | deadlocked
## Verification: CERTIFIED by <model> | provisional (same-model) | n/a
## Requirements source: brainstorming spec <path> | live brainstorming | built-in elicitation

## Approach
<the plan, in steps>

## Questions
- [resolved/verified]  <q> → <answer> (<file:line | doc | run>)
- [resolved/user]      <q> → <answer> (user, <date>)
- [open/preference]    <q>        # must be empty before the loop runs
- [open/verifiable]    <q>        # grounding in progress

## Claims
- [verified] ...
- [assumed]  ...        # must be empty before "proven"

## Risks
- <risk> — mitigated: <how> | accepted: <why>

## Rejected alternatives
- <option> — rejected because <reason>

## Open questions / deadlocks (if any)
```

## No-subagent fallback (Claude.ai / single context)

Without subagents, simulate the two roles in one context but enforce strict turn separation: write the Proposer turn, then a clearly delimited Challenger turn that is instructed to ignore the Proposer's reasoning and attack only the artifact. This shares blind spots and is weaker — so the cross-model verification gate matters *more* here, not less. Never skip it on the grounds that the two roles already agreed.
