#!/usr/bin/env python3
"""Pre-commit check for the damage an edit over the M: share does to a file.

A file written from the PC through the SMB share loses its Unix exec bit
(100755 becomes 100644) and can come back with CRLF line endings. Both slip
into a commit unnoticed (ai-tools 1d141ee, and twice on 2026-10-30). This
refuses the commit and names the fix.

    commit-guard.py [REPO]     check what is staged in REPO (default: here)
    commit-guard.py --selftest
"""
import os
import subprocess
import sys
import tempfile

CRLF_FIX = "perl -pi -e 's/\\r$//' {p} && git add {p}"
EXEC_FIX = "chmod +x {p} && git add {p}"


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, check=True).stdout


def staged(repo):
    """(old mode, new mode, status, path) for every staged change."""
    parts = git(repo, "diff", "--cached", "--raw", "-z", "--no-renames").split(b"\0")
    out = []
    for meta, path in zip(parts[0::2], parts[1::2]):
        meta = meta.decode()
        if not meta.startswith(":"):
            continue
        old, new, _, _, status = meta[1:].split()
        out.append((old, new, status, path.decode("utf-8", "surrogateescape")))
    return out


def problems(repo):
    found = []
    for old, new, status, path in staged(repo):
        if status.startswith("D"):
            continue
        if old == "100755" and new == "100644":
            found.append(f"{path}: lost its exec bit (100755 -> 100644). Fix: " + EXEC_FIX.format(p=path))
        if new in ("100644", "100755"):
            data = git(repo, "show", f":{path}")
            if b"\0" not in data[:8000] and b"\r\n" in data:
                found.append(f"{path}: has CRLF line endings. Fix: " + CRLF_FIX.format(p=path))
    return found


def selftest():
    with tempfile.TemporaryDirectory() as t:
        def run(*a):
            git(t, *a)

        def write(name, data, mode=0o644):
            p = os.path.join(t, name)
            with open(p, "wb") as f:
                f.write(data)
            os.chmod(p, mode)

        run("init", "-q")
        for k, v in (("user.name", "t"), ("user.email", "t@t"), ("core.autocrlf", "false"),
                     ("core.fileMode", "true"), ("commit.gpgsign", "false")):
            run("config", k, v)
        write("run.sh", b"echo hi\n", 0o755)
        write("note.md", b"a\n")
        write("gone.sh", b"x\n", 0o755)
        run("add", ".")
        run("commit", "-q", "-m", "base")

        assert problems(t) == [], "nothing staged must pass"

        write("note.md", b"a\nb\n")
        run("add", "note.md")
        assert problems(t) == [], "a plain LF edit must pass"

        os.chmod(os.path.join(t, "run.sh"), 0o644)
        run("add", "run.sh")
        p = problems(t)
        assert len(p) == 1 and "run.sh: lost its exec bit" in p[0], p

        os.chmod(os.path.join(t, "run.sh"), 0o755)
        run("add", "run.sh")
        write("win.md", b"a\r\nb\r\n")
        run("add", "win.md")
        p = problems(t)
        assert len(p) == 1 and "win.md: has CRLF" in p[0], p

        run("rm", "-q", "--cached", "win.md")
        write("blob.bin", b"\0\x01\r\n\x02")
        run("add", "blob.bin")
        run("rm", "-q", "gone.sh")
        assert problems(t) == [], ("binary with CRLF bytes and a deleted script must pass", problems(t))
    print("selftest OK")
    return 0


def main(argv):
    if argv[1:2] == ["--selftest"]:
        return selftest()
    repo = argv[1] if len(argv) > 1 else "."
    found = problems(repo)
    for line in found:
        print("commit-guard: " + line, file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
