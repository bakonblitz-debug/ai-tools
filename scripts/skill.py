#!/usr/bin/env python3
"""skill.py — the /bacon:skill command: list, log and lint every plugin's skills.

  skill.py list                      every installed plugin's skills, on or off here
  skill.py log                       logging state and the log files on this machine
  skill.py log on|off [name ...]     turn run logs on or off (no name = all skills)
  skill.py log tail <name> [N]       last N lines (default 40) of one skill's log
  skill.py lint [plugin dir ...]     enforce the skill rules; exits 1 on a failure
  skill.py --selftest

Names are as typed: bacon:greet, or just greet when only one plugin has it.
The lint rules (docs: plugins/bacon/skills/skill-create/SKILL.md):
  fail  a plugin without a `list` skill
  fail  skill code that is not Python (py.sh, the interpreter picker, is the one exception)
  fail  a skill .py without a --selftest, or without skilllog
  fail  shell logic (a pipe, $( ), a loop) written into a SKILL.md: it belongs in a script
  fail  a SKILL.md without name or description
  warn  a description that does not open with quoted triggers
Stdlib only, Python 3.9.
"""
import importlib.util
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AI_TOOLS = HERE.parent
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
            return [f"no log for {name} yet ({'on' if skilllog.is_on(name, d) else 'off'}; `/bacon:skill log on {name}` turns it on)"]
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

def plugin_dirs(roots=None):
    if roots:
        return [Path(r) for r in roots]
    out = sorted(p for p in (AI_TOOLS / "plugins").glob("*") if (p / ".claude-plugin" / "plugin.json").exists())
    cc = AI_TOOLS.parent / "projects" / "claude-config" / "plugin"
    return out + ([cc] if (cc / ".claude-plugin" / "plugin.json").exists() else [])


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
        add("fail", pdir, "no `list` skill: copy bacon:list")
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
    log = skilllog.logger("bacon:skill")
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
