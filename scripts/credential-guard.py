#!/usr/bin/env python3
"""credential-guard: keep known credential files out of the session.

A Claude Code hook (PreToolUse and PostToolUse, matcher Bash|PowerShell|Read|Grep).
Known files: .env and its variants (the main case), Spotify prefs, .netrc, cloud and SSH keys.
  Bash        a command that names a known file is wrapped so it always succeeds; in its
              output, every value whose key is not allow-listed is masked (KEY=<withheld>)
              and every non-key line is withheld. Key names stay visible. Lines a recursive
              grep prints from a .env file are masked the same way, whatever the command.
  PowerShell  a command that names one is denied (use Bash).
  Read, Grep  a path or glob that names one is denied.
The header names counts only, never a value. The allow path prints nothing.
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
    # .env, .env.example, .env.local, .env-backup, .envrc; not process.env.X, .environment, env.ts
    ("env", r"(?:^|[\s'\"/\\=:<>(,])\.env(?:rc)?(?:[.-][\w-]+)*(?![\w-])"),
    ("spotify-prefs", r"spotify[\\/](?:[^\s'\"|;&<>]*[\\/])?prefs\b"),
    ("netrc", r"[._]netrc\b"),
    ("git-credentials", r"\.git-credentials\b"),
    ("aws-credentials", r"\.aws[\\/]credentials\b"),
    ("gh-hosts", r"gh[\\/]hosts\.yml\b"),
    ("docker-config", r"\.docker[\\/]config\.json\b"),
    ("ssh-private-key", r"\.ssh[\\/](?:id_[\w-]+(?![\w-])(?!\.pub)|\*)"),
]
_KNOWN = [(label, re.compile(p, re.I)) for label, p in KNOWN]

# group 1: everything up to the value (comment mark, export, key, separator); 2: key; 3: value
KEY_LINE = re.compile(r'^(\s*(?:#\s*)?(?:export\s+)?"?([\w.\-]+)"?\s*[=:]\s*)(.*)$')
HARMLESS = re.compile(r"^(?:\[exit \d+\]|\d{1,3})$")  # the wrap's exit line; `echo $?`
# A grep or rg line from a .env file: path, optional line number, then the line.
GREP_ENV = re.compile(r"^((?:[^\s:]*[\\/])?\.env(?:rc)?(?:[.-][\w-]+)*:(?:\d+[:-])?)(.*)$")

DENY_REASON = ("credential-guard: %s on a known credential file (%s) is blocked. Use the Bash tool "
               "(cat, grep): key names are shown and values off the allow-list are masked. To change "
               "the file, edit it through Bash too. Allow-lists: ai-tools/config/credential-guard.json.")
MASKED = ("credential-guard: %d value%s withheld from a credential file (%s); key names kept. "
          "To show a key's value, he adds it to ai-tools/config/credential-guard.json.")
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
        resp = event.get("tool_response")
        parts = [resp.get("stdout"), resp.get("stderr")] if isinstance(resp, dict) else list(_strings(resp))
        texts, n = [], 0
        for text in parts:
            if isinstance(text, str) and text:
                t, k = _mask_text(text, label, cfg)
                texts.append(t)
                n += k
        if not n:
            return None
        head = MASKED % (n, "" if n == 1 else "s", label or "env")
        return _withhold(head + "\n" + "\n".join(texts))

    return None


def _allowed(cfg, label):
    return set((cfg.get("allow") or {}).get(label) or [])


def _mask_line(line, allowed):
    """(line with its value masked unless the key is allowed, values masked)."""
    s = line.strip()
    if not s or HARMLESS.match(s):
        return line, 0
    m = KEY_LINE.match(line)
    if m:
        if m.group(2) in allowed or m.group(3).strip() in ("", '""', "''"):
            return line, 0
        return m.group(1) + "<withheld>", 1
    if s.startswith("#"):
        return line, 0
    return "<line withheld>", 1


def _mask_text(text, label, cfg):
    """Mask the output of a command. label: the credential file the command names, or None.
    Lines a recursive grep prints from a .env file are masked whatever the command was."""
    out, n = [], 0
    for line in text.split("\n"):
        g = GREP_ENV.match(line)
        if g:
            rest, k = _mask_line(g.group(2), _allowed(cfg, "env"))
            line = g.group(1) + rest
        elif label:
            line, k = _mask_line(line, _allowed(cfg, label))
        else:
            k = 0
        out.append(line)
        n += k
    return "\n".join(out), n


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

    def masked(out):
        o = ((out or {}).get("hookSpecificOutput") or {}).get("updatedToolOutput")
        return o.get("stdout") if o else None

    # Bash, after: values of keys off the allow-list are masked, key names stay.
    m = masked(post(WRAP + "cat " + sp_unix,
                    "app.autostart-mode=\"off\"\nautologin.blob=\"" + blob + "\"\n[exit 0]\n")) or ""
    check("bash post blob masked", "autologin.blob=<withheld>" in m and blob not in m, True)
    check("bash post allowed key kept", 'app.autostart-mode="off"' in m, True)
    check("bash post header counts", m.startswith("credential-guard: 1 value withheld"), True)
    check("bash post allow-listed passes",
          post(WRAP + cmd, "app.autostart-mode=\"off\"\n\n[exit 0]\n"), None)
    check("bash post quoted key passes",
          post(WRAP + cmd, '  "audio.sync_bitrate_enumeration": 4\n'), None)
    m = masked(post(WRAP + cmd, "", "autologin.blob=" + blob)) or ""
    check("bash post blob on stderr masked", "<withheld>" in m and blob not in m, True)
    m = masked(post(WRAP + cmd, blob + "\n")) or ""
    check("bash post non-key line withheld", "<line withheld>" in m and blob not in m, True)
    m = masked(post(WRAP + cmd, "12:autologin.blob=" + blob + "\n")) or ""
    check("bash post grep -n prefix masked", blob not in m and "<withheld>" in m, True)
    check("bash post unrelated untouched", post("cat notes.txt", "token=" + blob + "\n"), None)
    check("bash post exit-code line passes", post(WRAP + "[ -f " + sp_unix + " ]; echo $?", "0\n[exit 0]\n"), None)

    # .env files, the main case.
    envp = "/app/.e" + "nv"
    cfg["allow"]["env"] = ["APP_ENV"]
    check("env pre wrap", "updatedInput" in json.dumps(pre("Bash", {"command": "cat " + envp})), True)
    m = masked(post(WRAP + "cat " + envp,
                    "APP_ENV=local\nDB_PASSWORD=" + blob + "\n# DB_PASSWORD=" + blob + "\nexport API_TOKEN="
                    + blob + "\nEMPTY_ONE=\n# just a comment\n[exit 0]\n")) or ""
    for want in ["APP_ENV=local", "DB_PASSWORD=<withheld>", "# DB_PASSWORD=<withheld>",
                 "export API_TOKEN=<withheld>", "EMPTY_ONE=", "# just a comment"]:
        check("env keeps " + want, want in m, True)
    check("env no value", blob not in m, True)
    check("env header counts", m.startswith("credential-guard: 3 values withheld"), True)
    for p in [envp + ".example", "backend/.e" + "nv.local", "./.e" + "nv", "~/.e" + "nvrc", envp + "-backup"]:
        check("env known " + p, decision(pre("Read", {"file_path": p})), "deny")
    check("env glob known", decision(pre("Grep", {"pattern": "x", "glob": "**/.e" + "nv*"})), "deny")
    for p in ["/repo/.environment.md", "src/env.ts", "/repo/dotenv.md"]:
        check("env not known " + p, pre("Read", {"file_path": p}), None)
    check("env process.env untouched", pre("Bash", {"command": "grep -rn process.e" + "nv.APP_KEY src"}), None)
    # A recursive grep names no file but prints .env lines with a file prefix.
    m = masked(post("grep -rn APP_KEY .", "./.e" + "nv:3:APP_KEY=" + blob + "\nsrc/a.php:9:env('APP_KEY')\n")) or ""
    check("env grep prefix masked", "./.e" + "nv:3:APP_KEY=<withheld>" in m and blob not in m, True)
    check("env grep other lines kept", "src/a.php:9:env('APP_KEY')" in m, True)
    check("env grep allowed key passes", post("grep -rn APP_ENV .", "./.e" + "nv:1:APP_ENV=local\n"), None)

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
