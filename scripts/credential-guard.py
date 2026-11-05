#!/usr/bin/env python3
"""credential-guard: keep known credential files out of the session.

A Claude Code hook (PreToolUse and PostToolUse, matcher Bash|PowerShell|Read|Grep).
  Bash        a command that names a known credential file is wrapped so it always
              succeeds; afterwards its output must be allow-listed key lines only,
              or the whole output is withheld.
  PowerShell  a command that names one is denied (use Bash with a key filter).
  Read, Grep  a path or glob that names one is denied.
The notice names counts only, never a value. The allow path prints nothing.
Allow-lists: ../config/credential-guard.json. Plan: ~/www/.plans/credential-guard/PLAN.md

Usage: credential-guard.py          (hook; event read from stdin)
       credential-guard.py --selftest
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "..", "config", "credential-guard.json")

# Spike 0 (pii-guard, 2026-10-28), result E: this form keeps PostToolUse firing on a failed
# command. Result C: the rewrite is this prefix plus the original command, nothing else.
WRAP = "trap 'r=$?; echo \"[exit $r]\"; exit 0' EXIT; exec 2>&1; "


# (label, pattern). A command, path or glob "names" a file when its text matches.
# A path built at run time (cd x; cat prefs) is not seen: that takes a deliberate attempt.
KNOWN = [
    ("spotify-prefs", r"spotify[\\/](?:[^\s'\"|;&<>]*[\\/])?prefs\b"),
    ("netrc", r"[._]netrc\b"),
    ("git-credentials", r"\.git-credentials\b"),
    ("aws-credentials", r"\.aws[\\/]credentials\b"),
    ("gh-hosts", r"gh[\\/]hosts\.yml\b"),
    ("docker-config", r"\.docker[\\/]config\.json\b"),
    ("ssh-private-key", r"\.ssh[\\/](?:id_[\w-]+(?![\w-])(?!\.pub)|\*)"),
]
_KNOWN = [(label, re.compile(p, re.I)) for label, p in KNOWN]

KEY_LINE = re.compile(r'^"?([\w.\-]+)"?\s*[=:]')
HARMLESS = re.compile(r"^(?:\[exit \d+\]|\d{1,3})$")  # the wrap's exit line; `echo $?`

DENY_REASON = ("credential-guard: %s on a known credential file (%s) is blocked. Read it with the "
               "Bash tool and print only allow-listed keys, e.g. grep -E '^(key1|key2)=' <file>. "
               "Allow-lists: ai-tools/config/credential-guard.json.")
WITHHELD = ("credential-guard: output withheld. It printed %d line%s from a credential file (%s) "
            "outside the key allow-list. Values are not shown. Print only allow-listed keys, or ask "
            "him to add a key to ai-tools/config/credential-guard.json.")
FAILED_PRE = "credential-guard: blocked (internal error on a call that names a credential file)."
FAILED_POST = "credential-guard: output withheld (internal error on a command that names a credential file)."


def names_known(*texts):
    """Label of the first known credential file any of the texts names, else None."""
    for text in texts:
        if isinstance(text, str):
            for label, rx in _KNOWN:
                if rx.search(text):
                    return label
    return None


def load_config():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"allow": {}}


def _deny(reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def _withhold(text):
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedToolOutput": {
        "stdout": text, "stderr": "", "interrupted": False, "isImage": False}}}


def _strings(value):
    """Every string inside a tool response, whatever its shape."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def handle(event, cfg):
    """The hook's reply as a dict, or None to stay silent."""
    ev = event.get("hook_event_name")
    tool = event.get("tool_name")
    ti = event.get("tool_input") or {}
    if not isinstance(ti, dict):
        return None
    cmd = ti.get("command")

    if ev == "PreToolUse":
        if tool == "Bash" and isinstance(cmd, str) and not cmd.startswith(WRAP) and names_known(cmd):
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                           "updatedInput": dict(ti, command=WRAP + cmd)}}
        if tool == "PowerShell":
            label = names_known(cmd)
        elif tool == "Read":
            label = names_known(ti.get("file_path"))
        elif tool == "Grep":
            label = names_known(ti.get("path"), ti.get("glob"))
        else:
            return None
        return _deny(DENY_REASON % (tool, label)) if label else None

    if ev == "PostToolUse" and tool == "Bash":
        label = names_known(cmd)
        if not label:
            return None
        allowed = set((cfg.get("allow") or {}).get(label) or [])
        bad = 0
        for text in _strings(event.get("tool_response")):
            for line in text.splitlines():
                line = line.strip()
                if not line or HARMLESS.match(line):
                    continue
                m = KEY_LINE.match(line)
                if not (m and m.group(1) in allowed):
                    bad += 1
        return _withhold(WITHHELD % (bad, "" if bad == 1 else "s", label)) if bad else None

    return None


def run(raw, load=None):
    """Hook I/O: stdin text in, stdout text out. Fails closed once a known file is named."""
    try:
        event = json.loads(raw)
    except ValueError:
        return ""
    if not isinstance(event, dict):
        return ""
    try:
        out = handle(event, (load or load_config)())
        return json.dumps(out) if out else ""
    except Exception:
        ti = event.get("tool_input")
        texts = list(_strings(ti)) if isinstance(ti, (dict, list)) else [ti]
        if not names_known(*texts):
            return ""
        if event.get("hook_event_name") == "PreToolUse":
            return json.dumps(_deny(FAILED_PRE))
        return json.dumps(_withhold(FAILED_POST))


# ---------------------------------------------------------------- selftest

def selftest():
    # Fixtures are built at run time, so the source holds no path or value the guard matches.
    spot = "Spot" + "ify"
    sp_unix = '"$APPDATA/' + spot + '/pr' + 'efs"'
    sp_win = "C:\\Users\\x\\AppData\\Roaming\\" + spot + "\\pr" + "efs"
    sp_users = "$env:LOCALAPPDATA\\" + spot + "\\Users\\abc-user\\pr" + "efs"
    blob = "x7Qa" * 12
    cfg = {"allow": {"spotify-prefs": ["app.autostart-mode", "audio.sync_bitrate_enumeration"]}}
    fails = []

    def check(name, got, want):
        if got != want:
            fails.append("%s: got %r, want %r" % (name, got, want))

    def pre(tool, ti):
        return handle({"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": ti}, cfg)

    def post(cmd, stdout, stderr=""):
        resp = {"stdout": stdout, "stderr": stderr, "interrupted": False, "isImage": False}
        return handle({"hook_event_name": "PostToolUse", "tool_name": "Bash",
                       "tool_input": {"command": cmd}, "tool_response": resp}, cfg)

    def decision(out):
        return ((out or {}).get("hookSpecificOutput") or {}).get("permissionDecision")

    def withheld(out):
        o = ((out or {}).get("hookSpecificOutput") or {}).get("updatedToolOutput")
        return bool(o) and o.get("stdout", "").startswith("credential-guard: output withheld")

    # Bash, before: only commands naming a known file are touched, and only by the fixed prefix.
    check("bash pre unrelated", pre("Bash", {"command": "ls -la"}), None)
    cmd = "cat " + sp_unix + " | grep -E '^app\\.autostart-mode='"
    out = pre("Bash", {"command": cmd, "description": "d"})
    check("bash pre wrap", (out or {}).get("hookSpecificOutput", {}).get("updatedInput"),
          {"command": WRAP + cmd, "description": "d"})
    check("bash pre already wrapped", pre("Bash", {"command": WRAP + cmd}), None)

    # Bash, after.
    out = post(WRAP + "cat " + sp_unix, "app.autostart-mode=\"off\"\nautologin.blob=\"" + blob + "\"\n[exit 0]\n")
    check("bash post blob withheld", withheld(out), True)
    check("bash post notice has no value", blob in json.dumps(out), False)
    check("bash post notice counts", "1 line" in json.dumps(out), True)
    check("bash post allow-listed passes",
          post(WRAP + cmd, "app.autostart-mode=\"off\"\n\n[exit 0]\n"), None)
    check("bash post quoted key passes",
          post(WRAP + cmd, '  "audio.sync_bitrate_enumeration": 4\n'), None)
    check("bash post blob on stderr withheld", withheld(post(WRAP + cmd, "", "autologin.blob=" + blob)), True)
    check("bash post non-key line withheld", withheld(post(WRAP + cmd, blob + "\n")), True)
    check("bash post grep -n prefix withheld", withheld(post(WRAP + cmd, "12:app.autostart-mode=off\n")), True)
    check("bash post unrelated untouched", post("cat notes.txt", "token=" + blob + "\n"), None)
    check("bash post exit-code line passes", post(WRAP + "[ -f " + sp_unix + " ]; echo $?", "0\n[exit 0]\n"), None)

    # PowerShell, Read, Grep: denied when they name a known file.
    check("ps deny", decision(pre("PowerShell", {"command": "Get-Content " + sp_users})), "deny")
    check("ps unrelated", pre("PowerShell", {"command": "Get-ChildItem C:\\"}), None)
    check("read deny", decision(pre("Read", {"file_path": sp_win})), "deny")
    check("read unrelated", pre("Read", {"file_path": "C:\\notes\\" + spot + "-prefs-notes.md"}), None)
    check("grep deny path", decision(pre("Grep", {"pattern": "x", "path": "/Users/b/.aws/credentials"})), "deny")
    check("grep deny glob", decision(pre("Grep", {"pattern": "x", "path": "/h", "glob": "**/.git-credentials"})), "deny")

    # The known-file list.
    ssh = "/Users/b/.ssh/id_" + "ed25519"
    for p in ["~/.ne" + "trc", "C:\\Users\\x\\_ne" + "trc", "~/.config/gh/hosts.yml",
              "~/.docker/config.json", ssh, "cat ~/.ssh/*"]:
        check("known " + p, decision(pre("Read", {"file_path": p})), "deny")
    for p in [ssh + ".pub", "/repo/README.md", "/repo/prefs.json", "/repo/docker/config.json"]:
        check("not known " + p, pre("Read", {"file_path": p}), None)

    # run(): hook I/O and failing closed.
    check("run unrelated prints nothing", run(json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                                          "tool_input": {"command": "ls"}}), lambda: cfg), "")
    check("run bad stdin prints nothing", run("not json", lambda: cfg), "")

    def boom():
        raise ValueError("config broken")
    ev = {"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {"file_path": sp_win}}
    check("run error on known file denies", decision(json.loads(run(json.dumps(ev), boom) or "{}")), "deny")
    ev = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": WRAP + cmd},
          "tool_response": {"stdout": "autologin.blob=" + blob, "stderr": "", "interrupted": False, "isImage": False}}
    got = run(json.dumps(ev), boom)
    check("run error on known file withholds", withheld(json.loads(got or "{}")) and blob not in got, True)
    ev["tool_input"] = {"command": "ls"}
    check("run error on unrelated prints nothing", run(json.dumps(ev), boom), "")

    # The shipped config loads and only lists labels the script knows.
    real = load_config()
    check("config labels known", sorted(set(real.get("allow", {})) - set(l for l, _ in KNOWN)), [])

    for f in fails:
        print("FAIL " + f)
    print("credential-guard selftest: %d failed" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        try:
            sys.exit(selftest())
        except Exception as e:  # a stub or a crash is a red test, not a traceback
            print("FAIL selftest crashed: %s" % type(e).__name__)
            sys.exit(1)
    sys.stdout.write(run(sys.stdin.read()))
