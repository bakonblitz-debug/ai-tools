# Glossary

Short definitions for terms used across this playbook.

**Agent** — a running instance of Claude focused on one task in its own context. "Have the security agent review this" means a separate, focused session doing only that, isolated from the main conversation.

**Skill** — a packaged set of instructions and resources that teaches Claude to do a specific task consistently (e.g. `code-review`, `security-review`). Loaded into Claude Code, invoked by name or by a matching prompt. This repo ships three of its own (symlinked into `~/.claude/skills/`): [`handoff`](skills/handoff/SKILL.md), which delegates an out-of-scope tangent to a focused subagent instead of letting it creep into the current diff; [`tdd`](skills/tdd/SKILL.md), which builds behavior test-first; and [`ouroboros`](skills/ouroboros/SKILL.md), an adversarial two-agent planning loop that stress-tests a plan to convergence, then certifies it with an independent cross-model verifier.

**TDD (Test-Driven Development)** — write the test *before* the code. A test written first describes what the code is *supposed* to do; a test written after describes what it happens to do. The discipline cuts bugs by pinning behavior down before the implementation can drift from it. See the [`tdd` skill](skills/tdd/SKILL.md).

**Red → green → refactor** — the TDD loop. **Red:** write one failing test for the next behavior; run it; watch it fail for the right reason. **Green:** write the simplest code that makes it pass. **Refactor:** clean up structure and names while the test stays green. Repeat per behavior. A test you never saw fail is a test you can't trust.

**MCP (Model Context Protocol)** — the protocol Claude Code uses to talk to external tools and servers. An MCP server exposes capabilities (read the database schema, list routes, query an API) that the agent can call. Laravel Boost is an MCP server.

**Laravel Boost** — first-party Laravel tooling that runs as an MCP server, giving the agent the project's real routes, models, migrations, and config instead of guesses. Reduces hallucinations and token waste. Laravel 12/13 only.

**Plan Mode** — a Claude Code mode (Shift+Tab twice) where the agent writes a plan and waits for approval before changing files. Used for any non-trivial task.

**The four phases** — Plan → Build → Review → Ship. The shape every task moves through. See the [README](README.md#the-four-phases).

**Hallucination** — when the model produces plausible output that isn't real: a method, column, or API that doesn't exist. Caught by asking it to point to the source, and by feeding it real state via Boost.

**`/context` vs `/usage`** — `/context` is how full the current session's context window is (affects answer quality). `/usage` is plan limits / billing. Different questions.

**Triage buckets** — how review findings get sorted: **must-fix** (blocks the commit), **should-fix** (now if cheap, else note it), **note** (logged for later).

**CLAUDE.md / AGENTS.md** — guideline files Claude reads at session start for project conventions. Kept short, with the most important rules near the top, because earlier instructions carry more weight.
