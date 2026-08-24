---
name: context-query
description: >
  Use this skill for any question about *which* files in the context tree are
  newest, most recent, latest, or dated on/after some date — "the last 5
  entries", "what changed since the 23rd", "recent work on X". Leaf files are
  named <slug>-<epoch>-<YYYYMMDD>.md, so the date is in the FILENAME and these
  questions are a sort over names, never a search through file contents.
  Trigger on: latest, most recent, last N, newest, since <date>, up to date,
  what's new, recent notes. Do NOT grep file bodies for a date string — the
  dates are not written in the prose, and every format you guess will return
  nothing.
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

```bash
python3 context-query.py latest 5 --under <subfolder>
python3 context-query.py since 2026-08-23 --under <subfolder>
python3 context-query.py since "Aug 23 2026"
python3 context-query.py find <name-fragment>
python3 context-query.py --self-check
```

`since` accepts `2026-08-23`, `20260823`, `23-08-2026`, `08/23/2026`,
`2026/08/23`, `23 Aug 2026`, `August 23, 2026`, or a raw epoch — normalising the
format is the script's job, not yours. `--root` and `--under` work before or
after the subcommand. Output is one line per file: ISO date, epoch, then the
path relative to the root.

Default root is `$CONTEXT_ROOT`, else `/mnt/www/context/context`, else
`~/www/context/context`.

## Do not rebuild this by hand

The equivalent pipeline is easy to get subtly wrong:

```bash
# WRONG - splits on "-" and takes field 2, which is part of the slug
ls -1 *.md | sort -t- -k2 -rn | head -5
```

Most slugs contain hyphens, so field 2 is a word from the slug rather than the
epoch, and the result is a plausible-looking list in the wrong order. If you
must do it inline, anchor on the two numeric groups at the end:

```bash
ls -1 *.md | sed -E 's/^.*-([0-9]{9,10})-([0-9]{8})\.md$/\1 \2 &/' | sort -rn | head -5
```

Prefer the script.

## After you have the filenames

The listing answers "which files". To answer "what do they say", read them —
`read_file` on the paths returned. Never summarise an entry from its filename
alone.

## When this skill does not apply

Content questions ("which entries mention Laravel") are ordinary searches — use
`search_files` over the text. This skill is only for ordering and filtering by
date. It skips the handful of files that do not follow the naming convention
(`CONTEXT.md`, index and log files, and similar).
