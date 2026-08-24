#!/usr/bin/env python3
"""Query a context tree whose leaf files are named <slug>-<epoch>-<YYYYMMDD>.md

The date lives in the FILENAME, not the contents. So "the latest five" is a
sort over names, not a search through prose — and questions like "since the
23rd" need no date parsing of file bodies at all.

This exists because composing the equivalent shell pipeline correctly is the
step that keeps failing:

    ls -1 *.md | sed -E 's/^.*-([0-9]{9,10})-([0-9]{8})\\.md$/\\1 \\2 &/' | sort -rn

Splitting on "-" grabs the wrong field whenever a slug contains a hyphen, which
is most of them. Do not rebuild that by hand; call this instead.

    context-query.py latest 5
    context-query.py latest 5 --under <subfolder>
    context-query.py since 2026-08-23
    context-query.py since 23/08/2026 --under <subfolder>
    context-query.py find <name-fragment>
    context-query.py --self-check

`since` accepts any of: 2026-08-23, 20260823, 23-08-2026, 08/23/2026,
2026/08/23, 23 Aug 2026, "Aug 23, 2026", or a raw epoch. Normalising that here
means the caller never has to guess a format.

Root directory: --root, else $CONTEXT_ROOT, else the first of
/mnt/www/context/context or ~/www/context/context that exists.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from pathlib import Path

# <slug>-<epoch>-<YYYYMMDD>.<ext> — slugs contain hyphens, so anchor on the
# two numeric groups at the end rather than splitting the whole name.
LEAF = re.compile(r"^(?P<slug>.+)-(?P<epoch>\d{9,10})-(?P<ymd>\d{8})\.(?P<ext>md|pdf)$")

_MONTHS = {m.lower(): i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}


def default_root() -> Path:
    if os.environ.get("CONTEXT_ROOT"):
        return Path(os.environ["CONTEXT_ROOT"])
    for c in ("/mnt/www/context/context", "~/www/context/context"):
        p = Path(c).expanduser()
        if p.is_dir():
            return p
    return Path.cwd()


def parse_date(text: str) -> dt.date:
    """Best-effort date parse. Raises ValueError with the formats tried."""
    s = text.strip().strip(",")

    if re.fullmatch(r"\d{9,10}", s):                      # raw epoch
        return dt.datetime.fromtimestamp(int(s)).date()
    if re.fullmatch(r"\d{8}", s):                         # 20260823
        return dt.datetime.strptime(s, "%Y%m%d").date()

    # Month-name forms: "Aug 23 2026", "23 Aug 2026", "August 23, 2026"
    tokens = re.findall(r"[A-Za-z]+|\d+", s)
    month = next((_MONTHS[t.lower()[:3]] for t in tokens
                  if t.lower()[:3] in _MONTHS), None)
    if month:
        nums = [int(t) for t in tokens if t.isdigit()]
        day = next((n for n in nums if 1 <= n <= 31), None)
        year = next((n for n in nums if n >= 1000), None)
        if day and year:
            return dt.date(year, month, day)

    parts = [int(p) for p in re.split(r"[-/.]", s) if p.isdigit()]
    if len(parts) == 3:
        a, b, c = parts
        if a >= 1000:                                     # 2026-08-23
            return dt.date(a, b, c)
        if c >= 1000:
            # 23-08-2026 vs 08-23-2026 — day-first unless the first number
            # can only be a month.
            if a > 12:
                return dt.date(c, b, a)
            if b > 12:
                return dt.date(c, a, b)
            return dt.date(c, b, a)                       # ambiguous: day-first

    raise ValueError(
        f"unparseable date {text!r} — try 2026-08-23, 20260823, 23/08/2026, "
        f"'Aug 23 2026', or an epoch")


def leaves(root: Path, under: str | None = None):
    """Every leaf file under root, newest first. Non-conforming names skipped."""
    base = root / under if under else root
    if not base.is_dir():
        sys.exit(f"no such directory: {base}")
    found = []
    for p in base.rglob("*"):
        m = LEAF.match(p.name)
        if m:
            found.append((int(m.group("epoch")), m.group("ymd"), p))
    return sorted(found, key=lambda t: t[0], reverse=True)


def show(rows, root: Path) -> None:
    if not rows:
        print("(nothing matched)")
        return
    for epoch, ymd, path in rows:
        stamp = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"
        try:
            rel = path.relative_to(root)
        except ValueError:
            rel = path
        print(f"{stamp}  {epoch}  {rel}")


def self_check() -> None:
    d = dt.date(2026, 8, 23)
    # Epoch -> date is deliberately LOCAL time, matching how the YYYYMMDD
    # suffixes are generated. 1787486400 is midday UTC on the 23rd, so it
    # lands on the 23rd in any timezone; midnight-UTC values do not.
    for text in ["2026-08-23", "20260823", "23-08-2026", "23/08/2026",
                 "2026/08/23", "Aug 23 2026", "23 Aug 2026",
                 "August 23, 2026", "1787486400"]:
        got = parse_date(text)
        assert got == d, f"{text!r} -> {got}, expected {d}"

    # A hyphenated slug must not confuse the field split — the bug this replaces.
    m = LEAF.match("some-long-hyphenated-slug-1786700000-20260814.md")
    assert m and m.group("epoch") == "1786700000", "hyphenated slug misparsed"
    assert m.group("slug") == "some-long-hyphenated-slug"

    assert LEAF.match("another-leaf-file-1787407182-20260822.pdf")
    for skip in ["CONTEXT.md", "application-log.md", "notes-2026.md"]:
        assert not LEAF.match(skip), f"{skip} should not match"

    try:
        parse_date("not a date")
    except ValueError:
        pass
    else:
        raise AssertionError("bad date should raise")

    print("context-query self-check: 15/15 ok")


def main() -> None:
    # --root/--under are attached to BOTH the top level and every subcommand,
    # so `latest 5 --under X` and `--under X latest 5` both work.
    # Position-sensitive flags are exactly the kind of syntax this script
    # exists to stop the caller from having to get right.
    # SUPPRESS, not None: with parents= the subparser's default would otherwise
    # overwrite a value already parsed at the top level, silently dropping
    # `--under X latest 3` back to the whole tree.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", type=Path, default=argparse.SUPPRESS)
    common.add_argument("--under", default=argparse.SUPPRESS,
                        help="subfolder to restrict to")

    ap = argparse.ArgumentParser(
        parents=[common], description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--self-check", action="store_true")
    sub = ap.add_subparsers(dest="cmd")

    p_latest = sub.add_parser("latest", parents=[common],
                              help="the newest N leaf files")
    p_latest.add_argument("n", nargs="?", type=int, default=5)

    p_since = sub.add_parser("since", parents=[common],
                             help="leaf files dated on or after DATE")
    p_since.add_argument("date")

    p_find = sub.add_parser("find", parents=[common],
                            help="leaf files whose name contains TERM")
    p_find.add_argument("term")

    args = ap.parse_args()
    if args.self_check:
        self_check()
        return
    if not args.cmd:
        ap.print_help()
        sys.exit(2)

    root = getattr(args, "root", None) or default_root()
    rows = leaves(root, getattr(args, "under", None))

    if args.cmd == "latest":
        rows = rows[:args.n]
    elif args.cmd == "since":
        try:
            cutoff = parse_date(args.date)
        except ValueError as exc:
            sys.exit(str(exc))
        stamp = cutoff.strftime("%Y%m%d")
        rows = [r for r in rows if r[1] >= stamp]
    elif args.cmd == "find":
        needle = args.term.lower()
        rows = [r for r in rows if needle in r[2].name.lower()]

    show(rows, root)


if __name__ == "__main__":
    main()
