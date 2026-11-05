---
name: skill-create
description: >
  "create a skill", "make a command for", "new skill that", "add a /command". Creates a new skill from his one-line explanation, in the right plugin, listed, tested and committed.
argument-hint: "\"what the skill should do\""
---

# bacon: skill-create

Skills are his manual commands, like artisan commands: one per task, each listed by its plugin's
`list`. The argument is his explanation of what the new skill should do.

## 1. Decide, then say it in two lines

- **Plugin.** `bacon` (general, personal), `bacon-dev` (coding mode), `claude-config` (settings sync),
  or another plugin of his whose subject fits. A new plugin only when he asks for one. The plugin is an
  engineering call: pick it and state it, do not ask.
- **Name.** Short kebab-case, the noun or verb he would type: `/plugin:name`. Check it is free with
  `list-skills.py <plugin dir>`.
- **Several commands on one subject** (pause, resume, check…) are several skills sharing one script,
  not one skill with modes, unless he named it `<thing> <subcommand>`.

## 2. Work in a worktree

Git runs on the Mac (`ssh mac` from the PC). New branch and worktree per request:
`git worktree add ~/www/.worktrees/<repo>-<name> -b <name> main`, and write the files there.

## 3. Write `skills/<name>/SKILL.md`

```markdown
---
name: <name>
description: >
  "<trigger he'd say>", "<another>", "<another>". <One sentence: what it does.>
---
```

- The description is quoted triggers first, then one sentence. The list shows that sentence, so it
  must stand alone.
- **Python, wherever the skill does work.** Anything deterministic (parsing, sorting, dates, paths,
  file edits, checks, more than one command in a row) goes in a Python script, not in the skill text:
  it is precise, tested, and costs fewer tokens than having the model compose it each time. The skill
  text says when to run the script and how to read its output. Enforced by `skill.py lint`: skill code
  must be `.py` (only `py.sh`, the interpreter picker, is shell), and a SKILL.md may not hold a pipe,
  a command substitution or a loop.
- **Every skill script** sits in the skill folder or the plugin's `scripts/`, is Python 3.9 stdlib, has
  a `--selftest`, and logs through skilllog:
  ```python
  sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))  # ai-tools/scripts
  from skilllog import logger
  log = logger("<plugin>:<name>")
  ...
  with log.run(sys.argv[1:]):
      main()
  ```
  `log("event", key=value)` at the points worth seeing later; it costs nothing while logging is off.
  He reads them with `/bacon:skill log on <name>` then `/bacon:skill log tail <name>`.
- The skill calls it through the picker, never a named interpreter:
  `bash "<path to ai-tools>/scripts/py.sh" "<this skill's base directory>/<script>.py" <args>`.
- Read-only unless the task needs a write; a step that changes state outside the repo says so, and a
  step that cannot be undone asks first.

## 4. Keep the listings whole

- The plugin has no `list` skill → add one (copy `bacon:list`; it runs `scripts/list-skills.py` on
  the plugin folder, so it never needs editing).
- Run `list-skills.py <plugin dir>` and check the new row reads well.

## 5. Test, commit, report

- Run any script's selftest on both machines (the Mac has Python 3.9).
- `skill.py lint` must pass (`/bacon:skill lint`); the ai-tools pre-commit hook blocks the commit
  otherwise, and health-check fails until it does.
- Commit in the worktree (subject = the feature; body = list of changes; no attribution line), then
  fast-forward `main` on the Mac. Never push ai-tools (public); claude-config pushes through its own
  sync.
- Report: the command, what it does, its `list` row, and that it loads in the next session.
