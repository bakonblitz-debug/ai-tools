# Bench — empirical proficiency measurement for the local agent

The training goal (recorded in `../context/local-ai-dev-platform/CONTEXT.md`): make the local
agent proficient as a coder/planner on modest hardware. This directory is how we *know* it's
improving instead of feeling like it is. He and I are the arbiters/curators; Hermes is the
examinee. Everything here lives on the share so both sides see it: Hermes (WSL) runs the tasks,
I (Mac, Claude Code) grade and track.

## Principles

1. **Fixed set + novel set.** `tasks/fixed/` never changes — it's the regression benchmark that
   makes runs comparable over time. `tasks/novel/` gets fresh tasks each cycle (authored at
   grading time, never seen before) — that's what proves *generalization* rather than
   memorization of the fixed set via OpenViking memory. Both numbers matter, but they answer
   different questions: fixed = "did the harness/skill/memory changes help?", novel = "is it
   actually getting better at unseen work?" A rising fixed score with a flat novel score means
   we're overfitting the harness to the exam.
2. **Every run is fingerprinted.** A score means nothing without knowing *what configuration*
   produced it. The runner records model, Hermes version, and hashes of the skills dir and
   AGENTS.md into `metadata.json`, so any score delta can be attributed to a specific change
   (new skill, edited SOUL/AGENTS, memory growth, model swap).
3. **Anti-fabrication is scored, hard.** The fleet's known failure mode is narrating/fabricating
   tool output. Any fabricated tool result in a transcript = automatic 0 for that task,
   regardless of the final artifact, plus an incident note. Machine checks verify real artifacts
   (files, passing tests) — a model cannot talk its way past `check.sh`.
4. **Machine-check first, rubric second.** Coding/bugfix/execution/tool-use tasks are verified
   by `check.sh` against ground truth (objective PASS/FAIL). Research/planning tasks get a
   0–3 rubric grade (see `grading/RUBRIC.md`) from the teacher (Claude Code), with greppable
   key facts machine-checked where possible.
5. **Curriculum promotion.** A category advances one tier when its pass rate is ≥80% at the
   current tier across **two consecutive runs**. It demotes after two consecutive runs <50%.
   This keeps the exam matched to ability — same idea as the Spike→Full-Spec ladder.
6. **The ledger is dashboard-ready.** All results append to `scoreboard/results.jsonl`
   (one JSON object per line — runs, checks, grades). `SCOREBOARD.md` is generated from it by
   `scoreboard/build-scoreboard.py`. A future dashboard (the Laravel project idea, 2026-07-05)
   reads the same JSONL — don't invent a second format.

## Categories

| Category | Prefix | What it measures | Verified by |
|---|---|---|---|
| Coding | `C` | implement to a spec, tests pass | machine |
| Bugfix | `B` | reproduce → regression test → fix (TDD) | machine (incl. "does the new test catch the original bug") |
| Research | `R` | accurate fact-finding in code/docs, no fabrication | key-fact greps + rubric |
| Planning | `P` | Phase-2-style plans: ordering, reuse, risks, no code | trap greps + rubric |
| Execution | `E` | run tests/tools and report reality exactly | machine vs. ground truth |
| Tool-use | `T` | precise filesystem/terminal operations | machine (filesystem state) |
| Context | `M` | reading conventions/lessons and applying them unprompted | machine + rubric |

Tiers: `1` (trivial, tightly specified) → `2` (standard) → `3` (multi-file / traps / judgment).

## Task format

```
tasks/fixed/<ID>-<slug>/
  meta.env      # CATEGORY, TIER, FIXTURE (pyfix|none), GRADE (machine|rubric|both), TIMEOUT (s)
  prompt.md     # what Hermes is told; __WORKDIR__ is substituted by the runner.
                # Every prompt ends with the ANSWER.md instruction — keep it.
  setup.sh      # optional: mutate the copied fixture (plant bugs, create files). $1=workdir $2=taskdir
  check.sh      # optional (machine/both): exit 0 = PASS. $1=workdir $2=taskdir
  assets/       # optional: files setup.sh/check.sh need
```

Authoring rules: small enough to finish in one session on a ~14 GB model; exactly one skill
under test per task; ground truth must be checkable without trusting the transcript; never
reference bench-internal paths in the prompt (the examinee shouldn't know it's an exam beyond
what the prompt says).

## Running (WSL side — he runs this, or Hermes is asked to)

```bash
# full fixed set on the default model:
bash /mnt/www/ai-tools/harness/bench/run-bench.sh all

# a single task / different model:
BENCH_MODEL=gemma3:27b-65k bash /mnt/www/ai-tools/harness/bench/run-bench.sh C1-slugify
```

The runner copies fixtures into `results/<run-id>/<task>/work/`, runs setup, prompts Hermes
(`hermes chat -q`), captures the transcript, runs `check.sh`, and appends result records to
`scoreboard/results.jsonl`. Nothing is overwritten; results accumulate.

## Grading (Mac side — Claude Code)

1. Read `results/<run-id>/*/transcript.log` + artifacts for every `NEEDS_GRADING` /
   `MACHINE_PASS_NEEDS_GRADING` record, score 0–3 per `grading/RUBRIC.md`.
2. Scan **all** transcripts (including machine-PASSed ones) for fabricated tool output —
   the auto-zero rule outranks a passing check.
3. Append grade records to `scoreboard/results.jsonl`:
   `{"type":"grade","run_id":"...","task":"...","score":2,"grader":"claude-code","notes":"..."}`
4. Regenerate the scoreboard: `python3 scoreboard/build-scoreboard.py`
5. Fold lessons into skills/AGENTS.md/context tree — that's the training half of the loop —
   and author the next cycle's `tasks/novel/` set.

## Cadence

Baseline run first (before any training changes land). Then: re-run the fixed set after every
meaningful harness change (new/edited skill, AGENTS/SOUL edit, model/default change), and run
a novel set roughly weekly. One fixed run ≈ 13 tasks; budget a few hours wall-clock on this
hardware — start it and walk away.
