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

Usage:
  session-audit.py [context-repo] [--days N] [--all] [--stdout]
  session-audit.py --selftest
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


def selftest():
    import tempfile
    global PROJECTS
    ok = lambda m: print(f"  ok   {m}")

    def bad(m):
        print(f"  FAIL {m}")
        sys.exit(1)

    t = Path(tempfile.mkdtemp())

    def transcript(name, lines):
        """lines: dicts (valid records) or raw strings (e.g. a malformed line)."""
        p = t / name
        with p.open("w", encoding="utf8") as fh:
            for ln in lines:
                fh.write((json.dumps(ln) if isinstance(ln, dict) else ln) + "\n")
        return p

    def usage_msg(ts, model="m", tin=0, tout=0, cread=0, ccreate=0, think=0):
        return {"type": "assistant", "timestamp": ts,
                "message": {"model": model, "usage": {
                    "input_tokens": tin, "output_tokens": tout,
                    "cache_read_input_tokens": cread,
                    "cache_creation_input_tokens": ccreate,
                    "output_tokens_details": {"thinking_tokens": think},
                }}}

    def tool_use(ts, tid, name, **inp):
        return {"type": "assistant", "timestamp": ts,
                "message": {"content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}]}}

    def tool_result(ts, tid, text, is_error=False):
        return {"type": "user", "timestamp": ts,
                "message": {"content": [{"type": "tool_result", "tool_use_id": tid,
                                          "is_error": is_error,
                                          "content": [{"type": "text", "text": text}]}]}}

    def enqueue(ts, content):
        return {"type": "queue-operation", "operation": "enqueue", "timestamp": ts, "content": content}

    # 1. Token accounting sums across messages; models/date/duration/active_s derive
    #    from the first and last timestamp.
    p = transcript("tok.jsonl", [
        usage_msg("2026-01-01T10:00:00", model="claude-a", tin=100, tout=50, cread=20, ccreate=10, think=5),
        usage_msg("2026-01-01T10:05:00", model="claude-b", tin=200, tout=25),
    ])
    m, _ = scan(p)
    got = (m["assistant_msgs"], m["tokens_in"], m["tokens_out"], m["cache_read"], m["cache_create"], m["thinking"])
    if got != (2, 300, 75, 20, 10, 5):
        bad(f"token accounting wrong: {got}")
    if m["models"] != "claude-a,claude-b":
        bad(f"models not collected/sorted: {m['models']}")
    if m["date"] != "2026-01-01" or m["started"] != "2026-01-01T10:00:00" or m["ended"] != "2026-01-01T10:05:00":
        bad(f"date/started/ended wrong: {m}")
    if m["duration_s"] != 300 or m["active_s"] != 300:
        bad(f"duration/active_s wrong: {m}")
    ok("token accounting sums across messages; models/date/duration derived correctly")

    # 2. Interruptions: a queued task-notification is the system resuming itself,
    #    not him interrupting — only the latter counts.
    p = transcript("interrupt.jsonl", [
        enqueue("2026-01-01T10:00:00", "<task-notification>background task done</task-notification>"),
        enqueue("2026-01-01T10:00:01", "actually let's also fix the typo"),
    ])
    m, _ = scan(p)
    if m["interruptions"] != 1:
        bad(f"interruption count wrong (task-notification must not count): {m['interruptions']}")
    ok("a task-notification is not an interruption; a real interjection is")

    # 3. Generic tool errors are counted but never queued — the 60-candidates-in-
    #    two-days lesson.
    p = transcript("err.jsonl", [
        tool_use("2026-01-01T10:00:00", "id1", "Bash", command="ls -la /nope"),
        tool_result("2026-01-01T10:00:01", "id1", "ls: /nope: No such file or directory", is_error=True),
    ])
    m, cands = scan(p)
    if m["tool_errors"] != 1 or m["denials"] != 0:
        bad(f"tool error miscounted: {m}")
    if cands:
        bad(f"a generic tool error must not queue a candidate: {cands}")
    ok("generic tool errors are counted but never queued as candidates")

    # 4. A permission denial is both counted and queued.
    p = transcript("denied.jsonl", [
        tool_use("2026-01-01T10:00:00", "id2", "Bash", command="rm -rf /"),
        tool_result("2026-01-01T10:00:01", "id2", "Permission for this action was denied", is_error=True),
    ])
    m, cands = scan(p)
    if m["denials"] != 1:
        bad(f"denial not counted: {m}")
    if not any(c[0] == "permission_denied" for c in cands):
        bad(f"denial did not queue a candidate: {cands}")
    ok("a permission denial is counted and queued as a candidate")

    # 5. Read bytes are attributed to context vs code by the tool_use target path.
    ctx_text, code_text = "context file body " * 3, "code file body"
    p = transcript("bytes.jsonl", [
        tool_use("2026-01-01T10:00:00", "id3", "Read", file_path="/Users/x/www/context/context/foo.md"),
        tool_result("2026-01-01T10:00:01", "id3", ctx_text),
        tool_use("2026-01-01T10:00:02", "id4", "Read", file_path="/repo/src/foo.py"),
        tool_result("2026-01-01T10:00:03", "id4", code_text),
    ])
    m, _ = scan(p)
    if m["context_read_bytes"] != len(ctx_text) or m["code_read_bytes"] != len(code_text):
        bad(f"read bytes misattributed: {m}")
    if m["result_bytes"] != len(ctx_text) + len(code_text):
        bad(f"total result bytes wrong: {m}")
    ok("read bytes are attributed to context vs code by the tool_use target path")

    # 6. A Write/Edit aimed at a generated file is counted and queued.
    p = transcript("write.jsonl", [
        tool_use("2026-01-01T10:00:00", "id5", "Write", file_path="/repo/context/metrics/LEDGER.md"),
    ])
    m, cands = scan(p)
    if m["generated_edits"] != 1 or not any(c[0] == "generated_file_edit" for c in cands):
        bad(f"Write to a generated file not counted/queued: {m} {cands}")
    ok("a Write/Edit aimed at a generated file is counted and queued")

    # 7. Same, via a Bash redirect — and its own sanctioned generator is exempt.
    p = transcript("bash.jsonl", [
        tool_use("2026-01-01T10:00:00", "id6", "Bash", command="echo done >> application-log.md"),
        tool_use("2026-01-01T10:00:01", "id7", "Bash",
                 command="python3 harness/scripts/session-audit.py ctx >> application-log.md"),
    ])
    m, _ = scan(p)
    if m["generated_edits"] != 1:
        bad(f"unsanctioned Bash write not caught, or sanctioned one wrongly counted: {m}")
    ok("a Bash write to a generated file is caught; its own sanctioned generator is exempt")

    # 8. A malformed JSONL line is skipped, not fatal, and does not corrupt the
    #    records around it.
    p = transcript("malformed.jsonl", [
        usage_msg("2026-01-01T10:00:00", tin=1),
        "{not json",
        usage_msg("2026-01-01T10:00:01", tin=2),
    ])
    try:
        m, _ = scan(p)
    except Exception as e:
        bad(f"a malformed JSONL line must not crash the scan: {e!r}")
    if m["assistant_msgs"] != 2 or m["tokens_in"] != 3:
        bad(f"malformed line corrupted surrounding parsing: {m}")
    ok("a malformed JSONL line is skipped, not fatal")

    # 9. End to end: main() writes one row per session and queues a candidate; a
    #    second run over the same transcript is idempotent (no duplicate row, no
    #    re-queued candidate already seen).
    orig_projects, orig_argv = PROJECTS, sys.argv
    proj_dir = t / "projects" / "proj1"
    proj_dir.mkdir(parents=True)
    (proj_dir / "sess1.jsonl").write_text(
        "\n".join(json.dumps(r) for r in [
            usage_msg("2026-01-01T10:00:00", tin=10, tout=5),
            tool_use("2026-01-01T10:00:01", "id8", "Write", file_path="/repo/context/metrics/LEDGER.md"),
        ]) + "\n",
        encoding="utf8",
    )
    ctx_dir = t / "ctx"
    try:
        PROJECTS = t / "projects"
        sys.argv = ["session-audit.py", str(ctx_dir), "--all"]
        main()
        tsv = ctx_dir / "context" / "metrics" / "sessions.tsv"
        cand = ctx_dir / "context" / "metrics" / "candidates.md"
        if not tsv.exists():
            bad("main() did not write sessions.tsv")
        rows = [l for l in tsv.read_text(encoding="utf8").splitlines() if l and not l.startswith("#")]
        if len(rows) != 1 or "sess1" not in rows[0]:
            bad(f"expected exactly one row for the session: {rows}")
        if not cand.exists() or "generated_file_edit" not in cand.read_text(encoding="utf8"):
            bad("main() did not queue the generated-file-edit candidate")
        main()  # rerun over the same transcript
        rows2 = [l for l in tsv.read_text(encoding="utf8").splitlines() if l and not l.startswith("#")]
        if len(rows2) != 1:
            bad(f"a second run duplicated the session row: {rows2}")
        if cand.read_text(encoding="utf8").count("generated_file_edit") != 1:
            bad("a second run re-queued a candidate already seen")
        ok("main() writes one row per session and queues candidates idempotently across reruns")
    finally:
        PROJECTS, sys.argv = orig_projects, orig_argv

    print("selftest passed")


def main():
    if "--selftest" in sys.argv:
        selftest()
        return 0

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
