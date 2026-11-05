#!/usr/bin/env python3
"""skill.py — the /skill-kit:skills command: list, log and lint every plugin's skills.

  skill.py list                      every installed plugin's skills, on or off here
  skill.py log                       logging state and the log files on this machine
  skill.py log on|off [name ...]     turn run logs on or off (no name = all skills)
  skill.py log tail <name> [N]       last N lines (default 40) of one skill's log
  skill.py lint [plugin dir ...]     enforce the skill rules; exits 1 on a failure
  skill.py --selftest

Names are as typed: skill-kit:create, or just create when only one plugin has it.
The lint rules (docs: the skill-kit plugin's skills/create/SKILL.md):
  fail  a plugin without a `list` skill
  fail  skill code that is not Python (py.sh, the interpreter picker, is the one exception)
  fail  a skill .py without a --selftest, or without skilllog
  fail  shell logic (a pipe, $( ), a loop) written into a SKILL.md: it belongs in a script
  fail  a SKILL.md without name or description
  warn  a description that does not open with quoted triggers
  fail  in a plugin marked public (.claude-plugin/PUBLIC): one workspace's paths, machines, local
        tools or model names, or owner pronouns; a line ending in public-ok is exempt
Stdlib only, Python 3.9.
"""
import importlib.util
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECKOUT = HERE.parent  # the repo or plugin this copy of skill.py ships in
sys.path.insert(0, str(HERE))
import skilllog  # noqa: E402

_spec = importlib.util.spec_from_file_location("list_skills", HERE / "list-skills.py")
ls = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ls)

CODE_SUFFIXES = {".sh", ".bash", ".zsh", ".js", ".mjs", ".cjs", ".ts", ".rb", ".pl", ".ps1", ".php", ".lua"}
SHIM = "py.sh"
SHELL_LANGS = {"bash", "sh", "shell", "zsh", "console"}
SHELL_LOGIC = [(re.compile(r"\s\|\s"), "a pipe"), (re.compile(r"\$\("), "a $( ) substitution"),
               (re.compile(r";\s*do\b|\bdone\b\s*$|\bwhile\s"), "a loop")]

# A plugin with this marker file is published for anyone: it may not carry one workspace's specifics.
PUBLIC_MARK = "PUBLIC"
PUBLIC_TEXT = {".md", ".py", ".json", ".sh", ".txt", ".toml", ".yaml", ".yml"}
NOT_PUBLIC = [  # first match per line is reported; paths before words
    (re.compile(r"~/www\b|/mnt/www\b|\bM:\\|/Users/\w+"), "a workspace path"),  # public-ok
    (re.compile(r"\bssh mac\b|\bon-mac\.sh\b"), "ssh mac (one machine's setup)"),  # public-ok
    (re.compile(r"\bai-tools\b|\bclaude-config\b|context/memory\b"), "a reference to the private harness"),  # public-ok
    (re.compile(r"\b[Hh]ermes\b|\bOpenViking\b|\bLM ?Studio\b|\blmstudio\b"), "a local tool of one setup"),  # public-ok
    (re.compile(r"\b(deepseek|gemma\d?|qwen[\d.]*|llama[\d.]*|devstral)\b", re.I), "a local model name"),  # public-ok
    (re.compile(r"\b(he|his|him)\b"), "an owner pronoun (write for the user: you)"),  # public-ok
]


# ---- names -----------------------------------------------------------------------------------

def all_skills(claude=None):
    """{'plugin:skill', ...} for every plugin this machine knows."""
    out = set()
    for pdir, _ in ls.known_plugins(claude or ls.HOME / ".claude").values():
        if pdir:
            name, rows = ls.rows(pdir)
            out |= {c.lstrip("/") for c, _ in rows}
    return out


def resolve(name, known):
    if ":" in name or name == "all":
        return name
    hits = sorted(k for k in known if k.split(":", 1)[1] == name)
    if len(hits) == 1:
        return hits[0]
    raise SystemExit(f"skill: '{name}' matches {hits or 'no skill'}; use plugin:skill")


# ---- log -------------------------------------------------------------------------------------

def log_cmd(args, d=None, known=None):
    d = d or skilllog.DIR
    sub = args[0] if args else "status"
    if sub in ("on", "off"):
        names = [resolve(n, known if known is not None else all_skills()) for n in args[1:]] or ["all"]
        cur = skilllog.enabled_names(d)
        cur = (cur | set(names)) if sub == "on" else (set() if "all" in names else cur - set(names))
        d.mkdir(parents=True, exist_ok=True)
        if cur:
            (d / "enabled").write_text("\n".join(sorted(cur)) + "\n", encoding="utf-8")
        elif (d / "enabled").exists():
            (d / "enabled").unlink()
        return [f"logging {sub} for {', '.join(names)}", status_line(d)]
    if sub == "tail":
        if len(args) < 2:
            raise SystemExit("usage: skill.py log tail <name> [N]")
        name = resolve(args[1], known if known is not None else all_skills())
        n = int(args[2]) if len(args) > 2 else 40
        p = skilllog.log_path(name, d)
        if not p.exists():
            return [f"no log for {name} yet ({'on' if skilllog.is_on(name, d) else 'off'}; `/skill-kit:skills log on {name}` turns it on)"]
        return p.read_text(encoding="utf-8").splitlines()[-n:]
    if sub == "status":
        out = [status_line(d)]
        for p in sorted(d.glob("*.log")) if d.exists() else []:
            last = (p.read_text(encoding="utf-8").splitlines() or [""])[-1][:19]
            out.append(f"  {p.name}  {p.stat().st_size} bytes  last {last or '-'}")
        return out
    raise SystemExit("usage: skill.py log [status | on [name ...] | off [name ...] | tail <name> [N]]")


def status_line(d):
    names = skilllog.enabled_names(d)
    return "logging is off" if not names else ("logging is on for every skill" if "all" in names else "logging is on for " + ", ".join(sorted(names)))


# ---- lint ------------------------------------------------------------------------------------

def plugin_dirs(roots=None, claude=None):
    """The plugins to lint: the given roots, else this checkout's plugins plus every installed
    plugin that runs from a local clone. Claude's plugin cache is a copy, never linted or edited,
    and a clone under a vendor/ folder is someone else's plugin, so our rules don't apply to it."""
    if roots:
        return [Path(r) for r in roots]
    claude = Path(claude or ls.HOME / ".claude")
    managed = (claude / "plugins").resolve()  # cache and GitHub marketplaces: Claude's copies
    is_plugin = lambda d: (d / ".claude-plugin" / "plugin.json").exists()
    out = [CHECKOUT] if is_plugin(CHECKOUT) else []
    out += sorted(p for p in (CHECKOUT / "plugins").glob("*") if is_plugin(p))
    names = {ls.rows(p)[0] for p in out}
    seen = {p.resolve() for p in out}
    for pdir, _ in ls.known_plugins(claude).values():
        if pdir is None:
            continue
        r = pdir.resolve()
        if r in seen or managed in r.parents or "vendor" in r.parts:
            continue
        name = ls.rows(pdir)[0]
        if name in names:  # another checkout of a plugin this one provides (a worktree's main)
            continue
        seen.add(r)
        names.add(name)
        out.append(pdir)
    return out


def code_spans(md):
    """(line number, code) for shell code in a SKILL.md: fenced shell blocks and inline `spans`."""
    out, fence, lang = [], None, ""
    for i, line in enumerate(md.splitlines(), 1):
        m = re.match(r"^\s*(```+|~~~+)\s*([\w-]*)", line)
        if m and fence is None:
            fence, lang = m.group(1), m.group(2).lower()
            continue
        if fence is not None:
            if line.strip().startswith(fence):
                fence = None
            elif lang in SHELL_LANGS:
                out.append((i, line))
            continue
        out += [(i, s) for s in re.findall(r"`([^`]+)`", line)]
    return out


def lint_plugin(pdir):
    found = []
    add = lambda level, path, msg: found.append((level, str(path), msg))
    if not (pdir / "skills" / "list" / "SKILL.md").exists():
        add("fail", pdir, "no `list` skill: copy skill-kit:list")
    files = [p for p in [*(pdir / "scripts").glob("*"), *(pdir / "skills").rglob("*")]
             if p.is_file() and "__pycache__" not in p.parts and not p.name.startswith(".")]
    for f in files:
        if f.suffix in CODE_SUFFIXES and f.name != SHIM:
            add("fail", f, "skill code must be Python (deterministic, tested, logged); move it to a .py")
        elif f.suffix == ".py":
            text = f.read_text(encoding="utf-8", errors="replace")
            if "--selftest" not in text:
                add("fail", f, "no --selftest")
            if "skilllog" not in text:
                add("fail", f, "does not use skilllog (from skilllog import logger)")
    for md in sorted((pdir / "skills").glob("*/SKILL.md")):
        text = md.read_text(encoding="utf-8")
        fm = ls.frontmatter(text)
        if not fm.get("name") or not fm.get("description"):
            add("fail", md, "frontmatter needs name and description")
        elif not fm["description"].startswith('"'):
            add("warn", md, 'description should open with quoted triggers: "x", "y". Then one sentence.')
        for n, code in code_spans(text):
            for rx, what in SHELL_LOGIC:
                if rx.search(code):
                    add("fail", f"{md}:{n}", f"{what} in the skill text ({code.strip()[:60]}): put the logic in a script")
                    break
    if (pdir / ".claude-plugin" / PUBLIC_MARK).exists():
        for f in sorted(pdir.rglob("*")):
            if not f.is_file() or f.suffix not in PUBLIC_TEXT or {".git", "__pycache__"} & set(f.parts):
                continue
            for n, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if "public-ok" in line:
                    continue
                for rx, what in NOT_PUBLIC:
                    m = rx.search(line)
                    if m:
                        add("fail", f"{f}:{n}", f"public plugin: {what} ({m.group(0)}); generalise it, or end the line with public-ok")
                        break
    return found


def lint(roots=None):
    return [x for p in plugin_dirs(roots) for x in lint_plugin(p)]


# ---- selftest --------------------------------------------------------------------------------

def selftest():
    import tempfile
    fails = []

    def check(cond, msg):
        print(f"  {'ok  ' if cond else 'FAIL'} {msg}")
        if not cond:
            fails.append(msg)

    t = Path(tempfile.mkdtemp())
    p = t / "plug"
    (p / ".claude-plugin").mkdir(parents=True)
    (p / ".claude-plugin" / "plugin.json").write_text('{"name": "plug"}')

    def skill(name, desc, body=""):
        (p / "skills" / name).mkdir(parents=True, exist_ok=True)
        (p / "skills" / name / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {desc}\n---\n{body}", encoding="utf-8")

    skill("go", '"go now". Goes.', "Run `ls x | grep y`.\n\n```markdown\na | b\n```\n\n```bash\nfor f in *; do echo; done\n```\n")
    (p / "scripts").mkdir()
    (p / "scripts" / "run.sh").write_text("echo")
    (p / "scripts" / SHIM).write_text("exec python3")
    (p / "skills" / "go" / "tool.py").write_text("print(1)")
    got = lint([p])
    msgs = " ".join(m for _, _, m in got)
    check(any("no `list` skill" in m for _, _, m in got), "a plugin without list fails")
    check(any(path.endswith("run.sh") for _, path, _ in got) and not any(path.endswith(SHIM) for _, path, _ in got),
          "a .sh script fails, the py.sh shim does not")
    check("no --selftest" in msgs and "skilllog" in msgs, "a .py without selftest or skilllog fails")
    check(sum("a pipe" in m for _, _, m in got) == 1 and "a loop" in msgs, "shell logic in inline code and a bash block fails; a markdown block is ignored")
    skill("list", "Lists.")
    (p / "scripts" / "run.sh").unlink()
    (p / "skills" / "go" / "tool.py").write_text("import skilllog\n# --selftest\n")
    skill("go", '"go now". Goes.', "Run `bash py.sh tool.py --x`.\n")
    got = lint([p])
    check([lvl for lvl, _, _ in got] == ["warn"], f"a clean plugin passes; an unquoted description only warns: {got}")

    # a public plugin may not carry one workspace's specifics; a private one may
    skill("go", '"go now". Goes.', "Plans go to ~/www/.plans and he decides.\nRun it for the user.\nhis example  <!-- public-ok -->\n")  # public-ok
    (p / "hooks").mkdir()
    (p / "hooks" / "h.sh").write_text("# runs over ssh mac\n")  # public-ok
    check(not any("public plugin" in m for _, _, m in lint([p])), "a private plugin may name its workspace")
    (p / ".claude-plugin" / PUBLIC_MARK).write_text("")
    got = [(path, m) for _, path, m in lint([p]) if "public plugin" in m]
    check(sum(path.endswith("go/SKILL.md:5") for path, _ in got) == 1
          and any(path.endswith("go/SKILL.md:5") and "~/www" in m for path, m in got)  # public-ok
          and any(path.endswith("h.sh:1") and "ssh mac" in m for path, m in got)  # public-ok
          and not any(path.endswith("go/SKILL.md:6") or path.endswith("go/SKILL.md:7") for path, _ in got),
          f"a public plugin fails on workspace paths, ssh mac and owner pronouns, one finding per line, public-ok exempts a line: {got}")
    (p / ".claude-plugin" / PUBLIC_MARK).unlink()

    # with no roots, lint covers plugins installed from a local clone, never the plugin cache
    import json
    m = t / "market"
    (m / ".claude-plugin").mkdir(parents=True)
    (m / ".claude-plugin" / "marketplace.json").write_text(json.dumps({"plugins": [{"name": "loc", "source": "./"}]}))
    (m / "skills" / "list").mkdir(parents=True)
    c = t / ".claude"
    cached = c / "plugins" / "cache" / "gh" / "remote" / "1.0"
    (cached / "skills" / "list").mkdir(parents=True)
    third = c / "plugins" / "marketplaces" / "third"
    (third / ".claude-plugin").mkdir(parents=True)
    (third / ".claude-plugin" / "marketplace.json").write_text(json.dumps({"plugins": [{"name": "tp", "source": "./"}]}))
    (third / "skills" / "list").mkdir(parents=True)
    twin = t / "twin"  # another checkout of a plugin this checkout already provides
    own = ls.rows(plugin_dirs(claude=t / "no-claude")[0])[0]
    (twin / ".claude-plugin").mkdir(parents=True)
    (twin / ".claude-plugin" / "marketplace.json").write_text(json.dumps({"plugins": [{"name": own, "source": "./"}]}))
    (twin / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": own}))
    (twin / "skills" / "list").mkdir(parents=True)
    hm = t / "harness-market"  # a local marketplace that holds a vendor's clone under vendor/
    (hm / ".claude-plugin").mkdir(parents=True)
    (hm / ".claude-plugin" / "marketplace.json").write_text(json.dumps({"plugins": [{"name": "vp", "source": "./vendor/vp"}]}))
    vp = hm / "vendor" / "vp"
    (vp / "skills" / "go").mkdir(parents=True)
    (c / "plugins" / "known_marketplaces.json").write_text(json.dumps({
        "mk": {"installLocation": str(m)}, "th": {"installLocation": str(third)}, "tw": {"installLocation": str(twin)},
        "hv": {"installLocation": str(hm)}}))
    (c / "plugins" / "installed_plugins.json").write_text(json.dumps({"plugins": {
        "loc@mk": [{"installPath": str(c / "plugins" / "cache" / "mk" / "loc" / "1")}],
        "remote@gh": [{"installPath": str(cached)}], "tp@th": [{}], own + "@tw": [{}], "vp@hv": [{}]}}))
    (c / "settings.json").write_text("{}")
    dirs = [d.resolve() for d in plugin_dirs(claude=c)]
    check(m.resolve() in dirs and not {cached.resolve(), third.resolve(), twin.resolve(), vp.resolve()} & set(dirs),
          f"a local-clone plugin is linted; cached, third-party marketplace, vendor/ and duplicate-name ones are not: {dirs}")

    d = t / "logs"
    known = {"bacon:greet", "plug:go", "other:go"}
    check(resolve("greet", known) == "bacon:greet", "a unique short name resolves to plugin:skill")
    try:
        resolve("go", known)
        ambiguous = False
    except SystemExit:
        ambiguous = True
    check(ambiguous, "an ambiguous short name is refused")
    log_cmd(["on", "greet"], d, known)
    check(skilllog.enabled_names(d) == {"bacon:greet"}, "log on <name> enables that skill")
    skilllog.logger("bacon:greet", d)("hi")
    check(log_cmd(["tail", "greet", "5"], d, known)[-1].endswith(" hi"), "log tail shows the last lines")
    check("bacon-greet.log" in " ".join(log_cmd([], d, known)), "log status lists the log files")
    log_cmd(["off"], d, known)
    check(skilllog.enabled_names(d) == set() and not skilllog.logger("bacon:greet", d).on, "log off with no name turns everything off")
    print("selftest " + ("FAILED" if fails else "passed"))
    return 1 if fails else 0


def main(args):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    if args == ["--selftest"]:
        return selftest()
    log = skilllog.logger("skill-kit:skills")
    with log.run(args):
        cmd = args[0] if args else "list"
        if cmd == "list":
            print(ls.list_all())
            return 0
        if cmd == "log":
            print("\n".join(log_cmd(args[1:])))
            return 0
        if cmd == "lint":
            found = lint(args[1:] or None)
            for level, path, msg in sorted(found, key=lambda x: (x[0] != "fail", x[1])):
                print(f"{level:4}  {path}: {msg}")
            n = sum(level == "fail" for level, _, _ in found)
            print(f"lint: {n} failure(s), {len(found) - n} warning(s)")
            log("lint", failures=n, warnings=len(found) - n)
            return 1 if n else 0
        print(__doc__)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
