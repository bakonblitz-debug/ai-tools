#!/usr/bin/env python3
"""credential-guard: keep secrets out of what the session sends to the model.

A Claude Code hook, run locally (no network, no model). Registered on:
  PreToolUse  Bash|PowerShell   every command is wrapped so it always ends in success;
                                a failed command's output cannot be replaced otherwise
                                (spikes: pii-guard spike-0, credential-guard spike-1).
  PostToolUse Bash|PowerShell|Read|Grep
                                the output is masked before the model sees it:
                                1. a known credential file (.env first, see KNOWN) named by
                                   the command or path: every value whose key is not
                                   allow-listed becomes <withheld>, key names stay; strict
                                   files (SSH keys, .netrc...) lose every non-key line too;
                                2. on every output, whatever the command: secret shapes
                                   (vendor tokens, private keys, base64 app keys, JWTs,
                                   user:pass@ URLs, PASSWORD/SECRET/TOKEN/_KEY=value lines
                                   and quoted literals in code).
  UserPromptSubmit              a prompt holding a secret shape is blocked before it is
                                sent; start it with "secret-ok" to send it anyway.
The notices name counts only, never a value. Nothing to mask: prints nothing.
Allow-lists: ../config/credential-guard.json. Plan: ~/www/.plans/credential-guard/PLAN.md

Usage: credential-guard.py          (hook; event read from stdin)
       credential-guard.py --selftest
"""
import copy
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "..", "config", "credential-guard.json")

# The rewrite is a fixed prefix (and suffix) plus the original command byte for byte, nothing
# else: Claude Code does not re-check a rewritten command against the permission rules.
WRAP_BASH = "trap 'r=$?; echo \"[exit $r]\"; exit 0' EXIT; exec 2>&1; "
PS_HEAD = "try { "
PS_TAIL = "\n} finally { \"[exit $LASTEXITCODE]\"; exit 0 }"

_CTX = r"(?:^|[\s'\"/\\=:<>(,])"
# (label, pattern, strict). A command, path or glob "names" a file when its text matches.
# strict: the file has no harmless non-key lines, so every non-key line is withheld too.
KNOWN = [
    # .env, .env.example, .env.local, .env-backup, .envrc; not process.env.X, .environment, env.ts
    ("env", _CTX + r"\.env(?:rc)?(?:[.-][\w-]+)*(?![\w-])", False),
    ("spotify-prefs", r"spotify[\\/](?:[^\s'\"|;&<>]*[\\/])?prefs\b", False),
    ("netrc", r"[._]netrc\b", True),
    ("git-credentials", r"\.git-credentials\b", True),
    ("aws-credentials", r"\.aws[\\/]credentials\b", False),
    ("gh-hosts", r"gh[\\/]hosts\.yml\b", False),
    ("docker-config", r"\.docker[\\/]config\.json\b", False),
    ("ssh-private-key", r"\.ssh[\\/](?:id_[\w-]+(?![\w-])(?!\.pub)|\*)", True),
    ("composer-auth", _CTX + r"auth\.json\b", False),
    ("npmrc", r"\.npmrc\b", False),
    ("pypirc", r"\.pypirc\b", False),
    ("pgpass", r"[._]pgpass\b|pgpass\.conf\b", True),
    ("mysql-cnf", r"\.my\.cnf\b", False),
    ("htpasswd", r"\.htpasswd\b", True),
    ("gcloud-credentials", r"(?:application_default_|\b)credentials\.json\b|service[-_]account[\w.-]*\.json\b", False),
    ("kubeconfig", r"\.kube[\\/]config\b", False),
    ("wp-config", r"wp-config\.php\b", False),
]
_KNOWN = [(label, re.compile(p, re.I), strict) for label, p, strict in KNOWN]
_STRICT = {label for label, _, strict in KNOWN if strict}
# A grep/rg line from a known file: path, optional line number, then the file's line.
_PREFIX = [(label, re.compile(r"^(.*?(?:" + p + r"):(?:\d+[:-])?)(.*)$", re.I)) for label, p, _ in KNOWN]

# group 1: everything up to the value (comment mark, export, key, separator); 2: key; 3: value
KEY_LINE = re.compile(r'^(\s*(?:#\s*)?(?:export\s+)?"?([\w.\-]+)"?\s*[=:]\s*)(.*)$')
HARMLESS = re.compile(r"^(?:\[exit -?\d*\]|\d{1,3})$")  # the wraps' exit line; `echo $?`

# Secret shapes, checked on every output.
TOKENS = [re.compile(p) for p in [
    r"sk-ant-[\w-]{20,}",
    r"\bsk-(?:proj-)?(?=[\w-]*\d)(?=[\w-]*[A-Z])[\w-]{20,}",
    r"\bgh[pousr]_[A-Za-z0-9]{30,}",
    r"\bgithub_pat_\w{40,}",
    r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
    r"\bxox[abprs]-[\w-]{10,}",
    r"\bAIza[\w-]{35}",
    r"\bglpat-[\w-]{20,}",
    r"\b[sr]k_live_\w{20,}",
    r"\bSG\.[\w-]{22}\.[\w-]{43}",
    r"\bnpm_[A-Za-z0-9]{36}\b",
    r"\bhf_[A-Za-z0-9]{34}\b",
    r"\beyJ[\w-]{10,}\.eyJ[\w-]{10,}\.[\w-]{10,}",
    r"base64:[A-Za-z0-9+/]{30,}={0,2}",
]]
PK_BEGIN = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")
PK_END = re.compile(r"-----END [A-Z0-9 ]*PRIVATE KEY-----")
PK_INLINE = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|$)")
URL_CRED = re.compile(r"\b([a-z][a-z0-9+.-]*://[^\s:/@'\"]+:)([^\s@/'\"]+)@", re.I)
SECRET_KEY = re.compile(r"pass(?:word|wd|phrase)|secret|token|api[_-]?key|private[_-]?key|app[_-]?key"
                        r"|access[_-]?key|credential|dsn|[_-]key$", re.I)
QUOTED_KV = re.compile(r"""(["']?)([\w.-]*)\1(\s*(?:=>|[:=,])\s*)(["'])([^"'\n]*)\4""")
INLINE_EQ = re.compile(r"(?<![\w.-])([\w.-]+)(\s*=\s*)([^\s'\"&,;]*)")
YAML_KV = re.compile(r"^(\s*(?:[+-]\s*)?(?:#\s*)?)([\w.-]+)(:\s+)([^\s'\"#,;][^\s#,;]*)\s*$")
PLACEHOLDERS = {"null", "none", "nil", "true", "false", "undefined", "string", "number", "boolean",
                "bool", "int", "str", "required", "nullable", "confirmed", "sometimes", "hashed",
                "encrypted", "password", "passwd", "secret", "token", "changeme", "change_me",
                "example", "redacted", "empty", "test", "todo"}

MASKED = ("credential-guard: %d value%s withheld (%s); key names kept. To show a key's value, "
          "he adds it to ai-tools/config/credential-guard.json.")
NOTE = "[credential-guard: %d value%s withheld (%s)]"
PROMPT_BLOCK = ("credential-guard: this prompt looks like it holds %d secret value%s, so it was not "
                "sent. Remove them, or start the prompt with secret-ok to send it as it is.")
FAILED = "credential-guard: output withheld (internal error)."


def names_known(*texts):
    """Label of the first known credential file any of the texts names, else None."""
    for text in texts:
        if isinstance(text, str):
            for label, rx, _ in _KNOWN:
                if rx.search(text):
                    return label
    return None


def strip_prose(cmd):
    """The command without the text it only says: heredoc bodies, -m messages, echo text.
    So a commit message that mentions .env does not make the output a credential file's."""
    cmd = re.sub(r"<<-?\s*(['\"]?)(\w+)\1.*?^\s*\2\s*$", " ", cmd, flags=re.S | re.M)
    q = r"('[^']*'|\"(?:[^\"\\]|\\.)*\")"
    cmd = re.sub(r"(?:\s-m|--message)\s*=?\s*" + q, " ", cmd)
    return re.sub(r"\b(?:echo|printf|Write-Output|Write-Host)\s+" + q, " ", cmd)


def load_config():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"allow": {}}


def _allowed(cfg, label):
    return set((cfg.get("allow") or {}).get(label) or [])


def _placeholder(v):
    lv = v.lower()
    return (not v or lv in PLACEHOLDERS or v[0] in "<${%[(*=>!&|" or v.isdigit()
            or re.fullmatch(r"[x*.#-]+", lv) is not None or lv.startswith(("your", "change", "example"))
            or "{{" in v)


def _secret_literal(v):
    """A quoted value in code or config that looks like a real secret."""
    return (len(v) >= 6 and not re.search(r"[\s|]", v) and not _placeholder(v)
            and not re.fullmatch(r"[a-z]+(?:[_.-][a-z]+)+", v))


def _secret_bare(v, spaced):
    """An unquoted value. With spaces around the separator it is code-shaped, so a plain
    identifier (hashed_pw, request.form) is not a secret."""
    if len(v) < 4 or _placeholder(v) or re.search(r"[\s()\[\]{}]", v):
        return False
    return not (spaced and re.fullmatch(r"[A-Za-z_][A-Za-z_.]*", v))


def _is_secret_key(k):
    k = k.strip("\"'")
    return bool(SECRET_KEY.search(k)) or k.lower().lstrip("_") == "auth"


def _sub_spans(line, spans):
    """Replace (start, end) spans of line with <withheld>, right to left."""
    for a, b in sorted(spans, reverse=True):
        line = line[:a] + "<withheld>" + line[b:]
    return line, len(spans)


def scan_line(line):
    """(line with secret-shaped values masked, how many)."""
    n = 0
    for rx in TOKENS:
        line, k = rx.subn("<withheld>", line)
        n += k
    line, k = PK_INLINE.subn("<withheld>", line)
    n += k
    spans = [m.span(2) for m in URL_CRED.finditer(line) if not _placeholder(m.group(2))]
    line, k = _sub_spans(line, spans)
    n += k
    spans = [m.span(5) for m in QUOTED_KV.finditer(line)
             if _is_secret_key(m.group(2)) and _secret_literal(m.group(5))]
    line, k = _sub_spans(line, spans)
    n += k
    spans = [m.span(3) for m in INLINE_EQ.finditer(line)
             if _is_secret_key(m.group(1)) and _secret_bare(m.group(3), m.group(2) != "=")]
    line, k = _sub_spans(line, spans)
    n += k
    m = YAML_KV.match(line)
    if m and _is_secret_key(m.group(2)) and _secret_bare(m.group(4), True):
        line, k = _sub_spans(line, [m.span(4)])
        n += k
    return line, n


def _mask_file_line(line, label, cfg):
    """A line known to come from a credential file: values off the allow-list are masked."""
    s = line.strip()
    if not s or HARMLESS.match(s):
        return line, 0
    m = KEY_LINE.match(line)
    if m:
        if m.group(2) in _allowed(cfg, label) or m.group(3).strip() in ("", '""', "''"):
            return line, 0
        return m.group(1) + "<withheld>", 1
    if s.startswith("#") or label not in _STRICT:
        return line, 0
    return "<line withheld>", 1


def mask_text(text, label, cfg):
    """Mask one output. label: the credential file the whole output comes from, or None."""
    out, n, in_key = [], 0, False
    for line in text.split("\n"):
        if in_key:
            if PK_END.search(line):
                in_key = False
                out.append(line)
            else:
                out.append("<line withheld>")
                n += 1
            continue
        if PK_BEGIN.search(line) and not PK_END.search(line):
            in_key = True
            out.append(line)
            continue
        k = 0
        for plabel, rx in _PREFIX:
            g = rx.match(line)
            if g:
                rest, k = _mask_file_line(g.group(2), plabel, cfg)
                line = g.group(1) + rest
                break
        else:
            if label:
                line, k = _mask_file_line(line, label, cfg)
        line, k2 = scan_line(line)
        out.append(line)
        n += k + k2
    return "\n".join(out), n


def _plural(n):
    return "" if n == 1 else "s"


def handle(event, cfg):
    """The hook's reply as a dict, or None to stay silent."""
    ev = event.get("hook_event_name")
    tool = event.get("tool_name")

    if ev == "UserPromptSubmit":
        prompt = event.get("prompt")
        if not isinstance(prompt, str) or prompt.lstrip().lower().startswith("secret-ok"):
            return None
        n = sum(scan_line(line)[1] for line in prompt.split("\n"))
        return {"decision": "block", "reason": PROMPT_BLOCK % (n, _plural(n))} if n else None

    ti = event.get("tool_input") or {}
    if not isinstance(ti, dict):
        return None
    cmd = ti.get("command")

    if ev == "PreToolUse":
        if not isinstance(cmd, str):
            return None
        if tool == "Bash" and not cmd.startswith(WRAP_BASH):
            return {"hookSpecificOutput": {"hookEventName": ev, "updatedInput": dict(ti, command=WRAP_BASH + cmd)}}
        if tool == "PowerShell" and not (cmd.startswith(PS_HEAD) and cmd.endswith(PS_TAIL)):
            return {"hookSpecificOutput": {"hookEventName": ev,
                                           "updatedInput": dict(ti, command=PS_HEAD + cmd + PS_TAIL)}}
        return None

    if ev != "PostToolUse":
        return None
    resp = event.get("tool_response")
    new = copy.deepcopy(resp)

    if tool in ("Bash", "PowerShell") and isinstance(resp, dict):
        label = names_known(strip_prose(cmd)) if isinstance(cmd, str) else None
        n = 0
        for field in ("stdout", "stderr"):
            if isinstance(resp.get(field), str) and resp[field]:
                new[field], k = mask_text(resp[field], label, cfg)
                n += k
        if not n:
            return None
        new["stdout"] = MASKED % (n, _plural(n), label or "secrets") + "\n" + new.get("stdout", "")
    elif tool == "Read" and isinstance(resp, dict) and isinstance((resp.get("file") or {}).get("content"), str):
        label = names_known(ti.get("file_path"))
        content, n = mask_text(resp["file"]["content"], label, cfg)
        if not n:
            return None
        new["file"]["content"] = content + "\n" + NOTE % (n, _plural(n), label or "secrets")
    elif tool == "Grep" and isinstance(resp, dict) and isinstance(resp.get("content"), str):
        content, n = mask_text(resp["content"], None, cfg)
        if not n:
            return None
        new["content"] = content + "\n" + NOTE % (n, _plural(n), "secrets")
    else:
        return None
    return {"hookSpecificOutput": {"hookEventName": ev, "updatedToolOutput": new}}


def _failed(event):
    """A replacement output for when masking itself broke: withhold everything, keep the shape."""
    tool, resp = event.get("tool_name"), event.get("tool_response")
    try:
        new = copy.deepcopy(resp) if isinstance(resp, dict) else {}
        if tool == "Read" and isinstance(new.get("file"), dict):
            new["file"]["content"] = FAILED
        elif tool == "Grep" and "content" in new:
            new["content"] = FAILED
        else:
            new = {"stdout": FAILED, "stderr": "", "interrupted": False, "isImage": False}
    except Exception:
        new = {"stdout": FAILED, "stderr": "", "interrupted": False, "isImage": False}
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedToolOutput": new}}


def run(raw, load=None):
    """Hook I/O: stdin text in, stdout text out. Post: any internal error withholds the output."""
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
        if event.get("hook_event_name") == "PostToolUse":
            return json.dumps(_failed(event))
        return ""


# ---------------------------------------------------------------- selftest

def selftest():
    # Fixtures are built at run time, so the source holds no path or value the guard matches.
    spot = "Spot" + "ify"
    sp_unix = '"$APPDATA/' + spot + '/pr' + 'efs"'
    envp = "/app/.e" + "nv"
    blob = "x7Qa" * 12
    cfg = {"allow": {"spotify-prefs": ["app.autostart-mode", "audio.sync_bitrate_enumeration"],
                     "env": ["APP_ENV"]}}
    fails = []

    def check(name, got, want):
        if got != want:
            fails.append("%s: got %r, want %r" % (name, got, want))

    def ev(event, tool, ti, resp=None):
        e = {"hook_event_name": event, "tool_name": tool, "tool_input": ti}
        if resp is not None:
            e["tool_response"] = resp
        return handle(e, cfg)

    def bash_post(cmd, stdout, stderr="", tool="Bash"):
        return ev("PostToolUse", tool, {"command": cmd},
                  {"stdout": stdout, "stderr": stderr, "interrupted": False, "isImage": False})

    def replaced(out):
        return ((out or {}).get("hookSpecificOutput") or {}).get("updatedToolOutput")

    def stdout(out):
        return (replaced(out) or {}).get("stdout") or ""

    def scan(text):
        return mask_text(text, None, cfg)

    # Before: every Bash and PowerShell command is wrapped, by the fixed text only.
    out = ev("PreToolUse", "Bash", {"command": "ls -la", "description": "d"})
    check("bash wrap", out["hookSpecificOutput"]["updatedInput"], {"command": WRAP_BASH + "ls -la", "description": "d"})
    check("bash already wrapped", ev("PreToolUse", "Bash", {"command": WRAP_BASH + "ls"}), None)
    out = ev("PreToolUse", "PowerShell", {"command": "Get-ChildItem"})
    check("ps wrap", out["hookSpecificOutput"]["updatedInput"]["command"], PS_HEAD + "Get-ChildItem" + PS_TAIL)
    check("ps already wrapped", ev("PreToolUse", "PowerShell", {"command": PS_HEAD + "x" + PS_TAIL}), None)
    check("read pre silent", ev("PreToolUse", "Read", {"file_path": envp}), None)

    # Known credential files: values off the allow-list masked, key names kept.
    m = stdout(bash_post(WRAP_BASH + "cat " + sp_unix,
                         'app.autostart-mode="off"\nautologin.blob="' + blob + '"\n[exit 0]\n'))
    check("spotify blob masked", "autologin.blob=<withheld>" in m and blob not in m, True)
    check("spotify allowed key kept", 'app.autostart-mode="off"' in m, True)
    check("header counts", m.startswith("credential-guard: 1 value withheld (spotify-prefs)"), True)
    check("allow-listed passes", bash_post("cat " + sp_unix, 'app.autostart-mode="off"\n\n[exit 0]\n'), None)
    check("quoted key passes", bash_post("cat " + sp_unix, '  "audio.sync_bitrate_enumeration": 4\n'), None)
    check("stderr masked", blob in json.dumps(bash_post("cat " + sp_unix, "", "autologin.blob=" + blob)), False)
    m = stdout(bash_post("cat " + envp, "APP_ENV=local\nDB_PASSWORD=" + blob + "\n# DB_PASSWORD=" + blob
                         + "\nexport API_TOKEN=" + blob + "\nEMPTY_ONE=\n# just a comment\n[exit 0]\n"))
    for want in ["APP_ENV=local", "DB_PASSWORD=<withheld>", "# DB_PASSWORD=<withheld>",
                 "export API_TOKEN=<withheld>", "EMPTY_ONE=", "# just a comment"]:
        check("env keeps " + want, want in m, True)
    check("env no value", blob not in m, True)
    check("env short value masked", "hunt" in stdout(bash_post("cat " + envp, "DB_PASSWORD=hunt\nDB_HOST=x\n")), False)
    m = stdout(bash_post("cat ~/.ssh/id_" + "ed25519", "line-one-" + blob + "\nline-two\n"))
    check("strict file withholds non-key lines", "<line withheld>" in m and blob not in m, True)
    m = stdout(bash_post("cat ~/.ne" + "trc", "machine h login u pass" + "word " + blob + "\n"))
    check("netrc withheld", blob not in m, True)
    check("exit-code line passes", bash_post("[ -f " + sp_unix + " ]; echo $?", "0\n[exit 0]\n"), None)
    m = stdout(bash_post("grep -rn APP_KEY .", "./.e" + "nv:3:APP_KEY=" + blob + "\nsrc/a.php:9:env('APP_KEY')\n"))
    check("grep prefix masked", "./.e" + "nv:3:APP_KEY=<withheld>" in m and blob not in m, True)
    check("grep other lines kept", "src/a.php:9:env('APP_KEY')" in m, True)
    check("grep allowed key passes", bash_post("grep -rn APP_ENV .", "./.e" + "nv:1:APP_ENV=local\n"), None)
    win = "C:\\x\\.e" + "nv:3:DB_PASSWORD=" + blob
    check("grep windows prefix masked", blob in scan(win)[0], False)

    # Mentioning a file is not reading it (the commit-message false positive).
    msg = 'git commit -m "covers .e' + 'nv files and more"'
    check("commit message not a file", bash_post(msg, "lint: 0 failure(s)\n[main abc] covers\n"), None)
    here = "git commit -F - <<'EOF'\nmasks .e" + "nv values\nEOF"
    check("heredoc not a file", names_known(strip_prose(here)), None)
    check("echo not a file", names_known(strip_prose('echo "see the .e' + 'nv file"')), None)
    check("quoted path still a file", names_known(strip_prose("cat " + sp_unix)), "spotify-prefs")
    check("ssh-quoted cat still a file", names_known(strip_prose("ssh mac 'cat ~/www/a/.e" + "nv'")), "env")

    # Secret shapes, on any output.
    pw = "Zx9fK2mQ7pL4"
    shapes = {
        "anthropic": "key sk-" + "ant-api03-" + "A1b2" * 8,
        "openai": "sk-" + "proj-" + "Ab1" * 10,
        "github": "gh" + "p_" + "a1B2" * 9,
        "aws": "AK" + "IA" + "ABCDEFGHIJKLMNOP",
        "slack": "xo" + "xb-" + "123-456-abcdefghij",
        "google": "AI" + "za" + "x" * 35,
        "jwt": "Bearer ey" + "J" + "a" * 12 + ".ey" + "J" + "b" * 12 + "." + "c" * 12,
        "laravel": "APP_KEY=base64:" + "Q" * 40,
        "url": "mysql://root:" + pw + "@db:3306/app",
        "printenv": "DB_PASSWORD=" + pw,
        "spaced ini": "aws_secret_access_key = " + pw,
        "query": "GET /cb?code=1&access_token=" + pw + "&x=1",
        "npmrc": "//registry.npmjs.org/:_authToken=" + pw,
        "yaml": "  password: " + pw,
        "json": '{"client_secret": "' + pw + '"}',
        "php array": "'api_key' => '" + pw + "',",
        "php define": "define('DB_PASSWORD', '" + pw + "');",
        "assign": 'API_KEY = "' + pw + '"',
        "docker auth": '"auth": "' + pw + '"',
        "stripe key": "STRIPE_KEY=" + pw,
        "json private key": '"private_key": "-----BEGIN ' + 'PRIVATE KEY-----\\nMIIE' + blob + '\\n-----END ' + 'PRIVATE KEY-----\\n"',
    }
    for name, text in shapes.items():
        got, n = scan(text)
        check("shape " + name, n >= 1 and pw not in got and blob not in got and "A1b2A1b2" not in got
              and "Ab1Ab1" not in got and "a1B2a1B2" not in got and "ABCDEFGHIJKLMNOP" not in got
              and "abcdefghij" not in got and "x" * 35 not in got and "a" * 12 not in got and "Q" * 40 not in got, True)
    block = "-----BEGIN OPENSSH " + "PRIVATE KEY-----\n" + blob + "\n" + blob + "\n-----END OPENSSH " + "PRIVATE KEY-----"
    got, n = scan(block)
    check("private key block", blob not in got and n == 2 and got.startswith("-----BEGIN"), True)

    # Code that only talks about secrets is left alone.
    for code in ["'password' => 'required|min:8|confirmed',", "$password = $request->input('password');",
                 "const TOKEN_KEY = 'auth_access_token';", "password = request.form['password']",
                 "if (token == null) {", "'password' => 'hashed',", "token: string;", "TOKEN_TTL=3600",
                 "self.token = token", "api_key = get_key()", "password = hashed_pw", "MAIL_PASSWORD=null",
                 "DB_PASSWORD=${DB_PASSWORD}", "author: Jane", "PATH=/usr/bin:/bin", "primary_key=True",
                 "'foreign_key' => 'user_id',", "https://github.com/x/y", "DB_PASSWORD=",
                 "process.env.API_TOKEN", "sk-navigation-menu-wrapper-item", "url: https://example.com:8080/a"]:
        check("no false positive: " + code, scan(code), (code, 0))

    # Other tools keep their own output shape.
    rresp = {"type": "text", "file": {"filePath": envp, "content": "APP_ENV=local\nDB_PASSWORD=" + blob,
                                      "numLines": 2, "startLine": 1, "totalLines": 2}}
    r = replaced(ev("PostToolUse", "Read", {"file_path": envp}, rresp)) or {}
    check("read masked", blob not in json.dumps(r) and "DB_PASSWORD=<withheld>" in r.get("file", {}).get("content", ""), True)
    check("read shape kept", (r.get("type"), r.get("file", {}).get("filePath"), r.get("file", {}).get("numLines")),
          ("text", envp, 2))
    plain = {"type": "text", "file": {"filePath": "/a.md", "content": "hello", "numLines": 1, "startLine": 1, "totalLines": 1}}
    check("read plain untouched", ev("PostToolUse", "Read", {"file_path": "/a.md"}, plain), None)
    gresp = {"mode": "content", "numFiles": 0, "filenames": [], "content": win + "\nsrc/x.php:1:ok", "numLines": 2}
    g = replaced(ev("PostToolUse", "Grep", {"pattern": "x"}, gresp)) or {}
    check("grep tool masked", blob not in json.dumps(g) and g.get("mode") == "content" and "src/x.php:1:ok" in g.get("content", ""), True)
    m = stdout(bash_post(PS_HEAD + "Get-Content " + envp + PS_TAIL, "DB_PASSWORD=" + blob + "\n[exit ]", tool="PowerShell"))
    check("powershell masked", "<withheld>" in m and blob not in m, True)
    check("unrelated untouched", bash_post("cat notes.txt", "hello\nAPP_ENV=local\n[exit 0]\n"), None)

    # Prompts.
    def prompt(text):
        return handle({"hook_event_name": "UserPromptSubmit", "prompt": text}, cfg)
    p = prompt("use this key: gh" + "p_" + "a1B2" * 9)
    check("prompt blocked", (p or {}).get("decision") == "block" and "a1B2" not in json.dumps(p), True)
    check("prompt secret-ok", prompt("secret-ok gh" + "p_" + "a1B2" * 9), None)
    check("prompt plain", prompt("fix the DB_PASSWORD= line in .e" + "nv"), None)

    # The known-file list.
    for p in [envp + ".example", "backend/.e" + "nv.local", "./.e" + "nv", "~/.e" + "nvrc", envp + "-backup",
              "**/.e" + "nv*", "~/.ne" + "trc", "C:\\Users\\x\\_ne" + "trc", "~/.config/gh/hosts.yml",
              "~/.docker/config.json", "/Users/b/.ssh/id_" + "ed25519", "cat ~/.ssh/*", "app/auth.json",
              "~/.npmrc", "~/.pgpass", "~/.my.cnf", "public/.htpasswd", "gcp/service-account-prod.json",
              "~/.kube/config", "wp-config.php", "~/.config/gcloud/application_default_credentials.json"]:
        check("known " + p, names_known(p) is not None, True)
    for p in ["/Users/b/.ssh/id_" + "ed25519.pub", "/repo/README.md", "/repo/prefs.json", "/repo/docker/config.json",
              "/repo/.environment.md", "src/env.ts", "/repo/dotenv.md", "process.e" + "nv.APP_KEY",
              "C:\\notes\\" + spot + "-prefs-notes.md", "src/oauth.json.ts"]:
        check("not known " + p, names_known(p), None)

    # run(): hook I/O; a broken post withholds instead of passing the output through.
    check("run bad stdin prints nothing", run("not json", lambda: cfg), "")
    check("run silent event", run(json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Glob",
                                              "tool_input": {"pattern": "*"}}), lambda: cfg), "")

    def boom():
        raise ValueError("config broken")
    e = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "env"},
         "tool_response": {"stdout": "X=" + blob, "stderr": "", "interrupted": False, "isImage": False}}
    got = run(json.dumps(e), boom)
    check("run error withholds", FAILED in got and blob not in got, True)
    e = {"hook_event_name": "PostToolUse", "tool_name": "Read", "tool_input": {"file_path": "/a"}, "tool_response": rresp}
    got = json.loads(run(json.dumps(e), boom) or "{}")
    check("run error keeps read shape", replaced(got).get("file", {}).get("content"), FAILED)
    check("run error on pre is silent", run(json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                                       "tool_input": {"command": "ls"}}), boom), "")

    # The shipped config loads and only lists labels the script knows.
    real = load_config()
    check("config labels known", sorted(set(real.get("allow", {})) - set(l for l, _, _ in KNOWN)), [])

    for f in fails:
        print("FAIL " + f)
    print("credential-guard selftest: %d failed" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        try:
            sys.exit(selftest())
        except Exception as e:  # a crash is a red test, not a traceback
            print("FAIL selftest crashed: %s %s" % (type(e).__name__, e))
            sys.exit(1)
    sys.stdout.write(run(sys.stdin.read()))
