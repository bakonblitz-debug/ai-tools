---
name: skill
description: >
  "skill list", "list all skills", "what commands do I have", "every plugin's commands". Manages skills across every plugin; `list` prints all installed plugins' skills, on or off here.
argument-hint: list
---

# bacon: skill

The first word of the arguments is the subcommand.

## list (also the default when no argument is given)

Run from the Bash tool (`python3` on the Mac, `py -3` on the PC):

`python3 "<this skill's base directory>/../../../../scripts/list-skills.py" --all`

Print what it returns as it is: one table per plugin, plugins that are on first. "off here" means
installed but not enabled in this folder (bacon-dev turns on in coding-mode folders). Then stop.

## Anything else

Say which subcommands exist (`list`), and that a new skill is made with `/bacon:skill-create
"<what it should do>"`.
