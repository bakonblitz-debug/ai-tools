#!/usr/bin/env python3
"""list-skills.py — generated skill listings, so no list is ever maintained by hand.

  list-skills.py <plugin dir>   one plugin: a table of /<plugin>:<skill> and what each does
  list-skills.py --all          every plugin this machine knows (installed or enabled), on/off
  list-skills.py --selftest

Each row comes from the skill's SKILL.md frontmatter. A description that opens with quoted trigger
phrases ("load my context", "check the tree". Loads ...) is listed by what follows them; the
skill-kit:create convention writes descriptions that way. Stdlib only, Python 3.9.
"""
import json
import re
import sys
from pathlib import Path

HOME = Path.home()
WIDTH = 170


def frontmatter(text):
    """name and description from a SKILL.md header (the small YAML subset skills use)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out, key, block = {}, None, []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r"^([A-Za-z][\w-]*):\s*(.*)$", line)
        if m and not line.startswith((" ", "\t")):
            if key:
                out[key] = " ".join(block).strip()
            key, v = m.group(1), m.group(2).strip()
            block = [] if v in (">", "|", ">-", "|-") else [v.strip('"') if v.startswith('"') and v.endswith('"') and v.count('"') == 2 else v]
        elif key:
            block.append(line.strip())
    if key:
        out[key] = " ".join(block).strip()
    return out


def summary(desc):
    """What the skill does: the description without its leading quoted trigger phrases, cut to WIDTH."""
    rest = re.sub(r'^(\s*"[^"]*"[\s,.;:]*)+', "", desc).strip()
    s = rest or desc
    return s if len(s) <= WIDTH else s[:WIDTH].rsplit(" ", 1)[0] + "…"


def plugin_name(pdir):
    try:
        return json.loads((pdir / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["name"]
    except (OSError, ValueError, KeyError):
        return pdir.name


def rows(pdir):
    name = plugin_name(pdir)
    out = []
    for f in sorted((pdir / "skills").glob("*/SKILL.md")):
        fm = frontmatter(f.read_text(encoding="utf-8"))
        out.append((f"/{name}:{fm.get('name', f.parent.name)}", summary(fm.get("description", "(no description)"))))
    return name, out


def table(rs):
    lines = ["| Command | What it does |", "|---|---|"]
    lines += [f"| `{c}` | {d.replace('|', '/')} |" for c, d in rs]
    return "\n".join(lines)


def read_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def known_plugins(claude=HOME / ".claude"):
    """{ 'name@market': (dir or None, enabled) } from installed plugins, enabled plugins and marketplaces."""
    settings = read_json(claude / "settings.json")
    enabled = settings.get("enabledPlugins") or {}
    installed = (read_json(claude / "plugins" / "installed_plugins.json").get("plugins")) or {}
    markets = {k: v.get("installLocation") for k, v in read_json(claude / "plugins" / "known_marketplaces.json").items()}
    for k, v in (settings.get("extraKnownMarketplaces") or {}).items():
        markets.setdefault(k, ((v or {}).get("source") or {}).get("path"))
    out = {}
    for key in sorted(set(installed) | set(enabled)):
        name, _, market = key.partition("@")
        pdir = None
        mdir = markets.get(market)
        if mdir:  # a local marketplace: read the plugin from its source, not a cached copy
            for p in read_json(Path(mdir) / ".claude-plugin" / "marketplace.json").get("plugins") or []:
                if p.get("name") == name and isinstance(p.get("source"), str):
                    cand = (Path(mdir) / p["source"]).resolve()
                    pdir = cand if (cand / "skills").is_dir() else None
        if pdir is None:
            entries = installed.get(key) or []
            for e in entries if isinstance(entries, list) else [entries]:
                if e.get("installPath") and (Path(e["installPath"]) / "skills").is_dir():
                    pdir = Path(e["installPath"])
                    break
        out[key] = (pdir, bool(enabled.get(key)))
    return out


def list_all(claude=HOME / ".claude"):
    parts, none = [], []
    known = known_plugins(claude)
    for key in sorted(known, key=lambda k: (not known[k][1], k.split("@")[0])):  # on first, then by name
        pdir, on = known[key]
        if pdir is None:
            none.append(key)
            continue
        name, rs = rows(pdir)
        if not rs:
            none.append(key)
            continue
        parts.append(f"### {name} ({'on' if on else 'off here'})\n\n{table(rs)}")
    if none:
        parts.append("No skills (or not found on this machine): " + ", ".join(none))
    return "\n\n".join(parts)


def selftest():
    import tempfile
    fails = []

    def check(cond, msg):
        print(f"  {'ok  ' if cond else 'FAIL'} {msg}")
        if not cond:
            fails.append(msg)

    fm = frontmatter('---\nname: greet\ndescription: >\n  "Greet me", "what\'s open". Session opener:\n  offers what is open.\n---\nbody')
    check(fm == {"name": "greet", "description": "\"Greet me\", \"what's open\". Session opener: offers what is open."}, f"folded description is joined: {fm}")
    check(frontmatter('---\nname: x\ndescription: "Quoted whole."\n---') ["description"] == "Quoted whole.", "a fully quoted inline description loses its quotes")
    check(summary('"a", "b". Does the thing.') == "Does the thing.", "leading trigger phrases are dropped")
    check(summary("Plan, design, stress-test. Runs a loop.") == "Plan, design, stress-test. Runs a loop.", "a description without quoted triggers is kept whole")
    check(summary('"only triggers"') == '"only triggers"', "a description that is all triggers is kept")
    check(len(summary("word " * 100)) <= WIDTH + 1, "a long description is cut to the width")

    t = Path(tempfile.mkdtemp())
    m = t / "market"
    (m / ".claude-plugin").mkdir(parents=True)
    (m / ".claude-plugin" / "marketplace.json").write_text(json.dumps({"plugins": [{"name": "p", "source": "./plug"}]}))
    pd = m / "plug"
    (pd / ".claude-plugin").mkdir(parents=True)
    (pd / ".claude-plugin" / "plugin.json").write_text('{"name": "p"}')
    for s, d in (("list", '"list p". Lists p.'), ("go", "Goes.")):
        (pd / "skills" / s).mkdir(parents=True)
        (pd / "skills" / s / "SKILL.md").write_text(f"---\nname: {s}\ndescription: {d}\n---\n")
    name, rs = rows(pd)
    check(name == "p" and rs == [("/p:go", "Goes."), ("/p:list", "Lists p.")], f"one plugin lists its skills, sorted: {rs}")

    c = t / ".claude"
    (c / "plugins").mkdir(parents=True)
    (c / "settings.json").write_text(json.dumps({"enabledPlugins": {"p@mk": True, "gone@mk": False},
                                                  "extraKnownMarketplaces": {"mk": {"source": {"path": str(m)}}}}))
    out = list_all(c)
    check("### p (on)" in out and "`/p:go`" in out, f"--all finds a plugin through a directory marketplace in settings: {out[:80]}")
    check("not found on this machine): gone@mk" in out, "a plugin with no skills found is named, not dropped")

    print("selftest " + ("FAILED" if fails else "passed"))
    return 1 if fails else 0


def main(args):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    if args == ["--selftest"]:
        return selftest()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from skilllog import logger
    log = logger("list-skills")
    with log.run(args):
        if args == ["--all"]:
            print(list_all())
            return 0
        if len(args) == 1 and (Path(args[0]) / "skills").is_dir():
            name, rs = rows(Path(args[0]))
            log("listed", plugin=name, skills=len(rs))
            print(f"### {name}\n\n{table(rs)}")
            return 0
        print(__doc__)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
