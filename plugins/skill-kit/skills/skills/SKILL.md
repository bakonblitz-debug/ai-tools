---
name: skills
description: >
  "skill list", "list all skills", "skill log", "skill tail", "skill lint", "what commands do I have". Lists every installed plugin's skills, turns skill run logs on or off and shows them, and checks the skill rules.
argument-hint: list | log [on|off|tail] [name] | lint [plugin dir ...]
---

# skill-kit: skills

Every subcommand runs one script, from the Bash tool:

`bash "<this skill's base directory>/../../scripts/py.sh" "<this skill's base directory>/../../scripts/skill.py" <arguments>`

Pass the user's arguments through as they are; no argument means `list`. Print what the script returns, then
stop. Do not rebuild any of it by hand.

| You type | It does |
|---|---|
| `list` | Every installed plugin's skills, one table per plugin, plugins that are on first. "off here" = installed but not enabled in this folder. |
| `log` | Whether logging is on, and the log files on this machine. |
| `log on [name ...]` | Turns run logs on (no name = every skill). Names as typed: `skill-kit:skills` or `skills`. |
| `log off [name ...]` | Turns them off (no name = all). |
| `log tail <name> [N]` | The last N lines (default 40) of one skill's log. Read them and say in a line or two what the skill did, or where it failed. |
| `lint [plugin dir ...]` | Checks the skill rules; exits 1 on a failure. No directory = every plugin installed from a local folder (Claude's own plugin copies are skipped). Report the `fail` lines first, each with its fix. |

Logs stay on each machine in `~/.claude/skill-logs/`. A skill's script logs only while logging is on.
A new skill is made with `/skill-kit:create "<what it should do>"`.
