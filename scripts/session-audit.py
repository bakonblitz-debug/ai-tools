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

Also written beside sessions.tsv: usage.tsv (output tokens and dollars by activity), inputs.tsv
(new input tokens by source) and hooks.tsv (runs, errors, duration per session/event/hook; hook
tokens are in inputs.tsv under source `hook`).

PRIVACY: user message text is never read or stored. Interruptions are counted,
never quoted. Only tool-side output is excerpted, capped at 120 characters.

Usage:
  session-audit.py [context-repo] [--days N] [--all] [--stdout]
  session-audit.py [context-repo] --usage-report [--days N | --all]   output tokens by activity (default 7 days)
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
# The fingerprint is the last {...} on a candidate line; the excerpt before it may hold braces too.
SEEN_CAND = r"\{([^{}]+)\}\s*$"
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


USAGE_COLUMNS = ["session", "date", "project", "agent", "activity", "requests", "output", "thinking", "cost_usd"]
INPUT_COLUMNS = ["session", "date", "project", "agent", "source", "kind", "tokens", "images"]
HOOK_COLUMNS = ["session", "date", "project", "agent", "event", "hook", "runs", "errors", "duration_ms"]
HARNESS_TOOLS = {"ToolSearch", "AskUserQuestion", "Artifact", "ArtifactComments", "ArtifactData",
                 "SubagentHandback", "SendMessage", "ScheduleWakeup", "ExitPlanMode", "EnterPlanMode",
                 "EnterWorktree", "ExitWorktree", "Monitor", "CronCreate", "CronDelete", "CronList",
                 "ReadNotifications", "SendUserFile", "PushNotification", "SendFeedback", "Skill"}
BROWSER = ("mcp__claude-in-chrome__", "mcp__Claude_Browser__", "mcp__remote-devices__Claude_Browser__")


def activity(call):
    """What one tool call was for. Unknown tools fall to 'other'."""
    name, inp = call.get("name", ""), call.get("input") or {}
    if name in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
        return "planning" if "/.plans/" in str(inp.get("file_path", "")) else "coding"
    if name == "Skill":
        return "planning" if re.search(r"ouroboros|architect", str(inp.get("skill", ""))) else "harness"
    if name.startswith(BROWSER):
        return "browser"
    if name == "Bash":
        # ponytail: keyword heuristic, first match wins (write > verify > git > run > read);
        # parse the shell properly if it misleads. Python-level writes are matched on the
        # full text (they live inside heredocs); everything else on `bare`, which drops
        # heredoc bodies and quoted strings so a commit message or a grep pattern is not
        # mistaken for a command.
        cmd = str(inp.get("command", ""))
        # Redirects into /dev/null or a temp folder are logs, not edits.
        cmd = re.sub(r"[12]?>>?\s*[\"']?(/dev/null|/(private/)?tmp/|\$\{?TMP)[^\s;&|]*|2>&1", "", cmd)
        bare = re.sub(r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n.*?\n\1\b", "<<H", cmd, flags=re.S)
        bare = re.sub(r"'[^']*'|\"(?:\\.|[^\"\\])*\"", "Q", bare)
        at = r"(?:^|[;&|(]\s*|\bcd\s+\S+\s*&&\s*)(?:\w+=\S*\s+|caffeinate\s+-\w+\s+|time\s+|\S*/)*"
        if (re.search(r"(?<![<-])>>?\s*[^\s&]|\btee\b|sed -i|" + at + r"(mv|cp|rm|mkdir|touch)\s", bare)
                or re.search(r"write_text|open\([^)]*['\"][wa]|\.write\(", cmd)):
            return "planning" if re.search(r"/\.plans\b", cmd) else "coding"
        if re.search(r"--selftest|\b(pytest|vitest|jest|phpunit|tsc)\b|" + at + r"make\b|\b(npm|pnpm|yarn|bun) (run )?(test|build|check)|\b(go|cargo) (test|build)", bare):
            return "verifying"
        if re.search(at + r"(git|gh)\s", bare):
            return "git"
        if re.search(at + r"(docker|ddev)\s|" + at + r"(node|python3?|php|ruby|deno|bun|tsx|bash|sh)\b[^|;&]*?\s\S+\.(py|ts|mjs|js|php|rb|sh)\b", bare):
            return "running"
        return "reading"
    return {"Read": "reading", "Grep": "reading", "Glob": "reading", "Agent": "delegating", "Task": "delegating",
            "WebFetch": "web", "WebSearch": "web",
            # A headless run's schema answer is its answer.
            "StructuredOutput": "answering"}.get(name) or (
        "mcp:" + name.split("__")[1].removeprefix("claude_ai_") if name.startswith("mcp__")
        else "harness" if name in HARNESS_TOOLS or name.startswith("Task") else "other")


def group(agent):
    """Report table an agent belongs to: hooks run headless, so they sit with headless runs."""
    return "headless + hooks" if agent == "headless" or agent.startswith("hook:") \
        else "interactive (main + subagents)"


def usage_report(usage_tsv, days=7):
    """Output-token share by activity over the last `days` days (0 = all), one table per
    agent kind: interactive work (main + subagents) and headless runs (benchmarks, app and
    hook calls) are kept apart so one never skews the other."""
    from datetime import date, timedelta
    since = (date.today() - timedelta(days=days)).isoformat() if days else ""
    groups = {}
    for l in usage_tsv.read_text(encoding="utf8").splitlines():
        if l.startswith("#") or not l.strip():
            continue
        # Rows written before cost existed (2026-10-28) have 8 fields; their cost reads 0.
        _, d, _, agent, act, req, out, think, usd = (l.split("\t") + ["0"])[:9]
        if d >= since:
            g = group(agent)
            for key in (act, "~" + agent):  # "~" marks the per-agent rows
                t = groups.setdefault(g, {}).setdefault(key, [0.0, 0, 0, 0.0])
                t[0] += float(req); t[1] += int(out); t[2] += int(think); t[3] += float(usd)
    lines = []
    for g in sorted(groups, reverse=True):
        total = sum(t[1] for k, t in groups[g].items() if k[0] != "~") or 1
        usd = sum(t[3] for k, t in groups[g].items() if k[0] != "~")
        lines.append(f"== {g}: {total:,} output tokens, ${usd:.4f} (prices as of {PRICES_AS_OF})")
        for title, agents in (("activity", False), ("agent", True)):
            tot = {k.lstrip("~"): t for k, t in groups[g].items() if (k[0] == "~") == agents}
            lines.append(f"{title:28}{'requests':>9}{'output':>12}{'thinking':>10}{'cost $':>10}{'share':>7}")
            for key, (req, out, think, c) in sorted(tot.items(), key=lambda x: -x[1][1]):
                lines.append(f"{key:28}{req:>9g}{out:>12,}{think:>10,}{c:>10.2f}{round(100 * out / total):>6}%")
        lines.append("")
    inputs_tsv = usage_tsv.with_name("inputs.tsv")
    groups = {}
    for l in (inputs_tsv.read_text(encoding="utf8").splitlines() if inputs_tsv.exists() else []):
        if l.startswith("#") or not l.strip():
            continue
        _, d, _, agent, src, kind, tok, img = l.split("\t")
        if d >= since:
            g = groups.setdefault(group(agent), ({}, {}))
            for table, key in zip(g, (src, kind)):
                t = table.setdefault(key, [0, 0])
                t[0] += int(tok); t[1] += int(img)
    for g in sorted(groups, reverse=True):
        total = sum(t[0] for t in groups[g][0].values()) or 1
        lines.append(f"== new input, {g}: {total:,} tokens")
        for title, table in zip(("source", "kind"), groups[g]):
            lines.append(f"{title:22}{'tokens':>12}{'images':>8}{'share':>7}")
            for key, (tok, img) in sorted(table.items(), key=lambda x: -x[1][0]):
                lines.append(f"{key:22}{tok:>12,}{img:>8}{round(100 * tok / total):>6}%")
        lines.append("")
    return lines


# $ per million tokens: input, cache write 5m, cache write 1h, cache read, output.
# Source: claude-api reference (cached 2026-10-06), writes 1.25x / 2x input. Checked
# 2026-10-28 against Claude Code's own lastModelUsage costUSD: exact for opus-5-5,
# sonnet-4-6 and haiku-4-5. Matched by longest prefix, so date suffixes are fine.
# ponytail: fast mode and web search are not priced; neither appears in any transcript.
PRICES_AS_OF = "2026-10-28"
PRICES = {
    "claude-fable-5": (10, 12.5, 20, 0.25, 50),  # 5.1 cache read; Fable 5 not on file
    "claude-opus-5-5": (4, 5, 8, 0.20, 20),
    "claude-opus-5": (5, 6.25, 10, 0.50, 25),
    "claude-opus-4": (5, 6.25, 10, 0.50, 25),
    "claude-sonnet-5": (2, 2.5, 4, 0.20, 10),  # 5 and 5.5
    "claude-sonnet-4": (3, 3.75, 6, 0.30, 15),
    "claude-haiku-5-5": (0.10, 0.125, 0.20, 0.01, 0.50),
    "claude-haiku-4": (1, 1.25, 2, 0.10, 5),
}
LONG_PROMPT = {"claude-haiku-5-5": (100_000, 5)}  # over N prompt tokens, every rate x5 [assumed: reads too]


def cost(model, u):
    """Dollars for one request, or None when the model is not in the table. Writes with
    no 5m/1h split are priced 1h, which Claude Code uses (all real records carry it)."""
    key = max((k for k in PRICES if (model or "").startswith(k)), key=len, default=None)
    if not key:
        return None
    i, w5, w1, r, o = PRICES[key]
    tin, cr = u.get("input_tokens", 0) or 0, u.get("cache_read_input_tokens", 0) or 0
    cw = u.get("cache_creation_input_tokens", 0) or 0
    split = u.get("cache_creation") or {}
    c5 = split.get("ephemeral_5m_input_tokens", 0) or 0
    c1 = split.get("ephemeral_1h_input_tokens", cw - c5) or 0
    limit, mult = LONG_PROMPT.get(key, (0, 1))
    mult = mult if limit and tin + cr + cw > limit else 1
    return mult * (tin * i + c5 * w5 + c1 * w1 + cr * r + (u.get("output_tokens", 0) or 0) * o) / 1e6


CHARS_PER_TOKEN = 4  # ponytail: rough; only the ratio between parts of one request matters


# Models that take images up to 2576 px on the long edge (claude-api model-migration doc);
# the rest scale to 1568. ponytail: prefix list, extend it when a new family ships.
HIRES_VISION = ("claude-opus-4-7", "claude-opus-4-8", "claude-opus-5", "claude-sonnet-5", "claude-fable")


def image_tokens(block, model=""):
    """Tokens for one image block: width*height/750 after the long edge is scaled to the
    model's cap (vision docs). PNG and JPEG sizes come from their headers; unknown → 1600."""
    import base64, struct
    try:
        raw = base64.b64decode((block.get("source") or {}).get("data", ""), validate=False)
    except ValueError:
        raw = b""
    w = h = 0
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", raw[16:24])
    elif raw[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(raw) and raw[i] == 0xFF:
            if raw[i + 1] in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">HH", raw[i + 5:i + 9])
                break
            i += 2 + struct.unpack(">H", raw[i + 2:i + 4])[0]
    if not (w and h):
        return 1600
    scale = min(1, (2576 if model.startswith(HIRES_VISION) else 1568) / max(w, h))
    return w * scale * h * scale / 750


def result_kind(call):
    inp = call.get("input") or {}
    path = str(inp.get("file_path") or inp.get("notebook_path") or "")
    ext = path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
    name = call.get("name", "")
    return ext or {"Bash": "shell", "Grep": "search", "Glob": "search", "Agent": "report",
                   "Task": "report", "WebFetch": "web", "WebSearch": "web"}.get(name, "result")


def writes_generated(cmd):
    """The generated file a Bash command writes, or None.

    The file must be the TARGET of a write: a shell redirect, tee or sed -i aimed at
    it, or python writing it directly or through a variable bound to its path. Merely
    naming it near a write operator is not enough; that rule flagged reads (`2>/dev/null`,
    awk `>` comparisons, `open(p).read()`) and heredocs that mention one file and write
    another, about 170 false alarms by 2026-10-28.
    ponytail: a path built from pieces (or a sed script holding `;`) is missed; add a case if one appears.
    """
    for g in GENERATED:
        f = re.escape(g) + r"(?![\w.])"
        tok = r"[^\s;|&<>'\"]*"  # rest of a path token
        q = r"[^'\"\n]*"           # inside a quoted string
        if (re.search(r"(?<![\d&<>=-])>>?\s*[\"']?" + tok + f, cmd)
                or re.search(r"\btee\s+(?:-a\s+)?[\"']?" + tok + f, cmd)
                # sed's target is the last word of its segment, never inside its script.
                or re.search(r"\bsed\s+-i[^\n;|&]*\s[\"']?" + tok + f + r"[\"']?\s*(?=[;|&\n]|$)", cmd)
                or re.search(r"\bopen\(\s*['\"]" + q + f + r"['\"]\s*,\s*['\"][wa]", cmd)
                or re.search(r"['\"]" + q + f + r"['\"]\s*\)\s*\.write_text\(", cmd)):
            return g
        for var in re.findall(r"\b(\w+)\s*=\s*(?:Path\()?\s*['\"]" + q + f + r"['\"]", cmd):
            v = re.escape(var)
            if re.search(rf"\b{v}\.write_text\(|\bopen\(\s*{v}\s*,\s*['\"][wa]|\b{v}\.open\(\s*['\"][wa]", cmd):
                return g
    return None


def hook_id(att):
    """Script basename in a hook's command, else its hookName (plugin hooks show a status text)."""
    for tok in str(att.get("command", "")).replace('"', " ").replace("'", " ").split():
        if tok.endswith((".sh", ".py", ".js", ".cmd")):
            return re.split(r"[/\\]", tok)[-1]
    # hookName often already starts with the event ("SessionStart:startup"): drop it, the kind adds it back.
    return str(att.get("hookName") or "?").removeprefix(f"{att.get('hookEvent')}:")


def scan(path):
    """Return (metrics_row_dict, [candidate tuples]) for one transcript."""
    m = dict.fromkeys(COLUMNS, 0)
    m["hooks"] = {}  # (event, hook) -> [runs, errors, duration_ms]
    m["session"] = path.stem
    sub = path.parent.name == "subagents"  # <project>/<session>/subagents/<agent>.jsonl
    m["project"] = (path.parents[2] if sub else path.parent).name
    m["agent"] = "subagent" if sub else "main"
    if sub:  # keyed under its parent; the type comes from the meta file beside it
        m["session"] = f"{path.parents[1].name}/{path.stem}"
        try:
            meta = json.loads(path.with_suffix(".meta.json").read_text(encoding="utf8"))
            m["agent"] = f"subagent:{meta.get('agentType') or '?'}"
        except (OSError, ValueError):
            pass
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
    usage, model_of = {}, {}
    calls = {}  # requestId -> set of activities its tool calls belong to
    arrivals, pending, tool_meta = {}, [], {}
    first_prompt = None  # only its first line is read, for a [hook:<name>] tag
    last_model = ""  # an image arrives before its request: priced at the model seen last

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

        if rec.get("entrypoint") == "sdk-cli" and not sub:
            m["agent"] = "headless"  # claude -p: benchmarks, app and hook calls
        msg = rec.get("message", {})
        if rec.get("type") == "assistant" and msg.get("model") != "<synthetic>":
            if msg.get("model"):
                models.add(msg["model"])
                last_model = msg["model"]
            # One API response is written as several records repeating its usage; the
            # last one is final (streaming partials grow output_tokens). Key by
            # requestId, last wins. A record without one counts on its own.
            rid = rec.get("requestId") or len(usage)
            if rid not in usage:
                # What arrived since the previous request is this request's new input.
                arrivals[rid], pending = pending, []
            usage[rid] = msg.get("usage") or {}
            model_of[rid] = msg.get("model") or model_of.get(rid, "")
            for block in msg.get("content") or []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    calls.setdefault(rid, set()).add(activity(block))
                    tool_meta[block.get("id")] = (activity(block), result_kind(block))
                    pending.append([("own", rid), len(json.dumps(block.get("input"))) / CHARS_PER_TOKEN, 0])
                elif block.get("type") == "text":
                    pending.append([("own", rid), len(block.get("text", "")) / CHARS_PER_TOKEN, 0])
        elif rec.get("type") == "attachment":
            att = rec.get("attachment")
            kind = att.get("type") if isinstance(att, dict) else None
            if str(kind).startswith("hook_") or kind == "async_hook_response":
                # Its text sits in content AND stdout; measure the text once, never the JSON.
                body = next((att[k] for k in ("content", "stdout", "response") if att.get(k)), "")
                pending.append([("hook", f"{att.get('hookEvent')}:{hook_id(att)}"),
                                (len(body) if isinstance(body, str) else len(json.dumps(body))) / CHARS_PER_TOKEN, 0])
                if att.get("hookEvent") != "Stop":  # Stop runs are counted from stop_hook_summary only
                    run = m["hooks"].setdefault((att.get("hookEvent"), hook_id(att)), [0, 0, 0])
                    run[0] += 1
                    run[1] += att.get("exitCode") not in (None, 0)
                    run[2] += att.get("durationMs") or 0
            else:
                pending.append([("harness", kind or "other"), len(json.dumps(att)) / CHARS_PER_TOKEN, 0])
        elif rec.get("subtype") == "stop_hook_summary":
            for info in rec.get("hookInfos") or []:
                m["hooks"].setdefault(("Stop", hook_id(info)), [0, 0, 0])[0] += 1
            m["hooks"].setdefault(("Stop", "*"), [0, 0, 0])[1] += len(rec.get("hookErrors") or [])
        elif rec.get("type") == "user":
            c = msg.get("content")
            # Length only: his text is never stored. Injected text (reminders, command
            # output, compaction summaries) is harness, not a prompt.
            src = ("harness", "compaction") if rec.get("isCompactSummary") else \
                  ("harness", "injected") if rec.get("isMeta") else ("prompt", "-")
            if first_prompt is None and src[0] == "prompt":
                first_prompt = (c if isinstance(c, str) else next(
                    (b.get("text", "") for b in c or [] if isinstance(b, dict) and b.get("type") == "text"), ""))
                first_prompt = first_prompt.lstrip().split("\n", 1)[0]
            for b in ([{"type": "text", "text": c}] if isinstance(c, str) else c or []):
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_result":
                    where = tool_meta.get(b.get("tool_use_id"), ("other", "result"))
                    body = b.get("content")
                    for i in (body if isinstance(body, list) else [{"type": "text", "text": str(body)}]):
                        if isinstance(i, dict) and i.get("type") == "image":
                            pending.append([(where[0], "image"), image_tokens(i, last_model), 1])
                        elif isinstance(i, dict):
                            pending.append([where, len(str(i.get("text", ""))) / CHARS_PER_TOKEN, 0])
                elif b.get("type") == "image":
                    pending.append([(src[0], "image"), image_tokens(b, last_model), 1])
                elif b.get("type") == "text":
                    t = b.get("text", "")
                    s_ = ("harness", "injected") if src[0] == "prompt" and t.lstrip().startswith("<") else src
                    pending.append([s_, len(t) / CHARS_PER_TOKEN, 0])

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
                    candidates.append(("permission_denied", f"{path.stem}:{tid}", excerpt(body)))
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
                hit = writes_generated(cmd)
                if hit:
                    m["generated_edits"] += 1
                    candidates.append((
                        "generated_file_edit", f"{path.stem}:{block.get('id', '?')}",
                        f"a Bash command wrote {hit}, which is generated and must never be "
                        f"hand-edited — cmd: {excerpt(cmd)}",
                    ))
            elif block.get("type") == "tool_use" and block.get("name") in ("Write", "Edit", "NotebookEdit"):
                fp = str(block.get("input", {}).get("file_path", ""))
                if fp.endswith(GENERATED):
                    m["generated_edits"] += 1
                    candidates.append((
                        "generated_file_edit", f"{path.stem}:{block.get('id', '?')}",
                        f"wrote {os.path.basename(fp)}, which is generated and must never be hand-edited",
                    ))

    m["assistant_msgs"] = len(usage)  # API requests, not records
    for u in usage.values():
        m["tokens_in"] += u.get("input_tokens", 0) or 0
        m["tokens_out"] += u.get("output_tokens", 0) or 0
        m["cache_read"] += u.get("cache_read_input_tokens", 0) or 0
        m["cache_create"] += u.get("cache_creation_input_tokens", 0) or 0
        m["thinking"] += (u.get("output_tokens_details") or {}).get("thinking_tokens", 0) or 0
    m["activity"], m["unpriced"] = {}, set()
    for rid, u in usage.items():
        kinds = calls.get(rid) or {"answering"}
        out = u.get("output_tokens", 0) or 0
        think = (u.get("output_tokens_details") or {}).get("thinking_tokens", 0) or 0
        usd = cost(model_of[rid], u)
        if usd is None:
            m["unpriced"].add(model_of[rid])
        for k in kinds:  # ponytail: even split; weight by block size if it misleads
            a = m["activity"].setdefault(k, {"requests": 0, "output": 0, "thinking": 0, "cost": 0})
            a["requests"] += 1 / len(kinds)
            a["output"] += out / len(kinds)
            a["thinking"] += think / len(kinds)
            a["cost"] += (usd or 0) / len(kinds)
    # New input per request: session start, cache rebuild, then what arrived, by size.
    m["inputs"], m["carry"] = {}, 0
    def book(key, tok, img=0):
        e = m["inputs"].setdefault(key, [0.0, 0])
        e[0] += tok; e[1] += img
    prev_ctx = None
    for rid, u in usage.items():
        cr = u.get("cache_read_input_tokens", 0) or 0
        new = (u.get("cache_creation_input_tokens", 0) or 0) + (u.get("input_tokens", 0) or 0)
        m["carry"] += cr
        rebuild = 0 if prev_ctx is None else min(new, max(0, prev_ctx - cr))
        if rebuild:
            book(("cache rebuild", "-"), rebuild)
        rest = new - rebuild
        parts = []
        for key, est, img in arrivals.get(rid, []):
            if key[0] == "own":  # a response's own text and tool inputs, re-sent next turn
                kinds = calls.get(key[1]) or {"answering"}
                parts += [((k, "own output"), est / len(kinds), 0) for k in kinds]
            else:
                parts.append((key, est, img))
        est_total = sum(p[1] for p in parts)
        # Visible parts are booked at their estimated size, scaled down when the bill
        # is smaller (large tool outputs are truncated before they are sent). What
        # the bill holds beyond them never reached the transcript: measured
        # 2026-10-28 at about 1-1.5k tokens per request (framing, reminders).
        scale = min(1, rest / est_total) if est_total else 0
        for key, est, img in parts:
            book(key, est * scale, img)
        if rest > est_total:
            book(("session start", "-") if prev_ctx is None else ("harness", "not in transcript"), rest - est_total)
        prev_ctx = cr + new
    m["models"] = ",".join(sorted(models)) or "-"
    tag = re.match(r"\[hook:([\w.-]+)\]", first_prompt or "")
    if tag and m["agent"] == "headless":
        m["agent"] = f"hook:{tag[1]}"
    # active_s sums only the gaps a human could plausibly be present for. duration_s
    # spans first to last timestamp and is inflated by sessions left open for days,
    # which made the first tokens/hour figure meaningless (measured: 776 wall hours
    # across 80 sessions, 9.7h each).
    # Records arrive in file order, which is NOT timestamp order: sidechain and
    # subagent messages interleave. Summing gaps in file order walks back and forth
    # over the same wall time and counts it twice — measured 2026-09-29, active_s
    # exceeded duration_s in 46 of 85 rows, by up to 1.7x. Sort once, then both
    # figures derive from the same ordered list.
    IDLE = 300
    from datetime import datetime
    fmt = "%Y-%m-%dT%H:%M:%S"
    times = []
    for ts in stamps:
        try:
            times.append(datetime.strptime(ts[:19], fmt))
        except ValueError:
            continue
    times.sort()
    m["active_s"] = 0
    for prev, cur in zip(times, times[1:]):
        gap = (cur - prev).total_seconds()
        # A negative gap is impossible after sorting, so it means the sort was lost.
        # Absorbing it silently is what let a removed sort cancel its own double-count.
        assert gap >= 0, "timestamps not sorted before measuring active time"
        if gap <= IDLE:
            m["active_s"] += int(gap)
    m["duration_s"] = 0
    if times:
        m["started"] = times[0].strftime(fmt)
        m["ended"] = times[-1].strftime(fmt)
        m["date"] = m["started"][:10]
        m["duration_s"] = max(0, int((times[-1] - times[0]).total_seconds()))
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

    def usage_msg(ts, model="m", tin=0, tout=0, cread=0, ccreate=0, think=0, rid=None):
        return {"type": "assistant", "timestamp": ts, "requestId": rid,
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

    # 1b. One response is written as several records repeating its usage; streaming
    #     partials differ only in output_tokens, and the last record is final. Count
    #     each requestId once, with the last record's usage. Summing every record
    #     over-counted 2.2x (failures-2026.md, 2026-10-27). <synthetic> records are
    #     not API calls.
    p = transcript("split.jsonl", [
        usage_msg("2026-01-01T10:00:00", tin=100, tout=10, cread=1000, ccreate=50, rid="r1"),
        usage_msg("2026-01-01T10:00:01", tin=100, tout=40, cread=1000, ccreate=50, rid="r1"),
        usage_msg("2026-01-01T10:00:02", tin=100, tout=90, cread=1000, ccreate=50, think=7, rid="r1"),
        usage_msg("2026-01-01T10:01:00", tin=5, tout=3, cread=1100, ccreate=0, rid="r2"),
        usage_msg("2026-01-01T10:01:01", model="<synthetic>"),
    ])
    m, _ = scan(p)
    got = (m["assistant_msgs"], m["tokens_in"], m["tokens_out"], m["cache_read"], m["cache_create"], m["thinking"])
    if got != (2, 105, 93, 2100, 50, 7):
        bad(f"split response not deduplicated by requestId (requests, in, out, cread, ccreate, think): {got}")
    ok("a response split over several records counts once, with its last usage")

    # 1c. Output and thinking go to what the request did, classified from all its
    #     tool calls (one content block per record, so a request's calls are spread
    #     over several records). Mixed kinds split evenly; no tool = answering; a
    #     write under .plans/ is planning, not coding.
    def req(ts, rid, tout, *calls, think=0):
        u = {"output_tokens": tout, "output_tokens_details": {"thinking_tokens": think}}
        recs = [{"type": "assistant", "timestamp": ts, "requestId": rid,
                 "message": {"model": "m", "usage": u, "content": [{"type": "text", "text": "x"}]}}]
        for i, (name, inp) in enumerate(calls):
            recs.append({"type": "assistant", "timestamp": ts, "requestId": rid,
                         "message": {"model": "m", "usage": u, "content": [
                             {"type": "tool_use", "id": f"{rid}-{i}", "name": name, "input": inp}]}})
        return recs
    p = transcript("activity.jsonl",
        req("2026-01-01T10:00:00", "a", 100, ("Edit", {"file_path": "/x/app.py"}), think=40)
        + req("2026-01-01T10:00:01", "b", 60, ("Read", {"file_path": "/x/a.py"}), ("Grep", {"pattern": "y"}))
        + req("2026-01-01T10:00:02", "c", 80, ("Read", {"file_path": "/x/a.py"}), ("Bash", {"command": "pytest"}))
        + req("2026-01-01T10:00:03", "d", 30)
        + req("2026-01-01T10:00:04", "e", 20, ("Write", {"file_path": "/w/.plans/x/PLAN.md"}))
        + req("2026-01-01T10:00:05", "f", 10, ("mcp__claude-in-chrome__computer", {}))
        + req("2026-01-01T10:00:06", "g", 12, ("Agent", {"prompt": "p"}), ("Skill", {"skill": "bacon:ouroboros"})))
    m, _ = scan(p)
    want = {"coding": (1, 100, 40), "reading": (1.5, 100, 0), "verifying": (0.5, 40, 0),
            "answering": (1, 30, 0), "planning": (1.5, 26, 0), "browser": (1, 10, 0),
            "delegating": (0.5, 6, 0)}
    got = {k: (v["requests"], v["output"], v["thinking"]) for k, v in m["activity"].items()}
    if got != want:
        bad(f"output by activity wrong: {got}")
    ok("output and thinking are booked to the activity of each request, mixed requests split evenly")

    # 1d. Auto mode routes most work through Bash (79% of output on a real session),
    #     so Bash is split by what the command does: write > verify > git > read.
    for cmd, want in [("cat a.py | grep x", "reading"),
                      ("sed -n 1,20p a.py", "reading"),
                      ("sed -i '' 's/a/b/' a.py", "coding"),
                      ("python3 - <<'EOF'\nopen(p,'w').write(s)\nEOF", "coding"),
                      ("cat > /w/.plans/x/PLAN.md <<'EOF'", "planning"),
                      ("python3 scripts/session-audit.py --selftest", "verifying"),
                      ("cd app && npm test 2>&1 | tail", "verifying"),
                      ("git diff --stat", "git"),
                      ("caffeinate -i node --import ./r.mjs scripts/x.ts a.db > /private/tmp/s/out.log", "running"),
                      ("cd app && python3 scripts/import.py --all 2>&1 | tail", "running"),
                      ("docker compose up -d", "running"),
                      ("cd ~/www/.plans && python3 - <<'EOF'\nopen(p,'w')", "planning"),
                      ("git add a && git commit -q -F - <<'EOF'\nrun --selftest\nEOF", "git"),
                      ("grep -n 'git clone\\|cp -R\\|rsync' sync.sh", "reading"),
                      ("grep -n ACTIVE scripts/session-todo.sh docs/x.md", "reading"),
                      ("sed 's#a#b#' x.sh > \"$TMP/x\" && bash \"$TMP/x\"", "reading"),
                      ("~/.nvm/versions/node/v22/bin/node --import ./r.mjs scripts/x.ts", "running"),
                      ("echo hi 2>/dev/null", "reading")]:
        got = activity({"name": "Bash", "input": {"command": cmd}})
        if got != want:
            bad(f"Bash {cmd!r} classified {got}, want {want}")
    for name, want in [("mcp__claude_ai_Indeed__search_jobs", "mcp:Indeed"),
                       ("mcp__claude_ai_Gmail__send_message", "mcp:Gmail"),
                       ("StructuredOutput", "answering"), ("ToolSearch", "harness"),
                       ("TaskUpdate", "harness"), ("AskUserQuestion", "harness")]:
        got = activity({"name": name, "input": {}})
        if got != want:
            bad(f"Bash {cmd!r} classified {got}, want {want}")
    ok("Bash commands are split into coding, planning, verifying, git and reading")

    # 1e. New input (cache write + uncached input) of each request is split: the first
    #     request is session start; a cache read below the previous context is a cache
    #     rebuild (expiry after an idle gap, compaction); the rest is shared by size
    #     between what arrived since the previous request: its own output, his prompt,
    #     tool results by source and file type (images by pixel count), harness text.
    import base64, struct
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\0\0\0\rIHDR" + struct.pack(">II", 1280, 900) + b"\0" * 20).decode()
    def u(rid, ts, cr, cw, tin=0, *blocks):
        return [{"type": "assistant", "timestamp": ts, "requestId": rid,
                 "message": {"model": "m", "content": [b], "usage": {
                     "input_tokens": tin, "output_tokens": 1, "cache_read_input_tokens": cr,
                     "cache_creation_input_tokens": cw}}} for b in blocks or [{"type": "text", "text": "ok"}]]
    def res(ts, tid, *content):
        return {"type": "user", "timestamp": ts, "message": {"content": [
            {"type": "tool_result", "tool_use_id": tid, "content": list(content)}]}}
    p = transcript("inputs.jsonl", [
        {"type": "user", "timestamp": "2026-01-01T10:00:00", "message": {"content": "p" * 400}}]
        + u("r1", "2026-01-01T10:00:01", 0, 20000, 5,
            {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "/x/a.py"}})
        + [res("2026-01-01T10:00:02", "t1", {"type": "text", "text": "c" * 4000})]
        + u("r2", "2026-01-01T10:00:03", 20005, 1100, 0,
            {"type": "tool_use", "id": "t2", "name": "mcp__claude-in-chrome__computer", "input": {}})
        + [res("2026-01-01T10:00:04", "t2", {"type": "image", "source": {
            "type": "base64", "media_type": "image/png", "data": png}})]
        + u("r3", "2026-01-01T10:00:05", 21105, 1600)
        + [{"type": "attachment", "timestamp": "2026-01-01T12:00:00", "attachment": {"x": "h" * 1200}}]
        + u("r4", "2026-01-01T12:00:06", 20000, 3000))
    m, _ = scan(p)
    got = {k: (round(v[0]), v[1]) for k, v in m["inputs"].items()}
    total_new = 20005 + 1100 + 1600 + 3000
    if round(sum(v[0] for v in m["inputs"].values())) != total_new:
        bad(f"input split does not add up to the new input {total_new}: {got}")
    # r1 is split like any request: his 400-char prompt (100) is booked as a prompt, the rest is session start.
    if got.get(("session start", "-")) != (19905, 0) or got.get(("prompt", "-")) != (100, 0):
        bad(f"first request should be prompt 100 + session start 19905: {got}")
    if got.get(("cache rebuild", "-")) != (2705, 0):
        bad(f"cache rebuild after the 2h gap should be (21105+1600) - 20000 = 2705: {got}")
    if not 285 <= got.get(("harness", "other"), (0,))[0] <= 295:
        bad(f"the rest of r4 (295, less r3's short reply) should go to the typeless attachment: {got}")
    # Billed beyond what the transcript shows (about 1-1.5k per real request: framing,
    # injected reminders) is its own line, not spread over the visible parts. Here:
    # r2 1100 - ~1007 visible, r3 1600 - ~1537.
    if not 140 <= got.get(("harness", "not in transcript"), (0,))[0] <= 170:
        bad(f"the excess over the visible parts should be booked as not in transcript: {got}")
    if ("reading", "py") not in got or got[("reading", "py")][0] < 800:
        bad(f"the .py read should take most of r2's new input: {got}")
    if got.get(("browser", "image"), (0, 0))[1] != 1 or got[("browser", "image")][0] < 1300:
        bad(f"the 1280x900 screenshot (~1536 tokens) should take most of r3's new input: {got}")
    # Opus 4.7 and later, Sonnet 5 and Fable take images up to 2576 px on the long edge;
    # older models scale to 1568. Measured 2026-10-29: three 1126x2000 photos billed
    # ~2.8-2.9k each on claude-opus-5-5 (w*h/750 = 3003; the 1568 cap gave 1846).
    tall = {"source": {"data": base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\0\0\0\rIHDR"
                                                 + struct.pack(">II", 1126, 2000) + b"\0" * 20).decode()}}
    if round(image_tokens(tall, "claude-opus-5-5")) != 3003 or round(image_tokens(tall, "claude-haiku-4-5")) != 1846:
        bad(f"image cap by model: opus-5-5 {image_tokens(tall, 'claude-opus-5-5'):.0f} (want 3003), "
            f"haiku-4-5 {image_tokens(tall, 'claude-haiku-4-5'):.0f} (want 1846)")
    if m["carry"] != 20005 + 21105 + 20000:
        bad(f"carry should be the sum of cache reads: {m['carry']}")
    ok("new input is split into session start, cache rebuild, and what arrived by source and file type")

    # 1e2. Attachments are named. A hook attachment carries its text twice (content and
    #      stdout) plus metadata, so it is measured by the text, once, under (hook,
    #      <event>:<script>); any other attachment is harness/<its type>.
    def booked(*atts):
        recs = [usage_msg("2026-01-01T10:00:00", tin=10, rid="r1")] + [
            {"type": "attachment", "timestamp": "2026-01-01T10:00:01", "attachment": a} for a in atts
        ] + [usage_msg("2026-01-01T10:00:02", cread=10, ccreate=5000, rid="r2")]
        mm, _ = scan(transcript("att.jsonl", recs))
        return {k: round(v[0]) for k, v in mm["inputs"].items()}, mm
    got, _ = booked({"type": "skill_listing", "content": "s" * 400})
    if not 100 <= got.get(("harness", "skill_listing"), 0) <= 200:
        bad(f"a skill_listing attachment should be booked under harness/skill_listing: {got}")
    got, _ = booked({"type": "hook_success", "hookEvent": "SessionStart", "hookName": "SessionStart:startup",
                     "command": "bash ~/ai-tools/hooks/claude-bootstrap.sh --x", "content": "x" * 400,
                     "stdout": "x" * 400, "stderr": "", "exitCode": 0, "durationMs": 5})
    if got.get(("hook", "SessionStart:claude-bootstrap.sh")) != 100:
        bad(f"a hook attachment should book its text once (100) under hook/SessionStart:claude-bootstrap.sh: {got}")
    got, _ = booked({"type": "hook_success", "hookEvent": "SessionStart", "hookName": "SessionStart:startup",
                     "command": "Loading ponytail mode...", "content": "x" * 40})
    if ("hook", "SessionStart:startup") not in got:
        bad(f"a plugin hook with a status-text command should be named by its hookName: {got}")
    got, _ = booked({"type": "hook_additional_context", "hookEvent": "UserPromptSubmit",
                     "hookName": "plan-mindset", "content": ["y" * 400]})
    if not 100 <= got.get(("hook", "UserPromptSubmit:plan-mindset"), 0) <= 110:
        bad(f"a list content should be measured in characters, not items: {got}")
    # The first request is split like any other: its arrivals at their estimate, the rest is session start.
    mm, _ = scan(transcript("first.jsonl", [
        {"type": "attachment", "timestamp": "2026-01-01T10:00:00", "attachment": {
            "type": "hook_success", "hookEvent": "SessionStart", "command": "bash /x/boot.sh", "content": "x" * 400}},
        usage_msg("2026-01-01T10:00:01", ccreate=5000, rid="r1")]))
    got = {k: round(v[0]) for k, v in mm["inputs"].items()}
    if got != {("hook", "SessionStart:boot.sh"): 100, ("session start", "-"): 4900}:
        bad(f"the first request should split its hook (100) from session start (4900): {got}")
    ok("attachments are named: hooks by event and script (text counted once), the rest by type")

    # 1f. Dollar cost per request from the dated price table: cache writes priced by
    #     their 5m/1h split, date-suffixed model ids match their family, Haiku 5.5 bills
    #     the long rate when the prompt is over 100k, and cost lands on the activity.
    def priced(rid, ts, model, tin, w5, w1, cr, tout, *calls):
        use = {"input_tokens": tin, "output_tokens": tout, "cache_read_input_tokens": cr,
               "cache_creation_input_tokens": w5 + w1,
               "cache_creation": {"ephemeral_5m_input_tokens": w5, "ephemeral_1h_input_tokens": w1}}
        return [{"type": "assistant", "timestamp": ts, "requestId": rid, "message": {
            "model": model, "usage": use, "content": [b]}}
            for b in [{"type": "text", "text": "x"}]
            + [{"type": "tool_use", "id": rid, "name": n, "input": i} for n, i in calls]]
    p = transcript("cost.jsonl",
        # 1000·4 + 2000·5 + 3000·8 + 10000·0.20 + 500·20 = $0.05
        priced("c1", "2026-01-01T10:00:00", "claude-opus-5-5", 1000, 2000, 3000, 10000, 500,
               ("Edit", {"file_path": "/x/a.py"}))
        # long rate: 150000·0.05 + 1000·2.50 = $0.01
        + priced("c2", "2026-01-01T10:00:01", "claude-haiku-5-5", 0, 0, 0, 150000, 1000)
        # 1000·1 + 1000·5 = $0.006
        + priced("c3", "2026-01-01T10:00:02", "claude-haiku-4-5-20251001", 1000, 0, 0, 0, 1000))
    m, _ = scan(p)
    got = {k: round(v.get("cost", 0), 6) for k, v in m["activity"].items()}
    if got != {"coding": 0.05, "answering": 0.016}:
        bad(f"cost by activity wrong, want coding 0.05, answering 0.016: {got}")
    m, _ = scan(transcript("unpriced.jsonl", [usage_msg("2026-01-01T10:00:00", model="claude-x-9", tout=5)]))
    if m["unpriced"] != {"claude-x-9"}:
        bad(f"a model missing from the price table must be reported, not priced at 0 silently: {m['unpriced']}")
    ok("cost per request follows the price table, the 5m/1h write split and the long-prompt rate")

    # 1g. A model call made by a hook runs headless with a fixed first prompt line
    #     `[hook:<name>]`; only that line is read. The same line in an interactive
    #     session is just text.
    hook_prompt = {"type": "user", "timestamp": "2026-01-01T10:00:00", "entrypoint": "sdk-cli",
                   "message": {"content": "[hook:summarize]\nthe rest is never read"}}
    reply = usage_msg("2026-01-01T10:00:01", tout=3); reply["entrypoint"] = "sdk-cli"
    m, _ = scan(transcript("hook.jsonl", [hook_prompt, reply]))
    if m["agent"] != "hook:summarize":
        bad(f"a headless run opened by [hook:summarize] should be agent hook:summarize: {m['agent']}")
    del hook_prompt["entrypoint"], reply["entrypoint"]
    m, _ = scan(transcript("nohook.jsonl", [hook_prompt, reply]))
    if m["agent"] != "main":
        bad(f"an interactive session is never a hook: {m['agent']}")
    ok("a headless run whose first prompt line is [hook:<name>] is booked to that hook")

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
                 command="python3 scripts/session-audit.py ctx >> application-log.md"),
    ])
    m, _ = scan(p)
    if m["generated_edits"] != 1:
        bad(f"unsanctioned Bash write not caught, or sanctioned one wrongly counted: {m}")
    ok("a Bash write to a generated file is caught; its own sanctioned generator is exempt")

    # 7b. Reads are not writes; the real writes seen in transcripts still are.
    reads = [
        "cut -f18 metrics/sessions.tsv 2>/dev/null | sort | uniq -c | head",
        "awk -F'\\t' '$8 > 100 {print $8}' $M/sessions.tsv | sort -n",
        "python3 - <<'EOF'\np='context/career/application-log.md'\nlines=open(p).read().split('\\n')\nprint(len(lines))\nEOF",
        "python3 - <<'EOF'\nf=Path('failures.md')\nf.write_text('read-only Bash on sessions.tsv')\nEOF",
        "grep -c x sessions.tsv > /tmp/count.txt",
    ]
    writes = [
        "echo done >> application-log.md",
        "sort sessions.tsv | tee -a ctx/sessions.tsv",
        "sed -i '' 's/a/b/' context/sessions.tsv",
        "python3 - <<'EOF'\np='context/career/application-log.md'\ns=open(p).read()\nopen(p,'w').write(s)\nEOF",
        "python3 - <<'EOF'\nfrom pathlib import Path\np=Path('ctx/sessions.tsv')\np.write_text('x')\nEOF",
        "python3 -c \"open('ctx/LEDGER.md','a').write('x')\"",
    ]
    reads.append("sed -i '' 's/every item\\./as `ACTIVE.md` lists it./' $f")
    wrong = [c for c in reads if writes_generated(c)] + [c for c in writes if not writes_generated(c)]
    if wrong:
        bad(f"generated-file write detector wrong on: {wrong}")
    ok("read-only commands on generated files are not flagged; real writes still are")

    # 7c. A fingerprint is read back right even when the excerpt before it holds a "{".
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        q = Path(d) / "c.md"
        q.write_text("- [ ] generated_file_edit | cmd: awk '{a… {sess-1:toolu_9}\n", encoding="utf8")
        if load_seen(q, SEEN_CAND) != {"sess-1:toolu_9"}:
            bad(f"fingerprint misread after a brace in the excerpt: {load_seen(q, SEEN_CAND)}")
    ok("a queued fingerprint is read back right after a brace in its excerpt")

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
    head = usage_msg("2026-01-01T11:00:00", model="claude-opus-5-5", tout=7); head["entrypoint"] = "sdk-cli"
    (proj_dir / "head1.jsonl").write_text(json.dumps(head) + "\n", encoding="utf8")
    hook = {"type": "user", "timestamp": "2026-01-01T11:30:00", "entrypoint": "sdk-cli",
            "message": {"content": "[hook:summarize]\nx"}}
    (proj_dir / "hook1.jsonl").write_text(json.dumps(hook) + "\n" + json.dumps(
        dict(head, timestamp="2026-01-01T11:30:01")) + "\n", encoding="utf8")
    (proj_dir / "sess1" / "subagents").mkdir(parents=True)
    (proj_dir / "sess1" / "subagents" / "sub1.jsonl").write_text(
        "\n".join(json.dumps(r) for r in [
            usage_msg("2026-01-01T10:00:02", tout=3),
            tool_use("2026-01-01T10:00:03", "id9", "Write", file_path="/repo/context/metrics/LEDGER.md"),
        ]) + "\n", encoding="utf8")
    (proj_dir / "sess1" / "subagents" / "sub1.meta.json").write_text(
        json.dumps({"agentType": "Explore", "toolUseId": "toolu_1"}), encoding="utf8")
    ctx_dir = t / "ctx"
    # A row written before step 4 under the bare file name must be replaced, not doubled.
    (ctx_dir / "context" / "metrics").mkdir(parents=True)
    (ctx_dir / "context" / "metrics" / "usage.tsv").write_text(
        "sub1\t2026-01-01\tproj1\tsubagent\tanswering\t1\t3\t0\n", encoding="utf8")
    # Its candidate was queued under the bare file name too; it must not come back.
    (ctx_dir / "context" / "metrics" / "candidates.md").write_text(
        "- [ ] generated_file_edit | old {sub1:id9}\n", encoding="utf8")
    try:
        PROJECTS = t / "projects"
        sys.argv = ["session-audit.py", str(ctx_dir), "--all"]
        main()
        tsv = ctx_dir / "context" / "metrics" / "sessions.tsv"
        cand = ctx_dir / "context" / "metrics" / "candidates.md"
        if not tsv.exists():
            bad("main() did not write sessions.tsv")
        rows = [l for l in tsv.read_text(encoding="utf8").splitlines() if l.startswith("sess1\t")]
        if len(rows) != 1:
            bad(f"expected exactly one row for the session: {rows}")
        if not cand.exists() or "generated_file_edit" not in cand.read_text(encoding="utf8"):
            bad("main() did not queue the generated-file-edit candidate")
        main()  # rerun over the same transcript
        rows2 = [l for l in tsv.read_text(encoding="utf8").splitlines() if l.startswith("sess1\t")]
        if len(rows2) != 1:
            bad(f"a second run duplicated the session row: {rows2}")
        if cand.read_text(encoding="utf8").count("generated_file_edit") != 2:
            bad("a second run re-queued a candidate already seen")
        if cand.read_text(encoding="utf8").count("id9") != 1:
            bad("a subagent candidate came back under a new fingerprint")
        usage_tsv = ctx_dir / "context" / "metrics" / "usage.tsv"
        urows = [l for l in usage_tsv.read_text(encoding="utf8").splitlines() if l and not l.startswith("#")] \
            if usage_tsv.exists() else []
        if sorted(urows) != ["head1\t2026-01-01\tproj1\theadless\tanswering\t1\t7\t0\t0.000140",
                             "hook1\t2026-01-01\tproj1\thook:summarize\tanswering\t1\t7\t0\t0.000140",
                             "sess1\t2026-01-01\tproj1\tmain\tanswering\t1\t5\t0\t0.000000",
                             "sess1\t2026-01-01\tproj1\tmain\tcoding\t1\t0\t0\t0.000000",
                             "sess1/sub1\t2026-01-01\tproj1\tsubagent:Explore\tanswering\t1\t3\t0\t0.000000",
                             "sess1/sub1\t2026-01-01\tproj1\tsubagent:Explore\tcoding\t1\t0\t0\t0.000000"]:
            bad(f"usage.tsv wrong or duplicated after a rerun: {urows}")
        inputs_tsv = ctx_dir / "context" / "metrics" / "inputs.tsv"
        irows = [l for l in inputs_tsv.read_text(encoding="utf8").splitlines() if l and not l.startswith("#")] \
            if inputs_tsv.exists() else []
        if irows != ["sess1\t2026-01-01\tproj1\tmain\tsession start\t-\t10\t0"]:
            bad(f"inputs.tsv wrong or duplicated after a rerun: {irows}")
        # A pruned transcript keeps its rows: the history is the point.
        (proj_dir / "sess1.jsonl").unlink()
        main()
        if len([l for l in usage_tsv.read_text(encoding="utf8").splitlines() if l.startswith("sess1\t")]) != 2:
            bad("rows of a pruned transcript were dropped from usage.tsv")
        if len([l for l in inputs_tsv.read_text(encoding="utf8").splitlines() if l.startswith("sess1\t")]) != 1:
            bad("rows of a pruned transcript were dropped from inputs.tsv")
        rep = usage_report(usage_tsv, days=0)
        if not any(l.split()[:2] == ["subagent:Explore", "2"] for l in rep):
            bad(f"usage report has no per-agent line: {rep}")
        if not any(l.startswith("== new input") for l in rep):
            bad(f"usage report has no input table: {rep}")
        if not any(l.split()[:2] == ["answering", "2"] and l.endswith("100%") for l in rep) \
                or not any("headless" in l for l in rep):
            bad(f"usage report wrong: {rep}")
        # Hooks sit with headless runs, never in the interactive table; cost is shown.
        if not any(l.startswith("== headless + hooks: 14 output tokens, $0.0003") for l in rep) \
                or not any(l.split()[:2] == ["hook:summarize", "1"] for l in rep):
            bad(f"usage report should group hooks with headless runs and show dollars: {rep}")
        ok("main() writes sessions.tsv and usage.tsv idempotently; a pruned transcript keeps its rows")
    finally:
        PROJECTS, sys.argv = orig_projects, orig_argv

    # 9b. hooks.tsv: runs, errors and duration per (session, event, hook). A hook attachment is
    #     one run (error = exitCode not 0); Stop runs come from stop_hook_summary alone, so the
    #     Stop attachment of the same hook is not a second run. Rewritten per session, and a
    #     session's legacy harness/attachment rows are replaced by the named ones.
    def att(ts, **a):
        return {"type": "attachment", "timestamp": ts, "attachment": a}
    hproj = t / "projects2" / "projH"
    hproj.mkdir(parents=True)
    (hproj / "hk1.jsonl").write_text("\n".join(json.dumps(r) for r in [
        usage_msg("2026-01-02T10:00:00", tin=10, rid="r1"),
        att("2026-01-02T10:00:01", type="hook_success", hookEvent="SessionStart", hookName="SessionStart:startup",
            command="bash /x/a.sh SECRET-CMD", content="SECRET-CONTENT", stdout="SECRET-CONTENT",
            stderr="", exitCode=0, durationMs=50),
        att("2026-01-02T10:00:02", type="hook_success", hookEvent="SessionStart", hookName="SessionStart:startup",
            command="bash /x/a.sh SECRET-CMD", content="", stdout="", stderr="SECRET-ERR", exitCode=1, durationMs=30),
        {"type": "system", "subtype": "stop_hook_summary", "timestamp": "2026-01-02T10:00:03", "hookCount": 2,
         "hookInfos": [{"command": "bash /x/s1.sh SECRET-CMD"}, {"command": "python3 /x/s2.py"}],
         "hookErrors": ["SECRET-ERR"], "hookAdditionalContext": []},
        att("2026-01-02T10:00:04", type="async_hook_response", hookEvent="Stop", hookName="Stop",
            command="bash /x/s1.sh", response={"k": "SECRET-CONTENT"}),
        usage_msg("2026-01-02T10:00:05", cread=10, ccreate=5000, rid="r2"),
    ]) + "\n", encoding="utf8")
    hctx = t / "ctx2"
    (hctx / "context" / "metrics").mkdir(parents=True)
    (hctx / "context" / "metrics" / "inputs.tsv").write_text(
        "hk1\t2026-01-02\tprojH\tmain\tharness\tattachment\t5\t0\n", encoding="utf8")
    try:
        PROJECTS = t / "projects2"
        sys.argv = ["session-audit.py", str(hctx), "--all"]
        hooks_tsv = hctx / "context" / "metrics" / "hooks.tsv"
        for _ in (1, 2):  # the rerun must not duplicate
            main()
            hrows = sorted(l for l in hooks_tsv.read_text(encoding="utf8").splitlines()
                           if l and not l.startswith("#")) if hooks_tsv.exists() else []
            want = [f"hk1\t2026-01-02\tprojH\tmain\t{e}\t{h}\t{r}\t{x}\t{d}" for e, h, r, x, d in [
                ("SessionStart", "a.sh", 2, 1, 80), ("Stop", "*", 0, 1, ""), ("Stop", "s1.sh", 1, 0, ""),
                ("Stop", "s2.py", 1, 0, "")]]
            if hrows != sorted(want):
                bad(f"hooks.tsv wrong or duplicated: {hrows}")
        irows = (hctx / "context" / "metrics" / "inputs.tsv").read_text(encoding="utf8")
        if "\tattachment\t" in irows:
            bad(f"the legacy harness/attachment row survived a rescan: {irows}")
        for f in (hctx / "context" / "metrics").glob("*.tsv"):
            if "SECRET" in f.read_text(encoding="utf8"):
                bad(f"a command string, content or stderr leaked into {f.name}")
        ok("hooks.tsv counts runs, errors and duration per hook; Stop once, from its summary; rerun is idempotent")
    finally:
        PROJECTS, sys.argv = orig_projects, orig_argv

    # 10. Records are not guaranteed to be in timestamp order — sidechain and
    #     subagent messages interleave. Measured 2026-09-29: active_s exceeded
    #     duration_s in 46 of 85 real rows, up to 1.7x, inflating tokens/active-hour.
    #
    #     This fixture is deliberately shaped: the first and last RECORDS are not the
    #     earliest and latest TIMES. The previous version used [10:00, 10:02, 10:01,
    #     10:03], whose ends happened to be the extremes, so started/ended passed
    #     without sorting — and asserting `active_s <= duration_s` asserted a theorem
    #     (after sorting it is true by construction), not a behaviour. Deleting
    #     times.sort() left all ten cases green. Pin the values, not the inequality.
    p = transcript("unordered.jsonl", [
        usage_msg("2026-01-01T10:02:00", tin=1),
        usage_msg("2026-01-01T10:00:00", tin=1),
        usage_msg("2026-01-01T10:03:00", tin=1),
        usage_msg("2026-01-01T10:01:00", tin=1),
    ])
    m, _ = scan(p)
    got = (m["started"], m["ended"], m["duration_s"], m["active_s"])
    if got != ("2026-01-01T10:00:00", "2026-01-01T10:03:00", 180, 180):
        bad(f"out-of-order records mis-measured: {got}, wanted the 10:00..10:03 span")
    else:
        ok("out-of-order records are sorted before measuring, not just bounded")

    # 11. The idle threshold must actually be exercised: a gap longer than IDLE is
    #     time he was away, and must not count as active.
    p = transcript("idle.jsonl", [
        usage_msg("2026-01-01T10:00:00", tin=1),
        usage_msg("2026-01-01T10:01:00", tin=1),
        usage_msg("2026-01-01T12:00:00", tin=1),   # 119 min gap, far over IDLE=300s
        usage_msg("2026-01-01T12:00:30", tin=1),
    ])
    m, _ = scan(p)
    if m["active_s"] != 90 or m["duration_s"] != 7230:
        bad(f"idle gap mishandled: active={m['active_s']} duration={m['duration_s']}, wanted 90/7230")
    else:
        ok("a gap longer than IDLE is not counted as active time")

    # 12. A row written at an older column set must be kept AND counted. This is the
    #     failure the whole schema question rests on: add a column, and every row
    #     whose transcript has been pruned stays short forever. 37 of 111 real rows
    #     were already in that state on 2026-10-05, and a reader doing
    #     zip(header, fields) drops their tail without a word.
    tsv = t / "ragged.tsv"
    full = "\t".join(["s-full"] + ["0"] * (len(COLUMNS) - 1))
    short = "\t".join(["s-short"] + ["0"] * (len(COLUMNS) - 4))
    tsv.write_text("# comment\n" + "\t".join(COLUMNS) + "\n" + full + "\n" + short + "\n")
    loaded, stale_n = load_rows(tsv)
    if stale_n != 1:
        bad(f"ragged row not counted: stale={stale_n}, wanted 1")
    if "s-short" not in loaded:
        bad("ragged row was dropped — history that cannot be re-derived must survive")
    if "s-full" not in loaded or COLUMNS[0] not in loaded:
        bad("load_rows lost a good row or the header")
    ok("a row at an older column set is kept and counted, not silently truncated")

    print("selftest passed")


def load_rows(tsv):
    """Load existing rows, and count the ones written at an older column set.

    A session is rewritten as it grows, so a row is replaced rather than appended —
    but a row whose transcript has been pruned can never be rewritten, and keeps the
    field count it was born with. Adding a column therefore makes the file ragged,
    and a reader doing zip(header, fields) truncates the short rows without a word.
    Measured 2026-10-05: 37 of 111 rows already have no surviving transcript, and the
    transcript directory lost 27 files in a single day. This counts them out loud
    rather than letting a renderer quietly drop a third of history.
    """
    rows, stale = {}, 0
    if not tsv.exists():
        return rows, stale
    for line in tsv.read_text(encoding="utf8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split("\t")
        if not parts or not parts[0]:
            continue
        if parts[0] == COLUMNS[0]:          # the header row
            rows[parts[0]] = line
            continue
        if len(parts) != len(COLUMNS):
            stale += 1
        rows[parts[0]] = line
    return rows, stale


def main():
    if "--selftest" in sys.argv:
        selftest()
        return 0

    # sys.argv[i] is the word before sys.argv[1:][i]: the number after --days is not a path.
    args = [a for i, a in enumerate(sys.argv[1:]) if not a.startswith("--") and sys.argv[i] != "--days"]
    ctx = Path(args[0]) if args else Path.home() / "www" / "context"
    days = 0 if "--all" in sys.argv else 2
    if "--days" in sys.argv:
        days = int(sys.argv[sys.argv.index("--days") + 1])
    to_stdout = "--stdout" in sys.argv
    if "--usage-report" in sys.argv:
        print("\n".join(usage_report(ctx / "context" / "metrics" / "usage.tsv",
                                     days if "--days" in sys.argv or "--all" in sys.argv else 7)))
        return 0

    if not PROJECTS.is_dir():
        print(f"session-audit: no transcripts at {PROJECTS}", file=sys.stderr)
        return 0

    outdir = ctx / "context" / "metrics"
    tsv = outdir / "sessions.tsv"
    cand = outdir / "candidates.md"

    rows, stale = load_rows(tsv)
    usage_tsv = outdir / "usage.tsv"
    # Keyed (session, activity). Rows of pruned transcripts are kept: history is the point.
    usage_rows = {tuple(l.split("\t")[:5:4]): l for l in
                  (usage_tsv.read_text(encoding="utf8").splitlines() if usage_tsv.exists() else [])
                  if l and not l.startswith("#")}
    inputs_tsv = outdir / "inputs.tsv"
    # Keyed (session, source, kind); same rule: rows of pruned transcripts are kept.
    input_rows = {(f[0], f[4], f[5]): l for l in
                  (inputs_tsv.read_text(encoding="utf8").splitlines() if inputs_tsv.exists() else [])
                  if l and not l.startswith("#") for f in [l.split("\t")]}
    hooks_tsv = outdir / "hooks.tsv"
    # Keyed (session, event, hook); same rule.
    hook_rows = {(f[0], f[4], f[5]): l for l in
                 (hooks_tsv.read_text(encoding="utf8").splitlines() if hooks_tsv.exists() else [])
                 if l and not l.startswith("#") for f in [l.split("\t")]}
    seen_cand = load_seen(cand, SEEN_CAND)

    cutoff = days * 86400
    now = max((p.stat().st_mtime for p in PROJECTS.rglob("*.jsonl")), default=0)
    new_cands, touched, unpriced = [], 0, set()
    for path in sorted(PROJECTS.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime):
        if days > 0 and now and (now - path.stat().st_mtime) > cutoff:
            continue
        m, cands = scan(path)
        if not m["assistant_msgs"]:
            continue
        rows.pop(path.stem, None)
        rows[m["session"]] = "\t".join(str(m[c]) for c in COLUMNS)
        for k in [k for k in usage_rows if k[0] in (m["session"], path.stem)]:
            del usage_rows[k]
        for act, a in m["activity"].items():
            usage_rows[(m["session"], act)] = "\t".join([
                m["session"], m["date"], m["project"], m["agent"], act, f"{round(a['requests'], 2):g}",
                str(round(a["output"])), str(round(a["thinking"])), f"{a['cost']:.6f}"])
        for k in [k for k in input_rows if k[0] in (m["session"], path.stem)]:
            del input_rows[k]
        for (src, kind), (tok, img) in m["inputs"].items():
            if round(tok) or img:
                input_rows[(m["session"], src, kind)] = "\t".join([
                    m["session"], m["date"], m["project"], m["agent"], src, kind, str(round(tok)), str(img)])
        for k in [k for k in hook_rows if k[0] in (m["session"], path.stem)]:
            del hook_rows[k]
        for (ev, hk), (runs, errs, ms) in m["hooks"].items():
            hook_rows[(m["session"], ev, hk)] = "\t".join([
                m["session"], m["date"], m["project"], m["agent"], ev, hk, str(runs), str(errs),
                "" if ev == "Stop" else str(ms)])  # a Stop summary carries no duration
        touched += 1
        unpriced |= m["unpriced"]
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
    usage_tsv.write_text(
        "# Output tokens and dollars by activity — derived, never authored\n"
        "# Written by session-audit.py. One row per (session, activity); a request whose tool calls\n"
        "# span several activities is split evenly between them, so requests can be fractional.\n"
        f"# cost_usd = the whole request (input, cache, output) at PRICES as of {PRICES_AS_OF}.\n"
        "# " + "\t".join(USAGE_COLUMNS) + "\n"
        + "".join(usage_rows[k] + "\n" for k in sorted(usage_rows)), encoding="utf8")
    inputs_tsv.write_text(
        "# New input tokens (cache write + uncached) by source — derived, never authored\n"
        "# Written by session-audit.py. source = activity whose tool result or own output was re-sent,\n"
        "# or session start / cache rebuild / prompt / harness. Visible parts are char/4 estimates\n"
        "# scaled to the bill; the remainder is harness/not in transcript. Carry (cache read) is in sessions.tsv.\n"
        "# harness/attachment is the legacy lump of sessions scanned before attachments were named (pre-split history).\n"
        "# " + "\t".join(INPUT_COLUMNS) + "\n"
        + "".join(input_rows[k] + "\n" for k in sorted(input_rows)), encoding="utf8")
    hooks_tsv.write_text(
        "# Hook runs, errors and time by session — derived, never authored\n"
        "# Written by session-audit.py. One row per (session, event, hook); hook = script basename or hookName,\n"
        "# never the command, output or stderr. Silent hooks leave no transcript record and are absent.\n"
        "# Stop: runs from stop_hook_summary only; hook * = the summary's hookErrors; duration empty.\n"
        "# " + "\t".join(HOOK_COLUMNS) + "\n"
        + "".join(hook_rows[k] + "\n" for k in sorted(hook_rows)), encoding="utf8")

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

    if unpriced - {""}:
        print(f"session-audit: no price for {', '.join(sorted(unpriced - {''}))} — booked at $0; "
              f"add it to PRICES", file=sys.stderr)
    if stale:
        print(f"session-audit: {stale} row(s) at an older column set — their transcripts are gone, "
              f"so they cannot be re-derived; a reader must not trend across them", file=sys.stderr)
    print(f"session-audit: {touched} session(s) measured, {len(new_cands)} candidate(s) queued")
    return 0


if __name__ == "__main__":
    sys.exit(main())
