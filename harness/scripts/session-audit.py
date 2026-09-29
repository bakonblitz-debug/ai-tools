#!/usr/bin/env python3
"""session-audit.py — derive per-session metrics, and flag the few things needing a verdict.

Two outputs, deliberately separated, because mixing them is how a channel turns
into a log nobody reads (the HANDOFF.md lesson):

1. `context/metrics/sessions.tsv` — one row per session, all counts, no judgement.
   This is the substrate for the cost, behaviour and adherence panels. Noise is
   fine here: it is aggregate.

2. `context/metrics/candidates.md` — only signals that almost always mean a real
   mistake and need a human label: a permission denial, or an edit to a generated
   file. Rare by design. They sit under a `## Still open` heading, which
   `session-todo.sh` already prints at the start of every session, so an
   unlabelled one keeps surfacing until it is promoted to `failures.md` or struck.

Measured 2026-09-29: emitting every `is_error` tool result produced 60 candidates
in two days — failed greps, no-match globs, "file has not been read yet". Those are
working friction, not failures, so they are COUNTED and not queued.

PRIVACY: user message text is never read or stored. Interruptions are counted,
never quoted. Only tool-side output is excerpted, capped at 120 characters.

Usage: session-audit.py [context-repo] [--days N] [--all] [--stdout]
"""
import json
import os
import re
import sys
from pathlib import Path

PROJECTS = Path.home() / ".claude" / "projects"
GENERATED = ("application-log.md", "LEDGER.md", "ACTIVE.md", "sessions.tsv")
# The sanctioned writers. A generated file being written BY ITS GENERATOR is the
# system working; only a hand-written change is a violation. Without this exemption
# the detector flagged 24 events, nearly all of them the generators doing their job.
SANCTIONED = ("context-index.sh", "sync-log", "session-audit.py", "sync-memory.sh",
              "health-check.sh", "session-todo.sh", "context-check-monthly.sh")
EXCERPT = 120
HEADING = "## Still open — unlabelled candidates"
# started/ended/duration_s are what make tokens-per-hour and tokens-per-request
# computable (his choice of headline metric, 2026-09-29). A request is one assistant
# message; an hour is wall clock between the first and last timestamp in the session,
# which includes his thinking time and is therefore a rate for the SESSION, not for me.
COLUMNS = [
    "session", "date", "started", "ended", "duration_s", "active_s", "project", "assistant_msgs",
    "interruptions", "tool_errors", "denials", "generated_edits", "tokens_in",
    "tokens_out", "cache_read", "cache_create", "thinking", "models",
    "result_bytes", "context_read_bytes", "code_read_bytes",
]


def excerpt(text):
    one = re.sub(r"\s+", " ", str(text)).strip()
    return (one[: EXCERPT - 1] + "…") if len(one) > EXCERPT else one


def scan(path):
    """Return (metrics_row_dict, [candidate tuples]) for one transcript."""
    m = dict.fromkeys(COLUMNS, 0)
    m["session"] = path.stem
    m["project"] = path.parent.name
    m["date"] = ""
    m["started"] = ""
    m["ended"] = ""
    models = set()
    stamps = []
    # tool_use id -> where that call pointed, so a tool_result's size can be
    # attributed to what was being read. Reading is the suspected cost driver for
    # context retrieval, and "suspected" is why this is measured rather than argued.
    targets = {}
    candidates = []

    for line in path.open(encoding="utf8", errors="replace"):
        try:
            rec = json.loads(line)
        except ValueError:
            continue

        ts = rec.get("timestamp", "")
        if ts:
            if not m["date"]:
                m["date"] = ts[:10]
                m["started"] = ts
            m["ended"] = ts
            stamps.append(ts)

        if rec.get("type") == "queue-operation" and rec.get("operation") == "enqueue":
            body = str(rec.get("content", "")).lstrip()
            if not body.startswith("<task-notification>"):
                m["interruptions"] += 1
            continue

        msg = rec.get("message", {})
        if rec.get("type") == "assistant":
            m["assistant_msgs"] += 1
            if msg.get("model"):
                models.add(msg["model"])
            u = msg.get("usage") or {}
            m["tokens_in"] += u.get("input_tokens", 0) or 0
            m["tokens_out"] += u.get("output_tokens", 0) or 0
            m["cache_read"] += u.get("cache_read_input_tokens", 0) or 0
            m["cache_create"] += u.get("cache_creation_input_tokens", 0) or 0
            m["thinking"] += (u.get("output_tokens_details") or {}).get("thinking_tokens", 0) or 0

        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                inp = block.get("input", {}) or {}
                where = " ".join(str(inp.get(k, "")) for k in
                                 ("file_path", "path", "command", "pattern", "notebook_path"))
                targets[block.get("id")] = where
            if block.get("type") == "tool_result":
                body = block.get("content")
                if isinstance(body, list):
                    body = " ".join(b.get("text", "") for b in body if isinstance(b, dict))
                body = str(body)
                tid = block.get("tool_use_id", "?")
                size = len(body)
                m["result_bytes"] += size
                where = targets.get(tid, "")
                if "www/context" in where or "context/context" in where:
                    m["context_read_bytes"] += size
                elif where:
                    m["code_read_bytes"] += size
                # Must OPEN the result. A result that merely quotes a denial (a
                # transcript inspection, for instance) is not itself a denial.
                if body.lstrip().startswith("Permission for this action was denied"):
                    m["denials"] += 1
                    candidates.append(("permission_denied", f"{m['session']}:{tid}", excerpt(body)))
                elif block.get("is_error"):
                    m["tool_errors"] += 1
            elif block.get("type") == "tool_use" and block.get("name") == "Bash":
                # Auto mode routes most edits through Bash, so a Write/Edit-only check
                # is blind to nearly everything. Measured 2026-09-29: two real
                # application-log.md violations in this very session were invisible
                # until this branch existed.
                cmd = str(block.get("input", {}).get("command", ""))
                if any(tool in cmd for tool in SANCTIONED):
                    continue
                # The write operator must actually be aimed at the file. Requiring only
                # co-occurrence of a name and a ">" anywhere in the command matched
                # unrelated redirects.
                # Both directions. Shell redirects put the operator first
                # (`> application-log.md`); a python heredoc names the path first and
                # writes through a variable later (`p='...'; open(p,'w')`). Matching only
                # the shell order missed both real violations in this session.
                WRITE = r"(?:>>?|tee\s+|sed -i\b|write_text|open\(|\.write\()"
                hit = next((g for g in GENERATED
                            if re.search(WRITE + r"[^\n;|&]{0,80}" + re.escape(g), cmd)
                            or re.search(re.escape(g) + r"[\s\S]{0,400}?" + WRITE, cmd)), None)
                if hit:
                    m["generated_edits"] += 1
                    candidates.append((
                        "generated_file_edit", f"{m['session']}:{block.get('id', '?')}",
                        f"a Bash command wrote {hit}, which is generated and must never be "
                        f"hand-edited — cmd: {excerpt(cmd)}",
                    ))
            elif block.get("type") == "tool_use" and block.get("name") in ("Write", "Edit", "NotebookEdit"):
                fp = str(block.get("input", {}).get("file_path", ""))
                if fp.endswith(GENERATED):
                    m["generated_edits"] += 1
                    candidates.append((
                        "generated_file_edit", f"{m['session']}:{block.get('id', '?')}",
                        f"wrote {os.path.basename(fp)}, which is generated and must never be hand-edited",
                    ))

    m["models"] = ",".join(sorted(models)) or "-"
    # active_s sums only the gaps a human could plausibly be present for. duration_s
    # spans first to last timestamp and is inflated by sessions left open for days,
    # which made the first tokens/hour figure meaningless (measured: 776 wall hours
    # across 80 sessions, 9.7h each).
    IDLE = 300
    m["active_s"] = 0
    if len(stamps) > 1:
        from datetime import datetime
        fmt = "%Y-%m-%dT%H:%M:%S"
        prev = None
        for ts in stamps:
            try:
                cur = datetime.strptime(ts[:19], fmt)
            except ValueError:
                continue
            if prev is not None:
                gap = (cur - prev).total_seconds()
                if 0 <= gap <= IDLE:
                    m["active_s"] += int(gap)
            prev = cur
    m["duration_s"] = 0
    if m["started"] and m["ended"]:
        try:
            from datetime import datetime
            fmt = "%Y-%m-%dT%H:%M:%S"
            a = datetime.strptime(m["started"][:19], fmt)
            b = datetime.strptime(m["ended"][:19], fmt)
            m["duration_s"] = max(0, int((b - a).total_seconds()))
        except ValueError:
            m["duration_s"] = 0
    return m, candidates


def load_seen(path, pattern):
    seen = set()
    if path.exists():
        for line in path.read_text(encoding="utf8").splitlines():
            hit = re.search(pattern, line)
            if hit:
                seen.add(hit.group(1))
    return seen


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ctx = Path(args[0]) if args else Path.home() / "www" / "context"
    days = 0 if "--all" in sys.argv else 2
    if "--days" in sys.argv:
        days = int(sys.argv[sys.argv.index("--days") + 1])
    to_stdout = "--stdout" in sys.argv

    if not PROJECTS.is_dir():
        print(f"session-audit: no transcripts at {PROJECTS}", file=sys.stderr)
        return 0

    outdir = ctx / "context" / "metrics"
    tsv = outdir / "sessions.tsv"
    cand = outdir / "candidates.md"

    # A session is rewritten as it grows, so a row is replaced rather than appended.
    rows = {}
    if tsv.exists():
        for line in tsv.read_text(encoding="utf8").splitlines():
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split("\t")
            if parts:
                rows[parts[0]] = line
    seen_cand = load_seen(cand, r"\{([^}]+)\}\s*$")

    cutoff = days * 86400
    now = max((p.stat().st_mtime for p in PROJECTS.rglob("*.jsonl")), default=0)
    new_cands, touched = [], 0
    for path in sorted(PROJECTS.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime):
        if days > 0 and now and (now - path.stat().st_mtime) > cutoff:
            continue
        m, cands = scan(path)
        if not m["assistant_msgs"]:
            continue
        rows[m["session"]] = "\t".join(str(m[c]) for c in COLUMNS)
        touched += 1
        for signal, fp, note in cands:
            if fp not in seen_cand:
                seen_cand.add(fp)
                new_cands.append(f"- [ ] {signal} | {note} {{{fp}}}")

    if to_stdout:
        print("\t".join(COLUMNS))
        for k in sorted(rows):
            print(rows[k])
        print(f"\n{len(new_cands)} new candidate(s):")
        print("\n".join(new_cands) if new_cands else "  none")
        return 0

    outdir.mkdir(parents=True, exist_ok=True)
    header = (
        "# Per-session metrics — derived, never authored\n"
        "# Written by session-audit.py from ~/.claude/projects/*.jsonl. One row per session,\n"
        "# replaced in place as a session grows. No user text is read; interruptions are counted.\n"
        "# " + "\t".join(COLUMNS) + "\n"
    )
    tsv.write_text(header + "\n".join(rows[k] for k in sorted(rows)) + "\n", encoding="utf8")

    if new_cands:
        if not cand.exists():
            cand.write_text(
                "# Candidate failures — detected mechanically, labelled by hand\n\n"
                "Each line is EVIDENCE that something happened, not a verdict. Promote a real one to\n"
                "`failures.md` with its class and who caught it, or strike it as noise. Either way the\n"
                "line leaves this section — which is named so `session-todo.sh` keeps printing it until\n"
                "it is empty.\n\n"
                "Only two signals queue here: a permission denial, and an edit to a generated file.\n"
                "Everything else is counted in `sessions.tsv` instead, because emitting every tool\n"
                "error produced 60 lines in two days and a noisy queue gets ignored.\n\n"
                + HEADING + "\n\n",
                encoding="utf8",
            )
        text = cand.read_text(encoding="utf8")
        if HEADING not in text:
            text += "\n" + HEADING + "\n\n"
        cand.write_text(text.rstrip("\n") + "\n" + "\n".join(new_cands) + "\n", encoding="utf8")

    print(f"session-audit: {touched} session(s) measured, {len(new_cands)} candidate(s) queued")
    return 0


if __name__ == "__main__":
    sys.exit(main())
