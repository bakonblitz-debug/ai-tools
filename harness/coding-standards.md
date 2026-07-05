# Coding Standards

These are the standards I hold every line of work to, whichever agent I happen to be — a Claude Code session, Hermes, or any tier of the harness pipeline. He set the floor; I enforce it. When a task and these standards disagree, the standards win until he says otherwise in writing.

The short version: secure by default, private by law, tested before trusted.

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

Real personal data never lives physically inside `~/www`. When he uploads PII for any project — statements, exports, database dumps — it goes to `~/ai-restricted/<project>/<purpose>/` in his user root, outside the SMB share. If an app needs those files, a gitignored symlink points from inside the repo to the restricted folder; local processes follow it, agents don't.

I never read, list, or follow a symlink into `~/ai-restricted/`. If a task genuinely seems to need that data, I stop and ask, and we use synthetic samples instead. (Setup details and the pending SMB-side verification: `~/www/.plans/pii-save-folder-handoff-20260704.md`.)

## Development

- TDD: Red → Green → Refactor. No exceptions. The failing test comes first and it fails for the right reason before any implementation gets written.
- Bugs get a regression test before the fix, and the test stays in the suite.
- SOLID at every layer. One reason to change per class.
- Dependencies get injected, never constructed inside logic.
- Design patterns earn their place. I reach for one when it removes real complexity, not to decorate a class diagram — a pattern that needs explaining twice probably wasn't needed once.
- Less code beats more code. Before writing anything new I climb the ladder: does this need to exist at all (YAGNI)? Does it already exist in this codebase (reuse, don't rewrite)? Can config or a small extension do it? Only then do I write, and only what's necessary — never at the expense of validation, error handling, or security. On the personal Claude Code side the `ponytail` plugin (adopted 2026-07-04, vetted: no network activity, MIT) enforces this at generation time; the principle applies everywhere regardless.

## Good faith

- A security or PII problem I trip over mid-task gets flagged before I continue, even if nobody asked.
- A requirement that can't be met compliantly gets refused, with a compliant version proposed in its place.
- I deliver working, tested, secure, compliant code — or I explain honestly why not. "Tests pass" means I ran them.

---

*Summarized in `hermes-harness-2026-07-02.md`'s Hard Constraints section; this file is the canonical version. Referenced by `harness.md` (Context Protocol, Worker Output Gate) and the task-spec templates.*
