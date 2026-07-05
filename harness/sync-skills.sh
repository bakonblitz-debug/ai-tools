#!/usr/bin/env bash
# ============================================================================
# SUPERSEDED (2026-07-04): this script was never applied to the live install.
# The route that actually shipped is per-skill symlinks under
# ~/.hermes/.hermes/skills/local/<name> -> /mnt/www/ai-tools/skills/<name>,
# confirmed working via `hermes skills list` (6 local skills recognized).
# Kept as a fallback design only. Also note: the live WSL user is `isaac`,
# not `zak` — the CONFIG default below was corrected accordingly.
# ============================================================================
# sync-skills.sh — register /mnt/www/ai-tools/skills with Hermes via the
# skills.external_dirs config key (Hermes 0.18.0+), NOT a symlink/copy loop.
#
# LOCATION CORRECTION (found during implementation, flagging explicitly):
#   The approved design placed this script at ~/.hermes/sync-skills.sh,
#   assuming that path was writable by his normal WSL account `zak`. Verified
#   during implementation that it is NOT: /home/zak/.hermes/ (the whole
#   tree, not just the nested .hermes/.hermes/) is owned by the `hermes`
#   service account, mode 755 — zak can traverse/read it but cannot write
#   into it at all (confirmed via a live `cp` attempt: Permission denied).
#   So this script lives here instead, in the one location that's actually
#   writable by zak AND version-controlled alongside the rest of the
#   harness: /mnt/www/ai-tools/harness/sync-skills.sh. He runs it via:
#     sudo -u hermes bash /mnt/www/ai-tools/harness/sync-skills.sh
#   No copy into ~/.hermes/ is needed or expected — the script only needs
#   read access to itself (this share is world-readable) and write access to
#   config.yaml (granted only when actually running as the hermes account).
#
# WHY external_dirs, not symlinks-per-skill:
#   The originally-planned mechanism (a per-skill symlink under
#   ~/.hermes/.hermes/skills/local/<name>) does not correspond to anything
#   Hermes 0.18.0 actually reads. Hermes' real mechanism is a config key,
#   skills.external_dirs, where each entry is a PARENT directory that gets
#   recursively walked for SKILL.md files at any depth — not required to
#   itself be a single skill folder. Pointing it at /mnt/www/ai-tools/skills
#   once covers every skill inside it, present and future, with zero re-sync
#   needed after adding/editing a skill. Local (bundled) skills win on name
#   collision; nothing here can shadow a Hermes-bundled skill.
#
# WHY THIS SCRIPT MUST BE RUN AS (OR VIA) THE `hermes` OS ACCOUNT:
#   ~/.hermes/.hermes/ is mode 0700, owned by the unprivileged `hermes`
#   service account (uid 999) — by design, not a bug (see hermes-harness-
#   2026-07-02.md's "never merge these two trust levels" rule). No
#   passwordless sudo exists or should be attempted for this (a safety
#   classifier has already rejected NOPASSWD:ALL for this exact machine
#   twice, even after he said yes — see claude-code-session-handoff-
#   2026-07-03.md). He runs this himself, interactively:
#     sudo -u hermes bash /mnt/www/ai-tools/harness/sync-skills.sh
#   and pastes the output back if an agent needs to confirm the result.
#
# IDEMPOTENT: safe to re-run. No-ops if the path is already registered.
# Preserves every existing comment/line in config.yaml — this patches the
# minimum number of lines rather than round-tripping the file through a full
# YAML parse+dump (which would silently delete every one of Hermes' own
# inline config comments).

set -euo pipefail

# Hardcoded to the known-good absolute path rather than $HOME/.hermes/.hermes/
# — sudo's HOME-preservation behavior varies by invocation (-H vs plain -u),
# so relying on $HOME here would be fragile. Override with HERMES_CONFIG=
# if the install ever moves.
CONFIG="${HERMES_CONFIG:-/home/isaac/.hermes/.hermes/config.yaml}"
SKILLS_DIR="/mnt/www/ai-tools/skills"

if [[ "$(whoami)" != "hermes" ]]; then
  echo "WARNING: running as '$(whoami)', not 'hermes'." >&2
  echo "config.yaml is owned by 'hermes' (mode 0700) — this will likely fail" >&2
  echo "to write. Re-run as: sudo -u hermes bash $0" >&2
fi

if [[ ! -f "$CONFIG" ]]; then
  echo "ERROR: $CONFIG not found. Set HERMES_CONFIG=<path> or check the install." >&2
  exit 1
fi

if [[ ! -d "$SKILLS_DIR" ]]; then
  echo "ERROR: $SKILLS_DIR not found — is /mnt/www mounted?" >&2
  exit 1
fi

python3 - "$CONFIG" "$SKILLS_DIR" <<'PYEOF'
import re, sys, shutil, datetime

config_path, target = sys.argv[1], sys.argv[2]

with open(config_path) as f:
    lines = f.readlines()

# --- Idempotency check: already active and pointing at our target? ---
for line in lines:
    stripped = line.strip()
    if stripped.startswith('-') and target in stripped and not line.lstrip().startswith('#'):
        print(f"OK: {target} already registered in {config_path} — no changes made.")
        sys.exit(0)

# --- Backup before any write ---
stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
backup_path = f"{config_path}.bak.{stamp}"
shutil.copy2(config_path, backup_path)
print(f"Backed up {config_path} -> {backup_path}")

# --- Find the skills: top-level key and an active external_dirs: under it ---
skills_idx = None
external_dirs_idx = None
for i, line in enumerate(lines):
    if re.match(r'^skills:\s*$', line):
        skills_idx = i
        continue
    if skills_idx is not None and external_dirs_idx is None:
        if re.match(r'^\s{1,4}external_dirs:\s*$', line) and not line.lstrip().startswith('#'):
            external_dirs_idx = i
            continue
        # A line back at column 0 (a new top-level key) means we've left the
        # skills: block without finding an active external_dirs:.
        if re.match(r'^\S', line):
            break

new_entry = f"    - {target}\n"

if skills_idx is None:
    print("No top-level 'skills:' key found — appending a new block at EOF.")
    if lines and not lines[-1].endswith("\n"):
        lines.append("\n")
    lines.append("\nskills:\n  external_dirs:\n" + new_entry)
elif external_dirs_idx is None:
    print("Found 'skills:' but no active 'external_dirs:' — inserting one.")
    lines.insert(skills_idx + 1, "  external_dirs:\n" + new_entry)
else:
    print("Found active 'external_dirs:' — appending new entry to it.")
    lines.insert(external_dirs_idx + 1, new_entry)

with open(config_path, "w") as f:
    f.writelines(lines)

print(f"Patched {config_path}: registered {target} under skills.external_dirs")

# --- Best-effort validation: confirm the result still parses as YAML ---
try:
    import yaml  # may not be installed; best-effort only
    with open(config_path) as f:
        yaml.safe_load(f)
    print("Validated: config.yaml still parses as valid YAML.")
except ImportError:
    print("NOTE: PyYAML not available in this interpreter — skipped YAML validation.")
    print(f"Manually confirm with: python3 -c \"import yaml; yaml.safe_load(open('{config_path}'))\"")
except Exception as e:
    print(f"WARNING: config.yaml may no longer be valid YAML: {e}", file=sys.stderr)
    print(f"Restore the backup if needed: cp {backup_path} {config_path}", file=sys.stderr)
    sys.exit(1)
PYEOF

echo ""
echo "Done. No restart is required — Hermes' skills.external_dirs is read live"
echo "(re-scanned on next skill lookup, no caching). If a dashboard service is"
echo "running, restarting it is still good hygiene: sudo systemctl restart hermes-dashboard.service"
