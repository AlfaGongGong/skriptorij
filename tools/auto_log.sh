#!/usr/bin/env bash
set -u
cd /root/skriptorij || exit 1
[ "$(git rev-parse --show-toplevel 2>/dev/null)" = "/root/skriptorij" ] || { echo "STOP: nije repo"; exit 1; }
TASK="${1:-.}"; ACTION="${2:-.}"; EXPECTED="${3:-.}"; RESULT="${4:-.}"
TS=$(date +%Y%m%d_%H%M%S); HTS=$(date +"%Y-%m-%d %H:%M"); HEAD=$(git rev-parse --short HEAD)
LF="/storage/emulated/0/Download/BOOKLYFI_AI_LOG.md"
HF="/storage/emulated/0/Download/BOOKLYFI_DEEPSEEK_HANDOFF.md"
[ -f "$LF" ] && cat >> "$LF" << L

## [$HTS] [DeepSeek/Auto] — \`$HEAD\`
**Task:** $TASK
**Action:** $ACTION
**Expected:** $EXPECTED
**Result:** $RESULT
L
[ -f "$HF" ] && cat >> "$HF" << H

---

## [Auto-update $HTS] — \`$HEAD\`
- **Task:** $TASK
- **Action:** $ACTION
- **Expected:** $EXPECTED
- **Result:** $RESULT
H
echo "OK: log+handoff upisani"
