#!/usr/bin/env bash
set -u
cd /root/skriptorij || exit 1
[ "$(git rev-parse --show-toplevel 2>/dev/null)" = "/root/skriptorij" ] || { echo "STOP: nije repo"; exit 1; }
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/diag_b1_b5_$TS.log"
{
echo "=== HEAD: $(git rev-parse --short HEAD) ==="
echo
echo "=== 1. core/tipografija.py (B1) ==="
if [ -f core/tipografija.py ]; then
    echo "OK: postoji ($(wc -l < core/tipografija.py) linija)"
    grep -n "^def \|^class " core/tipografija.py | head -10
else
    echo "FAIL: NE POSTOJI"
fi
echo
echo "=== 2. Importi iz core.tipografija ==="
for f in core/text_utils.py core/kalkovi/dijalog.py epub/styler.py epub/packager.py; do
    if [ -f "$f" ]; then
        n=$(grep -c "from core.tipografija import\|import core.tipografija" "$f" 2>/dev/null || echo 0)
        echo "$f: $n import(a)"
        grep -n "from core.tipografija import" "$f" 2>/dev/null | head -3 | sed 's/^/    /'
    else
        echo "$f: NE POSTOJI"
    fi
done
echo
echo "=== 3. Stari obrasci (koje B1-B5 treba da zamijeni) ==="
echo "-- _navodnici_u_tekstu --"
grep -n "_navodnici_u_tekstu" core/text_utils.py 2>/dev/null | head -5
echo "-- _post_process_tipografija --"
grep -n "_post_process_tipografija" core/text_utils.py 2>/dev/null | head -5
echo "-- DIJALOG_TIPOGRAFIJA --"
grep -rn "DIJALOG_TIPOGRAFIJA" core/kalkovi/dijalog.py 2>/dev/null | head -3
echo
echo "=== 4. pipeline.py trosi li tipografiju ==="
grep -n "from core.tipografija import\|_post_process_tipografija\|_navodnici_u_tekstu" processing/pipeline.py 2>/dev/null | head -10
echo
echo "=== 5. Git log ==="
git log --oneline -5
echo
echo "=== 6. py_compile ==="
find core processing epub -name "*.py" 2>/dev/null | xargs -I{} venv/bin/python3 -m py_compile {} 2>&1 | head -5
echo "(prazno = OK)"
echo
echo "=== KRAJ ==="
} 2>&1 | tee "$LOG"
bash tools/out.sh "$LOG"
echo "Log: $LOG"
