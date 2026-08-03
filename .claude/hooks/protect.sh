#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 blender-web contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Deny writes to protected paths. harness/+oracle/ lock activates once .claude/harness.lock exists
# (they must first be BUILT during M0). upstream/ and tests/golden/ are always protected.
INPUT=$(cat)
python3 - "$INPUT" <<'PY'
import json, os, re, sys
try: d = json.loads(sys.argv[1])
except Exception: sys.exit(0)
p = (d.get("tool_input") or {}).get("file_path") or ""
root = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
rel = os.path.relpath(p, root) if p.startswith("/") else p
always = r"^(upstream/|tests/golden/)"
locked = r"^(harness/|oracle/)"
deny = bool(re.match(always, rel)) or (os.path.exists(os.path.join(root, ".claude/harness.lock")) and bool(re.match(locked, rel)))
if deny:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
      "permissionDecisionReason": f"{rel} is protected. Port changes go in patches/ or owned dirs; harness disputes go in notes/harness-issues.md."}}))
PY
exit 0
