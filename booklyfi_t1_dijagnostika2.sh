#!/bin/bash
# T1 dijagnostika 2 — samo citanje, nista se ne mijenja
cd /root/skriptorij || exit 1
clear
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/t1_dijagnostika2_$TS.log"
KANON="/storage/emulated/0/Books/MoonReader/kanon/The_Wisdom_of_Crowds.json"

{
echo "=== A: PREVODILAC_TEMPLATE 15-72 ==="
sed -n '15,72p' core/prompts.py

echo
echo "=== B: get_prevodilac_prompt 367-406 ==="
sed -n '367,406p' core/prompts.py

echo
echo "=== C: rel_glosar u pipeline.py (svi hitovi) ==="
grep -n "rel_glosar\|extract_relevant_glossary\|build_glosar_tekst\|context_mgr\|glosar_za_prompt" processing/pipeline.py processing/workers.py

echo
echo "=== D: pipeline.py 1130-1152 ==="
sed -n '1130,1152p' processing/pipeline.py

echo
echo "=== E: pipeline.py 1395-1410 ==="
sed -n '1395,1410p' processing/pipeline.py

echo
echo "=== F: pipeline.py 505-520 ==="
sed -n '505,520p' processing/pipeline.py

echo
echo "=== G: build_glosar_tekst + extract_relevant_glossary 724-802 ==="
sed -n '724,802p' analysis/book_context.py

echo
echo "=== H: kanon direktoriji ==="
ls -la /root/skriptorij/data/kanon/knjige/ 2>&1 | head -20
ls -la /storage/emulated/0/Books/MoonReader/kanon/ 2>&1 | head -20

echo
echo "=== I: kanon statistika i Bayaz ==="
venv/bin/python3 << PYEOF
import json
from collections import Counter
d = json.load(open("$KANON", encoding="utf-8"))
t = d["termini"]
print("termina:", len(t))
print("kategorije:", dict(Counter(v.get("kategorija") for v in t.values())))
print("potvrdjeno:", dict(Counter(v.get("potvrdjeno") for v in t.values())))
razl = {k: v["hr"] for k, v in t.items() if v.get("hr") != k}
print("hr != EN kljuc:", len(razl), list(razl.items())[:15])
print("sa odbacenim varijantama:", sum(1 for v in t.values() if v.get("odbacene_varijante")))
print("sa spoji_sa:", [(k, v["spoji_sa"]) for k, v in t.items() if v.get("spoji_sa")][:10])
for ime in ("Bayaz", "Glokta", "Rikke", "Savine"):
    print(ime, "->", json.dumps(t.get(ime), ensure_ascii=False))
top = sorted(t.items(), key=lambda kv: -kv[1].get("broj_pojava", 0))[:10]
print("top10 po pojavama:", [(k, v["hr"], v["broj_pojava"]) for k, v in top])
PYEOF
} 2>&1 | tee "$LOG"

bash tools/out.sh "$LOG"
