#!/bin/bash
# TWOC: cijena resumea + neparni navodnici + TOC kod + (uz potvrdu) resume + finalna provjera
cd /root/skriptorij || exit 1
clear
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/twoc_resume_$TS.log"
export CK="/storage/emulated/0/booklyfi_checkpoints/_skr_The_Wisdom_of_Crowds/checkpoints"
export BOOK_FILE="The_Wisdom_of_Crowds.epub"

{
echo "=== HEAD: $(git rev-parse --short HEAD) ==="

echo
echo "=== 1. Cijena resumea: blokovi ispod 7.5 ==="
venv/bin/python3 << 'PYEOF'
import os, json
CK = os.environ["CK"]
sc = json.load(open(CK + "/quality_scores.json", encoding="utf-8"))
nizak = sorted((k, float(v)) for k, v in sc.items() if isinstance(v, (int, float)) and v < 7.5)
print(f"  blokova ispod 7.5: {len(nizak)} od {len(sc)}")
for k, v in nizak:
    print(f"    {k}: {v}")
PYEOF

echo
echo "=== 2. Neparni navodnici u .chk (odlomci) ==="
venv/bin/python3 << 'PYEOF'
import os, re, glob
CK = os.environ["CK"]
tag = re.compile(r"<[^>]+>")
ukupno, ex = 0, []
for p in sorted(glob.glob(CK + "/*.chk")):
    if p.endswith((".prevod.chk", ".lektura.chk")): continue
    t = open(p, encoding="utf-8", errors="replace").read()
    for para in re.findall(r"<p\b[^>]*>.*?</p>", t, re.S):
        x = tag.sub("", para)
        if x.count("\u201e") != x.count("\u201d"):
            ukupno += 1
            if len(ex) < 4:
                ex.append((os.path.basename(p), x.strip()[:70], x.strip()[-50:]))
print(f"  odlomaka sa nejednakim „ / ”: {ukupno}")
for e in ex:
    print(f"    {e[0]}: {e[1]!r} ... {e[2]!r}")
PYEOF

echo
echo "=== 3. TOC / nav kod ==="
grep -rn "_je_toc_fajl\|_je_nonprose_blok" --include=*.py processing core epub | head -12
echo "--- workers._je_toc_fajl"
sed -n '14,45p' processing/workers.py
echo "--- styler.py 1470-1530 (nav)"
sed -n '1470,1530p' epub/styler.py
echo "--- NEPREVEDENO u kodu"
grep -rn "NEPREVEDENO" --include=*.py processing core epub | head -10

echo
echo "=== 4. Resume ==="
read -r -t 60 -p "Pokrenuti resume (API pozivi za blokove ispod 7.5)? [d/N] " ODG </dev/tty
echo
if [ "$ODG" = "d" ] || [ "$ODG" = "D" ]; then
venv/bin/python3 << 'PYEOF'
import os, json, time, urllib.request
def api(path, data=None):
    req = urllib.request.Request("http://127.0.0.1:8080" + path,
          data=json.dumps(data).encode() if data else None,
          headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())
try:
    st = api("/api/status")
    if any(k in str(st.get("status", "")).lower() for k in ("run", "proc", "pokret", "obrad")):
        print("server vec radi:", st.get("status")); raise SystemExit(0)
    print("start:", api("/api/start", {"book": os.environ["BOOK_FILE"]}))
except SystemExit:
    raise
except Exception as e:
    print("API nedostupan:", repr(e)); raise SystemExit(0)
t0 = time.time(); zadnji = ""
while time.time() - t0 < 2400:
    time.sleep(20)
    try: st = api("/api/status")
    except Exception: continue
    s = f"{st.get('status')} {st.get('pct')}% {st.get('ok')}"
    if s != zadnji: print("  ", s); zadnji = s
    if "ZAVR" in str(st.get("status", "")).upper() and time.time() - t0 > 30: break
else:
    print("timeout 40 min — provjeri UI")
PYEOF
echo
echo "=== 5. Finalna provjera ==="
[ -f booklyfi_twoc_final_check.sh ] && bash booklyfi_twoc_final_check.sh 2>&1 | tail -60
else
  echo "Resume preskocen."
fi
} 2>&1 | tee "$LOG"

bash tools/out.sh "$LOG"
