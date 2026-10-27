# Scoped refactor — behaviour-preserving

For cleaning up **one** area — a controller, a service, a module — without changing what it does. The goal is "same behaviour, better shape."

**Not** for: refactoring while adding a feature (do those as separate tasks), or a whole-codebase audit (that's a much bigger, multi-step effort). One area at a time.

## Precondition: tests first

A refactor without tests is just untested rewriting. Before changing structure, make sure the behaviour is pinned by tests. If it isn't:

```
Plan Mode. Before refactoring <area>, identify its current behaviour and
write characterization tests that lock in what it does today (including
the ugly edge cases). Don't change any logic yet — just capture behaviour.
```

## Opening prompt (Plan Mode)

```
Plan Mode. Refactor <file/area>. Goal: <readability / remove duplication /
extract responsibility / whatever>. Behaviour must not change — the existing
tests must still pass unchanged.

Propose the refactor as a sequence of small, verifiable steps, each of which
keeps the tests green. Tell me what smells you see and which you'd leave
alone. Don't change public interfaces unless I approve it.
```

Small steps matter: a giant one-shot rewrite is impossible to review and easy to get subtly wrong. I want a sequence I can check.

## After each step

```
Run the tests. Show me the diff for this step before moving to the next.
```

## Review follow-up

```
Review this refactor: confirm behaviour is unchanged, flag any place the
new structure introduces a bug or changes an edge case.
```

## Common failure modes

- **Behaviour drift dressed as cleanup.** A "refactor" that quietly changes an edge case. Characterization tests catch this — that's why they come first.
- **Big-bang rewrite.** One enormous diff that's impossible to review. Insist on steps.
- **Interface changes I didn't ask for.** Renamed public methods that break callers elsewhere. "Don't change public interfaces unless approved."
- **Over-abstraction.** Three layers of indirection where the problem was one long method. More structure isn't always better; sometimes the fix is *less*.
