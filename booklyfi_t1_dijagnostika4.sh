#!/bin/bash
# T1 dijagnostika 4 — samo citanje (pise jedino u .logs/t1_ck)
cd /root/skriptorij || exit 1
clear
mkdir -p .logs .logs/t1_ck
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/t1_dijagnostika4_$TS.log"

{
echo "=== A1: core/engine.py 125-165 ==="
sed -n '125,165p' core/engine.py

echo
echo "=== A2: core/engine.py 635-650 ==="
sed -n '635,650p' core/engine.py

echo
echo "=== B: gdje se zadaje checkpoint_dir / clean_book_name ==="
grep -rn "checkpoint_dir *=\|clean_book_name *=" --include=*.py \
  core processing api main.py analysis 2>/dev/null | head -30

echo
echo "=== C: direktoriji checkpointa ==="
ls -d /storage/emulated/0/booklyfi_checkpoints/*/ 2>/dev/null | head -30

echo
echo "=== D: knjiga_id kad je checkpoint_dir = .../_skr_X/checkpoints ==="
venv/bin/python3 << 'PYEOF'
from pathlib import Path
from analysis.book_context import BookContextManager

for knjiga in ("The_Wisdom_of_Crowds", "TWOC_test_3pogl"):
    base = Path(".logs/t1_ck") / ("_skr_" + knjiga) / "checkpoints"
    base.mkdir(parents=True, exist_ok=True)
    m = BookContextManager(base)
    t = m.build_glosar_tekst()
    print(f"{base}")
    print(f"  checkpoint_dir.name   = {base.name!r}")
    print(f"  book_context.knjiga_id = {getattr(m.book_context, 'knjiga_id', 'NEMA')!r}")
    print(f"  glosar linija          = {len(t.splitlines()) if t else 0}")
PYEOF

echo
echo "=== E: gdje se ubacuje few-shot ==="
grep -rn "few_shot_.*\.json\|few_shot_prompt_blok\|FEW_SHOT" --include=*.py \
  core analysis processing 2>/dev/null | head -30

echo
echo "=== F: Bayaz vs Bajaz po few-shot fajlovima ==="
venv/bin/python3 << 'PYEOF'
import glob
for p in sorted(glob.glob("data/few_shot*.json")):
    s = open(p, encoding="utf-8").read()
    print(f"{p}: Bayaz={s.count('Bayaz')} Bajaz={s.count('Bajaz')}")
PYEOF

echo
echo "=== G: Bayaz/Bajaz u replacements i glosar_pravila ==="
grep -n "Bayaz\|Bajaz" data/replacements.json data/glosar_pravila.json | cut -c1-200 | head -20

echo
echo "=== H: Bayaz vs Bajaz u checkpointima (broj fajlova) ==="
for d in "/storage/emulated/0/booklyfi_checkpoints/_skr_TWOC_test_3pogl/checkpoints" \
         "/storage/emulated/0/booklyfi_checkpoints/_BAK_A15_20261101_130534/checkpoints"; do
  echo "$d"
  echo "  fajlova sa Bayaz: $(grep -rIl 'Bayaz' "$d" --include=*.chk 2>/dev/null | wc -l)"
  echo "  fajlova sa Bajaz: $(grep -rIl 'Bajaz' "$d" --include=*.chk 2>/dev/null | wc -l)"
done
} 2>&1 | tee "$LOG"

bash tools/out.sh "$LOG"
