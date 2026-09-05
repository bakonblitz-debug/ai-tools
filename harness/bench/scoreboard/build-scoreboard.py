#!/usr/bin/env python3
"""Render SCOREBOARD.md from scoreboard/results.jsonl.

    python3 scoreboard/build-scoreboard.py

The ledger is append-only and holds three record types: `run` (one per
invocation, carrying the fingerprint), `check` (one per task), and `note`
(free text, used to void a run whose numbers measured the harness). A run
named by a note containing VOID is excluded from every rate here -- silently
dropping it would be worse than the bad number was.
"""

import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEDGER = HERE / "results.jsonl"
OUT = HERE.parent / "SCOREBOARD.md"


def load():
    runs, checks, voided = {}, [], set()
    for line in LEDGER.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r["type"] == "run":
            runs[r["run_id"]] = r
        elif r["type"] == "check":
            checks.append(r)
        elif r["type"] == "note" and "VOID" in r.get("note", ""):
            voided.add(r["run_id"])
    return runs, [c for c in checks if c["run_id"] not in voided], voided


def main():
    runs, checks, voided = load()
    by_task = defaultdict(list)
    for c in checks:
        by_task[c["task"]].append(c)

    lines = ["# Scoreboard", "",
             f"Generated from `scoreboard/results.jsonl` — {len(checks)} scored attempts"
             f" across {len({c['run_id'] for c in checks})} runs"
             + (f", {len(voided)} run(s) voided." if voided else "."), "",
             "| task | category | tier | passes | attempts | rate | median s |",
             "|---|---|---|---|---|---|---|"]
    for task in sorted(by_task):
        cs = by_task[task]
        ok = sum(c["result"] in ("PASS", "MACHINE_PASS_NEEDS_GRADING") for c in cs)
        secs = sorted(c["secs"] for c in cs)
        lines.append(f"| {task} | {cs[0]['category']} | {cs[0]['tier']} | {ok} | {len(cs)} | "
                     f"{ok / len(cs):.0%} | {secs[len(secs) // 2]} |")

    lines += ["", "## Runs", "",
              "| run | model | ctx | hermes | skills | soul |", "|---|---|---|---|---|---|"]
    for rid, r in sorted(runs.items()):
        mark = " **VOID**" if rid in voided else ""
        lines.append(f"| {rid}{mark} | {r['model']} | {r['ctx']} | {r['hermes']} | "
                     f"`{r['skills_sha']}` | `{r['soul_sha']}` |")

    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT} — {len(by_task)} tasks, {len(checks)} attempts")


if __name__ == "__main__":
    main()
