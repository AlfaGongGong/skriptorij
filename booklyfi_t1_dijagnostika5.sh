#!/bin/bash
# T1 dijagnostika 5 — samo citanje
cd /root/skriptorij || exit 1
clear
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/t1_dijagnostika5_$TS.log"

{
echo "=== A: engine._ucitaj_kanon_glosar i _auto_generiraj_kanon ==="
venv/bin/python3 << 'PYEOF'
import ast
src = open("core/engine.py", encoding="utf-8").read()
lines = src.splitlines()
for n in ast.walk(ast.parse(src)):
    if isinstance(n, ast.FunctionDef) and n.name in ("_ucitaj_kanon_glosar", "_auto_generiraj_kanon"):
        print(f"--- {n.name} {n.lineno}-{n.end_lineno}")
        print("\n".join(lines[n.lineno-1:n.end_lineno]))
PYEOF

echo
echo "=== B: book_context.py 527-585 (few-shot) ==="
sed -n '527,585p' analysis/book_context.py

echo
echo "=== C: core/few_shot_global.py ==="
cat core/few_shot_global.py

echo
echo "=== D: pipeline.py 1330-1350 i 1605-1620 ==="
sed -n '1330,1350p' processing/pipeline.py
echo ...
sed -n '1605,1620p' processing/pipeline.py

echo
echo "=== E: Bajaz/Bayaz u book_context_cache.json po checkpointima ==="
for d in /storage/emulated/0/booklyfi_checkpoints/_skr_*/checkpoints /storage/emulated/0/booklyfi_checkpoints/_BAK_*/checkpoints; do
  f="$d/book_context_cache.json"
  [ -f "$f" ] && echo "$(basename $(dirname $d)): Bayaz=$(grep -o 'Bayaz' "$f" | wc -l) Bajaz=$(grep -o 'Bajaz' "$f" | wc -l)  $(stat -c %y "$f" | cut -c1-16)"
done

echo
echo "=== F: struktura few_shot_abercombie.json i Bajaz parovi ==="
venv/bin/python3 << 'PYEOF'
import json
d = json.load(open("data/few_shot_abercombie.json", encoding="utf-8"))
print("tip:", type(d).__name__, list(d.keys())[:5] if isinstance(d, dict) else len(d))
p = d["parovi"] if isinstance(d, dict) and "parovi" in d else d
print("parova:", len(p))
print("kljucevi prvog:", list(p[0].keys()))
bad = [x for x in p if "Bajaz" in json.dumps(x, ensure_ascii=False)]
print("parova sa Bajaz:", len(bad))
for x in bad[:2]:
    print(" ", json.dumps(x, ensure_ascii=False)[:250])
PYEOF
} 2>&1 | tee "$LOG"

bash tools/out.sh "$LOG"
