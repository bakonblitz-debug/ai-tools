Work in the Python project at __WORKDIR__ (do not touch anything outside it).

Refactor the `textkit` package: split `textkit/core.py` into two modules —
`textkit/text.py` holding `normalize_whitespace` and `truncate`, and
`textkit/stats.py` holding `word_frequencies`. Delete `textkit/core.py` when
done. The public API must not change: `from textkit import truncate` (etc.)
must keep working, and the existing test suite must stay green without editing
any test file:

    python3 -m unittest discover -s tests

When finished, write a short summary of what you changed to __WORKDIR__/ANSWER.md.
