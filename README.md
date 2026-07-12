# Claude Dev With Me

> My personal playbook for building software with Claude Code: how I plan, build, review, and ship — and how I keep an agent focused so it writes code I'd actually merge.

This repo is the source of truth for how I work with [Claude Code](https://docs.claude.com/en/docs/claude-code) on my own projects. It's a living document — I add to it after I learn something the hard way, not before.

The whole thing rests on one idea: **a coding agent does its best work when it has one clear job and just enough context to do it.** Everything below is in service of that.

---

## Contents

- [Quick reference (Cheat Sheet)](cheat-sheet.md) — one-page summary
- [Setup](setup.md) — install checklist, Laravel Boost, plugins
- [Models](models.md) — which model for which job, and how to switch
- [Glossary](glossary.md) — MCP, Boost, skill, agent, the four phases
- [Prompting guides](harness/prompting/) — copy-paste runbooks per scenario

1. [Principles](#principles)
2. [The Workflow](#the-workflow)
3. [The four phases](#the-four-phases)
4. [Prompting guides](#prompting-guides)
5. [Repository layout](#repository-layout)

---

## Principles

A few things I've found to be true. They're here so future-me remembers *why* the workflow looks the way it does.

**The agent is a fast junior, not an oracle.** Claude can write more code faster than I can, and it can spot things I miss. It can also produce code that looks right and fails in ways I won't see until runtime — invented methods, columns that don't exist, insecure defaults, patterns that don't match the rest of the codebase. I'm the one accountable for what ships. I read the diff.

**Watch for hallucinations.** Claude won't tell me when it's guessing. The tells:
- A method, helper, or class that doesn't exist — grep for it before trusting it.
- A column, table, or relationship not in the schema — check the migrations and models.
- An API call whose parameters or return shape don't match the real docs.
- Code that compiles but breaks on a path I didn't test.

When something looks plausible but off, I ask: *"Where is this defined? Show me the source."* If it can't point to a real location, it invented it.

**One job per agent.** I don't use a single prompt to plan, build, *and* review. Each is a different discipline. A reviewer that wrote the code it's reviewing is a bad reviewer. Splitting the work keeps each context small and each task sharp.

**Context is a budget, not a free resource.** Tokens get spent reading guidelines and generating output. More context in a session doesn't mean better output — past a point it means *worse* output, more drift, more hallucination. Instructions near the start of a session (and near the start of `CLAUDE.md`) carry more weight than ones buried later. So I keep instructions short, load only the files a task needs, and start fresh sessions for unrelated work.

**Feed it real state, not guesses.** On Laravel projects I run [Laravel Boost](setup.md#laravel-boost) so Claude reads my actual routes, models, and migrations over MCP instead of inferring them. This is the single biggest reduction in both hallucinations and wasted tokens — it stops the agent grepping around to rediscover what the project already knows.

**Plan mode for anything non-trivial.** <kbd>Shift</kbd>+<kbd>Tab</kbd> twice until it says *Plan Mode*. The agent writes a plan and waits for my approval before touching files. I get to catch a bad approach before it becomes a bad diff.

**Review is part of building, not a separate phase that gets skipped.** The review pass happens before I consider something done — not after something breaks.

---

## The Workflow

Every task — a one-line fix, a feature, a refactor — moves through the same four phases. Simple changes blow through them in seconds; big ones take real time at each step.

```
Receive request
   │
   ▼
Phase 1 — Plan      scope · files · tests · open questions
   │
   ▼
Phase 2 — Build     implement against the plan, write tests
   │
   ▼
Phase 3 — Review    separate code-review + security pass
   │
   ▼
Phase 4 — Ship      verify it runs, commit, push
```

Not every change needs the full ceremony. If I already know exactly what to change and it's one line, the token cost of planning isn't worth it — I just make the change. The judgment call is: *is the change well-understood, or am I guessing?* If I'm guessing, I plan.

---

## The four phases

### Phase 1 — Plan

Pick the [prompting guide](harness/prompting/) that matches the task and use its opening prompt in **Plan Mode**. A good plan states:

- **What's changing**, including scope boundaries — what I am *and am not* doing.
- **The files likely to be touched** (optional — naming them constrains token use when I already know; otherwise let the agent map the codebase).
- **The testing approach** — how I'll know it works.
- **Open questions** — anything I need to decide before implementation.

If the agent hits a question it can't answer, I have it note the question in the plan and proceed with the parts that are unblocked, rather than stalling everything.

### Phase 2 — Build

Implement against the plan from Phase 1. Claude writes the change, runs the existing tests, and writes new tests for new behavior. On Laravel projects, **Boost + the Laravel best-practices skill** keep the generated code aligned with framework conventions.

For anything with real logic — and *always* for bug fixes — I build it **test-first**: write a failing test for the next behavior, watch it fail for the right reason, write the simplest code to pass, then refactor while green. A test written before the code tests what the code is *supposed* to do, which is most of where bugs come from. This is the playbook's main "fewer bugs by construction" lever — the [`tdd` skill](harness/skills/tdd/SKILL.md) is the discipline, [`tdd.md`](harness/prompting/tdd.md) is the runbook. I skip the ceremony for trivial behavior-free code and throwaway spikes; I don't bureaucratize it.

Build is done when the change compiles, tests pass (each new one having been seen to fail then pass), and I've read the diff myself.

Structural cleanup of code that's drifted is *not* a build-time job — that's a separate refactor pass (see [`scoped-refactor.md`](harness/prompting/scoped-refactor.md)). "Implement this feature" and "untangle this module" are different tasks; mixing them produces a worse version of both.

### Phase 3 — Review

This is the phase that separates this from "just letting the agent write stuff." The review runs as a **separate pass on the finished change**, not as part of the prompt that generated it.

Two passes by default:
- **Code review** — structure, naming, error handling, test coverage, convention adherence. (`/code-review`, or the `feature-dev` plugin's reviewer.)
- **Security review** — injection surfaces, auth/authz, secrets handling, dependency CVEs, framework misconfiguration. (`/security-review`.)

If they don't trigger on their own, I prompt: *"Have the code-review and security agents review the most recent uncommitted work."*

Findings get triaged: **must-fix** (blocks the commit, loops back to Phase 2), **should-fix** (fix now if cheap, else note it), **note** (logged for later). See [`review-triggers.md`](harness/prompting/review-triggers.md).

### Phase 4 — Ship

Verify the change actually runs (not just that tests pass — run the app and look at the thing), then commit with a descriptive message and push. The commit history is the record of what changed and why; future-me reads it.

---

## Prompting guides

The workflow says *what* happens. The [`harness/prompting/`](harness/prompting/) guides say *how to prompt* for the scenarios that come up most. Each is a short runbook: when to use it, the opening prompt, what the review follow-ups look like, and the common ways it goes wrong.

| Scenario | Guide |
|----------|-------|
| Onboarding onto a codebase (mine or inherited) | [`project-intake.md`](harness/prompting/project-intake.md) |
| Fixing a reproducible bug | [`bug-fix.md`](harness/prompting/bug-fix.md) |
| Building a scoped new feature | [`new-feature.md`](harness/prompting/new-feature.md) |
| Building behaviour test-first (red-green-refactor) | [`tdd.md`](harness/prompting/tdd.md) |
| Behaviour-preserving cleanup of one area | [`scoped-refactor.md`](harness/prompting/scoped-refactor.md) |
| Running review on demand | [`review-triggers.md`](harness/prompting/review-triggers.md) |

I add guides as I hit new scenarios. A guide earns its place *after* I've done the thing once and learned what the prompt should say.

---

## Repository layout

```
claude-dev-with-me/
├── README.md          # This file — principles + workflow
├── cheat-sheet.md     # One-page quick reference
├── setup.md           # Install checklist, Boost, plugins
├── models.md          # Which model for which job
├── glossary.md        # Terms: MCP, Boost, skill, agent, phases
├── prompting/         # Scenario runbooks
│   ├── README.md      # Index: which guide when
│   ├── project-intake.md
│   ├── bug-fix.md
│   ├── new-feature.md
│   ├── tdd.md
│   ├── scoped-refactor.md
│   └── review-triggers.md
└── skills/            # Local Claude Code skills (symlink into ~/.claude/skills)
    ├── handoff/       # Delegate out-of-scope tangents to a focused subagent
    │   └── SKILL.md
    ├── ouroboros/     # Adversarial two-agent planning loop → cross-model-certified plan
    │   └── SKILL.md
    └── tdd/           # Build behaviour test-first: red → green → refactor
        └── SKILL.md
```

---

*A personal, evolving playbook. Updated whenever I learn something worth writing down.*
