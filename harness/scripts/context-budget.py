#!/usr/bin/env python3
"""context-budget.py — how full is this session's context, and is it time to hand off.

Measured 2026-09-29, which is why this exists: cache_read per request runs ~27k in a
5-19 message session and ~288k in a 150+ message one, and a single long session grew
from 48k to 506k tokens of context. Every request pays the whole accumulated size, so
session length is the largest cost driver in the corpus by an order of magnitude.

His rule: at 40% of the window, stop and hand the work to a fresh session via a plan
in .plans/ — fresh context is cheaper AND sharper than a long one.

Context size for a request = cache_read + cache_creation + input from that request's
usage block. The last assistant record in the transcript is therefore the current size.

WINDOW: unset by default and deliberately so. The real window is not something this
script can verify, and a wrong default would produce a confident wrong percentage.
Set CONTEXT_WINDOW (tokens) to get a percentage; without it the absolute number is
still reported.

Usage:
  context-budget.py [--transcript PATH] [--threshold 0.4] [--hook]
  context-budget.py --selftest
"""
import json
import os
import sys
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"


def context_size(path):
    """Tokens in context at the last assistant turn, and how many requests it took."""
    size, requests = 0, 0
    with open(path, encoding="utf8", errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("type") != "assistant":
                continue
            usage = rec.get("message", {}).get("usage") or {}
            cur = ((usage.get("cache_read_input_tokens") or 0)
                   + (usage.get("cache_creation_input_tokens") or 0)
                   + (usage.get("input_tokens") or 0))
            if cur:
                size = cur
                requests += 1
    return size, requests


def newest_transcript():
    files = list(PROJECTS.rglob("*.jsonl")) if PROJECTS.is_dir() else []
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def report(path, threshold):
    size, requests = context_size(path)
    if not size:
        return 0, "context-budget: no usage data in this transcript yet"
    window = os.environ.get("CONTEXT_WINDOW")
    if window and window.isdigit() and int(window) > 0:
        pct = size / int(window)
        line = f"context ≈ {size:,} tokens over {requests} requests — {pct:.0%} of {int(window):,}"
        if pct >= threshold:
            root = os.environ.get("WORKSPACE_ROOT", "~/www")
            return 1, (
                f"⚠ {line}. Past the {threshold:.0%} mark: write a handoff plan to "
                f"{root}/.plans/handoff-<topic>.md and continue in a fresh session. Every further "
                f"request in this one pays the full {size:,}."
            )
        return 0, line
    # No window to divide by, so report the absolute cost and let him judge.
    return 0, (f"context ≈ {size:,} tokens over {requests} requests "
               f"(set CONTEXT_WINDOW to get a percentage)")


def selftest():
    import tempfile
    t = Path(tempfile.mkdtemp())
    ok = lambda m: print(f"  ok   {m}")

    def bad(m):
        print(f"  FAIL {m}")
        sys.exit(1)

    def write(name, sizes):
        p = t / name
        with p.open("w", encoding="utf8") as fh:
            for s in sizes:
                fh.write(json.dumps({
                    "type": "assistant",
                    "message": {"usage": {"cache_read_input_tokens": s,
                                          "cache_creation_input_tokens": 0,
                                          "input_tokens": 0}},
                }) + "\n")
        return p

    p = write("a.jsonl", [1000, 5000, 9000])
    size, reqs = context_size(p)
    if size != 9000 or reqs != 3:
        bad(f"last-turn size wrong: {size}/{reqs}")
    ok("context size is the LAST turn, not the sum")

    os.environ.pop("CONTEXT_WINDOW", None)
    rc, msg = report(p, 0.4)
    if rc != 0 or "%" in msg:
        bad(f"no window should mean no percentage: {msg}")
    ok("without CONTEXT_WINDOW it reports absolute tokens and never a made-up percent")

    os.environ["CONTEXT_WINDOW"] = "100000"
    rc, msg = report(p, 0.4)
    if rc != 0:
        bad(f"9% should not trip the threshold: {msg}")
    ok("under threshold is quiet")

    p2 = write("b.jsonl", [1000, 45000])
    rc, msg = report(p2, 0.4)
    if rc != 1 or "handoff" not in msg:
        bad(f"45% should trip and name the handoff: {msg}")
    ok("over threshold trips and names the handoff path")

    p3 = write("c.jsonl", [])
    rc, msg = report(p3, 0.4)
    if rc != 0 or "no usage data" not in msg:
        bad(f"empty transcript should be quiet and explicit: {msg}")
    ok("an empty transcript says so rather than reporting zero")

    os.environ.pop("CONTEXT_WINDOW", None)
    print("selftest passed")


def main():
    if "--selftest" in sys.argv:
        selftest()
        return 0

    threshold = 0.4
    if "--threshold" in sys.argv:
        threshold = float(sys.argv[sys.argv.index("--threshold") + 1])

    path = None
    if "--transcript" in sys.argv:
        path = Path(sys.argv[sys.argv.index("--transcript") + 1])
    elif "--hook" in sys.argv:
        # The hook payload names the transcript; fall back to the newest file.
        try:
            payload = json.load(sys.stdin)
            tp = payload.get("transcript_path")
            if tp and Path(tp).exists():
                path = Path(tp)
        except Exception:
            path = None
    if path is None:
        path = newest_transcript()
    if path is None or not Path(path).exists():
        return 0

    rc, msg = report(Path(path), threshold)
    # As a hook, stay silent below the line: a budget warning printed every single
    # turn is noise, and noise gets filtered out exactly when it matters.
    if "--hook" in sys.argv and rc == 0:
        return 0
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
