---
name: create
description: >
  "create a skill", "make a command for", "new skill that", "add a /command". Creates a new skill from a one-line explanation, in the right plugin, listed, tested and linted.
argument-hint: "\"what the skill should do\""
---

# skill-kit: create

Skills are manual commands: one per task, each listed by its plugin's `list`. The argument is the
user's explanation of what the new skill should do.

## 1. Decide, then say it in two lines

- **Plugin.** One of the user's own plugins whose subject fits (installed from a local folder, so it
  can be edited). A new plugin only when the user asks for one. Pick it and state it; do not ask.
  Never write into Claude's plugin cache (`~/.claude/plugins/`): it is a copy and gets replaced.
- **Name.** Short kebab-case, the noun or verb the user would type: `/plugin:name`. Check it is free
  with `/skill-kit:skills list`.
- **Several commands on one subject** (pause, resume, check…) are several skills sharing one script,
  not one skill with modes, unless the user named it `<thing> <subcommand>`.

## 2. Write `skills/<name>/SKILL.md`

```markdown
---
name: <name>
description: >
  "<trigger the user would say>", "<another>", "<another>". <One sentence: what it does.>
---
```

- The description is quoted triggers first, then one sentence. The list shows that sentence, so it
  must stand alone.
- **Python, wherever the skill does work.** Anything deterministic (parsing, sorting, dates, paths,
  file edits, checks, more than one command in a row) goes in a Python script, not in the skill text:
  it is precise, tested, and costs fewer tokens than having the model compose it each time. The skill
  text says when to run the script and how to read its output. Enforced by the lint: skill code must
  be `.py` (only `py.sh`, the interpreter picker, is shell), and a SKILL.md may not hold a pipe, a
  command substitution or a loop.
- **Every skill script** sits in the skill folder or the plugin's `scripts/`, is Python 3.9 stdlib,
  has a `--selftest`, and logs through skilllog. Copy `py.sh` and `skilllog.py` from this plugin's
  `scripts/` into the target plugin's `scripts/` if they are not there yet. In a script in
  `skills/<name>/`:
  ```python
  sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))  # the plugin's scripts/
  from skilllog import logger
  log = logger("<plugin>:<name>")
  ...
  with log.run(sys.argv[1:]):
      main()
  ```
  `log("event", key=value)` at the points worth seeing later; it costs nothing while logging is off.
  Read them with `/skill-kit:skills log on <name>` then `/skill-kit:skills log tail <name>`.
- The skill calls it through the picker, never a named interpreter:
  `bash "<this skill's base directory>/../../scripts/py.sh" "<this skill's base directory>/<script>.py" <args>`.
- Read-only unless the task needs a write; a step that changes state outside the repo says so, and a
  step that cannot be undone asks first.

## 3. Keep the listings whole

- The plugin has no `list` skill → add one (copy `skill-kit:list` and `scripts/list-skills.py`; it
  lists the plugin folder, so it never needs editing).
- Run `/skill-kit:skills list` and check the new row reads well.

## 4. Test, lint, report

- Run every new script's `--selftest`.
- `/skill-kit:skills lint <plugin dir>` must pass.
- Commit the way the plugin's repo usually takes commits; do not push unless the user asks.
- Report: the command, what it does, its `list` row, and that it loads in the next session.
