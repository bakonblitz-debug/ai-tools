Work in the Python project at __WORKDIR__ (do not touch anything outside it).

Add a function `slugify(text)` to the `textkit` package and export it from
`textkit/__init__.py`. Behavior: lowercase the input; keep runs of letters and
digits; replace every other run of characters with a single hyphen; no leading
or trailing hyphens. A test file `tests/test_slugify.py` already exists and
defines the expected behavior exactly — make the whole suite pass:

    python3 -m unittest discover -s tests

When finished, write a short summary of what you changed to __WORKDIR__/ANSWER.md.
