#!/usr/bin/env bash
INPUT=$(cat)
echo "$INPUT" | grep -q '"stop_hook_active":\s*true' && exit 0
if [ -f "${CLAUDE_PROJECT_DIR}/harness/GATE_RED" ]; then
  REASON=$(head -c 400 "${CLAUDE_PROJECT_DIR}/harness/GATE_RED")
  python3 -c "import json,sys;print(json.dumps({'decision':'block','reason':'Harness red for current milestone: '+sys.argv[1]+' — continue with the next fix_plan.md item.'}))" "$REASON"
fi
exit 0
