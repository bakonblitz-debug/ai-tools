# ai-tools

> A personal harness for [Claude Code](https://docs.claude.com/en/docs/claude-code): two plugins of skills, the hooks that run around every session, a health check, and the coding standards and prompting runbooks the agents work to.

It started as a playbook ("Claude Dev With Me") and grew into the machinery that runs it. The playbook's workflow now lives in the `bacon-dev` skills; the principles behind it are kept at the end of this file.

The idea underneath all of it: **a coding agent does its best work when it has one clear job and just enough context to do it.**

---

## Contents

1. [Quick start](#quick-start)
2. [The plugins and their commands](#the-plugins-and-their-commands)
3. [Skill rules](#skill-rules)
4. [Making a new skill](#making-a-new-skill)
5. [Hooks](#hooks)
6. [Health check](#health-check)
7. [Where everything is](#where-everything-is)
8. [Principles](#principles)

Further reading: [harness design](docs/README.md) · [coding standards](docs/coding-standards.md) · [prompting guides](docs/prompting/) · [setup](docs/setup.md) · [models](docs/models.md) · [glossary](docs/glossary.md) · [cheat sheet](docs/cheat-sheet.md)

---

## Quick start

```
git clone git@github.com:bakonblitz-debug/ai-tools.git
python3 ai-tools/scripts/install.py --dry-run   # shows the plan, touches nothing
python3 ai-tools/scripts/install.py
git -C ai-tools config core.hooksPath .githooks # the pre-commit skill lint, once per clone
bash ai-tools/scripts/health-check.sh
```

Needs bash, python3 and git. No package installs.

The installer asks a few questions, writes `.env`, and **merges** its hooks into `~/.claude/settings.json`: it backs the file up first, leaves your own hooks alone, and prints how to undo everything it did. It refuses unknown flags, and without a terminal it refuses to run unless given `--yes` (take every default); `--help` shows the options.

Then add the plugins inside a Claude Code session:

```
/plugin marketplace add bakonblitz-debug/ai-tools
/plugin install bacon@ai-tools
/plugin install bacon-dev@ai-tools
```

**What you can skip.** Most hooks want a *context repo*: a private git repo of accumulated project notes. If you have none, the installer skips that group; you lose the session digest and the auto-committed memory, not the skills, standards or runbooks. The setup this was built on (two machines sharing one tree over SMB, a local model runner, a macOS launchd job) is optional too: anything you do not have reports SKIP in the health check, not FAIL.

---

## The plugins and their commands

The repo is a Claude Code marketplace (`.claude-plugin/marketplace.json`) with two plugins.

| Plugin | What it is for | See its commands |
|---|---|---|
| `bacon` | Everyday toolkit: session opener, context-tree lookups, deep engineering mode, the skill commands | `/bacon:list` |
| `bacon-dev` | Coding mode: the plan → prove → build pipeline, tangent hand-offs, merge-conflict resolution | `/bacon-dev:list` |

`/bacon:skill list` shows every installed plugin's skills at once, with whether each plugin is on here. All three listings are generated from the skill files by `scripts/list-skills.py`, so no list is kept by hand.

**bacon**

| Command | What it does |
|---|---|
| `/bacon:greet` | Session opener: offers what is open today as a picker. Run it as the first prompt (`claude "/bacon:greet"`). |
| `/bacon:second-brain` | Deep engineering mode: orient in code and memory, plan, build test-first, record decisions. |
| `/bacon:context-query` | Lists context files by the date in their file name ("latest", "since <date>"). |
| `/bacon:ai-tools-context` | Loads or updates the context tree paired with this repo, for installs without the bootstrap hook. |
| `/bacon:skill` | `list`, `log on\|off\|tail`, `lint`: lists, logs and checks every plugin's skills. |
| `/bacon:skill-create` | Creates a new skill from a one-line description. |
| `/bacon:list` | This table, generated. |

**bacon-dev**

| Command | What it does |
|---|---|
| `/bacon-dev:architect` | Conductor for any code change: research, plan, prove the plan, split it into tasks, build, review. Sequences the others. |
| `/bacon-dev:ouroboros` | Adversarial planning loop: a planner and an attacker until the plan survives, then a verdict. |
| `/bacon-dev:handoff` | Out-of-scope bug or TODO found mid-task: writes a focused plan in `.plans/` instead of fixing it inline. |
| `/bacon-dev:git-conflict` | Resolves merge and rebase conflicts, including two agents or worktrees touching the same file. |
| `/bacon-dev:list` | This table, generated. |

**Coding mode.** `bacon-dev` is off in user settings and switched on per project: `bash scripts/coding-mode.sh <project dir>` enables it (with the other coding plugins) in that folder's `.claude/settings.json`; `--check` reports what is missing without touching anything. Its `SessionStart` hook loads the coding rules from [`docs/coding-standards.md`](docs/coding-standards.md).

---

## Skill rules

Every skill in every plugin follows the same rules, set on 2026-11-04 and enforced by a lint:

- **Skill code is Python** (3.9, stdlib only). The one shell file is `scripts/py.sh`, which picks a Python that actually runs on the machine (the Windows `python3` is often a Store stub).
- **Every skill script has `--selftest`** and logs through `scripts/skilllog.py`. Logging is off until `/bacon:skill log on`; logs stay on each machine in `~/.claude/skill-logs/`, and `/bacon:skill log tail <name>` shows the last lines.
- **No shell logic in a `SKILL.md`.** A pipe, a `$( )` or a loop belongs in a script the skill calls.
- **Every plugin has a `list` skill**, and every `SKILL.md` has a name and a description. Descriptions open with the quoted phrases that should trigger them (a warning, not a failure).

`/bacon:skill lint` (`scripts/skill.py lint`) checks all of it. The same lint runs in `.githooks/pre-commit`, which blocks a commit that breaks a rule once `git config core.hooksPath .githooks` is set in the clone, and in the health check.

---

## Making a new skill

```
/bacon:skill-create "<what it should do, in one line>"
```

It picks the plugin whose subject fits (a new plugin only when asked), checks the name is free, writes the `SKILL.md` and any Python script to the rules above, adds a `list` skill if the plugin has none, runs the lint and the selftests, and commits. The full procedure is in [`plugins/bacon/skills/skill-create/SKILL.md`](plugins/bacon/skills/skill-create/SKILL.md).

---

## Hooks

`scripts/install.py` wires three groups, split by what each needs:

| Group | Needs | Hooks |
|---|---|---|
| `context` | a context repo | `claude-bootstrap.sh` (session digest: open handoffs, priority item), `plan-mindset.sh`, `wrong.sh`, `sync-memory.sh` (auto-commits context and memory writes), `session-audit.py` |
| `budget` | nothing | `context-budget.py` (warns as the context window fills) |
| `plans` | a writable `.plans/` | `handoff.sh` (surfaces and checks `.plans/handoff-*.md` files) |

Plugins carry their own hooks: `bacon-dev` adds the coding-rules hook above. Hermes (the local agent) is not wired by the installer.

---

## Health check

```
bash scripts/health-check.sh             # every check, one line each
bash scripts/health-check.sh skill       # only checks whose name contains "skill"
```

Each check prints PASS, FAIL or SKIP, and a failing one prints the command to run by hand. It covers the workspace and the other machine, every script's `--selftest`, the skill lint, that the harness map lists every file, that the context tree is synced and consistent, that coding-mode projects have their plugins, and `no_personal_identifiers`: this repo is public, so no personal name or address may appear outside a short allowlist (the licence and the plugin manifests).

---

## Where everything is

The full file index is the **harness map**: [`docs/harness-map.md`](docs/harness-map.md), with an [interactive version](docs/harness-map.html). It lists every file, what fires it, and what it touches; the health check fails when a file is missing from it.

```
ai-tools/
├── .claude-plugin/        # marketplace.json: the two plugins
├── plugins/bacon/         # skills invoked as /bacon:*
├── plugins/bacon-dev/     # coding mode, /bacon-dev:*, plus its coding-rules hook
├── scripts/               # hooks and tools: install.py, health-check.sh, skill.py,
│                          #   list-skills.py, skilllog.py, py.sh, session-todo.sh, …
├── .githooks/pre-commit   # the skill lint before every commit
├── tools/observatory/     # read-only dashboard over session and usage metrics
├── bin/now                # dates in the forms the workspace uses, and their age
├── config/                # delegation config for the tiered pipeline
├── templates/             # spike and task-spec templates, the launchd example
├── docs/                  # harness design and map, coding standards, prompting runbooks,
│                          #   setup, models, glossary, cheat sheet
└── .env.example           # every machine-local key, documented
```

---

## Principles

The workflow is now run by `/bacon-dev:architect`; these are the reasons it looks the way it does.

**The agent is a fast junior, not an oracle.** It writes code faster and spots things a person misses. It also writes code that looks right and fails at runtime: invented methods, columns that do not exist, insecure defaults. The person who merges is accountable, so the person reads the diff.

**Watch for invented code.** A method, column or API parameter that is not in the source is the usual tell. Ask "where is this defined? Show me the source." If it cannot point to a real location, it invented it.

**One job per agent.** Planning, building and reviewing are different disciplines; a reviewer that wrote the code is a bad reviewer. Splitting the work keeps each context small and each task sharp.

**Context is a budget.** Past a point, more context means more drift. Keep instructions short, load only the files a task needs, start fresh sessions for unrelated work.

**Feed it real state, not guesses.** On Laravel projects, [Laravel Boost](docs/setup.md#laravel-boost) lets the agent read the real routes, models and migrations instead of inferring them.

**Plan before anything non-trivial, test first for anything with logic.** A failing test written before the code tests what the code is supposed to do. The rule is in [`coding-standards.md`](docs/coding-standards.md#tdd-rule); the runbook is [`tdd.md`](docs/prompting/tdd.md).

**Review is part of building.** A separate code-review and security pass runs on the finished change, before it counts as done. Findings are must-fix, should-fix or note ([`review-triggers.md`](docs/prompting/review-triggers.md)).

| Scenario | Runbook |
|---|---|
| Onboarding onto a codebase | [`project-intake.md`](docs/prompting/project-intake.md) |
| Fixing a reproducible bug | [`bug-fix.md`](docs/prompting/bug-fix.md) |
| Building a scoped feature | [`new-feature.md`](docs/prompting/new-feature.md) |
| Building test-first | [`tdd.md`](docs/prompting/tdd.md) |
| Behaviour-preserving cleanup | [`scoped-refactor.md`](docs/prompting/scoped-refactor.md) |
| Running review on demand | [`review-triggers.md`](docs/prompting/review-triggers.md) |
