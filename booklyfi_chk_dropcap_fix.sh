#!/usr/bin/env bash
# booklyfi_chk_dropcap_fix.sh
#   Clover->Klover u drop-cap spanu na pocetku part0225 i part0238 (.chk), pa rebuild+gate+forbid
set -u
REPO="/root/skriptorij"
CK="/storage/emulated/0/booklyfi_checkpoints/_skr_The_Wisdom_of_Crowds/checkpoints"
BK="/storage/emulated/0/booklyfi_checkpoints/_backup"

# REPO GUARD (P18)
cd "$REPO" 2>/dev/null || { echo "STOP: nema $REPO"; exit 1; }
[ "$(git rev-parse --show-toplevel 2>/dev/null)" = "$REPO" ] || { echo "STOP: nije repo"; exit 1; }
[ -d "$CK" ] || { echo "STOP: nema $CK"; exit 1; }

PY="venv/bin/python3"; [ -x "$PY" ] || PY="python3"
mkdir -p .logs "$BK"
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/chk_dropcap_fix_$TS.log"
clear

main() {
    TAR="$BK/chk_pre_dropcap_fix_$TS.tar.gz"
    tar -czf "$TAR" -C "$CK" . || { echo "Backup NEUSPJEO, prekid."; return 1; }
    echo "Backup  : $TAR"
    echo "Rollback: tar -xzf $TAR -C $CK"

    CK="$CK" "$PY" - << 'EOF_PY'
import os, sys
from pathlib import Path
CK = Path(os.environ["CK"])
D = '<span class="dc1_drop_capital_">'
EDITS = [
    ("part0225.html_blok_0.chk", D + 'C</span>lover je sjedio', D + 'K</span>lover je sjedio'),
    ("part0238.html_blok_0.chk", D + 'C</span>lover duboko udahnu', D + 'K</span>lover duboko udahnu'),
]
plan = []
for fn, old, new in EDITS:
    p = CK / fn
    if not p.is_file():
        print(f"STOP: nema {fn}. Nista nije upisano."); sys.exit(2)
    raw = p.read_text("utf-8", "replace")
    if raw.count(old) == 1:
        plan.append((p, raw.replace(old, new, 1), old, new))
    elif raw.count(new) == 1:
        print(f"  {fn}: vec primijenjeno")
    else:
        print(f"STOP: {fn}: staro x{raw.count(old)} (treba 1). Nista nije upisano."); sys.exit(2)
for p, newraw, old, new in plan:
    print(f"\n--- {p.name}\n  STARO: ...{old[-60:]}\n  NOVO : ...{new[-60:]}")
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(newraw, encoding="utf-8")
    os.replace(tmp, p)
print(f"\nIzmijenjeno fajlova: {len(plan)} (ocekivano 2)")
EOF_PY
    RC=$?
    [ $RC -eq 0 ] || { echo "STOP (rc=$RC): rebuild se ne pokrece. Nista nije upisano."; return $RC; }

    echo
    echo "=== Rebuild + gate ==="
    bash tools/booklyfi_rebuild_gate.sh
    GRC=$?

    echo
    echo "=== Zabranjena imena u finalnom EPUB-u ==="
    P=$(ls -t .logs/last_styled_*.path 2>/dev/null | head -1)
    FINAL=$(cat "$P" 2>/dev/null)
    ls -l "$FINAL"
    "$PY" tools/epub_gate.py "$FINAL" --forbid Clover,Calder,Nail
    echo "forbid rc=$?"
    return $GRC
}

main 2>&1 | tee "$LOG"
RC=${PIPESTATUS[0]}
[ -x tools/out.sh ] && bash tools/out.sh "$LOG"
echo "Log: $LOG"
exit $RC
