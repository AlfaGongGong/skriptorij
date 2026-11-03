#!/bin/bash
# TWOC: rubrika scorera prihvaca „…” + izvor heuristike i pragova (backup + test)
cd /root/skriptorij || exit 1
clear
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/twoc_rubrika_$TS.log"
BK=".logs/prompts_backup_$TS.py"

{
echo "=== HEAD: $(git rev-parse --short HEAD) ==="
cp core/prompts.py "$BK" || exit 1
echo "Backup: $BK"

echo
echo "=== 1. Izmjena rubrike ==="
venv/bin/python3 << 'PYEOF'
import sys
P = "core/prompts.py"
src = open(P, encoding="utf-8").read()
STARO = "  tipograf 9-10=em-crtice,dobra interpunkcija | 7-8=1-2 greske | 5-6=navodnici umj.crtice | 1-4=haos\n"
NOVO = ("  tipograf 9-10=ispravni navodnici „…” ili em-crtice za dijalog, dobra interpunkcija | "
        "7-8=1-2 greske | 5-6=ASCII navodnici \" ili pomijesani stilovi | 1-4=haos\n"
        "  (Dijalog u navodnicima „…” je ISPRAVAN i ne smije se kaznjavati.)\n")
n = src.count(STARO)
print("pojavljivanja STARO:", n)
if n != 1:
    print("STOP"); sys.exit(1)
open(P, "w", encoding="utf-8").write(src.replace(STARO, NOVO, 1))
print("upisano")
PYEOF
if [ $? -ne 0 ]; then cp "$BK" core/prompts.py; exit 1; fi

venv/bin/python3 -c "import ast; ast.parse(open('core/prompts.py',encoding='utf-8').read()); print('ast OK')" \
  && venv/bin/python3 -m py_compile core/prompts.py && echo "compile OK" \
  || { cp "$BK" core/prompts.py; echo "vraceno"; exit 1; }
venv/bin/python3 -c "
import sys; sys.path.insert(0,'.')
from core.prompts import QUALITY_SCORER_SYS as q
print('test:', 'ISPRAVAN' in q and 'umj.crtice' not in q)"

echo
echo "=== 2. Heuristika: izvor ==="
venv/bin/python3 << 'PYEOF'
import ast
src = open("core/quality.py", encoding="utf-8").read()
L = src.splitlines()
for n in ast.walk(ast.parse(src)):
    if isinstance(n, ast.FunctionDef) and n.name == "_izracunaj_heuristicki_score":
        print("\n".join(L[n.lineno-1:min(n.end_lineno, n.lineno+110)]))
PYEOF

echo
echo "=== 3. Pragovi i ucestalost kvara scorera ==="
grep -n "_QUALITY_RESCUE_THRESHOLD\s*=" core/quality.py
grep -rIh "AI ocjena nije dostupna\|scorer.*prazan\|SCORER.*nije" .logs /storage/emulated/0/Download/*.log 2>/dev/null | wc -l | sed 's/^/zapisa "scorer nedostupan" u logovima: /'
grep -n "def _odaberi_scorer_provider" -A 25 core/quality.py | head -40

echo
echo "Rollback: cp $BK core/prompts.py"
} 2>&1 | tee "$LOG"

bash tools/out.sh "$LOG"
