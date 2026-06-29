---
name: tdd
description: >
  Use this skill when building or changing behavior and you want a test-first
  (TDD) discipline: write a failing test that describes the desired behavior,
  watch it fail for the right reason, write the simplest code to make it pass,
  then refactor with the test as a safety net. Reach for it whenever the task is
  "add this behavior", "fix this bug", "this function should do X", or any change
  where correctness matters — and especially when the user says "do this TDD",
  "write the test first", "red-green-refactor", or "test-driven". This is the
  default build discipline for non-trivial logic; it produces fewer bugs because
  the test pins the behavior down before the code can drift from it.
---

# TDD (Test-Driven Development)

## Why this exists

A test written *after* the code tends to test what the code happens to do. A test
written *before* the code tests what the code is *supposed* to do — and the
difference is most of where bugs come from. TDD flips the order on purpose:

1. **You can't have a passing test for behavior that doesn't exist yet**, so the
   test forces you to state the behavior precisely before writing it.
2. **A test you watched fail first is a test you trust.** If a test passes the
   moment you write it — before the implementation exists — it isn't testing what
   you think it is. Seeing it go red, then green, proves it actually exercises the
   new code.
3. **Refactoring stops being scary.** Once behavior is locked under a green test,
   you can restructure freely; the test tells you the instant you break something.

This is the playbook's "fewer bugs" lever. It doesn't make code correct by magic —
it makes incorrect code *fail loudly and early*, while the change is still small
and cheap to fix, instead of in production where it's expensive.

## The loop: red → green → refactor

```
┌─────────────────────────────────────────────────────┐
│  RED      Write ONE failing test for the next         │
│           smallest piece of behavior. Run it.         │
│           Watch it fail — for the RIGHT reason.       │
│                         │                             │
│                         ▼                             │
│  GREEN    Write the SIMPLEST code that makes it pass. │
│           Not the elegant version — the passing one.  │
│           Run the test. It goes green.                │
│                         │                             │
│                         ▼                             │
│  REFACTOR Now clean it up — names, duplication,       │
│           structure — with the test holding behavior  │
│           steady. Re-run. Still green.                │
└────────────────────────┬────────────────────────────┘
                         ▼
            Repeat for the next slice of behavior.
```

Each lap is small — minutes, not hours. The point is a tight feedback loop, not a
grand design up front. The design *emerges* from making each test pass and then
cleaning up.

### The three rules, stated plainly

- **Red:** don't write production code until you have a failing test that demands
  it.
- **Green:** write only enough production code to make the failing test pass —
  resist building ahead of the tests.
- **Refactor:** don't add behavior and clean up in the same step. Green first,
  *then* improve, with the test as your net.

## The procedure

1. **Pick the next smallest behavior.** Not the whole feature — one observable
   thing it should do. "Returns an empty list when there are no orders" is a slice.
   "Build the order system" is not.
2. **Write the test first.** Name it after the behavior, not the method:
   `it_rejects_a_withdrawal_that_exceeds_the_balance`, not `test_withdraw`. Assert
   the behavior you want to exist.
3. **Run it and confirm it fails — for the right reason.** A test that errors
   because of a typo or a missing import isn't red, it's broken. You want it to
   fail on the *assertion* (or on the missing method you're about to write), proving
   it's testing the real thing. **Never skip this step** — a test you never saw fail
   is a test you can't trust.
4. **Write the simplest code that passes.** Hardcoding a return value to get to
   green is allowed and often correct — the next test will force you to generalize.
   Don't gold-plate.
5. **Run the whole suite, not just the new test.** Green new test, and nothing else
   went red.
6. **Refactor.** Remove duplication, fix names, extract where it clarifies — only
   now, and only while green. Re-run after each meaningful change.
7. **Loop.** Next behavior, next test. Stop when the feature's behaviors are all
   covered and green.

When you finish, the change arrives with its tests already written, each one
having been seen to fail then pass. That's the artifact: behavior, pinned.

## When to be strict — and when not to

This is *pragmatic* test-first, not dogma. Use judgment:

**Lead with a test** for anything with real logic: branching, calculations,
validation, state changes, edge cases, bug fixes (see below), anything you'd be
nervous to change later.

**Don't bother with the full ceremony** for:
- Trivial, behavior-free code — a one-line getter, a config constant, a plain DTO
  with no logic. A test there asserts nothing worth asserting.
- Throwaway spikes — when you're exploring to *learn* what to build, not building
  it. Spike to understand, then delete the spike and TDD the real thing.
- Pure mechanical refactors where the behavior is already covered by existing tests
  — those tests *are* your safety net; run them, don't write new ones.

When unsure, lean toward writing the test. The cost of one extra small test is low;
the cost of a silent bug is not. But don't bureaucratize — a test that only exists
to satisfy a ritual is noise.

## TDD for bug fixes (the highest-value case)

This is where test-first pays the most, and it has a strict order:

1. **Reproduce the bug as a failing test first.** Write a test that asserts the
   *correct* behavior. Run it — it fails, reproducing the bug. Now you've captured
   the bug in a way that can never silently come back.
2. **Then fix the code** until that test goes green.
3. The test stays in the suite as a permanent regression guard.

A bug fix without a failing-test-first is a fix you're taking on faith. Don't.

## What makes a good test (so the discipline actually helps)

- **Asserts behavior, not implementation.** Test the output/effect, not which
  private method got called. Tests coupled to internals break on every refactor and
  punish the cleanup TDD is supposed to enable.
- **One reason to fail.** Each test pins one behavior. When it goes red later, the
  name alone should tell you what broke.
- **Fast and isolated.** No shared state leaking between tests; order-independent.
  Slow suites get skipped, and a skipped suite protects nothing.
- **Readable as a spec.** Arrange / act / assert. A teammate should read the test
  and understand the behavior without reading the implementation.
- **Tests the edges.** Empty, null, zero, boundary, the error path — not just the
  happy case. The happy path rarely ships the bug.

## How this fits the four phases

TDD lives inside **Phase 2 — Build**, and it changes what "build" means: instead of
"write code, then add tests," it's "write a test, write code, refactor, repeat."
The plan from Phase 1 should already name the behaviors to cover; TDD turns each one
into a red→green→refactor lap. Build is done when every planned behavior has a test
that was seen to fail then pass, the whole suite is green, and the diff has been
read. Phase 3 review still happens — TDD reduces bugs, it doesn't replace the
separate review pass.

## Laravel / Pest section

On Laravel projects this maps cleanly onto Pest (or PHPUnit). Concrete shape:

**Red — write the failing test.** Feature tests for HTTP/endpoint behavior, unit
tests for isolated logic:

```php
// tests/Feature/WithdrawalTest.php
it('rejects a withdrawal that exceeds the balance', function () {
    $account = Account::factory()->create(['balance' => 50_00]);

    $response = $this->postJson("/accounts/{$account->id}/withdraw", [
        'amount' => 75_00,
    ]);

    $response->assertStatus(422);
    expect($account->fresh()->balance)->toBe(50_00); // unchanged
});
```

Run just this test and watch it fail for the right reason:

```bash
php artisan test --filter=rejects_a_withdrawal_that_exceeds_the_balance
# or with Pest directly:
./vendor/bin/pest --filter="rejects a withdrawal"
```

**Green — simplest code that passes.** Add the validation/guard, nothing more. Run
the filtered test until green.

**Refactor — then run the whole suite:**

```bash
php artisan test          # everything green, not just the new test
```

Laravel-specific reflexes:

- **Lean on factories** for arrange — `Account::factory()->create([...])` — so each
  test sets up exactly the state it needs and nothing leaks.
- **`RefreshDatabase`** keeps tests isolated; a migrated, rolled-back DB per test is
  what makes them order-independent.
- **Feed real state via Boost.** When planning which behaviors to test, let
  [Laravel Boost](../../setup.md#laravel-boost) surface the actual routes, models,
  and validation rules so the tests assert against the real app, not a guessed one.
- **Assert the effect, not the query.** `expect($account->fresh()->balance)` (the
  observable state) over asserting which Eloquent method ran.
- Feature test for "what the user/endpoint experiences," unit test for "this class
  in isolation." Reach for the unit test when the logic is gnarly enough that an
  HTTP round-trip would obscure what's actually being checked.

## Common failure modes

- **Writing the test after the code.** The most common slip — and it quietly turns
  TDD into "tests that describe whatever the code does." If you wrote code first,
  you skipped the discipline; the test no longer proves the behavior was intended.
- **Never watching it fail.** A test added straight to green might be asserting
  nothing (wrong path, mocked-away logic, tautology). Always see red first.
- **Testing implementation, not behavior.** Brittle tests that break on every
  refactor, defeating the "refactor freely" payoff. Assert outcomes.
- **Steps too big.** A test that demands a whole subsystem to pass isn't a TDD lap,
  it's a deferred big-bang. Shrink the slice.
- **Refactoring while red.** Changing structure *and* behavior at once means when it
  breaks you don't know which. Get to green, then refactor.
- **Skipping the suite run.** Passing the new test while silently breaking three
  others. Run everything before calling it done.
