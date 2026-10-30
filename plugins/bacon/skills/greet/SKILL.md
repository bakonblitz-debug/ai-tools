---
name: greet
description: >
  Greet me, what's open, what should we work on, start of session. Session opener: offers what is open today as picker options, top items first. Run as the first prompt (`claude "/bacon:greet"`).
---

# Greet

Open the session with a choice, not a wall of text. One picker, then wait. Steps 1–3 make no tool call
other than the picker: everything they need is already in the digest.

## 1. Find the digest

Look in this session's context for the startup digest that a SessionStart hook may have added:
a line like `Priority fixes N/M · next: <item>` and a `Still open` list whose lines name files such as
`plans/handoff-<topic>.md   open — <status text>`.

**No digest in context** (a fresh install without the hooks): ask in plain text, "What are we working on
today?" and stop. No picker, no tool calls.

## 2. Build at most 4 options, in this fixed order

1. **The priority item** — the `next:` part of the priority line. Label: its first few words. Description:
   the full item.
2. **Open handoffs** — the first two `plans/handoff-*.md` lines in the digest. The digest already lists
   them newest first, so take them in that order; run no command to re-sort or re-check them. Label: the
   topic from the file name, in words (`handoff-pc-boot-bsod.md` → "PC boot crashes"). Description: the
   text after `open` on that line, shortened.
3. **"Show the full list"** — always last. Description: every open item, as `ACTIVE.md` lists it.

Fewer items than that → fewer options, but always at least the last one. Do not invent options that are
not in the digest, and do not rank by your own judgment: the order above is the rule.

## 3. Ask

One AskUserQuestion call: header "Today", question "What do you want to start with?", the options from
step 2. Before it, at most one short line of text (a greeting, no summary of the list). The picker's
automatic "Other" covers anything typed.

## 4. After the answer

- **An item** → read its file, say in three lines or fewer where it stands and what the next step is,
  and ask before doing anything that changes state.
- **Show the full list** → print the `Still open` list from the digest as it is (or `ACTIVE.md` at the
  workspace root if the digest says more items exist).
- **Other** → do what was typed.
