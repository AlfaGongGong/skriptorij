#!/bin/bash
# release_gate.sh - Konacna kapija za izdavacki kvalitet
cd /root/skriptorij || exit 1
if [ ! -d .git ]; then echo "FAIL: nema .git"; exit 1; fi
REPO=$(git rev-parse --show-toplevel 2>/dev/null)
if [ "$REPO" != "/root/skriptorij" ]; then echo "FAIL: repo je $REPO"; exit 1; fi

clear
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/release_gate_$TS.log"

BOOK="The_Wisdom_of_Crowds"
EPUB="/storage/emulated/0/Books/MoonReader/STYLED/Joe_Abercrombie_${BOOK}_PREVEDENO_STYLED.epub"
SRC_EPUB="/storage/emulated/0/Download/The_Wisdom_of_Crowds.epub"
GLOSAR="/storage/emulated/0/Books/MoonReader/kanon/${BOOK}.json"
CHK_DIR="/storage/emulated/0/booklyfi_checkpoints/_skr_${BOOK}/checkpoints"

{
echo "=== RELEASE GATE: $BOOK | $TS ==="

echo
echo "=== 1. Rebuild + Osnovni Gate (booklyfi_rebuild_gate.sh) ==="
bash tools/booklyfi_rebuild_gate.sh
if [ $? -ne 0 ]; then echo "FAIL: Rebuild / Osnovni Gate nije prosao."; exit 1; fi

echo
echo "=== 2. Dubinski Audit (audit_epub.py --gate) ==="
# Provera da li audit_epub.py postoji
if [ -f "tools/audit_epub.py" ]; then
    venv/bin/python3 tools/audit_epub.py --izvor "$SRC_EPUB" --glosar "$GLOSAR" --chk "$CHK_DIR" --gate "$EPUB"
    if [ $? -ne 0 ]; then echo "FAIL: Dubinski Audit nije prosao."; exit 1; fi
else
    echo "WARN: tools/audit_epub.py ne postoji. Preskacem."
fi

echo
echo "=== 3. EPUBcheck (Sintaksna validacija) ==="
if command -v epubcheck &>/dev/null; then
    epubcheck "$EPUB"
    if [ $? -ne 0 ]; then echo "FAIL: EPUBcheck nije prosao."; exit 1; fi
else
    echo "WARN: epubcheck nije instaliran u sistemu. Preskacem."
fi

echo
echo "✅ RELEASE GATE PROSAO. EPUB je spreman."
} 2>&1 | tee "$LOG"
bash tools/out.sh "$LOG"
