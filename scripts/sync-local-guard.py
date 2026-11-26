#!/usr/bin/env python3
"""sync-local-guard.py — keeps a machine-local copy of credential-guard that the hooks run.

Why: the hooks used to run credential-guard straight from the ai-tools checkout. On the PC that
is the M: share, and when the share drops, Python cannot open the script and exits 2, which
Claude Code reads as "block": every prompt and shell call stopped (2026-11-23). The local copy
lives on the machine's own disk (~/.claude/local-guard, so C: on the PC), keeps scanning while
the share is down, and blocks exactly as the source does whenever it runs.

  sync-local-guard.py             copy the guard down, move local review hits up to the source
  sync-local-guard.py --quiet     the same, printing only problems (for the SessionStart hook)
  sync-local-guard.py --check     read-only: does the local copy match the source? (health check)
  sync-local-guard.py --selftest

The local root can be moved with CREDENTIAL_GUARD_LOCAL_ROOT (used by the selftest).
"""
import hashlib
import os
import shutil
import sys
import tempfile
from enum import IntEnum

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE_ROOT = os.path.dirname(HERE)
DEFAULT_LOCAL_ROOT = os.path.join(os.path.expanduser("~"), ".claude", "local-guard")
LOCAL_ROOT_VARIABLE = "CREDENTIAL_GUARD_LOCAL_ROOT"

# The guard finds its config next to itself (scripts/../config), so the copy keeps that layout.
MIRRORED_FILES = (
    "scripts/credential-guard.py",
    "config/credential-guard.json",
    "config/pii-guard/self.json",
)
PRIVATE_FILES = {"config/pii-guard/self.json"}
REVIEW_LOG = "config/pii-guard/review.tsv"
REVIEW_LOG_IN_TRANSIT_SUFFIX = ".moving-"
PRIVATE_FILE_MODE = 0o600


class SyncExitCode(IntEnum):
    SUCCESS = 0
    LOCAL_COPY_DIFFERS = 1
    SOURCE_UNREACHABLE = 3       # never 2: exit 2 from a hook means "block" to Claude Code
    SELFTEST_FAILED = 4
    INVALID_USAGE = 64


def local_root():
    return os.environ.get(LOCAL_ROOT_VARIABLE) or DEFAULT_LOCAL_ROOT


def path_under(root, relative_path):
    return os.path.join(root, *relative_path.split("/"))


def file_digest(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def source_is_reachable(source_root):
    return os.path.isfile(path_under(source_root, MIRRORED_FILES[0]))


def copy_atomically(source_path, destination_path, is_private):
    os.makedirs(os.path.dirname(destination_path), exist_ok=True)
    handle, staging_path = tempfile.mkstemp(dir=os.path.dirname(destination_path), prefix=".staging-")
    os.close(handle)
    try:
        shutil.copyfile(source_path, staging_path)
        if is_private:
            os.chmod(staging_path, PRIVATE_FILE_MODE)
        os.replace(staging_path, destination_path)
    finally:
        if os.path.exists(staging_path):
            os.remove(staging_path)


def differing_files(source_root, copy_root):
    """Names of mirrored files whose local copy is missing, stale or stray."""
    differing = []
    for relative_path in MIRRORED_FILES:
        source_path, copy_path = path_under(source_root, relative_path), path_under(copy_root, relative_path)
        source_exists, copy_exists = os.path.isfile(source_path), os.path.isfile(copy_path)
        if source_exists != copy_exists:
            differing.append(relative_path + (" (missing locally)" if source_exists else " (stray locally)"))
        elif source_exists and file_digest(source_path) != file_digest(copy_path):
            differing.append(relative_path + " (stale)")
    return differing


def copy_guard_down(source_root, copy_root):
    changed = []
    for relative_path in MIRRORED_FILES:
        source_path, copy_path = path_under(source_root, relative_path), path_under(copy_root, relative_path)
        if os.path.isfile(source_path):
            if not os.path.isfile(copy_path) or file_digest(source_path) != file_digest(copy_path):
                copy_atomically(source_path, copy_path, relative_path in PRIVATE_FILES)
                changed.append(relative_path)
        elif os.path.isfile(copy_path):
            os.remove(copy_path)
            changed.append(relative_path + " (removed)")
    return changed


def move_review_hits_up(source_root, copy_root):
    """Appends the local copy's review hits to the source log, so no hit stays only on one machine.
    The local log is renamed first, so hits the guard writes meanwhile start a fresh file."""
    local_log = path_under(copy_root, REVIEW_LOG)
    if os.path.isfile(local_log) and os.path.getsize(local_log) > 0:
        try:
            os.replace(local_log, local_log + REVIEW_LOG_IN_TRANSIT_SUFFIX + str(os.getpid()))
        except OSError:
            pass  # the guard has it open (Windows); the next sync takes it
    log_folder = os.path.dirname(local_log)
    in_transit = sorted(name for name in (os.listdir(log_folder) if os.path.isdir(log_folder) else [])
                        if name.startswith(os.path.basename(REVIEW_LOG) + REVIEW_LOG_IN_TRANSIT_SUFFIX))
    moved_lines = 0
    for name in in_transit:
        transit_path = os.path.join(log_folder, name)
        with open(transit_path, encoding="utf-8") as handle:
            hits = handle.read()
        if hits and not hits.endswith("\n"):
            hits += "\n"
        source_log = path_under(source_root, REVIEW_LOG)
        os.makedirs(os.path.dirname(source_log), exist_ok=True)
        with open(source_log, "a", encoding="utf-8") as handle:
            handle.write(hits)
        moved_lines += hits.count("\n")
        os.remove(transit_path)
    return moved_lines


def run_sync(source_root, copy_root, quiet):
    if not source_is_reachable(source_root):
        print("local guard copy not refreshed: the source at %s is unreachable; the existing copy "
              "keeps running" % source_root, file=sys.stderr)
        return SyncExitCode.SOURCE_UNREACHABLE
    changed = copy_guard_down(source_root, copy_root)
    moved_lines = move_review_hits_up(source_root, copy_root)
    if not quiet or changed:
        print("local guard copy at %s: %s; %d review hits moved to the source" % (
            copy_root, ", ".join(changed) or "already current", moved_lines))
    return SyncExitCode.SUCCESS


def run_check(source_root, copy_root):
    if not source_is_reachable(source_root):
        print("cannot compare: the source at %s is unreachable" % source_root)
        return SyncExitCode.SOURCE_UNREACHABLE
    differing = differing_files(source_root, copy_root)
    if differing:
        print("local copy at %s differs: %s (fix: python3 %s)" % (
            copy_root, ", ".join(differing), os.path.join(HERE, os.path.basename(__file__))))
        return SyncExitCode.LOCAL_COPY_DIFFERS
    print("local copy at %s matches the source" % copy_root)
    return SyncExitCode.SUCCESS


def selftest():
    failures = []

    def expect(label, actual, wanted):
        if actual != wanted:
            failures.append("%s: got %r, want %r" % (label, actual, wanted))

    workspace = tempfile.mkdtemp()
    source_root, copy_root = os.path.join(workspace, "source"), os.path.join(workspace, "local")
    for relative_path, content in ((MIRRORED_FILES[0], "guard v1\n"), (MIRRORED_FILES[1], "{}\n"),
                                   (MIRRORED_FILES[2], "{\"self\": []}\n")):
        os.makedirs(os.path.dirname(path_under(source_root, relative_path)), exist_ok=True)
        with open(path_under(source_root, relative_path), "w", encoding="utf-8") as handle:
            handle.write(content)
    try:
        expect("no copy yet differs", run_check(source_root, copy_root), SyncExitCode.LOCAL_COPY_DIFFERS)
        expect("first sync", run_sync(source_root, copy_root, quiet=True), SyncExitCode.SUCCESS)
        expect("copy matches", run_check(source_root, copy_root), SyncExitCode.SUCCESS)
        if os.name == "posix":
            expect("private file is owner-only",
                   os.stat(path_under(copy_root, MIRRORED_FILES[2])).st_mode & 0o777, PRIVATE_FILE_MODE)
        with open(path_under(source_root, MIRRORED_FILES[0]), "w", encoding="utf-8") as handle:
            handle.write("guard v2\n")
        expect("stale copy differs", run_check(source_root, copy_root), SyncExitCode.LOCAL_COPY_DIFFERS)
        expect("stale copy is named", differing_files(source_root, copy_root),
               [MIRRORED_FILES[0] + " (stale)"])
        run_sync(source_root, copy_root, quiet=True)
        with open(path_under(copy_root, MIRRORED_FILES[0]), encoding="utf-8") as handle:
            expect("sync refreshes the guard", handle.read(), "guard v2\n")
        os.remove(path_under(source_root, MIRRORED_FILES[2]))
        run_sync(source_root, copy_root, quiet=True)
        expect("file gone from source is removed locally",
               os.path.exists(path_under(copy_root, MIRRORED_FILES[2])), False)
        local_log = path_under(copy_root, REVIEW_LOG)
        with open(local_log, "w", encoding="utf-8") as handle:
            handle.write("hit one\nhit two")
        with open(local_log + REVIEW_LOG_IN_TRANSIT_SUFFIX + "1", "w", encoding="utf-8") as handle:
            handle.write("leftover hit\n")
        run_sync(source_root, copy_root, quiet=True)
        with open(path_under(source_root, REVIEW_LOG), encoding="utf-8") as handle:
            moved = sorted(handle.read().splitlines())
        expect("review hits reach the source, leftovers included", moved,
               ["hit one", "hit two", "leftover hit"])
        expect("local review log is emptied", os.path.exists(local_log), False)
        expect("review log is never mirrored down", REVIEW_LOG in MIRRORED_FILES, False)
        shutil.rmtree(source_root)
        expect("sync with the share down", run_sync(source_root, copy_root, quiet=True),
               SyncExitCode.SOURCE_UNREACHABLE)
        expect("copy survives the share being down",
               os.path.isfile(path_under(copy_root, MIRRORED_FILES[0])), True)
        expect("check with the share down", run_check(source_root, copy_root), SyncExitCode.SOURCE_UNREACHABLE)
        expect("no exit code means block", 2 in {code.value for code in SyncExitCode}, False)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    for failure in failures:
        print("FAIL " + failure)
    print("sync-local-guard selftest: %d failed" % len(failures))
    return SyncExitCode.SELFTEST_FAILED if failures else SyncExitCode.SUCCESS


def main(arguments):
    if arguments == ["--selftest"]:
        return selftest()
    if arguments == ["--check"]:
        return run_check(SOURCE_ROOT, local_root())
    if arguments in ([], ["--quiet"]):
        return run_sync(SOURCE_ROOT, local_root(), quiet=arguments == ["--quiet"])
    print(__doc__.strip(), file=sys.stderr)
    return SyncExitCode.INVALID_USAGE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
