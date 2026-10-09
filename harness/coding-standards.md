# Coding Standards

These are the standards I hold every line of work to, whichever agent I happen to be — a Claude Code session, Hermes, or any tier of the harness pipeline. He set the floor; I enforce it. When a task and these standards disagree, the standards win until he says otherwise in writing.

The short version: secure by default, private by law, tested before trusted.

> Paths below are written as `<workspace>/…`. The real root is `~/www` (Mac/Linux),
> `/mnt/www` (WSL2), or `M:\` (Windows) — see `detect_root()` in
> `harness/scripts/session-todo.sh`.

---

## Security

OWASP Top 10 (2021) is the working checklist, not a poster on the wall. Before any feature ships I can answer pass/fail on each item for the surface it touches. In practice, most of it comes down to habits:

- Parameterized queries only. String-built SQL doesn't get written, not even "just for this one report."
- Validate at every boundary, sanitize on output, escape at the point of use. Input is hostile until proven otherwise, and proving it once doesn't cover the next boundary.
- Least privilege and defense in depth. A process, account, or token gets the narrowest access that still works.
- Secrets never go in source. Not in code, not in fixtures, not in comments, not in commit history. `.env` files stay where they are (the egress lock is the real protection), but their *values* never get copied into anything I write.

## Privacy — the compliance floor

**Loi 25 > PIPEDA > GDPR > HIPAA > CCPA.** Quebec's Loi 25 is the strictest law he answers to, so it sets the bar; meeting it generally covers the rest. Concretely:

- No real PII in tests, logs, URLs, error responses, or temp files. Ever. Synthetic fixtures only.
- Mask on display. Blind indexes for sensitive fields that need to be searchable.
- Log IDs and event types, never values that identify a person.
- New field storing personal data? Purpose limitation applies — say why it exists or don't add it.
- If I find PII in source or fixtures while doing something else, I flag it before continuing. Off-task doesn't mean off-duty.

## The save folder — where real PII lives

Established 2026-07-04, after real bank statements turned up inside the shared tree.

Real personal data never lives physically inside `<workspace>`. When he uploads PII for any project — statements, exports, database dumps — it goes to `~/ai-restricted/<project>/<purpose>/` in his user root, outside the SMB share. If an app needs those files, a gitignored symlink points from inside the repo to the restricted folder; local processes follow it, agents don't.

I never read, list, or follow a symlink into `~/ai-restricted/`. If a task genuinely seems to need that data, I stop and ask, and we use synthetic samples instead. (Setup details and the pending SMB-side verification: `<workspace>/.plans/pii-save-folder-handoff-20260704.md`.)

## Development

- TDD: Red → Green → Refactor. No exceptions. The failing test comes first and it fails for the right reason before any implementation gets written. **One failing test per lap** — a batch of assertions handed over at once is test-first, not TDD, and it measurably costs more: same worker, same day, 4 attempts for an 18-assertion batch vs 0 retries across 4 single-test laps.
- Non-trivial work is planned before it is written: `architect` (idea → proven plan → tasks), then `ouroboros` at least once to challenge the plan adversarially, then TDD. Skipping straight to code is the exception and needs a reason.
- A green typecheck is not a correctness verdict. It checks shape; the defects that matter are semantic. The acceptance test is the verdict, and it is authored by whoever owns the rule — never by the worker implementing it.
- When a delegated attempt fails, return a **mechanical diagnosis, not a verdict**. "Test 4 is red" does not teach; "your `\b` is on the wrong side of the optional period, so end-of-string after `.` is not a boundary" fixes it first try.
- Bugs get a regression test before the fix, and the test stays in the suite.
- SOLID at every layer. One reason to change per class.
- Dependencies get injected, never constructed inside logic.
- Design patterns earn their place. I reach for one when it removes real complexity, not to decorate a class diagram — a pattern that needs explaining twice probably wasn't needed once.
- **Scripts I write for myself are kept and reused, never improvised twice.** If a script will run more than once — a parser, a capture helper, a reconciliation, a cleanup, a diagnostic — it goes into the repo it serves (`scripts/` with a runner entry) or into `harness/scripts/` when it is cross-project, *not* into the session scratchpad. His rule, stated 2026-08-16, and it is general: it costs fewer tokens than re-deriving the thing and it keeps the behaviour identical each run. A scratchpad script is invisible to the next session and to the other machine, so what gets re-derived drifts. **The test is whether the script has future value, not whether the answer does** — a one-time diff or an exploratory query is a genuine throwaway; anything I would write a second time is not. Before writing a helper, check whether I already wrote it. Cross-project helpers that exist today: **`harness/scripts/on-mac.sh`** — runs a command on the Mac inside a workspace project, because on this two-machine share Docker on the Windows side cannot bind-mount the workspace (it mounts *empty and silently*) and git object writes fail over SMB from there. Use it for any build, test or git operation against `<workspace>`; `sync-memory.sh` and `claude-bootstrap.sh` are the other two.
- Less code beats more code. Before writing anything new I climb the ladder: does this need to exist at all (YAGNI)? Does it already exist in this codebase (reuse, don't rewrite)? Can config or a small extension do it? Only then do I write, and only what's necessary — never at the expense of validation, error handling, or security. On the personal Claude Code side the `ponytail` plugin (adopted 2026-07-04, vetted: no network activity, MIT) enforces this at generation time; the principle applies everywhere regardless.

### Why one test per lap — the measurement

Same worker (`devstral:65k`), same verification, same day:

| shape | attempts to green | inference | tokens |
|---|---|---|---|
| 18 assertions handed over at once | **4** | ~100 s | ~1500 |
| one failing test per lap, 4 laps | **0 retries** | ~4 s | ~160 |

Under the batch prompt it wrote local-calendar date arithmetic that drifts across a DST boundary; given
one narrow test it reached for the millisecond form unprompted. The size of the target mattered more
than the model. A small lap also caught a bug the spec never mentioned (a future-dated posting counting
as "recent").

## Commits

His rule, stated 2026-10-09: a log has to be readable weeks later, and one commit per small change buries it.

- **One commit per feature, per project, per day.** Several commits only when the feature has distinct contiguous parts (migrations, models, a queue, events, routing).
- **Over about 30 files, split by section of the feature.** A single scaffold that cannot be split stays whole.
- If I commit several times locally while working, I squash them into that shape before the work is done, and always before a push. `harness/scripts/squash-history.sh` does it without touching file content.
- **Subject:** what the commit is for, feature or fix, in the imperative. **Body:** a list, one full sentence per change.
- No narrative. No account of mistakes, dead ends or what I had not thought of. No attribution trailer.

```
Add goalie projections to the picks page

- Add a goalie projection model based on starts.
- Give goalies their own stat lines on the player card.
- Score a goalie goal as 15 points, per league rules.
- Fix the flat form curve for goalies.
```

The context/memory repo is the one exception: its sync hook commits on its own schedule.

## Harness systems — the bar for anything the harness itself runs

His standing instruction, 2026-09-29: *"always assume that we want this systematic. Solid as heck,
tests, analyzable, no vagueness, deterministic as much as it can ever be."* This applies to every
script, hook, check and data file the harness runs on itself. "Solid as heck" is not a feeling, so it
is spelled out as conditions something either meets or does not:

1. **Generated beats maintained.** If a human has to remember to update it, it rots. The career index
   rotted twice inside a month with a check already watching it. Generate the file, or have a check
   that fails when it drifts — never rely on discipline.
2. **A rule with no check is a preference.** Every invariant gets a check, and every check **fails
   loudly when it scans nothing**. A lint that walks an empty tree and reports success manufactures
   confidence, which is worse than no lint.
3. **Tests live with the script.** An embedded `--selftest` over synthetic fixtures, following
   `session-todo.sh` and `context-index.sh`. Synthetic because these scripts ship in the public repo
   and the real data carries PII.
4. **Determinism is a requirement, not a preference.** Same input, same bytes. `LC_ALL=C` on every
   sort, no timestamps in generated output, no dependence on `find` order or locale. Two machines must
   produce identical files.
5. **Idempotence.** Running twice changes nothing. If the second run differs, the ordering inside the
   script is wrong (generate what a later step points at *first*).
6. **Machine-parseable output.** One record per line, fixed field count, a stable fingerprint for
   dedup. If a human has to read prose to extract a number, it cannot be analysed.
7. **Watermark anything derived from a moving source.** A file generated from git history trails HEAD
   the moment it is written. Record the rev it was built at and verify against that, or "stale" and
   "hand-edited" become indistinguishable and the check flaps forever.
8. **Failure must be visible without anyone looking.** No silent `exit 0`. Surface through a channel he
   already reads — the session digest, a handoff file — not a new one, and not a mail that only fires
   on failure: the jobhunt capture died quietly for two days that way.
9. **Serialise, do not race.** Hooks fire concurrently with manual runs. Take a lock (`mkdir` is the
   atomic primitive available everywhere; macOS has no `flock(1)`), and under contention **skip rather
   than fail** — a verdict about a tree being rewritten underneath you is noise.
10. **A detector must be tested against a known instance of what it detects.** Measured 2026-09-29: a
    failure detector written in the same session as two real violations found neither, because it
    watched `Write`/`Edit` while every edit went through Bash. Loosening it then flagged 24 events that
    were the sanctioned generators doing their job. **If the panel is empty, assume the parser is
    broken before assuming the behaviour was clean.**
11. **Never let the measured party author the measurement.** Any metric whose numerator I maintain is a
    metric I can improve by doing less bookkeeping. Prefer counts derived from raw evidence — his
    interruptions, tool denials, reverts, re-edits — and state each metric's gaming vector next to it.

## Language-specific standards

Everything above is the universal floor. It holds in every language and every framework, and nothing below relaxes it.

On top of it, each language and framework has its own conventions. Those live as drop-in files next to this one, in `coding-standards.d/`. When I start work in a language or framework, I check that directory for a matching file (`php.md`, `frontend.md`, and so on) and load it if it exists. If there is no file for what I'm working in, the universal floor still fully applies, and if I establish a convention worth keeping I add the drop-in rather than letting it live only in my head. New languages are a single file dropped into that directory, so this list stays out of my way as it grows.

## Good faith

- A security or PII problem I trip over mid-task gets flagged before I continue, even if nobody asked.
- A requirement that can't be met compliantly gets refused, with a compliant version proposed in its place.
- I deliver working, tested, secure, compliant code — or I explain honestly why not. "Tests pass" means I ran them.

---

*Summarized in a private Hermes operating note (not in this repo) under its Hard Constraints section; this file is the canonical version. Referenced by `harness.md` (Context Protocol, Worker Output Gate) and the task-spec templates.*
