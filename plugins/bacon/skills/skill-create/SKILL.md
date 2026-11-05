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
- The body is numbered steps. A command that runs more than once goes in a script in the plugin's
  `scripts/` (one entry script per plugin, like claude-config's `cc.sh`), called as
  `"<this skill's base directory>/../../scripts/<script>"`. Scripts get a `--selftest` or a test.
- Read-only unless the task needs a write; a step that changes state outside the repo says so, and a
  step that cannot be undone asks first.

## 4. Keep the listings whole

- The plugin has no `list` skill → add one (copy `bacon:list`; it runs `scripts/list-skills.py` on
  the plugin folder, so it never needs editing).
- Run `list-skills.py <plugin dir>` and check the new row reads well.

## 5. Test, commit, report

- Run any script's selftest on both machines (the Mac has Python 3.9).
- Commit in the worktree (subject = the feature; body = list of changes; no attribution line), then
  fast-forward `main` on the Mac. Never push ai-tools (public); claude-config pushes through its own
  sync.
- Report: the command, what it does, its `list` row, and that it loads in the next session.
