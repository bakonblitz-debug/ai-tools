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
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

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
    ("pii-guard-files", r"pii-guard[\\/](?:review\.tsv|self\.json)", True),
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
PROMPT_BLOCK = ("credential-guard: this prompt looks like it holds %d secret or personal value%s, so it "
                "was not sent. Remove them, or start the prompt with pii-ok (or secret-ok) to send it as it is.")
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


# Only read-only commands are wrapped. Auto mode reviews a command before the hook runs and
# refuses one the hook then changed (seen 2026-11-05), so wrapping a state-changing command
# would bounce it once every time. Read-only commands skip that review, and they are the ones
# that print secrets. Cost: a failing state-changing command's output is not masked.
BASH_READERS = set("""cat head tail less more grep egrep fgrep rg ag ls tree wc sort uniq cut awk sed jq yq
    env printenv echo printf type stat file diff cmp exit true false cd pwd test [ which command basename
    dirname realpath readlink date uname whoami id hostname du df column tr xxd od strings nl tac fold""".split())
GIT_READERS = set("diff show log status blame grep rev-parse ls-files describe shortlog cat-file ls-tree reflog".split())
PS_READERS = set("""select-string test-path resolve-path measure-object sort-object select-object where-object
    format-table format-list out-string convertfrom-json convertto-json write-output write-host echo cat type
    gc ls dir gci sls findstr exit cd pwd""".split())
_REDIRECT_OK = re.compile(r"\d?>&\d|\d?>\s*(?:/dev/null|\$null)")


def _segment_reads(seg, shell):
    seg = seg.strip().lstrip("(")
    if not seg:
        return True
    if ">" in _REDIRECT_OK.sub("", seg):
        return False  # writes a file
    if shell == "powershell":
        seg = re.sub(r"^\$\w+\s*=\s*", "", seg)
    else:
        seg = re.sub(r"^(?:\w+=\S*\s+)+", "", seg)  # VAR=x cmd
    words = seg.split()
    if not words:
        return True
    w0 = words[0].lower()
    rest = words[1:]
    if shell == "powershell":
        return w0.startswith("get-") or w0 in PS_READERS
    if w0 == "git":
        i = 0
        while i < len(rest) and rest[i].startswith("-"):
            i += 2 if rest[i] in ("-C", "-c", "--git-dir", "--work-tree", "--namespace") else 1
        sub = rest[i:i + 1]
        rest = rest[i:]
        if sub == ["config"]:
            return any(f in rest for f in ("--get", "--list", "-l", "--get-all"))
        return bool(sub) and sub[0] in GIT_READERS
    if w0 == "docker":
        sub = [w for w in rest if not w.startswith("-")][:2]
        return bool(sub) and (sub[0] in ("logs", "inspect", "ps", "images", "version", "info")
                              or (sub[0] == "compose" and sub[1:2] and sub[1] in ("config", "logs", "ps")))
    if w0 == "php" and rest[:1] == ["artisan"]:
        return rest[1:2] and rest[1] in ("config:show", "env", "route:list", "about", "--version")
    if w0 == "sed":
        return not any(w.startswith("-i") for w in rest)
    if w0 == "find":
        return not any(w in ("-delete", "-exec", "-execdir", "-ok") for w in rest)
    return w0 in BASH_READERS


def read_only(cmd, shell):
    """True when every step of the command only reads."""
    return all(_segment_reads(s, shell) for s in re.split(r"\|\||&&|[|;\n]", cmd))


def load_config():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        cfg = {"allow": {}}
    cfg["self"] = load_self()
    return cfg


def _allowed(cfg, label):
    return set((cfg.get("allow") or {}).get(label) or [])


def _placeholder(v):
    lv = v.lower()
    return (not v or lv in PLACEHOLDERS or v[0] in "<${%[(*=>!&|`" or v.isdigit()
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
        line, k3 = pii_line(line, cfg)
        out.append(line)
        n += k + k2 + k3
    return "\n".join(out), n


# ---------------------------------------------------------------- PII
# His rules (2026-11-05): mask anything that identifies a person (names, addresses, phones,
# emails, SIN/SSN, cards, bank accounts); gender, age and descriptions are fine; his own
# identifiers are allowed; just mask, no picker. Reliable classes and labelled fields mask
# now. Unlabelled names and street addresses only go to a local review log for a week, so he
# can see the false-positive rate before they mask anything (plan: .plans/handoff-pii-guard.md).
# The files sit in the harness, so every machine that runs this script from the share uses one
# copy. config/pii-guard/ is git-ignored: ai-tools is public, and short values like a phone
# number can be brute-forced back from a hash. The selftest fails if git would track them.
PII_DIR = os.path.join(HERE, "..", "config", "pii-guard")
SELF_FILE = os.path.join(PII_DIR, "self.json")      # sha256 of his own identifiers, never plain
REVIEW_FILE = os.path.join(PII_DIR, "review.tsv")   # log-only hits, plain: Read-denied, git-ignored
# Before 2026-11-05 each machine kept its own copy here; still read so no --add-self is lost.
LEGACY_DIR = os.path.join(os.path.expanduser("~"), ".claude", "pii-guard")
SELF_FILES = [SELF_FILE, os.path.join(LEGACY_DIR, "self.json")]
REVIEW_FILES = [REVIEW_FILE, os.path.join(LEGACY_DIR, "review.tsv")]
REVIEW = []

_FILE_TLDS = set("png jpg jpeg gif svg webp ico css scss js mjs ts tsx jsx php json md txt lock yml yaml xml html vue py rb go rs sh".split())
# Role addresses name a team, not a person (cve-watch: secure@, psirt@ ...).
_EMAIL_SKIP_LOCAL = {"git", "noreply", "no-reply", "donotreply", "do-not-reply", "postmaster", "mailer-daemon",
                     "security", "secure", "psirt", "cna", "support", "help", "info", "contact", "hello", "admin",
                     "sales", "team", "privacy", "legal", "abuse", "webmaster", "press", "jobs", "careers", "hr",
                     "billing", "office", "bugs", "notifications"}
_EMAIL_SKIP_DOMAIN = ("example.com", "example.org", "example.net", "example", "test", "invalid", "localhost",
                      "local", "noreply.github.com")
EMAIL = re.compile(r"(?<![\w.+-])([A-Za-z0-9._%+-]+)@((?:[A-Za-z0-9-]+\.)+([A-Za-z]{2,24}))(?![\w-])")
NAME_EMAIL = re.compile(r"([A-Z][A-Za-zÀ-ÿ'’.-]+(?: [A-Z][A-Za-zÀ-ÿ'’.-]+){1,3})(\s*<\s*)"
                        r"([A-Za-z0-9._%+-]+@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,24})(\s*>)")
PHONE = re.compile(r"(?<![\w+.-])(?:\+?1[ .-]?)?(?:\(\d{3}\) ?\d{3}[ .-]\d{4}|\d{3}-\d{3}-\d{4}|\d{3}\.\d{3}\.\d{4})(?![\w.]|-\d)")
PHONE_INTL = re.compile(r"(?<=[\s:=(\"'])\+[1-9]\d{0,2}(?:[ .-]?\d{1,4}){2,6}(?![\w.-])")
SIN = re.compile(r"(?<![\w.-])\d{3}([ -])\d{3}\1\d{3}(?![\w.-])")  # not SVG/number data: 178.936 392.4
SIN_CTX = re.compile(r"(?i)\b(?:sin|nas|social insurance(?: number)?)\b[^\d\n]{0,20}(\d{9})(?!\d)")
SSN = re.compile(r"(?<![\d-])(\d{3})-(\d{2})-(\d{4})(?![\d-])")
SSN_CTX = re.compile(r"(?i)\b(?:ssn|social security(?: number)?)\b[^\d\n]{0,20}(\d{9})(?!\d)")
# Real card layouts only: bare, 4-4-4-4(-1..3), Amex 4-6-5 (not runs like "7 8 8 9 8 6" in data)
CARD = re.compile(r"(?<![\w.-])(?:\d{13,19}|\d{4}([ -])\d{4}\1\d{4}\1\d{4}(?:\1\d{1,3})?|\d{4}([ -])\d{6}\2\d{5})(?![\w.-])")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b")
BANK_CTX = re.compile(r"(?i)\b(?:account|acct|compte|folio|transit|institution|routing|aba)\b"
                      r"(?:[ _-]?(?:no\.?|number|num|#|n°|numéro|id))?[\"']?\s*(?:=>|[:=#])?\s*[\"']?(\d[\d -]{3,20}\d)(?!\d)")
CHEQUE = re.compile(r"(?<![\d-])\d{5}-\d{3}-\d{5,12}(?![\d-])")
POSTAL_CA = re.compile(r"(?<![A-Za-z0-9])[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z][ -]\d[ABCEGHJ-NPRSTV-Z]\d(?![A-Za-z0-9])")
ZIP_STATE = re.compile(r"\b(?:A[KLRZ]|C[AOT]|D[CE]|FL|GA|HI|I[ADLN]|K[SY]|LA|M[ADEINOST]|N[CDEHJMVY]|O[HKR]|PA|RI|"
                       r"S[CD]|T[NX]|UT|V[AT]|W[AIVY]),?\s+(\d{5}(?:-\d{4})?)\b")
_PERSON_KEYS = (r"(?:first|last|full|given|family|middle|maiden|customer|contact|client|employee|candidate|"
                r"recipient|sender|display)[ _-]?name|firstname|lastname|fullname|surname|pr[ée]nom|nom")
_ADDRESS_KEYS = (r"(?:home|work|billing|shipping|mailing|street|postal)?[ _-]?address(?:[ _-]?(?:line)?[ _-]?\d)?"
                 r"|street|adresse|rue|postal[ _-]?code|postcode|zip(?:[ _-]?code)?|code[ _-]?postal")
KEYED = [("name", re.compile(r"""(?<![\w-])(["']?)(""" + _PERSON_KEYS + r""")(?![\w-])\1(\s*(?:=>|[:=])\s*)(["'])([^"'\n]{1,80})\4""", re.I)),
         ("address", re.compile(r"""(?<![\w-])(["']?)(""" + _ADDRESS_KEYS + r""")(?![\w-])\1(\s*(?:=>|[:=])\s*)(["'])([^"'\n]{1,120})\4""", re.I))]
KEYED_BARE = [("name", re.compile(r"^(\s*(?:[+-]\s*)?)(" + _PERSON_KEYS + r")(\s*[:=]\s*)([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'’. -]{0,60}?)\s*$", re.I)),
              ("address", re.compile(r"^(\s*(?:[+-]\s*)?)(" + _ADDRESS_KEYS + r")(\s*[:=]\s*)([^\s\"'][^\"'\n]{2,120}?)\s*$", re.I))]
STREET = re.compile(r"\b\d{1,6}(?:-\d{1,6})?,?\s+(?:(?:rue|chemin|boulevard|boul\.?|avenue|av\.?)\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ'’.-]+"
                    r"(?:\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ'’.-]+){0,3}|(?:[A-Z][\w'’.-]*\s+){1,4}(?:Street|St|Avenue|Ave|Road|Rd|"
                    r"Boulevard|Blvd|Drive|Dr|Lane|Ln|Court|Ct|Way|Place|Pl|Crescent|Cres|Terrace|Highway|Hwy|Parkway|Circle)\b\.?)")
GENERIC_NAME = re.compile(r"""(["']?)(name|author|owner|contact|user|full_name)\1(\s*(?:=>|[:=])\s*)(["'])"""
                          r"""([A-Z][a-zà-ÿ'’-]+(?: [A-Z][a-zà-ÿ'’-]+){1,3})\4""")


def _norm(v):
    return re.sub(r"\s+", " ", v.strip().lower())


def _hash(v):
    return hashlib.sha256(_norm(v).encode("utf-8")).hexdigest()


def load_self(paths=None):
    own = set()
    for p in paths or SELF_FILES:
        try:
            with open(p, encoding="utf-8") as f:
                own |= set(json.load(f).get("sha256", []))
        except (OSError, ValueError, AttributeError, TypeError):
            pass
    return own


def _luhn(d):
    total = 0
    for i, c in enumerate(reversed(d)):
        n = int(c)
        if i % 2:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return total % 10 == 0


def _card_ok(m):
    d = re.sub(r"\D", "", m.group(0))
    if not 13 <= len(d) <= 19 or not _luhn(d):
        return False
    return (d[0] == "4" or 51 <= int(d[:2]) <= 55 or 2221 <= int(d[:4]) <= 2720 or d[:2] in ("34", "37", "65", "35")
            or d[:4] == "6011")


def _iban_ok(m):
    s = m.group(0).replace(" ", "")
    if not 15 <= len(s) <= 34:
        return False
    return int("".join(str(int(c, 36)) for c in s[4:] + s[:4])) % 97 == 1


def _phone_ok(m):
    d = re.sub(r"\D", "", m.group(0))[-10:]
    return len(d) == 10 and d[0] in "23456789" and d[3] in "23456789"


def _email_ok(m, own):
    local, domain, tld = m.group(1).lower(), m.group(2).lower(), m.group(3).lower()
    return not (local in _EMAIL_SKIP_LOCAL or tld in _FILE_TLDS or _hash(m.group(0)) in own
                or any(domain == s or domain.endswith("." + s) for s in _EMAIL_SKIP_DOMAIN))


def _ssn_ok(m):
    a, g, s = m.group(1), m.group(2), m.group(3)
    return a not in ("000", "666") and a[0] != "9" and g != "00" and s != "0000"


def _keyed_ok(cls, v):
    v = v.strip()
    if not v or _placeholder(v) or "|" in v or re.fullmatch(r"[a-z]+(?:[_.-][a-z]+)*", v):
        return False
    if cls == "name":
        return re.fullmatch(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'’. -]{0,60}", v) is not None
    if not re.search(r"[A-Za-zÀ-ÿ]", v):
        return False  # an IP, a number: not a street address
    return bool(re.search(r"\d", v)) or len(v.split()) >= 2


def pii_line(line, cfg):
    """(line with PII masked, how many). Log-only classes go to REVIEW, not masked."""
    own = cfg.get("self") or set()
    spans = []  # (start, end, tag)

    def free(a, b):
        return all(b <= s or a >= e for s, e, _ in spans)

    for m in NAME_EMAIL.finditer(line):
        if _hash(m.group(1)) not in own and _hash(m.group(3)) not in own:
            spans.append(m.span(1) + ("<name>",))
    for cls, rx in KEYED:
        for m in rx.finditer(line):
            if _keyed_ok(cls, m.group(5)) and _hash(m.group(5)) not in own and free(*m.span(5)):
                spans.append(m.span(5) + ("<%s>" % cls,))
    for cls, rx in KEYED_BARE:
        m = rx.match(line)
        if m and _keyed_ok(cls, m.group(4)) and _hash(m.group(4)) not in own and free(*m.span(4)):
            spans.append(m.span(4) + ("<%s>" % cls,))
    checks = [
        (EMAIL, 0, "<email>", lambda m: _email_ok(m, own)),
        (IBAN, 0, "<iban>", _iban_ok),
        (CARD, 0, "<card>", _card_ok),
        (SSN, 0, "<ssn>", _ssn_ok),
        (SSN_CTX, 1, "<ssn>", lambda m: True),
        (SIN, 0, "<sin>", lambda m: m.group(0)[0] not in "08" and _luhn(re.sub(r"\D", "", m.group(0)))),
        (SIN_CTX, 1, "<sin>", lambda m: _luhn(m.group(1))),
        (CHEQUE, 0, "<bank-account>", lambda m: True),
        (BANK_CTX, 1, "<bank-account>", lambda m: 5 <= len(re.sub(r"\D", "", m.group(1))) <= 17),
        (PHONE, 0, "<phone>", lambda m: _phone_ok(m) and _hash(m.group(0)) not in own),
        (PHONE_INTL, 0, "<phone>", lambda m: 8 <= len(re.sub(r"\D", "", m.group(0))) <= 15 and _hash(m.group(0)) not in own),
        (POSTAL_CA, 0, "<postal-code>", lambda m: True),
        (ZIP_STATE, 1, "<postal-code>", lambda m: True),
    ]
    for rx, grp, tag, ok in checks:
        for m in rx.finditer(line):
            a, b = m.span(grp)
            if "<" in line[a:b] or not free(a, b) or not ok(m):
                continue
            spans.append((a, b, tag))
    for m in STREET.finditer(line):
        if free(*m.span()):
            REVIEW.append(("street", m.group(0)))
    for m in GENERIC_NAME.finditer(line):
        if free(*m.span(5)) and _hash(m.group(5)) not in own:
            REVIEW.append(("name", m.group(5)))
    for a, b, tag in sorted(spans, reverse=True):
        line = line[:a] + tag + line[b:]
    return line, len(spans)


def flush_review():
    """Append this run's log-only hits to the local review file. Never fails the hook."""
    global REVIEW
    rows, REVIEW = REVIEW, []
    if not rows:
        return
    try:
        os.makedirs(PII_DIR, exist_ok=True)
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
        with open(REVIEW_FILE, "a", encoding="utf-8") as f:
            for cls, value in rows:
                f.write("%s\t%s\t%s\n" % (stamp, cls, re.sub(r"[\t\r\n]+", " ", value)))
    except OSError:
        pass


def _refuse_inside_claude():
    if os.environ.get("CLAUDECODE"):
        print("Refused: run this in your own terminal, not through Claude Code (its output would reach the model).")
        sys.exit(2)


def add_self():
    """Store the hash of one of his own identifiers. Run by him, in his terminal."""
    _refuse_inside_claude()
    own = load_self()
    print("Type a value that identifies you (full name, first name, last name, email, phone); blank line to stop.")
    while True:
        try:
            v = input("> ")
        except EOFError:
            break
        if not v.strip():
            break
        own.add(_hash(v))
    os.makedirs(PII_DIR, exist_ok=True)
    with open(SELF_FILE, "w", encoding="utf-8") as f:
        json.dump({"sha256": sorted(own)}, f, indent=1)
    print("%d value(s) stored as hashes in %s" % (len(own), SELF_FILE))


def pii_review(clear=False):
    """Show the log-only hits (counts, then examples). Run by him, in his terminal."""
    _refuse_inside_claude()
    if clear:
        for p in REVIEW_FILES:
            try:
                os.remove(p)
            except FileNotFoundError:
                pass
        print("cleared")
        return
    rows = []
    for p in REVIEW_FILES:
        try:
            with open(p, encoding="utf-8") as f:
                rows += [line.rstrip("\n").split("\t", 2) for line in f if line.count("\t") >= 2]
        except FileNotFoundError:
            pass
    by = {}
    for _, cls, value in rows:
        by.setdefault(cls, []).append(value)
    if not by:
        print("nothing logged yet")
    for cls, values in sorted(by.items()):
        uniq = sorted(set(values))
        print("%s: %d hits, %d distinct. Real person (y) or false positive (n)?" % (cls, len(values), len(uniq)))
        for v in uniq[:40]:
            print("   " + v)


def _plural(n):
    return "" if n == 1 else "s"


def handle(event, cfg):
    """The hook's reply as a dict, or None to stay silent."""
    ev = event.get("hook_event_name")
    tool = event.get("tool_name")

    if ev == "UserPromptSubmit":
        prompt = event.get("prompt")
        if not isinstance(prompt, str) or prompt.lstrip().lower().startswith(("secret-ok", "pii-ok")):
            return None
        n = sum(scan_line(line)[1] + pii_line(line, cfg)[1] for line in prompt.split("\n"))
        del REVIEW[:]  # a prompt's log-only hits are his own text: not logged
        return {"decision": "block", "reason": PROMPT_BLOCK % (n, _plural(n))} if n else None

    ti = event.get("tool_input") or {}
    if not isinstance(ti, dict):
        return None
    cmd = ti.get("command")

    if ev == "PreToolUse":
        if not isinstance(cmd, str):
            return None
        if tool == "Bash" and not cmd.startswith(WRAP_BASH) and read_only(cmd, "bash"):
            return {"hookSpecificOutput": {"hookEventName": ev, "updatedInput": dict(ti, command=WRAP_BASH + cmd)}}
        if tool == "PowerShell" and not (cmd.startswith(PS_HEAD) and cmd.endswith(PS_TAIL)) \
                and read_only(cmd, "powershell"):
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
        new["stdout"] = MASKED % (n, _plural(n), label or "secrets/PII") + "\n" + new.get("stdout", "")
    elif tool == "Read" and isinstance(resp, dict) and isinstance((resp.get("file") or {}).get("content"), str):
        label = names_known(ti.get("file_path"))
        content, n = mask_text(resp["file"]["content"], label, cfg)
        if not n:
            return None
        new["file"]["content"] = content + "\n" + NOTE % (n, _plural(n), label or "secrets/PII")
    elif tool == "Grep" and isinstance(resp, dict) and isinstance(resp.get("content"), str):
        content, n = mask_text(resp["content"], None, cfg)
        if not n:
            return None
        new["content"] = content + "\n" + NOTE % (n, _plural(n), "secrets/PII")
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
        if load is None:
            flush_review()
        else:
            del REVIEW[:]
        return json.dumps(out) if out else ""
    except Exception:
        del REVIEW[:]
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
    for c in ["cat " + envp, "grep -rn x . | head -5", "git log --oneline -3", "env | sort", "cd a && cat b",
              "cat x; exit 3", "git config --get user.email", "docker compose config", "sed -n 1,5p f",
              "php artisan config:show database", "cat x 2>&1", "grep x f >/dev/null", "DEBUG=1 printenv",
              "git -C /repo show HEAD:a.txt", "[ -f x ]; echo $?"]:
        check("wraps " + c, read_only(c, "bash"), True)
    for c in ["git worktree add x main", "git commit -m 'a'", "rm " + envp, "cat a > b", "echo x >> f",
              "sed -i s/a/b/ f", "ssh mac 'cat x'", "npm install", "find . -delete", "cp a b",
              "git config user.name x", "docker run img", "php artisan migrate", "bash x.sh", "py -3 x.py"]:
        check("leaves " + c, read_only(c, "bash"), False)
        check("bash pre leaves " + c, ev("PreToolUse", "Bash", {"command": c}), None)
    for c in ["Get-Content x", "Get-ChildItem | Select-Object Name", "(Select-String -Path f -Pattern x).Count",
              "$e = Get-WinEvent -MaxEvents 5", "Get-Content f | Where-Object { $_ -match 'x' }"]:
        check("ps wraps " + c, read_only(c, "powershell"), True)
    for c in ["Remove-Item x", "py -3 x.py", "Set-Content x y", "Get-Content a > b", "ssh mac 'ls'"]:
        check("ps leaves " + c, read_only(c, "powershell"), False)

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
                 "process.env.API_TOKEN", "sk-navigation-menu-wrapper-item", "url: https://example.com:8080/a",
                 "`PASSWORD=`-style lines", "set `TOKEN=` in the docs"]:
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

    # PII: masked, except his own identifiers; descriptive attributes stay.
    other = "jane.roe" + "@" + "corp.io"
    me = "sam.tester" + "@" + "mail.io"
    cfg["self"] = {_hash(me), _hash("Sam Tester"), _hash("514-555-0100")}

    def complete(p):
        return next(p + c for c in "0123456789" if _luhn(p + c))
    sin = complete("13045428")
    card = "4111" + " 1111" * 3
    pii = {
        "email": ("write to " + other, "<email>"),
        "phone dashed": ("call 514-555-0199 now", "<phone>"),
        "phone parens": ("(514) 555-0199", "<phone>"),
        "phone +1": ("cell: +1 514 555 0199", "<phone>"),
        "phone intl": ("tel: +33 6 12 34 56 78", "<phone>"),
        "sin": ("SIN " + sin[:3] + " " + sin[3:6] + " " + sin[6:], "<sin>"),
        "sin context": ("NAS: " + sin, "<sin>"),
        "ssn": ("ssn 123-45-6789", "<ssn>"),
        "card": ("paid with " + card, "<card>"),
        "card bare": ("cc=" + card.replace(" ", ""), "<card>"),
        "iban": ("IBAN GB82 " + "WEST 1234 5698 7654 32", "<iban>"),
        "bank account": ("account number: 1234567", "<bank-account>"),
        "compte": ("Compte: 12345 678", "<bank-account>"),
        "cheque": ("transit 12345-003-1234567", "<bank-account>"),
        "postal ca": ("Montréal, QC H2X 1Y4", "<postal-code>"),
        "zip": ("New York, NY 10001", "<postal-code>"),
        "first name": ("'first_name' => 'Jane',", "<name>"),
        "first name bare": ("first_name: Jane", "<name>"),
        "address": ("'address' => '123 Main Street',", "<address>"),
        "name and email": ("Author: Jane Roe <" + other + ">", "Author: <name> <<email>>"),
    }
    for name, (text, want) in pii.items():
        got, n = pii_line(text, cfg)
        check("pii " + name, (want in got, n >= 1), (True, True))
    for text in ["Author: Sam Tester <" + me + ">", "mail " + me, "call 514-555-0100", "git@github.com:x/y.git",
                 "logo user@2x.png", "vue@3.4.0", "noreply@anthropic.com", "a@example.com",
                 "report to secure" + "@" + "corp.io", "admin" + "@" + "budgetapp.local", "2026-11-05",
                 "192.168.100.200", "123-456-7890", "v1.2.3 at 10:30:45", "sin " + sin[:-1] + str((int(sin[-1]) + 1) % 10),
                 "000-12-3456", "4111111111111111ab", "card 4111" + " 1111" * 2 + " 1112",
                 "id " + sin[:3] + " " + sin[3:6] + " " + sin[6:8] + str((int(sin[-1]) + 1) % 10), "ts 1730800000000", "account_id = 42",
                 "'first_name' => 'required|string|max:255',", '"name": "my-app"', "$table->string('first_name');",
                 "'address' => 'required',", "ip_address = '10.0.0.1'", "remote_address = 'gw host 12b'", "username: bob", "gender: female", "age: 34",
                 "first_name: fake()->firstName()", "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>",
                 '<path d="M234.936 400.8C204.136 400.8 178.936 392.4 159.336 375.6C140.136 358.8"',
                 "8477951,20252026,82,74,46,0.561,8,2025-10-15,33,streaky,7 8 8 9 8 6 8 9 7 7 6 6 6 6 7 9 8 9",
                 "rule family=\"ipv4\" source address=\"10.0.0.12\" service name=\"ssh\""]:
        check("pii kept: " + text, pii_line(text, cfg), (text, 0))
    del REVIEW[:]
    check("street log-only", pii_line("lives at 42 Wallaby Way, Sydney", cfg)[1], 0)
    check("street logged", [c for c, _ in REVIEW], ["street"])
    del REVIEW[:]
    pii_line('"name": "Jane Roe"', cfg)
    check("generic name logged, not masked", [c for c, _ in REVIEW], ["name"])
    del REVIEW[:]
    m = stdout(bash_post("git log -1", "Author: Jane Roe <" + other + ">\n[exit 0]"))
    check("pii masked in tool output", other not in m and "Jane Roe" not in m, True)
    check("review file is a strict known file", names_known("~/.claude/pii-guard/review.tsv"), "pii-guard-files")
    check("harness self file is a strict known file", names_known(SELF_FILE), "pii-guard-files")

    # The PII files live in the harness (one copy for every machine), never in git.
    check("pii dir in harness config", os.path.normpath(PII_DIR),
          os.path.normpath(os.path.join(HERE, "..", "config", "pii-guard")))
    for f in (SELF_FILE, REVIEW_FILE):
        try:
            r = subprocess.run(["git", "-C", HERE, "check-ignore", "-q", f], capture_output=True, timeout=10)
            if r.returncode in (0, 1):  # 128: not a repo or git unusable here (SMB); nothing to check
                check("git ignores " + os.path.basename(f), r.returncode, 0)
        except (OSError, subprocess.SubprocessError):
            pass
    tmp = tempfile.mkdtemp()
    a, b = os.path.join(tmp, "a.json"), os.path.join(tmp, "b.json")
    for p, hs in ((a, ["h1", "h2"]), (b, ["h2", "h3"])):
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"sha256": hs}, fh)
    check("self list merges harness and legacy copies", load_self([a, b, os.path.join(tmp, "none.json")]),
          {"h1", "h2", "h3"})
    shutil.rmtree(tmp, ignore_errors=True)

    # Prompts.
    def prompt(text):
        return handle({"hook_event_name": "UserPromptSubmit", "prompt": text}, cfg)
    p = prompt("use this key: gh" + "p_" + "a1B2" * 9)
    check("prompt blocked", (p or {}).get("decision") == "block" and "a1B2" not in json.dumps(p), True)
    check("prompt secret-ok", prompt("secret-ok gh" + "p_" + "a1B2" * 9), None)
    check("prompt plain", prompt("fix the DB_PASSWORD= line in .e" + "nv"), None)
    check("prompt pii blocked", (prompt("call 514-555-0199 for me") or {}).get("decision"), "block")
    check("prompt pii-ok", prompt("pii-ok call 514-555-0199 for me"), None)
    check("prompt own email", prompt("my email is " + me), None)

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
    if sys.argv[1:] == ["--add-self"]:
        sys.exit(add_self())
    if sys.argv[1:2] == ["--pii-review"]:
        sys.exit(pii_review(clear=sys.argv[2:] == ["--clear"]))
    # Bytes in, ASCII out: the hook's JSON is UTF-8, and Windows would decode stdin as cp1252
    # (seen 2026-11-05: a masked Read turned "…" into mojibake). json.dumps escapes non-ASCII.
    sys.stdout.write(run(sys.stdin.buffer.read().decode("utf-8", "replace")))
