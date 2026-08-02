Work in the Python project at __WORKDIR__ (do not touch anything outside it).

Bug report: `textkit.word_frequencies` does not behave as its own docstring
specifies when the input contains punctuation — e.g. counting `"dog, dog!"`
should yield `{"dog": 2}`. The current test suite passes anyway, which means
the bug has no test coverage.

Follow TDD bug-fix discipline strictly:
1. Write a failing regression test first (add it under `tests/`), run it, and
   confirm it fails against the current code for the right reason.
2. Then fix the implementation so the whole suite passes:

    python3 -m unittest discover -s tests

3. Keep the regression test in the suite — do not delete or weaken it.

When finished, write the root cause, your test, and your fix to __WORKDIR__/ANSWER.md.
