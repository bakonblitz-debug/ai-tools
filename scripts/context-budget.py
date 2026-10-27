#!/usr/bin/env python3
"""context-budget.py — how full is this session's context, and is it time to hand off.

Measured 2026-09-29, which is why this exists: cache_read per request runs ~27k in a
5-19 message session and ~288k in a 150+ message one, and a single long session grew
from 48k to 506k tokens of context. Every request pays the whole accumulated size, so
session length is the largest cost driver in the corpus by an order of magnitude.

His rule (2026-10-14, replacing "40% of the window"): hand off early and without
asking. Past --threshold tokens (default 150,000) this tells the model to write the
folder's automatic plan, handoff-auto-<folder>.md, whose path handoff.sh derives. It
stays quiet while that plan is fresher than 20 minutes, so it asks again only as the
work moves on. settings.json's autoCompactWindow then compacts the session on its own,
and handoff.sh --session-start puts the plan back in front of the fresh context.

Context size for a request = cache_read + cache_creation + input from that request's
usage block. The last assistant record in the transcript is therefore the current size.

Usage:
  context-budget.py [--transcript PATH] [--threshold TOKENS] [--hook]
  context-budget.py --selftest
"""
import json
import os
import subprocess
import sys
import time
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


FRESH_S = 20 * 60


def report(path, threshold, plan):
    size, requests = context_size(path)
    if not size:
        return 0, "context-budget: no usage data in this transcript yet"
    line = f"context ≈ {size:,} tokens over {requests} requests"
    if size < threshold:
        return 0, line
    if plan is None:
        return 1, f"⚠ {line}. Past {threshold:,}: write a handoff plan in .plans/ now."
    try:
        age = time.time() - plan.stat().st_mtime
    except OSError:
        age = None
    if age is not None and age < FRESH_S:
        return 0, line
    verb = "Write" if age is None else "refresh"
    return 1, (
        f"⚠ {line}, past the {threshold:,} line. Do this now, without asking him: "
        f"{verb} {plan} — what this session is doing, what is done, what is next, the "
        f"files involved — with a `## Status` section reading `open`. When the session "
        f"compacts or he clears it, that plan is put back in automatically. Set its "
        f"status to `done` when the work finishes. Do not announce the bookkeeping."
    )


def auto_plan(cwd):
    """The plan path handoff.sh owns for this folder, or None if it cannot say."""
    if not cwd:
        return None
    sh = Path(__file__).with_name("handoff.sh")
    try:
        out = subprocess.run(["bash", str(sh), "--auto-path", cwd],
                             capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        return None
    return Path(out) if out else None


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

    plan = t / "handoff-auto-x.md"
    rc, msg = report(p, 150000, plan)
    if rc != 0:
        bad(f"9k should not trip a 150k line: {msg}")
    ok("under the line is quiet")

    big = write("b.jsonl", [1000, 160000])
    rc, msg = report(big, 150000, plan)
    if rc != 1 or str(plan) not in msg:
        bad(f"160k with no plan should trip and name the plan's path: {msg}")
    ok("over the line with no plan written trips and names the exact file")

    plan.write_text("## Status\nopen\n")
    rc, msg = report(big, 150000, plan)
    if rc != 0:
        bad(f"a plan written minutes ago should silence it: {msg}")
    ok("a freshly written plan silences it, so it does not nag every turn")

    old = time.time() - 30 * 60
    os.utime(plan, (old, old))
    rc, msg = report(big, 150000, plan)
    if rc != 1 or "refresh" not in msg:
        bad(f"a plan 30 minutes stale should ask for a refresh: {msg}")
    ok("a stale plan is asked to be refreshed")

    p3 = write("c.jsonl", [])
    rc, msg = report(p3, 150000, plan)
    if rc != 0 or "no usage data" not in msg:
        bad(f"empty transcript should be quiet and explicit: {msg}")
    ok("an empty transcript says so rather than reporting zero")

    print("selftest passed")


def main():
    if "--selftest" in sys.argv:
        selftest()
        return 0

    threshold = 150000
    if "--threshold" in sys.argv:
        threshold = int(sys.argv[sys.argv.index("--threshold") + 1])

    path, cwd = None, os.getcwd()
    if "--transcript" in sys.argv:
        path = Path(sys.argv[sys.argv.index("--transcript") + 1])
    elif "--hook" in sys.argv:
        # The hook payload names the transcript and the folder; fall back to the newest file.
        try:
            payload = json.load(sys.stdin)
            tp = payload.get("transcript_path")
            if tp and Path(tp).exists():
                path = Path(tp)
            cwd = payload.get("cwd") or cwd
        except Exception:
            path = None
    if path is None:
        path = newest_transcript()
    if path is None or not Path(path).exists():
        return 0

    # The launch folder, the same key handoff.sh --session-start reads back.
    cwd = os.environ.get("CLAUDE_PROJECT_DIR") or cwd
    rc, msg = report(Path(path), threshold, auto_plan(cwd))
    # As a hook, stay silent below the line: a budget warning printed every single
    # turn is noise, and noise gets filtered out exactly when it matters.
    if "--hook" in sys.argv and rc == 0:
        return 0
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
