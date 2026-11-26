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
  PreToolUse  Write|Edit|NotebookEdit
                                a new hardcoded secret is denied: secrets live in .env, a
                                database or a secret file. "write-ok" allows one reviewed
                                write. A mask is never written back over a real value.
  UserPromptSubmit              a prompt holding a secret shape is blocked before it is
                                sent; start it with "secret-ok" to send it anyway. Agent
                                reports use the strict detector, so quoted code passes.
The notices name counts, files and lines, never a value. Nothing to mask: prints nothing.
Allow-lists: ../config/credential-guard.json. Plan: ~/www/.plans/credential-guard/PLAN.md

Usage: credential-guard.py          (hook; event read from stdin)
       credential-guard.py --selftest
       credential-guard.py --audit <repo>...   (read-only: file, line and kind, never a value)
"""
import copy
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter

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
QUOTED_KV = re.compile(r"""(["']?)([\w.-]*)\1(\s*(?:=>|[:=])\s*)(["'])([^"'\n]*)\4""")
# define('KEY', 'value') and ['key', 'value']. Separate from QUOTED_KV: a comma there would pair
# one entry's value with the next entry's key, and the real value after it went unmasked.
CALL_KV = re.compile(r"""[(\[]\s*(["'])([\w.-]+)\1(\s*,\s*)(["'])([^"'\n]*)\4""")
TOKEN_COUNT_KEY = re.compile(r"tokens|token_count|(?:input|output|total|prompt|completion|cache\w*)_tokens", re.I)
TOKEN_FORMULA = re.compile(r"[a-z_]+(?:\+[a-z_]+)+")
INLINE_EQ = re.compile(r"(?<![\w.-])([\w.-]+)(\s*=\s*)([^\s'\"&,;]*)")
YAML_KV = re.compile(r"^(\s*(?:[+-]\s*)?(?:#\s*)?)([\w.-]+)(:\s+)([^\s'\"#,;][^\s#,;]*)\s*$")
PLACEHOLDERS = {"null", "none", "nil", "true", "false", "undefined", "string", "number", "boolean",
                "bool", "int", "str", "required", "nullable", "confirmed", "sometimes", "hashed",
                "encrypted", "password", "passwd", "secret", "token", "changeme", "change_me",
                "example", "redacted", "empty", "test", "todo"}

MASKED = ("credential-guard: %d value%s withheld (%s); key names kept. To show a key's value, "
          "he adds it to ai-tools/config/credential-guard.json.")
NOTE = "[credential-guard: %d value%s withheld (%s)]"
PROMPT_ROWS = 5  # lines listed in a block notice; the rest are counted
_TAG = re.compile(r"<(withheld|email|phone|sin|ssn|card|iban|bank-account|postal-code|name|address)>")
_FILE_REF = re.compile(r"[\w.\\/-]+\.[A-Za-z]\w{0,5}:\d+(?:-\d+)?")
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
    spans = {m.span(5) for rx in (QUOTED_KV, CALL_KV) for m in rx.finditer(line)
             if _is_secret_key(m.group(2)) and _secret_literal(m.group(5))}
    line, k = _sub_spans(line, spans)
    n += k
    spans = [m.span(3) for m in INLINE_EQ.finditer(line)
             if _is_secret_key(m.group(1)) and _secret_bare(m.group(3), m.group(2) != "=")
             and not (m.group(2) != "=" and TOKEN_COUNT_KEY.fullmatch(m.group(1))
                      and TOKEN_FORMULA.fullmatch(m.group(3)))]
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


# ---------------------------------------------------------------- strict detector
# scan_line masks, so a false alarm hides one value. Anything that STOPS work (an agent report,
# a write) uses this one instead: a false alarm there loses a whole report or blocks an edit.
_STRICT_KEY = re.compile(r"(?:^|[_.-])(?:pass|pwd)$", re.I)
_CAMEL_KEY = re.compile(r"[a-z0-9](?:Key|Pass)$")
_PW_KEY = re.compile(r"pass(?:word|wd|phrase)|(?:^|[_.-])(?:pass|pwd)$", re.I)
_ALGORITHMS = {"argon2id", "argon2i", "argon2d", "bcrypt", "scrypt", "pbkdf2", "sha1", "sha256", "sha384", "sha512",
               "md5", "hs256", "hs384", "hs512", "rs256", "rs384", "rs512", "es256", "es384", "es512", "aes-256-cbc",
               "aes-256-gcm"}
_WHOLE_PLACEHOLDER = re.compile(r"\$\{[^}]*\}|\$\w+|<[^<>]+>|%\w+%|\{\{.*\}\}")
_COLON_WORDS = re.compile(r"[a-z0-9_-]+(?::[a-z0-9_-]+)+")
_PIPE_RULES = re.compile(r"[a-z_]+(?::[^|]*)?(?:\|[a-z_]+(?::[^|]*)?)+")
_LOWER_IDENT = re.compile(r"[a-z]+(?:[_.-][a-z]+)+")
_NAME_PARTS = re.compile(r"[a-z0-9]+(?:[-_.:][a-z0-9]+)+")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
_CODE_IDENT = re.compile(r"[A-Za-z_$][\w$]*(?:(?:\.|->|::)[A-Za-z_$][\w$]*)*")
STRICT_ENV = re.compile(r"""^(?P<indent>\s*)(?P<list>[-+]\s+)?(?:\#\s*)?(?P<export>export\s+)?(?P<kq>["']?)(?P<key>[\w.-]+)(?P=kq)"""
                        r"""(?:(?P<eq>\s*=\s*)|:\s+)(?P<val>[^\s'"`\#,;()]+)\s*(?:\#.*)?$""")
STRICT_QUOTED = re.compile(r"""(?<![\w.-])(?P<kq>["'`]?)(?P<key>[\w.-]+)(?P=kq)\s*(?:\]\s*)?"""
                           r"""(?::\s*[\w.\[\]|<>, ]{1,40}?\s*(?==))?(?:=>|:=|=|:)\s*(?P<q>["'`])(?P<val>[^"'`\n]*)(?P=q)""")
STRICT_INLINE = re.compile(r"""(?<![\w.-])(?P<key>[\w.-]+)(?:\s*:=\s*|=)(?P<val>[^\s'"`&,;]+)""")
STRICT_FLAG = re.compile(r"""(?<!\S)--?(?P<key>[\w-]+)\s+(?P<val>[^\s'"`&,;-][^\s'"`&,;]*)""")


def _strict_key(k):
    k = k.strip("\"'`")
    return bool(_is_secret_key(k) or _STRICT_KEY.search(k) or _CAMEL_KEY.search(k))


def _is_path(v):
    if "+" in v or "=" in v:
        return False
    for seg in re.split(r"[\\/]", v):
        if len(seg) >= 12 and re.search("[a-z]", seg) and re.search("[A-Z]", seg) and re.search(r"\d", seg):
            return False
    return bool(re.match(r"/|\./|\.\./|~/|[A-Za-z]:[\\/]", v)
                or re.fullmatch(r"[\w.-]+(?:[\\/][\w.-]+)*\.[A-Za-z][A-Za-z0-9]{0,5}", v))


def _strict_placeholder(v):
    """True only when the whole value is clearly not a secret. Not _placeholder: its first-character
    rule would pass a generated password that happens to start with a symbol."""
    low = v.lower()
    return (not v or low in PLACEHOLDERS or low in _ALGORITHMS or _WHOLE_PLACEHOLDER.fullmatch(v) is not None
            or re.match(r"</?[A-Za-z][\w-]*>", v) is not None  # markup right after "KEY=" in a doc
            or re.fullmatch(r"[x*.#-]+", low) is not None or low.startswith(("your", "change", "example"))
            or re.match(r"[a-z][a-z0-9+.-]*://", low) is not None or re.search(r"\s", v) is not None
            or _COLON_WORDS.fullmatch(v) is not None or _PIPE_RULES.fullmatch(v) is not None or _is_path(v))


def _strict_value(key, v, dotenv=False, report=False):
    """report: an agent report quoting code. Its tool output was already masked, so a short simple
    literal there is an example like a test password, and stopping would lose the whole report."""
    if _strict_placeholder(v) or (not dotenv and _LOWER_IDENT.fullmatch(v)):
        return False
    letter, digit = re.search("[A-Za-z]", v), re.search(r"\d", v)
    if _PW_KEY.search(key.strip("\"'`")):
        if report and not dotenv and len(v) < 12 and not (re.search("[a-z]", v) and re.search("[A-Z]", v) and digit):
            return False
        return len(v) >= 8 and bool(letter) and bool(digit or re.search(r"[^\w]|_", v))
    if len(v) < 16 or not letter or not digit:
        return False
    return bool(_UUID.fullmatch(v)) or not _NAME_PARTS.fullmatch(v)


def _code_value(v):
    """An unquoted value that reads as code: a variable, a property, the start of a call."""
    head = re.split(r"[(\[{]", v.rstrip(")]}"), 1)[0]
    if not _CODE_IDENT.fullmatch(head):
        return False
    for seg in re.split(r"\.|->|::", head):  # a random string is not a variable name
        if len(seg) >= 10 and re.search(r"\d", seg) and (len(seg) >= 16 or (re.search("[a-z]", seg) and re.search("[A-Z]", seg))):
            return False
    return True


def strict_hits(line, in_test=False, prose=False, report=False):
    """[(start, end, kind)]: values on this line that look like real secrets. in_test skips keyed
    values; prose (a sentence in a doc) keeps only shapes and line-anchored config forms."""
    spans = []

    def add(a, b, kind):
        if a < b and all(b <= s or a >= e for s, e, _ in spans):
            spans.append((a, b, kind))

    for rx in TOKENS:
        for m in rx.finditer(line):
            add(m.start(), m.end(), "token")
    for m in PK_INLINE.finditer(line):
        add(m.start(), m.end(), "private-key")
    for m in URL_CRED.finditer(line):
        if not _strict_placeholder(m.group(2)):
            add(m.start(2), m.end(2), "url-password")
    if in_test:
        return sorted(spans)
    m = STRICT_ENV.match(line)
    if m and _strict_key(m.group("key")):
        v, eq = m.group("val"), m.group("eq")
        dotenv = eq == "=" and (not m.group("indent") or bool(m.group("list"))) or bool(m.group("export"))
        is_code = eq is not None and not dotenv
        if not (is_code and _code_value(v)) and _strict_value(m.group("key"), v, dotenv, report):
            add(m.start("val"), m.end("val"), "hardcoded-secret")
    if prose:
        return sorted(spans)
    for m in STRICT_QUOTED.finditer(line):
        if m.group("key").lower() == "pass" and not m.group("kq"):
            continue  # the English word, as in "cannot pass: `x`"
        if _strict_key(m.group("key")) and _strict_value(m.group("key"), m.group("val"), False, report):
            add(m.start("val"), m.end("val"), "hardcoded-secret")
    for m in CALL_KV.finditer(line):
        if m.group(2).lower() != "pass" and _strict_key(m.group(2)) \
                and _strict_value(m.group(2), m.group(5), False, report):  # ("PASS", "FAIL_2") is a status list
            add(m.start(5), m.end(5), "hardcoded-secret")
    for rx in (STRICT_INLINE, STRICT_FLAG):
        for m in rx.finditer(line):
            v = m.group("val").rstrip(")]}")
            if _strict_key(m.group("key")) and not _code_value(v) and _strict_value(m.group("key"), v, False, report):
                add(m.start("val"), m.start("val") + len(v), "hardcoded-secret")
    return sorted(spans)


def strict_line(line, in_test=False, prose=False, report=False):
    """(line with the strict hits masked, how many)."""
    hits = strict_hits(line, in_test, prose, report)
    return _sub_spans(line, [(a, b) for a, b, _ in hits])


# ---------------------------------------------------------------- write block
# His rule (2026-11-21): secrets live in .env, a database or a secret file, never in code.
STATE_DIR = os.path.join(tempfile.gettempdir(), "credential-guard")  # local, never the SMB share
WRITE_TOOLS = ("Write", "Edit", "NotebookEdit")
PENDING_TTL = 3600
ARMED_TTL = 600
MAX_COMPARE = 1024 * 1024  # mask_text on more than this could pass the 10 s hook timeout
PEM_MAX_LINES = 64
_ENV_STORE = re.compile(r"\.envrc|\.env(?:\.(?:local|prod|production|stage|staging|dev|development|test|testing|ci)(?:\.local)?)?")
_OTHER_STORE = re.compile(r"\.netrc|\.npmrc|\.pypirc|\.pgpass|\.git-credentials|\.htpasswd")
_MASK_TAG = re.compile(r"<(line withheld|withheld|email|phone|sin|ssn|card|iban|bank-account|postal-code|name|address)>")
_SECRET_TAGS = {"withheld", "line withheld"}
_FENCE = re.compile(r"\s*(?:```|~~~)")
WRITE_FAILED = "credential-guard: the write check failed, so this write was not checked for secrets."


def _git(cwd, *args, timeout=3):
    """(exit code, stdout), or (None, "") if git could not run. Read-only calls only: the two
    settings let git answer in repos on the share, which it otherwise refuses as dubious ownership."""
    try:
        r = subprocess.run(["git", "-c", "safe.directory=*", "-c", "core.fsmonitor=false", "-C", cwd] + list(args),
                           capture_output=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None, ""
    return r.returncode, r.stdout.decode("utf-8", "replace")


def _anchor(path):
    """(nearest existing folder, the path relative to it), so a file in a new folder can be asked about."""
    p = os.path.abspath(path)
    d = os.path.dirname(p)
    while not os.path.isdir(d):
        parent = os.path.dirname(d)
        if parent == d:
            return None, None
        d = parent
    return d, os.path.relpath(p, d).replace("\\", "/")


def secret_store(path):
    """True when this file is a real secret store: the right name, git-ignored and untracked."""
    base = os.path.basename(path)
    is_env = _ENV_STORE.fullmatch(base) is not None
    if not is_env and not _OTHER_STORE.fullmatch(base):
        return False
    cwd, rest = _anchor(path)
    if not cwd:
        return is_env
    ignored, _ = _git(cwd, "check-ignore", "-q", "--", rest)
    tracked, _ = _git(cwd, "ls-files", "--error-unmatch", "--", rest)
    if ignored not in (0, 1) or tracked not in (0, 1):
        return is_env  # git cannot answer here
    return ignored == 0 and tracked == 1


def _test_rel(rel):
    parts = rel.split("/")
    return (any(p in ("test", "tests", "__tests__", "fixtures") for p in parts[:-1])
            or re.search(r"\.(?:test|spec)\.[cm]?[jt]sx?$", parts[-1]) is not None)


def _in_test(path):
    """Judged from the repo root, never by comparing paths: on the PC git reports a UNC root."""
    cwd, rest = _anchor(path)
    if not cwd:
        return False
    rc, prefix = _git(cwd, "rev-parse", "--show-prefix")
    return rc == 0 and _test_rel(prefix.strip() + rest)


def _lf(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _read_before(path):
    """(text, readable, exists). Bytes are kept through surrogateescape, so legacy encodings compare."""
    try:
        if os.path.getsize(path) > MAX_COMPARE:
            return "", False, True
        with open(path, "rb") as f:
            return _lf(f.read().decode("utf-8", "surrogateescape")), True, True
    except FileNotFoundError:
        return "", True, False
    except OSError:
        return "", False, True


def _changed(before, lines):
    """Indexes of the lines that are new: stripped lines, compared as a multiset."""
    old = Counter(l.strip() for l in before.split("\n"))
    out = set()
    for i, line in enumerate(lines):
        s = line.strip()
        if old[s] > 0:
            old[s] -= 1
        elif s:
            out.add(i)
    return out


def _scan_lines(lines, changed, in_test, prose_file):
    """[(line number, kinds)] for changed lines, including a changed line inside a key block."""
    out, fence, pem_left = [], False, 0
    for i, line in enumerate(lines):
        if prose_file and _FENCE.match(line):
            fence = not fence
            continue
        kinds = set()
        if i in changed:
            kinds = {k for _, _, k in strict_hits(line, in_test, prose_file and not fence)}
        if PK_BEGIN.search(line) and not PK_END.search(line):
            pem_left = PEM_MAX_LINES
        elif pem_left:
            if PK_END.search(line):
                pem_left = 0
            else:
                pem_left -= 1
                if i in changed:
                    kinds.add("private-key")
        if kinds:
            out.append((i + 1, sorted(kinds)))
    return out


def _mask_kinds(path, before, after, readable, exists, narrow_old):
    """The mask tags this write would put where the guard hid a real value, or an empty set."""
    if not exists:
        return set()
    was, now = Counter(_MASK_TAG.findall(before)), Counter(_MASK_TAG.findall(after))
    raised = {t for t in now if now[t] > was[t]}
    if not raised:
        return set()
    if not readable:
        return raised
    empty = {"allow": {}, "self": set()}
    label = names_known(path)
    try:
        if narrow_old is not None and not mask_text(narrow_old, label, empty)[1]:
            return set()  # the edit replaces only text Claude could see
        shown = Counter(_MASK_TAG.findall(mask_text(before, label, empty)[0]))
    finally:
        del REVIEW[:]
    hidden = {t for t in shown if shown[t] > was[t]}
    if hidden & _SECRET_TAGS and raised & _SECRET_TAGS:
        return raised & _SECRET_TAGS
    return raised & hidden


def _state_key():
    os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)
    p = os.path.join(STATE_DIR, "key")
    try:
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(secrets.token_bytes(32))
    except FileExistsError:
        pass
    for _ in range(5):  # another hook may be between creating the file and writing it
        with open(p, "rb") as f:
            key = f.read()
        if len(key) == 32:
            return key
        time.sleep(0.02)
    raise OSError("no state key")


def _digest(path, after):
    text = os.path.normcase(os.path.abspath(path)) + "\0" + after
    return hmac.new(_state_key(), text.encode("utf-8", "backslashreplace"), hashlib.sha256).hexdigest()


def _pending():
    """Live pending entries, oldest first; expired ones are removed."""
    out, now = [], time.time()
    try:
        names = os.listdir(STATE_DIR)
    except OSError:
        return out
    for name in names:
        if not name.endswith(".json"):
            continue
        p = os.path.join(STATE_DIR, name)
        try:
            with open(p, encoding="utf-8") as f:
                e = json.load(f)
            if now - e["created"] > PENDING_TTL:
                os.remove(p)
            else:
                out.append(e)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return sorted(out, key=lambda e: e["created"])


def _save_pending(e):
    p = os.path.join(STATE_DIR, e["id"] + ".json")
    tmp = "%s.%s.tmp" % (p, secrets.token_hex(4))
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(e, f)
    os.replace(tmp, p)


def _remember(session, agent, path, digest):
    norm = os.path.normcase(os.path.abspath(path))
    for e in _pending():
        if (e["session"], e["path"], e["hmac"]) == (session, norm, digest):
            return e["id"]
    e = {"id": secrets.token_hex(3), "session": session, "agent": agent, "path": norm, "hmac": digest,
         "created": time.time(), "armed_until": 0}
    _save_pending(e)
    return e["id"]


def _consume(session, agent, path, digest):
    """True if the owner armed exactly this write. os.remove makes it work once."""
    norm, now = os.path.normcase(os.path.abspath(path)), time.time()
    for e in _pending():
        if (e["session"], e["path"], e["hmac"]) == (session, norm, digest) and e["armed_until"] > now \
                and (agent is None or agent == e["agent"]):
            try:
                os.remove(os.path.join(STATE_DIR, e["id"] + ".json"))
                return True
            except OSError:
                continue
    return False


def arm_write_ok(prompt, session):
    """write-ok [id]: allow one denied write in this session. The owner's prompt only."""
    m = re.match(r"\s*write-ok(?:\s+([0-9a-f]{6})\b)?", prompt, re.I)
    live = [e for e in _pending() if e["session"] == session]
    if m and m.group(1):
        live = [e for e in live if e["id"] == m.group(1).lower()]
        if not live:
            return {"systemMessage": "credential-guard: write-ok found no blocked write with that id in this session."}
    if not live:
        return {"systemMessage": "credential-guard: write-ok found no blocked write in this session."}
    if len(live) > 1:
        rows = ", ".join("%s (%s)" % (e["id"], os.path.basename(e["path"])) for e in live)
        return {"systemMessage": "credential-guard: write-ok did nothing, %d writes are blocked: %s. "
                                 "Send write-ok <id> for the one you reviewed." % (len(live), rows)}
    e = live[0]
    e["armed_until"] = time.time() + ARMED_TTL
    _save_pending(e)
    return {"systemMessage": "credential-guard: write-ok allows one retry of the blocked write to %s, for 10 minutes."
                             % os.path.basename(e["path"])}


def _deny(reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def write_check(event):
    """PreToolUse on Write, Edit, NotebookEdit: the reply, or None to allow. Needs no config, so a
    broken config cannot switch it off. Names the file, line and kind, never a value."""
    tool, ti = event.get("tool_name"), event.get("tool_input") or {}
    path = ti.get("notebook_path" if tool == "NotebookEdit" else "file_path")
    if not isinstance(path, str):
        return None
    before, readable, exists = _read_before(path)
    narrow_old = None
    if tool == "Write":
        if not isinstance(ti.get("content"), str):
            return None
        after = _lf(ti["content"])
        compare, mask_after = before, after
    elif tool == "Edit":
        old, new = ti.get("old_string"), ti.get("new_string")
        if not isinstance(old, str) or not isinstance(new, str):
            return None
        old, new = _lf(old), _lf(new)
        if readable and old and old in before:
            after = before.replace(old, new) if ti.get("replace_all") else before.replace(old, new, 1)
            compare, mask_after, narrow_old = before, after, old
        else:
            after, compare, mask_after = new, "", before + "\n" + new
    else:
        if not isinstance(ti.get("new_source"), str):
            return None
        after = _lf(ti["new_source"])
        compare, mask_after = "", before + "\n" + after

    tags = _mask_kinds(path, before, mask_after, readable, exists, narrow_old)
    if tags & _SECRET_TAGS:
        return _deny("credential-guard: write blocked. %s holds real values Claude cannot see, and this write would "
                     "replace them with the mask text. Use a narrow Edit that avoids the masked text, or the owner "
                     "makes this change. write-ok cannot approve it." % path)

    lines = after.split("\n")
    changed = _changed(compare, lines)
    prose_file = path.lower().endswith((".md", ".txt"))
    hits = _scan_lines(lines, changed, False, prose_file)
    if hits:
        if secret_store(path):
            hits = []
        elif _in_test(path):
            hits = _scan_lines(lines, changed, True, prose_file)
    if not hits and not tags:
        return None

    session, agent = event.get("session_id"), event.get("agent_id")
    digest = _digest(path, after)
    if _consume(session, agent, path, digest):
        return None
    entry = _remember(session, agent, path, digest)
    out = ["credential-guard: write blocked, id %s" % entry, "  file: " + path]
    out += ["  line %-4d %s" % (n, ", ".join(kinds)) for n, kinds in hits[:PROMPT_ROWS]]
    if len(hits) > PROMPT_ROWS:
        out.append("  and %d more line%s" % (len(hits) - PROMPT_ROWS, _plural(len(hits) - PROMPT_ROWS)))
    if tags:
        out.append("  mask text would replace a real value: " + ", ".join(sorted(tags)))
    out.append("  Keep secrets in .env, a database or a secret file and read them from there. "
               "If this is a false alarm, the owner can send write-ok.")
    return _deny("\n".join(out))


# ---------------------------------------------------------------- audit
_RESTRICTED = re.compile(r"/tmp/(?:bank|cc)(?:/|$)")  # real statements live there; never opened


def _audit_blocked(path):
    p = os.path.abspath(path).replace("\\", "/")
    home = os.path.join(os.path.expanduser("~"), "ai-restricted").replace("\\", "/")
    return _RESTRICTED.search(path.replace("\\", "/")) is not None or _RESTRICTED.search(p) is not None \
        or p == home or p.startswith(home + "/")


def _has_symlink(root, rel):
    p = root
    for part in rel.split("/"):
        p = os.path.join(p, part)
        try:
            if os.path.islink(p) or not os.path.lexists(p):
                return True
        except OSError:
            return True
    return False


def audit_repo(repo):
    """[(file, line, kind)] for one repo's tracked files. Never a value. Read-only."""
    root = os.path.abspath(repo)
    rc, listing = _git(root, "ls-files", "-z", timeout=60)
    if rc != 0:
        return [("", 0, "git could not list this repo")]
    rows = []
    for rel in listing.split("\0"):
        if not rel:
            continue
        full = os.path.join(root, *rel.split("/"))
        if _audit_blocked(full) or _has_symlink(root, rel):
            continue
        label = names_known(rel)
        if label:
            rows.append((rel, 0, "tracked credential file (%s), not opened" % label))
            continue
        try:
            if os.path.getsize(full) > MAX_COMPARE:
                continue
            with open(full, "rb") as f:
                data = f.read()
        except OSError:
            continue
        if b"\0" in data[:8192]:
            continue
        lines = _lf(data.decode("utf-8", "surrogateescape")).split("\n")
        hits = _scan_lines(lines, set(range(len(lines))), _test_rel(rel), rel.lower().endswith((".md", ".txt")))
        rows += [(rel, n, ", ".join(kinds)) for n, kinds in hits]
    return rows


def audit_main(repos):
    """Print repo, file, line and kind for each repo. Nothing is changed."""
    total = 0
    for repo in repos:
        if _audit_blocked(os.path.realpath(repo)):
            print("%s\t\t0\tskipped: restricted" % repo)
            continue
        rows = audit_repo(repo)
        total += len(rows)
        for rel, n, kind in rows:
            print("%s\t%s\t%d\t%s" % (repo, rel, n, kind))
    print("audit: %d finding%s in %d repo%s" % (total, _plural(total), len(repos), _plural(len(repos))))
    return 0


def prompt_report(prompt, cfg):
    """The block notice for a prompt, or None if it is clean: source, then one row per line
    with its kind, any file:line on it, and a short excerpt. Only masked text is quoted.
    An agent report gets the strict detector, because a false alarm loses the whole report."""
    lines = prompt.split("\n")
    is_task = prompt.lstrip().startswith("<task-notification>")
    detect = (lambda l: strict_line(l, report=True)) if is_task else scan_line
    base = next((i for i, l in enumerate(lines) if "<result>" in l), 0) if is_task else 0
    rows, total = [], 0
    for i, line in enumerate(lines):
        if is_task:  # the report's first and last lines carry its wrapper tags
            line = re.sub(r"^<result>|</result>$", "", line)
        masked, k = detect(line)
        masked, k2 = pii_line(masked, cfg)
        if not k + k2:
            continue
        total += k + k2
        literal = [m.group(1) for m in _TAG.finditer(line)]  # tags already in the text are not hits
        hits = []
        for m in _TAG.finditer(masked):
            if m.group(1) in literal:
                literal.remove(m.group(1))
            else:
                hits.append(m)
        kinds = sorted({"secret" if m.group(1) == "withheld" else m.group(1) for m in hits}) or ["secret"]
        at = max(0, hits[0].start() - 24) if hits else 0
        excerpt = " ".join(masked[at:at + 64].split())
        ref = _FILE_REF.search(masked)
        rows.append("  line %-4d %-14s %s...%s..." % (i - base + 1 if is_task and i >= base else i + 1,
                                                      ",".join(kinds), ref.group(0) + "  " if ref else "", excerpt))
    if not total:
        return None
    if is_task:
        name = re.search(r'<summary>Agent "(.*?)"', prompt)
        task = re.search(r"<task-id>([^<]+)</task-id>", prompt)
        source = 'agent "%s" (task %s), line numbers count from its result' % (
            name.group(1) if name else "unknown", task.group(1)[:8] if task else "?")
        action = "Its result did not reach Claude. To pass it on, send it in a prompt starting with secret-ok."
    else:
        source = "your prompt"
        action = "Remove them, or start the prompt with secret-ok (or pii-ok) to send it as is."
    out = ["credential-guard: not sent, %d value%s on %d line%s" % (total, _plural(total), len(rows), _plural(len(rows))),
           "  from: " + source] + rows[:PROMPT_ROWS]
    if len(rows) > PROMPT_ROWS:
        out.append("  and %d more line%s" % (len(rows) - PROMPT_ROWS, _plural(len(rows) - PROMPT_ROWS)))
    return "\n".join(out + ["  " + action])


def handle(event, cfg):
    """The hook's reply as a dict, or None to stay silent."""
    ev = event.get("hook_event_name")
    tool = event.get("tool_name")

    if ev == "UserPromptSubmit":
        prompt = event.get("prompt")
        if not isinstance(prompt, str) or prompt.lstrip().lower().startswith(("secret-ok", "pii-ok")):
            return None
        report = prompt_report(prompt, cfg)
        del REVIEW[:]  # a prompt's log-only hits are his own text: not logged
        # continue:false, because decision:block makes Claude Code print the whole prompt after the reason.
        if report:
            return {"continue": False, "stopReason": report}
        return arm_write_ok(prompt, event.get("session_id")) if prompt.lstrip().lower().startswith("write-ok") else None

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
    if event.get("hook_event_name") == "PreToolUse" and event.get("tool_name") in WRITE_TOOLS:
        try:  # before any config load, so a broken config cannot switch the block off
            out = write_check(event)
        except Exception:
            del REVIEW[:]
            out = {"systemMessage": WRITE_FAILED}
        return json.dumps(out) if out else ""
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

def _selftest_strict(check):
    """The strict detector, the write block, write-ok and the mask rule. Fixtures are built at run time."""
    global STATE_DIR
    pw, hx, b64 = "Zx9fK2mQ7pL4", "a1b2c3d4" * 4, "Ab3/xY9+" * 5
    sym = "!" + pw + "#aB3xY9"
    tok = "gh" + "p_" + "a1B2" * 9
    P, S, T = "pass" + "word", "api" + "_key", "to" + "ken"
    head, tail = "-----BEGIN " + "PRIVATE KEY-----", "-----END " + "PRIVATE KEY-----"
    body = "MIIE" + "x7Qa" * 14

    for text in [P + ' = "' + pw + '"', P + ' = "' + sym + '"', S + ' = "' + hx + '"', S + ' = "' + b64 + '"',
                 "DB_PASSWORD=" + pw, "export DB_PASSWORD=" + pw, "  " + P + ": " + pw, "- DB_PASSWORD=" + pw,
                 P + ' := "' + pw + '"', 'cfg["' + P + '"] = "' + pw + '"', P + ': str = "' + pw + '"',
                 "const " + P + " = `" + pw + "`", "--" + P + " " + pw, "GET /cb?access_" + T + "=" + hx + "&x=1",
                 "DB_PASS=" + pw, 'pwd = "' + pw + '"', 'signingKey = "' + hx + '"',
                 '{"user": "bob", "' + P + '": "' + pw + '"}', '{"user":"bob","' + P + '":"' + pw + '"}',
                 "'user' => 'bob', '" + P + "' => '" + pw + "',", "define('DB_PASSWORD', '" + pw + "');",
                 S + ' = "550e8400-e29b-41d4-a716-446655440000"', tok, head, "mysql://root:" + pw + "@db/app"]:
        got, n = strict_line(text)
        check("strict hit: " + text[:24], n >= 1 and pw not in got and hx not in got and tok not in got, True)
    for text in ["login(user, " + P + "=new_" + P + ", remember=True)", "refresh(" + T + "=access_" + T + ", ttl=60)",
                 "max_" + T + "s=config.max_" + T + "s", T.upper() + '_URL = "https://oauth2.example.com/' + T + '"',
                 'API_KEY_HEADER = "X-Api-Key"', 'PASSWORD_HASH = "argon2id"', T + '_type = "bearer"',
                 "'" + T + "_type' => 'Bearer',", "config('services.stripe.secret', 'fallback')",
                 "'" + P + "' => 'required|min:8|confirmed',", "'" + P + "' => 'password.confirm',",
                 P + '_field = "user_' + P + '"', T + "s = in+out+cache_read+cache_create",
                 "- Tokens = in+out+cr+cc of the main row", P + " = user.passwordHash", P + " = currentUser." + P,
                 P + " = get_" + P + "(user)", "    " + P + "=new_" + P + ",", "pass: read-only", "pass: 1024/1024",
                 'cache_key = "cache:v2:user:settings"', "storage_key = 'user-settings-v2-cache'",
                 "oauth_private_key = 'storage/oauth-private.key'", P + "_url = '/" + P + "/reset'",
                 "DB_PASSWORD=${DB_PASSWORD}", "API_KEY=<withheld>", "API_KEY=%API_KEY%", "DB_PASSWORD=your_" + P,
                 "<code>PASSWORD=</code>-style lines"]:
        check("strict clean: " + text[:32], strict_line(text), (text, 0))
    for text in ['ok = c in ("PASS", "PASS_WITH_CAVEATS_2026")', "the test the lookup cannot pass: `document.query2Selector`"]:
        check("the word pass: " + text[:20], strict_line(text), (text, 0))
    check("a quoted pass key still hits", strict_line('{"pass": "' + pw + '"}')[1], 1)
    check("test path skips keyed", strict_line(P + ' = "' + pw + '"', in_test=True)[1], 0)
    check("test path keeps tokens", strict_line(tok, in_test=True)[1], 1)
    check("prose skips sentences", strict_line("use " + P + ' = "' + pw + '" in prose', prose=True)[1], 0)
    check("prose keeps dotenv lines", strict_line("DB_PASSWORD=" + pw, prose=True)[1], 1)

    # The two masking fixes.
    check("formula not masked", scan_line(T + "s = in+out+cache_read+cache_create")[1], 0)
    check("auth tokens still masked", scan_line("auth_" + T + "s = abc+def")[1], 1)
    for text in ['{"user": "bob", "' + P + '": "' + pw + '"}', '{"user":"bob","' + P + '":"' + pw + '"}',
                 "'user' => 'bob', '" + P + "' => '" + pw + "',", "define('DB_PASSWORD', '" + pw + "');"]:
        check("masked after a pair: " + text[:20], pw in scan_line(text)[0], False)

    # Agent reports use the strict detector, typed prompts keep the broad one.
    cfg = {"allow": {}, "self": set()}

    def say(text, session="s1"):
        return handle({"hook_event_name": "UserPromptSubmit", "prompt": text, "session_id": session}, cfg)

    def report(text):
        return say('<task-notification>\n<summary>Agent "A" finished</summary>\n<result>' + text
                   + "\n</result>\n</task-notification>")
    check("report quoting code passes", report("- `login(user, " + P + "=new_" + P + ")`\n- " + T + "s = in+out+cr+cc"), None)
    example = "assert login(" + P + '="hunter22")'
    check("report quoting a test password passes", report("- `" + example + "`"), None)
    check("the same literal in code still hits", strict_line(example)[1], 1)
    check("report with a strong literal stops", (report(P + ' = "' + pw + '"') or {}).get("continue"), False)
    check("report with a dotenv line stops", (report("DB_PASSWORD=hunter22") or {}).get("continue"), False)
    check("report with a token stops", (report("found " + tok) or {}).get("continue"), False)
    check("report with a key stops", (report(head + "\n" + body + "\n" + tail) or {}).get("continue"), False)
    check("typed dotenv still stops", (say("DB_PASSWORD=" + pw + "\nAPP_ENV=local") or {}).get("continue"), False)

    # The write block, in a real throwaway repo.
    tmp = tempfile.mkdtemp()
    saved, STATE_DIR = STATE_DIR, os.path.join(tmp, "state")
    # The fixture repo answers only to its own .gitignore: a machine's global ignore file
    # (often listing every .env) would otherwise decide what counts as a store.
    git_isolation = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "XDG_CONFIG_HOME": tmp}
    environment_before_isolation = {name: os.environ.get(name) for name in git_isolation}
    os.environ.update(git_isolation)
    repo = os.path.join(tmp, "repo")
    os.makedirs(repo)
    subprocess.run(["git", "init", "-q", repo], capture_output=True, timeout=10)

    def put(name, data):
        p = os.path.join(repo, *name.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data if isinstance(data, bytes) else data.encode("utf-8"))
        return p

    def path(name):
        return os.path.join(repo, *name.split("/"))

    def event(tool, ti, session="s1", agent=None):
        e = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": ti, "session_id": session}
        if agent:
            e["agent_id"] = agent
        return e

    def write(name, content, session="s1", agent=None):
        return write_check(event("Write", {"file_path": path(name), "content": content}, session, agent))

    def edit(name, old, new):
        return write_check(event("Edit", {"file_path": path(name), "old_string": old, "new_string": new}))

    def denied(out):
        return ((out or {}).get("hookSpecificOutput") or {}).get("permissionDecision") == "deny"

    def entry(out):
        m = re.search(r"\bid ([0-9a-f]{6})\b", out["hookSpecificOutput"]["permissionDecisionReason"])
        return m.group(1) if m else None

    put(".gitignore", "/.env\n")
    line = "DB_PASSWORD=" + pw
    out = write("app.py", "x = 1\n" + P + ' = "' + pw + '"\n')
    check("code secret denied", denied(out), True)
    check("deny names the line", "line 2" in out["hookSpecificOutput"]["permissionDecisionReason"], True)
    check("deny holds no value", pw in json.dumps(out), False)
    check("clean write allowed", write("clean.py", "x = 1\n"), None)
    check("ignored env allowed", write(".env", line), None)
    for name in [".env.example", "sub/new/.env", ".env.py", "wp-config.php", "src/.npmrc"]:
        check("not a store: " + name, denied(write(name, line)), True)
    put("fill.py", S + ' = ""\n')
    check("filling an empty key denied", denied(edit("fill.py", '""', '"' + hx + '"')), True)
    legacy = put("legacy.py", ("a = 1\r\n" + P + ' = "' + pw + '"\r\n').encode())
    check("legacy line, CRLF rewrite allowed", write("legacy.py", "a = 2\n" + P + ' = "' + pw + '"\n'), None)
    check("edit near a legacy secret allowed", edit("legacy.py", "a = 1", "a = 3"), None)
    check("legacy file exists", os.path.exists(legacy), True)
    put("key.py", 'k = """' + head + "\n" + body + "\n" + tail + '"""\n')
    check("key body edit denied", denied(edit("key.py", body, body[:-4] + "AAAA")), True)
    for text in [head + "\n" + body + "\n" + tail, head + "\nProc-Type: 4,ENCRYPTED\n\n" + body + "\n" + tail,
                 'k = "' + head + '\\n" \\\n  "' + body + '\\n"', '{"private_key": "' + head + "\\n" + body + '\\n"}']:
        check("key form denied", denied(write("keys.py", text)), True)
        check("key form stops a report", (report(text) or {}).get("continue"), False)
    check("fenced dotenv denied", denied(write("n.md", "# Setup\n```\n" + line + "\n```\n")), True)
    check("dotenv line in md denied", denied(write("n2.md", line + "\n")), True)
    check("sentence in md allowed", write("n3.md", "Set " + P + ' = "' + pw + '" here.\n'), None)
    check("test dir keyed allowed", write("tests/a.py", P + ' = "' + pw + '"\n'), None)
    check("test dir token denied", denied(write("tests/b.py", tok + "\n")), True)
    check("test_ script at root denied", denied(write("test_smtp.py", P + ' = "' + pw + '"\n')), True)
    check("js spec allowed", write("src/a.spec.ts", P + ' = "' + pw + '"\n'), None)
    check("yml test name denied", denied(write("site.test.yml", P + ": " + pw + "\n")), True)

    # Never write a mask back over a real value.
    put(".env", line + "\nAPP_ENV=local\n")
    for text in ["DB_PASSWORD=<withheld>\nAPP_ENV=local\n", "MAIL_PASSWORD=<withheld>\nAPP_ENV=local\n",
                 "export DB_PASSWORD=<withheld>\nAPP_ENV=local\n", 'DB_PASSWORD="<withheld>"\nAPP_ENV=local\n']:
        out = write(".env", text)
        check("mask over env denied", denied(out), True)
        check("mask denial has no override", entry(out), None)
    put("compose.yml", "url: postgres://u:" + pw + "@db:5432/app\n")
    check("mask with changed port denied", denied(write("compose.yml", "url: postgres://u:<withheld>@db:5433/app\n")), True)
    put("a.json", '{"args": ["postgres://u:' + pw + '@db/app"]}\n')
    check("mid-line json mask denied", denied(write("a.json", '{"args": ["postgres://u:<withheld>@db/app"], "x": 1}\n')), True)
    put("c.php", "'" + P + "' => '" + pw + "', 'host' => 'db',\n")
    check("php mask denied", denied(write("c.php", "'" + P + "' => '<withheld>', 'host' => 'db2',\n")), True)
    put("d.php", "define('DB_PASSWORD', '" + pw + "');\n")
    check("define mask denied", denied(write("d.php", "define('DB_PASSWORD', '<withheld>');\n// x\n")), True)
    put("l.php", b"// caf\xe9\ndefine('DB_PASSWORD', '" + pw.encode() + b"');\n")
    check("latin-1 mask denied", denied(write("l.php", "// cafe\ndefine('DB_PASSWORD', '<withheld>');\n")), True)
    os.makedirs(path("isdir"), exist_ok=True)
    check("unreadable file, mask denied", denied(write("isdir", "x = <withheld>\n")), True)
    say("write-ok")
    check("write-ok cannot approve a mask", denied(write(".env", "DB_PASSWORD=<withheld>\nAPP_ENV=local\n")), True)
    with open(path(".env"), encoding="utf-8") as f:
        check("env value survived", pw in f.read(), True)
    put("n.py", "# note\n" + P + ' = "' + pw + '"\n')
    check("narrow edit may add the tag", edit("n.py", "# note", "# <withheld> note"), None)
    put("n.py", "# note\n" + P + ' = "' + pw + '"\n')
    check("write of the same is denied", denied(write("n.py", "# <withheld> note\n" + P + ' = "' + pw + '"\n')), True)
    put("u.md", "Usage: skill foo\n")
    check("usage tag allowed", write("u.md", "Usage: skill <name>\n"), None)
    put("x.xml", "<name>a</name>\n")
    check("xml tag edit allowed", edit("x.xml", "<name>a</name>", "<name>b</name>"), None)
    put("h.html", "<p>x</p>\n")
    check("html tag allowed", write("h.html", "<address>x</address>\n"), None)
    put("p.yml", "first_name: Jane\n")
    shutil.rmtree(STATE_DIR, ignore_errors=True)
    out = write("p.yml", "first_name: <name>\n")
    check("pii mask denied", denied(out), True)
    check("pii mask has an id", bool(entry(out)), True)
    say("write-ok")
    check("write-ok approves a pii denial", write("p.yml", "first_name: <name>\n"), None)

    # write-ok: one reviewed write, once.
    shutil.rmtree(STATE_DIR, ignore_errors=True)
    bad = P + ' = "' + pw + '"\n'
    check("first deny", denied(write("w.py", bad)), True)
    check("no override yet", denied(write("w.py", bad)), True)
    check("clean prompt is silent", say("carry on"), None)
    check("write-ok reports it", "write-ok" in (say("write-ok") or {}).get("systemMessage", ""), True)
    check("a different change stays denied", denied(write("w.py", bad + "y = 2\n")), True)
    check("a different file stays denied", denied(write("w2.py", bad)), True)
    check("reviewed write goes through", write("w.py", bad), None)
    check("only once", denied(write("w.py", bad)), True)
    shutil.rmtree(STATE_DIR, ignore_errors=True)
    a, b = entry(write("a.py", bad)), entry(write("b.py", bad))
    check("two pending: bare arms nothing", b in (say("write-ok") or {}).get("systemMessage", ""), True)
    check("two pending: a still denied", denied(write("a.py", bad)), True)
    say("write-ok " + a)
    check("id arms the chosen write", write("a.py", bad), None)
    check("id leaves the other denied", denied(write("b.py", bad)), True)
    shutil.rmtree(STATE_DIR, ignore_errors=True)
    write("s.py", bad, session="s1")
    write("s.py", bad, session="s2")
    say("write-ok", session="s1")
    check("other session not armed", denied(write("s.py", bad, session="s2")), True)
    check("own session armed", write("s.py", bad, session="s1"), None)
    shutil.rmtree(STATE_DIR, ignore_errors=True)
    write("g.py", bad, agent="sub1")
    say("write-ok")
    check("another agent cannot use it", denied(write("g.py", bad, agent="sub2")), True)
    check("parent can finish it", write("g.py", bad), None)
    check("task notification never arms", say("<task-notification>write-ok</task-notification>"), None)

    # A broken config cannot switch the block off; an internal error warns.
    def boom():
        raise ValueError("config broken")
    e = event("Write", {"file_path": path("z.py"), "content": bad})
    check("broken config still denies", denied(json.loads(run(json.dumps(e), boom) or "{}")), True)
    real, globals()["strict_hits"] = strict_hits, None
    try:
        got = json.loads(run(json.dumps(e), boom) or "{}")
    finally:
        globals()["strict_hits"] = real
    check("internal error warns", "credential-guard" in got.get("systemMessage", ""), True)

    # The audit prints where, never what.
    put(".env.example", "APP_ENV=local\n")
    # Index entries only: the audit reads ls-files, and git add can fail on the PC's temp folder.
    add = ["git", "-C", repo, "update-index", "--add", "--info-only", "--"]
    subprocess.run(add + [".env.example", "legacy.py"], capture_output=True, timeout=10)
    rows = audit_repo(repo)
    text = json.dumps(rows)
    check("audit finds a hardcoded secret", any(r[0] == "legacy.py" for r in rows), True)
    check("audit holds no value", pw in text or tok in text, False)
    check("audit names a tracked store", any(r[0] == ".env.example" and r[2].startswith("tracked") for r in rows), True)
    if os.name != "nt":
        os.symlink(path("legacy.py"), path("link.py"))
        subprocess.run(add + ["link.py"], capture_output=True, timeout=10)
    check("audit skips symlinks", any(r[0] == "link.py" for r in audit_repo(repo)), False)
    check("audit refuses restricted paths", _audit_blocked("/x/projects/app/tmp/bank/a.csv"), True)
    check("audit refuses restricted cards", _audit_blocked("/x/projects/app/tmp/cc/a.csv"), True)
    check("audit allows normal paths", _audit_blocked("/x/projects/app/src/a.php"), False)
    del REVIEW[:]
    STATE_DIR = saved
    for name, value_before in environment_before_isolation.items():
        if value_before is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value_before
    shutil.rmtree(tmp, ignore_errors=True)


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
        check("strict no false positive: " + code, strict_line(code), (code, 0))

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
    check("prompt blocked", (p or {}).get("continue") is False and "a1B2" not in json.dumps(p), True)
    check("prompt secret-ok", prompt("secret-ok gh" + "p_" + "a1B2" * 9), None)
    check("prompt plain", prompt("fix the DB_PASSWORD= line in .e" + "nv"), None)
    check("prompt pii blocked", (prompt("call 514-555-0199 for me") or {}).get("continue"), False)
    check("prompt pii-ok", prompt("pii-ok call 514-555-0199 for me"), None)
    check("prompt own email", prompt("my email is " + me), None)
    note = ('<task-notification>\n<task-id>abcdef1234567</task-id>\n<summary>Agent "Scan" finished</summary>\n'
            "<result>clean line\nsrc/a.py:12 mail " + other + "\n</result>\n</task-notification>")
    r = (prompt(note) or {}).get("stopReason") or ""
    for want in ['agent "Scan"', "abcdef12", "line 2 ", "email", "src/a.py:12"]:
        check("block notice names " + want, want in r, True)
    check("block notice holds no value", other in r, False)
    check("block notice has no decision key", "decision" in (prompt(note) or {}), False)
    r = (prompt("\n".join("mail " + other for _ in range(PROMPT_ROWS + 3))) or {}).get("stopReason") or ""
    check("block notice is capped", (r.count("  line "), "and 3 more lines" in r), (PROMPT_ROWS, True))
    check("literal tag is not a hit", prompt("the <email> placeholder"), None)

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

    _selftest_strict(check)

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
    if sys.argv[1:2] == ["--audit"]:
        sys.exit(audit_main(sys.argv[2:]))
    # Bytes in, ASCII out: the hook's JSON is UTF-8, and Windows would decode stdin as cp1252
    # (seen 2026-11-05: a masked Read turned "…" into mojibake). json.dumps escapes non-ASCII.
    sys.stdout.write(run(sys.stdin.buffer.read().decode("utf-8", "replace")))
