---
name: context-query
description: >
  "latest", "newest", "most recent", "last N", "since <date>", "what's new", "recent notes". Lists context files by the date in their FILENAME (<slug>-<epoch>-<YYYYMMDD>.md); never grep file bodies for a date.
---

# Querying the context tree by date

## The one thing to know

Leaf files are named `<slug>-<epoch>-<YYYYMMDD>.md`:

```
some-issue-slug-1787407182-20260822.md
another-long-hyphenated-slug-1786700000-20260814.md
```

Both an epoch and an ISO date, in the **name**. The file's prose does not
contain the date. So:

- "the latest 5" → sort filenames by the epoch, take 5.
- "since the 23rd" → compare the `YYYYMMDD` field.
- Searching *contents* for `2026-08-23`, `Aug 23, 2026`, `[Epoch: ...]` or any
  other format returns **nothing**, because it was never written there.

The canonical statement of this convention lives at the top of the tree's
`CONTEXT.md`, under "How this system works (conventions)". This skill is how to
act on it.

## Use the script

`context-query.py` sits next to this file. It handles the sorting and the date
parsing so you do not have to compose a shell pipeline.

Run it through the interpreter picker, which works on the Mac, the PC and WSL:

```bash
bash "<this skill's base directory>/../../../../scripts/py.sh" "<this skill's base directory>/context-query.py" latest 5 --under <subfolder>
```

The other forms, same prefix: `since 2026-08-23 --under <subfolder>`, `since "Aug 23 2026"`,
`find <name-fragment>`, `--selftest`.

`since` accepts `2026-08-23`, `20260823`, `23-08-2026`, `08/23/2026`,
`2026/08/23`, `23 Aug 2026`, `August 23, 2026`, or a raw epoch — normalising the
format is the script's job, not yours. `--root` and `--under` work before or
after the subcommand. Output is one line per file: ISO date, epoch, then the
path relative to the root.

Default root is `$CONTEXT_ROOT`, else `<workspace>/context/context`, where
`<workspace>` is the per-OS root (`~/www` on Mac/Linux, `/mnt/www` on WSL2,
`M:\` on Windows) computed by `detect_root()` in `scripts/session-todo.sh`.

## Do not rebuild this by hand

Never sort these names with a shell pipeline (`ls`, `sort`, `sed`). Most slugs
contain hyphens, so splitting on `-` sorts by a word from the slug, and the
result is a plausible-looking list in the wrong order. The script anchors on the
two numeric groups at the end; its docstring shows the broken pipeline.

## After you have the filenames

The listing answers "which files". To answer "what do they say", read them —
`read_file` on the paths returned. Never summarise an entry from its filename
alone.

## When this skill does not apply

Content questions ("which entries mention Laravel") are ordinary searches — use
`search_files` over the text. This skill is only for ordering and filtering by
date. It skips the handful of files that do not follow the naming convention
(`CONTEXT.md`, index and log files, and similar).
