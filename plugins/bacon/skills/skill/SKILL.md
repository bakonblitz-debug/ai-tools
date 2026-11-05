---
name: skill
description: >
  "skill list", "list all skills", "skill log", "skill tail", "skill lint", "what commands do I have". Lists every plugin's skills, turns skill run logs on or off and shows them, and checks the skill rules.
argument-hint: list | log [on|off|tail] [name] | lint
---

# bacon: skill

Every subcommand runs one script, from the Bash tool:

`bash "<this skill's base directory>/../../../../scripts/py.sh" "<this skill's base directory>/../../../../scripts/skill.py" <arguments>`

Pass his arguments through as they are; no argument means `list`. Print what the script returns, then
stop. Do not rebuild any of it by hand.

| He types | It does |
|---|---|
| `list` | Every installed plugin's skills, one table per plugin, plugins that are on first. "off here" = installed but not enabled in this folder. |
| `log` | Whether logging is on, and the log files on this machine. |
| `log on [name ...]` | Turns run logs on (no name = every skill). Names as typed: `bacon:greet` or `greet`. |
| `log off [name ...]` | Turns them off (no name = all). |
| `log tail <name> [N]` | The last N lines (default 40) of one skill's log. Read them and say in a line or two what the skill did, or where it failed. |
| `lint` | Checks the skill rules over every plugin; exits 1 on a failure. Report the `fail` lines first, each with its fix. |

Logs stay on each machine in `~/.claude/skill-logs/`. A skill's script logs only while logging is on.
A new skill is made with `/bacon:skill-create "<what it should do>"`.
