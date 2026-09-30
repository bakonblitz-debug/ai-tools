#!/usr/bin/env python3
"""install.py — wire the harness into a Claude Code install, for someone who is not him.

Asks what exists on this machine, writes harness/.env, merges the hooks the user
agreed to into ~/.claude/settings.json, and prints how to undo it.

The dangerous operation is the settings merge: a stranger's settings.json already
has their own hooks in it, and clobbering it is the worst thing this script can do.
That is why merge_hooks() is a pure function with the selftest pointed at it.

Usage: install.py [--selftest] [--dry-run]
"""
import datetime
import json
import os
import platform
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # never derived from a detected root:
HARNESS = HERE.parent                            # a script must find files next to it


def harness_dir(argv):
    """Where .env gets written. Overridable because otherwise there is no way to run
    this installer without mutating the live one — which is exactly how the real
    harness/.env got clobbered by a test run on 2026-09-30. HOME redirects settings
    and the plist; nothing redirected this."""
    for i, a in enumerate(argv):
        if a == "--harness-dir" and i + 1 < len(argv):
            return Path(argv[i + 1]).resolve()
        if a.startswith("--harness-dir="):
            return Path(a.split("=", 1)[1]).resolve()
    return HARNESS

# Three groups, not eight yes/nos. The split is by what each hook actually needs:
# six want the context repo (which most strangers will not have), one wants only a
# writable .plans/, and exactly one depends on nothing at all.
GROUPS = {
    "context": {
        "needs": "a context repo",
        "hooks": [
            ("SessionStart", None, "bash {h}/claude-bootstrap.sh {ctx}", 15, False),
            ("UserPromptSubmit", None, "bash {h}/plan-mindset.sh {ctx}", 10, False),
            ("UserPromptSubmit", None, "bash {h}/wrong.sh {ctx} --hook", 10, False),
            ("PostToolUse", "Write|Edit", "bash {h}/sync-memory.sh {ctx}", 90, True),
            ("Stop", None, "bash {h}/sync-memory.sh {ctx}", 90, True),
            ("Stop", None, "python3 {h}/session-audit.py {ctx}", 30, True),
        ],
    },
    "budget": {
        "needs": "nothing",
        "hooks": [
            ("UserPromptSubmit", None,
             "CONTEXT_WINDOW=${{CONTEXT_WINDOW:-1000000}} python3 {h}/context-budget.py --hook",
             10, False),
        ],
    },
    "plans": {
        "needs": "a writable .plans/ under the workspace root",
        "hooks": [("UserPromptSubmit", None, "bash {h}/handoff.sh --hook", 10, False)],
    },
}


def merge_hooks(settings, group_names, paths):
    """Return settings with the chosen groups' hooks merged in. Never destructive.

    Keyed on the rendered command string: a hook already present is left alone, which
    is what makes a re-run a no-op instead of a second copy. Everything already in the
    file — other hooks, unrelated top-level keys — is carried through untouched.
    """
    out = json.loads(json.dumps(settings))       # copy; callers keep their input
    hooks = out.setdefault("hooks", {})
    for name in group_names:
        for event, matcher, template, timeout, is_async in GROUPS[name]["hooks"]:
            cmd = template.format(**paths)
            groups = hooks.setdefault(event, [])
            if any(h.get("command") == cmd for g in groups for h in g.get("hooks", [])):
                continue                          # already wired; a re-run is a no-op
            entry = {"type": "command", "command": cmd, "timeout": timeout}
            if is_async:
                entry["async"] = True
            for g in groups:                      # join the group with the same matcher
                if g.get("matcher") == matcher:
                    g.setdefault("hooks", []).append(entry)
                    break
            else:
                g = {"hooks": [entry]}
                if matcher:
                    g["matcher"] = matcher
                groups.append(g)
    return out


def selftest():
    fails = []

    def bad(m):
        fails.append(m)
        print(f"  FAIL {m}")

    def ok(m):
        print(f"  ok   {m}")

    paths = {"h": "/opt/harness/scripts", "ctx": "/opt/context"}

    # 1. THE case. A stranger's own hook must survive the merge untouched.
    theirs = {
        "model": "opus",
        "hooks": {
            "UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": "echo mine", "timeout": 5}]}
            ]
        },
    }
    out = merge_hooks(theirs, ["budget"], paths)
    cmds = [h["command"] for g in out["hooks"]["UserPromptSubmit"] for h in g["hooks"]]
    if "echo mine" not in cmds:
        bad("merge dropped a pre-existing hook")
    elif out.get("model") != "opus":
        bad("merge dropped an unrelated top-level setting")
    elif not any("context-budget.py" in c for c in cmds):
        bad("merge did not add the requested hook")
    else:
        ok("a pre-existing unrelated hook survives the merge")

    # 2. Idempotent: running twice must not double-wire.
    once = merge_hooks({}, ["context", "budget", "plans"], paths)
    twice = merge_hooks(json.loads(json.dumps(once)), ["context", "budget", "plans"], paths)
    if json.dumps(once, sort_keys=True) != json.dumps(twice, sort_keys=True):
        bad("second run changed the settings — not idempotent")
    else:
        ok("running twice wires nothing a second time")

    # 3. Declining everything leaves the file byte-identical.
    before = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "theirs"}]}]}}
    after = merge_hooks(json.loads(json.dumps(before)), [], paths)
    if json.dumps(before, sort_keys=True) != json.dumps(after, sort_keys=True):
        bad("declining every group still modified the settings")
    else:
        ok("declining every group leaves settings untouched")

    # 4. A group that was not chosen is not wired.
    out = merge_hooks({}, ["budget"], paths)
    all_cmds = [h["command"] for ev in out["hooks"].values() for g in ev for h in g["hooks"]]
    if any("sync-memory" in c or "session-audit" in c for c in all_cmds):
        bad("wired the context group without being asked")
    else:
        ok("an unchosen group is not wired")

    # 5. Paths are substituted, and no placeholder survives into the output.
    out = merge_hooks({}, ["context"], paths)
    all_cmds = [h["command"] for ev in out["hooks"].values() for g in ev for h in g["hooks"]]
    if any("{h}" in c or "{ctx}" in c for c in all_cmds):
        bad("an unsubstituted placeholder reached the settings")
    elif not all(c.startswith(("bash /opt/harness", "python3 /opt/harness")) for c in all_cmds):
        bad(f"paths not substituted: {all_cmds}")
    else:
        ok("paths are substituted into every command")

    # 6. The matcher and async flags survive — PostToolUse without its matcher would
    #    fire sync-memory on every single tool call.
    out = merge_hooks({}, ["context"], paths)
    ptu = out["hooks"]["PostToolUse"]
    if not any(g.get("matcher") == "Write|Edit" for g in ptu):
        bad("PostToolUse lost its matcher — would fire on every tool call")
    elif not ptu[0]["hooks"][0].get("async"):
        bad("async flag lost")
    else:
        ok("matcher and async survive onto PostToolUse")

    # 7. --harness-dir must redirect the .env write. Without this the installer
    #    cannot be exercised without overwriting the live config; it did exactly
    #    that once, on 2026-09-30.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        if harness_dir(["--harness-dir", td]) != Path(td).resolve():
            bad("--harness-dir not honoured (space form)")
        elif harness_dir([f"--harness-dir={td}"]) != Path(td).resolve():
            bad("--harness-dir not honoured (equals form)")
        elif harness_dir([]) != HARNESS:
            bad("harness_dir default moved off the real harness")
        else:
            write_env({"WORKSPACE_ROOT": "/x"}, False, Path(td))
            if (Path(td) / ".env").read_text() != "WORKSPACE_ROOT=/x\n":
                bad("write_env ignored its target")
            else:
                ok("--harness-dir redirects the .env write away from the live config")

    if fails:
        print(f"selftest FAILED ({len(fails)})")
        return 1
    print("selftest passed")
    return 0


def detect_root():
    """Mirror of lib-root.sh. Kept in step with it deliberately — two implementations
    of one rule is a smell, but a bash helper cannot be sourced from Python without
    shelling out, and this is four lines."""
    if os.environ.get("WORKSPACE_ROOT"):
        return Path(os.environ["WORKSPACE_ROOT"])
    sysname = platform.system()
    if sysname == "Darwin":
        return Path.home() / "www"
    if sysname == "Windows":
        return Path("/m")
    if "microsoft" in platform.release().lower():
        return Path("/mnt/www")
    return Path.home() / "www"


def ask(prompt, default=None, skippable=True):
    hint = f" [{default}]" if default else (" [skip]" if skippable else "")
    try:
        got = input(f"{prompt}{hint}: ").strip()
    except EOFError:
        got = ""
    if not got:
        return default
    return "" if got == "-" else got


def confirm(prompt, default=True):
    got = ask(f"{prompt} (y/n)", "y" if default else "n")
    return str(got).lower().startswith("y")


def write_env(values, dry, target=None):
    """.env is machine-local and gitignored. An existing one is shown, never replaced
    behind his back — it is the file that proves the config worked on a real setup."""
    path = (target or HARNESS) / ".env"
    body = "".join(f"{k}={v}\n" for k, v in values.items() if v)
    if path.exists():
        if path.read_text() == body:
            print(f"  .env unchanged ({path})")
            return
        print(f"\n  {path} already exists and differs. Current:\n")
        for line in path.read_text().splitlines():
            print(f"    {line}")
        print("\n  New:\n")
        for line in body.splitlines():
            print(f"    {line}")
        if not confirm("\n  Replace it?", False):
            print("  kept the existing .env")
            return
    if dry:
        print(f"  [dry-run] would write {path}")
        return
    path.write_text(body)
    print(f"  wrote {path}")


def render_plist(root, dry, target=None):
    src = (target or HARNESS) / "templates" / "context-check.plist.example"
    if platform.system() != "Darwin" or not src.exists():
        return None
    dest = Path.home() / "Library" / "LaunchAgents" / "com.example.context-check.plist"
    body = src.read_text().replace("@WORKSPACE_ROOT@", str(Path.home()))
    if dry:
        print(f"  [dry-run] would render {dest}")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(body)
    print(f"  rendered {dest}")
    return dest


def main(argv):
    dry = "--dry-run" in argv
    hdir = harness_dir(argv)
    print("harness install\n" + "-" * 40)
    if dry:
        print("dry run — nothing will be written\n")

    root = ask("Workspace root", str(detect_root()))
    ctx_default = str(Path(root) / "context") if (Path(root) / "context").is_dir() else None
    ctx = ask("Context repo (enter '-' if you have none)", ctx_default)
    remote = ask("Remote host for the other machine ('-' for none)", None)

    chosen = []
    for name, spec in GROUPS.items():
        if name == "context" and not ctx:
            print(f"  skipping the '{name}' hooks — they need {spec['needs']}")
            continue
        if confirm(f"Wire the '{name}' hooks? (needs {spec['needs']})"):
            chosen.append(name)

    env = {"WORKSPACE_ROOT": root, "CONTEXT_ROOT": ctx or "", "REMOTE_HOST": remote or ""}
    print()
    write_env(env, dry, hdir)

    settings = Path.home() / ".claude" / "settings.json"
    backup = None
    if chosen:
        current = json.loads(settings.read_text()) if settings.exists() else {}
        merged = merge_hooks(current, chosen,
                             {"h": str(HERE), "ctx": ctx or ""})
        if merged == current:
            print("  settings.json already has these hooks — nothing to do")
        elif dry:
            print(f"  [dry-run] would merge {len(chosen)} group(s) into {settings}")
        else:
            if settings.exists():
                stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
                backup = settings.with_suffix(f".json.bak-{stamp}")
                shutil.copy2(settings, backup)
                print(f"  backed up {settings} -> {backup}")
            settings.parent.mkdir(parents=True, exist_ok=True)
            settings.write_text(json.dumps(merged, indent=2) + "\n")
            print(f"  merged {len(chosen)} group(s) into {settings}")

    plist = render_plist(root, dry, hdir) if confirm("Install the monthly context check (macOS)?", False) else None

    print("\n" + "-" * 40 + "\nTo undo:")
    if backup:
        print(f"  cp {backup} {settings}")
    elif chosen:
        print(f"  edit {settings} and remove the harness commands from 'hooks'")
    print(f"  rm {hdir / '.env'}")
    if plist:
        print(f"  launchctl unload {plist} && rm {plist}")
    print("\nHermes is not wired by this script — see harness/hermes-AGENTS.md for the manual step.")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main(sys.argv[1:]))
