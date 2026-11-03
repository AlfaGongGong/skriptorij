#!/bin/bash
# TWOC: zasto 6.3 + retro prag + ucitava li server novi text_utils (samo citanje)
cd /root/skriptorij || exit 1
clear
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/twoc_scorer_provjera_$TS.log"
export CK="/storage/emulated/0/booklyfi_checkpoints/_skr_The_Wisdom_of_Crowds/checkpoints"
export MIN=25

{
echo "=== HEAD: $(git rev-parse --short HEAD) | text_utils mtime: $(stat -c %y core/text_utils.py | cut -c1-19) ==="

echo
echo "=== 1. Retro prag: gdje se bira 248 blokova ==="
grep -n "AUTO-RETRO\|lošeg\|losih\|QA retry\|_RETRO_\|prag" processing/retro.py core/engine.py run.py processing/pipeline.py 2>/dev/null | head -30

echo
echo "=== 2. QUALITY_SCORER_SYS (prompts.py 310-330) ==="
sed -n '310,330p' core/prompts.py

echo
echo "=== 3. _scoruj_kvalitetu i konstante u core/quality.py ==="
grep -n "_CACHE_ACCEPT_SCORE\|6\.3\|6\.25\|default\|fallback\|return [0-9]" core/quality.py | head -25
venv/bin/python3 << 'PYEOF'
import ast
src = open("core/quality.py", encoding="utf-8").read()
L = src.splitlines()
for n in ast.walk(ast.parse(src)):
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "_scoruj_kvalitetu":
        print(f"--- _scoruj_kvalitetu {n.lineno}-{n.end_lineno}")
        print("\n".join(L[n.lineno - 1:min(n.end_lineno, n.lineno + 150)]))
PYEOF

echo
echo "=== 4. Raspodjela ocjena i nova upisana .chk ==="
venv/bin/python3 << 'PYEOF'
import os, re, json, glob, time
from collections import Counter
CK = os.environ["CK"]
sc = json.load(open(CK + "/quality_scores.json", encoding="utf-8"))
vals = [round(float(v), 2) for v in sc.values() if isinstance(v, (int, float))]
print("najcesce ocjene:", Counter(vals).most_common(8))
start = time.time() - float(os.environ["MIN"]) * 60
nov = [p for p in glob.glob(CK + "/*.chk")
       if not p.endswith((".prevod.chk", ".lektura.chk")) and os.path.getmtime(p) > start]
tag = re.compile(r"<[^>]+>")
print(f"\n.chk upisanih u zadnjih {os.environ['MIN']} min: {len(nov)}")
for p in sorted(nov, key=os.path.getmtime)[:12]:
    t = tag.sub("", open(p, encoding="utf-8", errors="replace").read())
    b = os.path.basename(p)[:-4]
    print(f"  {b:<26} {time.strftime('%H:%M:%S', time.localtime(os.path.getmtime(p)))}"
          f"  ASCII\"={t.count(chr(34))} „={t.count('„')} ocjena={sc.get(b)}")
PYEOF
} 2>&1 | tee "$LOG"

bash tools/out.sh "$LOG"
