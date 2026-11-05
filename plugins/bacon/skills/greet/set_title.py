#!/usr/bin/env python3
"""set_title.py — name the current Claude Code session, the way /rename does.

  set_title.py "Short topic title"
  set_title.py --selftest

Appends a custom-title line to this session's transcript (~/.claude/projects/*/<session id>.jsonl);
the /resume picker shows it. The session id comes from CLAUDE_CODE_SESSION_ID. Stdlib only, Python 3.9.
"""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))
from skilllog import logger  # noqa: E402

log = logger("bacon:greet")
MAX_LEN = 80


def clean(title):
    return re.sub(r"[\x00-\x1f\x7f]", "", title).strip()[:MAX_LEN].strip()


def transcript(session_id, home):
    hits = sorted((home / ".claude" / "projects").glob(f"*/{session_id}.jsonl"))
    return hits[0] if hits else None


def set_title(title, session_id, home):
    t = clean(title)
    if not t:
        raise SystemExit("set_title: the title is empty")
    if not session_id:
        raise SystemExit("set_title: CLAUDE_CODE_SESSION_ID is not set; not inside a Claude Code session")
    p = transcript(session_id, home)
    if p is None:
        raise SystemExit(f"set_title: no transcript for session {session_id}")
    line = json.dumps({"type": "custom-title", "customTitle": t, "sessionId": session_id}, ensure_ascii=False)
    with open(p, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(line + "\n")
    log("titled", title=t, transcript=str(p))
    return t


def selftest():
    import tempfile
    fails = []

    def check(cond, msg):
        print(f"  {'ok  ' if cond else 'FAIL'} {msg}")
        if not cond:
            fails.append(msg)

    home = Path(tempfile.mkdtemp())
    sid = "0000-test"
    (home / ".claude" / "projects" / "M--").mkdir(parents=True)
    tp = home / ".claude" / "projects" / "M--" / f"{sid}.jsonl"
    tp.write_text('{"type":"user"}\n', encoding="utf-8")
    got = set_title('PC boot "crashes"\n', sid, home)
    last = json.loads(tp.read_text(encoding="utf-8").splitlines()[-1])
    check(got == 'PC boot "crashes"' and last == {"type": "custom-title", "customTitle": got, "sessionId": sid},
          f"appends one valid custom-title line, quotes kept and escaped: {last}")
    check(len(clean("x" * 200)) == MAX_LEN, "the title is capped")
    for bad, msg in (("   ", "an empty title"), ("T", "no session id"), ("T", "no transcript")):
        try:
            set_title(bad, "" if msg == "no session id" else ("missing" if msg == "no transcript" else sid), home)
            refused = False
        except SystemExit:
            refused = True
        check(refused, f"{msg} is refused")
    check(len(tp.read_text(encoding="utf-8").splitlines()) == 2, "refused calls write nothing")
    print("selftest " + ("FAILED" if fails else "passed"))
    return 1 if fails else 0


def main(args):
    if args == ["--selftest"]:
        return selftest()
    if len(args) != 1:
        print(__doc__)
        return 2
    with log.run(args):
        print("session titled:", set_title(args[0], os.environ.get("CLAUDE_CODE_SESSION_ID", ""), Path.home()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
