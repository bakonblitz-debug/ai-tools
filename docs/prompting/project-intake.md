# Project intake — getting oriented

For starting work on a codebase I don't have in my head — a new personal project I'm picking back up, or something I've inherited. The goal is a fast, accurate mental map, *not* an audit and not a pile of changes.

## Opening prompt (Plan Mode — read-only)

```
Plan Mode, read-only — don't change anything.
Give me an orientation map of this codebase:
- What it is and what stack it's on (versions).
- The main entry points and how a request flows through.
- The key models/domain objects and how they relate.
- Where the important business logic lives.
- Anything surprising, risky, or clearly unfinished.

Keep it to what's actually here — don't infer features that aren't in the
code. Point to real files/lines so I can verify.
```

The "point to real files so I can verify" clause is doing real work: it keeps the summary grounded and lets me spot-check for hallucinated structure.

## If it's a Laravel project

Install/connect Boost first (see [setup](../setup.md#3--laravel-boost-laravel-projects-only)) so the map is built from real routes, models, and migrations rather than guesses.

## Generate or refresh CLAUDE.md

Once I trust the map, I have it write the project's guideline file:

```
Write a concise CLAUDE.md for this project: stack + versions, how to run it
and run tests, the conventions a new contributor must follow, and the
project-specific gotchas you found. Short and high-signal — most important
rules first. Don't pad it.
```

A lean `CLAUDE.md` pays off every session afterward; a bloated one taxes every session. If a project already has one (or two — e.g. a framework-generated one plus mine), reconcile them into a single source of truth.

## Common failure modes

- **Confident fiction.** A clean-sounding architecture summary describing code that isn't there. The "point to real files" rule plus my own spot-checks are the defense.
- **Premature changes.** Treating intake as a license to "fix things." Intake is read-only; changes are a separate, scoped task afterward.
- **Bloated CLAUDE.md.** A guideline file that dumps everything. Keep it to what changes the agent's behaviour; cut the rest.
