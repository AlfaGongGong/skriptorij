#!/bin/bash
# T1 dijagnostika D0-D5 — samo citanje, nista se ne mijenja
cd /root/skriptorij || exit 1
clear
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/t1_dijagnostika_$TS.log"
KANON="/storage/emulated/0/Books/MoonReader/kanon/The_Wisdom_of_Crowds.json"

{
echo "=== D0: HEAD, status, zadnji commiti ==="
git log --oneline -5
git status --short --untracked-files=no

echo
echo "=== D1: kanon fajl i struktura ==="
ls -la "$KANON"
venv/bin/python3 << PYEOF
import json
d = json.load(open("$KANON", encoding="utf-8"))
print("tip:", type(d).__name__)
if isinstance(d, dict):
    print("kljucevi (prvih 10):", list(d.keys())[:10])
    print("broj kljuceva:", len(d))
    for k, v in list(d.items())[:5]:
        s = json.dumps(v, ensure_ascii=False)
        print(f"  {k}: {s[:300]}")
else:
    print("duzina:", len(d))
    for e in d[:5]:
        print(" ", json.dumps(e, ensure_ascii=False)[:300])
PYEOF

echo
echo "=== D2: kako se kanon/glosar koristi ==="
grep -n "kanon\|glosar\|_extract_relevant_glossary\|glosar_injekcija" \
  analysis/book_context.py core/prompts.py processing/pipeline.py | head -60

echo
echo "=== D3: PREVODILAC prompt - gdje je ==="
grep -n "PREVODILAC\|_get_prevodilac_prompt\|_build_prevodilac\|def .*prevodilac" \
  core/prompts.py processing/pipeline.py analysis/book_context.py

echo
echo "=== D3b: definicije funkcija u core/prompts.py ==="
grep -n "^def \|^async def \|^[A-Z_]* = " core/prompts.py | head -80

echo
echo "=== D4: gdje se popunjava glosar u pipeline.py ==="
grep -n "glosar_injekcija\|glosar_tekst\|glosar_blok\|book_context\|BookContext" \
  processing/pipeline.py | head -40

echo
echo "=== D4b: definicije u analysis/book_context.py ==="
grep -n "^def \|^async def \|^class \|    def " analysis/book_context.py | head -60

echo
echo "=== D5: da li kanon imena stvarno postoje u TWOC kanonu (5 unosa vec iznad u D1) ==="
echo "(vidi D1)"
} 2>&1 | tee "$LOG"

bash tools/out.sh "$LOG"
