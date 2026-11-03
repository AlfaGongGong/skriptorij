#!/bin/bash
# TWOC: zadnje citanje prije popravke (7 blokova + tipografija)
cd /root/skriptorij || exit 1
clear
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/twoc_pre_fix_$TS.log"
export CK="/storage/emulated/0/booklyfi_checkpoints/_skr_The_Wisdom_of_Crowds/checkpoints"

{
echo "=== HEAD: $(git rev-parse --short HEAD) ==="

venv/bin/python3 << 'PYEOF'
import os, re, glob, sys, importlib, inspect
sys.path.insert(0, ".")
CK = os.environ["CK"]
sha = lambda t: re.sub(r"<!--\s*chunk_sha[^>]*-->\s*\n?", "", t)
CUT = re.compile(r"<[^<>]*$")
LEAK = re.compile(r"\{\s*[„\"“”]?\s*korektura")

print("\n=== 1. Sedam blokova: rep, duzina, guard-provjere ===")
for p in sorted(glob.glob(CK + "/*.prevod.chk")):
    b = os.path.basename(p)[:-len(".prevod.chk")]
    raw = open(p, encoding="utf-8", errors="replace").read()
    t = sha(raw)
    otvoreni = len(re.findall(r"<p\b", t)); zatvoreni = len(re.findall(r"</p>", t))
    print(f"  {b}: {len(t)} zn | <p>={otvoreni} </p>={zatvoreni} | "
          f"odsjecen_tag={bool(CUT.search(t.rstrip()))} | leak={bool(LEAK.search(t))}")
    print(f"      rep: {t.rstrip()[-110:]!r}")
    print(f"      ima lektura.chk: {os.path.exists(p.replace('.prevod.chk', '.lektura.chk'))}")

print("\n=== 2. Funkcija _post_process_tipografija ===")
fn = None
for mod in ("core.text_utils", "processing.pipeline", "core.quality", "epub.styler"):
    try:
        m = importlib.import_module(mod)
    except Exception as e:
        print(f"  {mod}: import pao {e!r}"); continue
    if hasattr(m, "_post_process_tipografija"):
        fn = m._post_process_tipografija
        print(f"  nadjena u {mod}")
        print(inspect.getsource(fn)[:3800])
        break
if fn is None:
    print("  NIJE NADJENA kao modulska funkcija")

print("\n=== 3. Test na pravom uzorku (part0174 blok 1) ===")
if fn:
    t = sha(open(CK + "/part0174.html_blok_1.chk", encoding="utf-8").read())
    print(f"  prije: ASCII={t.count(chr(34))} „={t.count('„')} “={t.count('“')} ”={t.count('”')}")
    try:
        r = fn(t)
        if isinstance(r, tuple): r = r[0]
        print(f"  poslije: ASCII={r.count(chr(34))} „={r.count('„')} “={r.count('“')} ”={r.count('”')}")
        i = t.find('"')
        print(f"  uzorak prije : {t[max(0,i-30):i+80]!r}")
        j = r.find(chr(34)) if chr(34) in r else i
        print(f"  uzorak poslije: {r[max(0,j-30):j+80]!r}")
    except Exception as e:
        print("  poziv pao:", repr(e))
PYEOF

echo
echo "=== 4. Gdje se _post_process_tipografija poziva ==="
grep -rn "_post_process_tipografija" --include=*.py --exclude-dir=venv --exclude-dir=.git . | head -12

echo
echo "=== 5. Konstante velicine chunka ==="
grep -n "MAX_CHUNK\|CHUNK_SIZE\|chunk_size\|CHUNK_MAX\|max_chunk\|MAX_CHARS\|_MAX_BLOK\|def .*split.*chunk\|def .*podijeli" \
  processing/pipeline.py core/engine.py processing/workers.py config/*.py core/text_utils.py 2>/dev/null | head -25

echo
echo "=== 6. Zasto su blokovi pali (logovi) ==="
for b in part0235 part0244 part0170 part0189 part0192; do
  echo "--- $b"
  grep -rIh "$b" .logs /storage/emulated/0/Download/*.log 2>/dev/null | grep -i "blok\|odsjec\|guard\|fallback\|LEKTOR\|prazan\|odbij" | tail -4 | cut -c1-230
done

echo
echo "=== 7. /api/start i resume ==="
sed -n '251,330p' api/routes/processing.py

echo
echo "=== 8. Fallback commit c74125b ==="
git show --stat --format='%h %s' c74125b | head -8
git show c74125b -- processing/pipeline.py | head -60

echo
echo "=== 9. Kako engine odlucuje sta preskoci (cache accept) ==="
grep -n "_CACHE_ACCEPT_SCORE" processing/pipeline.py | head -5
} 2>&1 | tee "$LOG"

bash tools/out.sh "$LOG"
