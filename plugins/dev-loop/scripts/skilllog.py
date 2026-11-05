#!/usr/bin/env python3
"""skilllog.py — optional run log for skill scripts. Off until `/skill-kit:skills log on`.

In a skill script:
    from skilllog import logger
    log = logger("myplugin:greet")        # the command name as you type it
    log("titled", title=t)                # one line, a no-op while logging is off
    with log.run(sys.argv[1:]):           # start, end with exit code and seconds, or the traceback
        main()

Logs live on each machine (never on the share): ~/.claude/skill-logs/<plugin>-<skill>.log, one line per
event: time, host, pid, event, fields as JSON. A log over MAX_BYTES rolls to .log.1. Turned on by the
`enabled` file in that folder (one name per line, or "all"), or SKILL_LOG=1 for one run.
Stdlib only, Python 3.9.
"""
import json
import os
import socket
import sys
import time
import traceback
from contextlib import contextmanager
from pathlib import Path

DIR = Path(os.environ.get("SKILL_LOG_DIR") or Path.home() / ".claude" / "skill-logs")
MAX_BYTES = 1_000_000


def enabled_names(d=None):
    try:
        return {line.strip() for line in ((d or DIR) / "enabled").read_text(encoding="utf-8").splitlines() if line.strip()}
    except OSError:
        return set()


def is_on(name, d=None):
    if os.environ.get("SKILL_LOG") == "1":
        return True
    names = enabled_names(d)
    return "all" in names or name in names


def log_path(name, d=None):
    return (d or DIR) / (name.replace(":", "-").replace("/", "-") + ".log")


class Logger:
    def __init__(self, name, d=None):
        self.name, self.dir = name, d or DIR
        self.on = is_on(name, self.dir)
        self.path = log_path(name, self.dir)

    def __call__(self, event, **fields):
        if not self.on:
            return
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            if self.path.exists() and self.path.stat().st_size > MAX_BYTES:
                self.path.replace(self.path.with_suffix(".log.1"))
            line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {socket.gethostname()} {os.getpid()} {event}"
            if fields:
                line += " " + json.dumps(fields, ensure_ascii=False, default=str)
            with open(self.path, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(line + "\n")
        except OSError:
            pass  # a log must never break the skill

    @contextmanager
    def run(self, argv=()):
        t0 = time.time()
        self("start", argv=list(argv))
        try:
            yield self
        except SystemExit as e:
            self("end", code=e.code, secs=round(time.time() - t0, 3))
            raise
        except BaseException:
            self("error", secs=round(time.time() - t0, 3), traceback=traceback.format_exc(limit=8))
            raise
        else:
            self("end", code=0, secs=round(time.time() - t0, 3))


def logger(name, d=None):
    return Logger(name, d)


def selftest():
    import tempfile
    fails = []

    def check(cond, msg):
        print(f"  {'ok  ' if cond else 'FAIL'} {msg}")
        if not cond:
            fails.append(msg)

    d = Path(tempfile.mkdtemp())
    os.environ.pop("SKILL_LOG", None)
    log = logger("bacon:x", d)
    log("hello")
    check(not log.path.exists(), "off by default: nothing is written")
    (d / "enabled").write_text("bacon:x\n", encoding="utf-8")
    log = logger("bacon:x", d)
    log("hello", n=1)
    check(log.path.name == "bacon-x.log" and ' hello {"n": 1}' in log.path.read_text(encoding="utf-8"), "on by name: one line with fields")
    check(not logger("bacon:y", d).on, "another skill stays off")
    (d / "enabled").write_text("all\n", encoding="utf-8")
    check(logger("bacon:y", d).on, '"all" turns every skill on')
    log = logger("bacon:z", d)
    try:
        with log.run(["a"]):
            raise SystemExit(3)
    except SystemExit:
        pass
    try:
        with log.run([]):
            raise ValueError("boom")
    except ValueError:
        pass
    text = log.path.read_text(encoding="utf-8")
    check('end {"code": 3' in text and "error" in text and "ValueError: boom" in text, "run() records the exit code and a traceback")
    global MAX_BYTES
    old, MAX_BYTES = MAX_BYTES, 10
    log("roll")
    MAX_BYTES = old
    check(log.path.with_suffix(".log.1").exists(), "a log over the limit rolls to .log.1")
    bad = Logger("bacon:w", d / "file-not-dir.txt")
    (d / "file-not-dir.txt").write_text("x")
    bad.on = True
    bad("still fine")
    check(True, "a log that cannot be written does not raise")
    print("selftest " + ("FAILED" if fails else "passed"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(selftest() if sys.argv[1:] == ["--selftest"] else (print(__doc__) or 2))
