#!/usr/bin/env bash
# booklyfi_rebuild_gate.sh
# Rebuild: SkriptorijAllInOne.generate_ncx() -> finalize() -> EpubStylerManager.stilizuj()
# Zatim tools/epub_gate.py nad STVARNO napravljenim STYLED EPUB-om.
REPO="/root/skriptorij"
cd "$REPO" 2>/dev/null || { echo "STOP: nema $REPO"; exit 1; }
[ "$(git rev-parse --show-toplevel 2>/dev/null)" = "$REPO" ] || { echo "STOP: nije repo"; exit 1; }

PY="venv/bin/python3"; [ -x "$PY" ] || PY="python3"
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/rebuild_gate_$TS.log"
PATHFILE=".logs/last_styled_$TS.path"
export BOOK="/storage/emulated/0/Download/The_Wisdom_of_Crowds.epub"
export STYLED_OLD="/storage/emulated/0/Books/MoonReader/STYLED/Joe_Abercrombie_The_Wisdom_of_Crowds_PREVEDENO_STYLED.epub"
export PATHFILE
clear

main() {
    echo "=== HEAD: $(git rev-parse --short HEAD) | $TS ==="
    [ -f "$BOOK" ] || { echo "FAIL: nema $BOOK"; return 1; }
    [ -f tools/epub_gate.py ] || { echo "FAIL: nema tools/epub_gate.py"; return 1; }

    echo
    echo "=== 1. Backup postojeceg STYLED EPUB-a ==="
    if [ -f "$STYLED_OLD" ]; then
        cp "$STYLED_OLD" "/storage/emulated/0/Download/styled_bak_$TS.epub" \
            && echo "Backup: styled_bak_$TS.epub" || { echo "FAIL: backup"; return 1; }
    else
        echo "Nema starog STYLED-a, preskacem."
    fi

    echo
    echo "=== 1.5. Primenjujem Overlay ispravke (ako postoje) ==="
    OVR_FILE="/storage/emulated/0/Download/BOOKLYFI_ISPRAVCI/The_Wisdom_of_Crowds.json"
    if [ -f "$OVR_FILE" ]; then
        "$PY" tools/apply_overlay.py "/storage/emulated/0/booklyfi_checkpoints/_skr_The_Wisdom_of_Crowds/checkpoints" "$OVR_FILE"
    fi

    echo
    echo "=== 2. Rebuild (SkriptorijAllInOne + styler) ==="
    "$PY" - << 'PYEOF'
import os, sys, traceback
from pathlib import Path
sys.path.insert(0, "/root/skriptorij")
try:
    from core.engine import SkriptorijAllInOne
    from epub.manager import EpubStylerManager
except ImportError as e:
    print(f"ImportError: {e}")
    sys.exit(1)

BOOK = os.environ["BOOK"]
PATHFILE = os.environ["PATHFILE"]
ss, sc = {}, {}
try:
    e = SkriptorijAllInOne(BOOK, "V10_TURBO", ss, sc)
    if not getattr(e, "html_files", None):
        e.html_files = sorted((Path(e.work_dir) / "text").glob("*.html"))
    print(f"HTML fajlova u work_dir: {len(e.html_files)}")

    e.generate_ncx()
    e.finalize()
    u = Path(ss.get("output_file", ""))
    if not u.is_file():
        print("STOP: finalize nije napravio EPUB.")
        sys.exit(1)
    print(f"Medjukorak: {u} ({u.stat().st_size} B)")

    r = EpubStylerManager(epub_path=u, log_callback=lambda m, a="info": None).stilizuj()
    print(f"Stilizacija ok={r.get('ok')}, poglavlja={r.get('chapters')}")
    s = Path(r.get("epub_path", ""))
    if not s.is_file():
        print("STOP: stilizacija nije napravila EPUB.")
        sys.exit(1)
    print(f"Finalni STYLED: {s} ({s.stat().st_size} B)")
    Path(PATHFILE).write_text(str(s), encoding="utf-8")
except Exception as ex:
    print(f"Rebuild greska: {ex}")
    traceback.print_exc()
    sys.exit(1)
PYEOF
    [ $? -eq 0 ] || { echo "PAO REBUILD"; return 1; }
    [ -s "$PATHFILE" ] || { echo "FAIL: nema putanje STYLED EPUB-a"; return 1; }
    FINAL=$(cat "$PATHFILE")

    echo
    echo "=== 3. Gate nad: $FINAL ==="
    "$PY" tools/epub_gate.py "$FINAL"
    GRC=$?

    echo
    echo "=== 4. Sazetak ==="
    case $GRC in
        0) echo "GATE PROSAO - nema FAIL gresaka." ;;
        1) echo "GATE PAO - provjeri FAIL stavke gore." ;;
        *) echo "GATE SE SRUSIO (kod $GRC) - pogledaj traceback gore." ;;
    esac
    return $GRC
}

main 2>&1 | tee "$LOG"
RC=${PIPESTATUS[0]}
[ -x tools/out.sh ] && bash tools/out.sh "$LOG"
echo "Log: $LOG"
exit $RC
