#!/bin/bash
# T1 dijagnostika 3 — samo citanje (jedino se pravi prazan .logs/t1_ck)
cd /root/skriptorij || exit 1
clear
mkdir -p .logs .logs/t1_ck
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/t1_dijagnostika3_$TS.log"

{
echo "=== A: gdje je definisan _extract_relevant_glossary i kako se puni glosar ==="
grep -rn "_extract_relevant_glossary\|build_glosar_tekst\|BookContextManager\|context_mgr\b" \
  --include=*.py --exclude-dir=venv --exclude-dir=.git --exclude-dir=_FROZEN_TWOC . | head -40

echo
echo "=== B: knjiga_id u kodu ==="
grep -rn "knjiga_id" --include=*.py --exclude-dir=venv --exclude-dir=.git --exclude-dir=_FROZEN_TWOC . | head -40

echo
echo "=== C: BookContextManager.__init__ 682-723 ==="
sed -n '682,723p' analysis/book_context.py

echo
echo "=== D: ko mijenja Bayaz -> Bajaz (kod/podaci) ==="
grep -rIn "Bajaz" data core processing analysis --include=*.py --include=*.json --include=*.txt --include=*.replacement* 2>/dev/null | cut -c1-200 | head -20
ls data | head -30

echo
echo "=== E: Bajaz u izlazu checkpointa ==="
grep -rIlc "Bajaz" /storage/emulated/0/booklyfi_checkpoints 2>/dev/null | head -10

echo
echo "=== F: stvarni tok na kanonu (BookContextManager, bez LLM-a) ==="
venv/bin/python3 << 'PYEOF'
import json
from pathlib import Path
from analysis.book_context import BookContextManager

m = BookContextManager(Path(".logs/t1_ck"))
print("knjiga_id atribut poslije __init__:", getattr(m, "knjiga_id", "NEMA"))
print("book_context atribut:", getattr(m, "book_context", "NEMA"))

sample = ("Bayaz looked at Glokta. Rikke and Leopold crossed the Crown road; "
          "the Inspectorate and the Weaver waited. The Styrians were near.")

for kid in (None, "The_Wisdom_of_Crowds", "TWOC_test_3pogl"):
    if kid is None:
        if hasattr(m, "knjiga_id"):
            delattr(m, "knjiga_id")
    else:
        m.knjiga_id = kid
    t = m.build_glosar_tekst()
    rel = m.extract_relevant_glossary(sample, t)
    print(f"\n--- knjiga_id={kid!r}: glosar linija={len(t.splitlines()) if t else 0}")
    print("relevantno za uzorak:")
    print(rel if rel else "  (PRAZNO)")

d = json.load(open("/storage/emulated/0/Books/MoonReader/kanon/The_Wisdom_of_Crowds.json", encoding="utf-8"))["termini"]
print("\nviseriječni EN termini:", [k for k in d if " " in k][:15])
print("kratki (<=4) EN termini:", [k for k in d if len(k) <= 4][:20])
PYEOF
} 2>&1 | tee "$LOG"

bash tools/out.sh "$LOG"
