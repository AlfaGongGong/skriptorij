#!/bin/bash
# TWOC: test hipoteze "scorer kaznjava dijalog u navodnicima" (samo citanje, bez API poziva)
cd /root/skriptorij || exit 1
clear
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/twoc_scorer_hipoteza_$TS.log"
export CK="/storage/emulated/0/booklyfi_checkpoints/_skr_The_Wisdom_of_Crowds/checkpoints"

{
echo "=== HEAD: $(git rev-parse --short HEAD) ==="

echo
echo "=== 1. Cijela rubrika QUALITY_SCORER_SYS ==="
venv/bin/python3 -c "
import sys; sys.path.insert(0,'.')
from core.prompts import QUALITY_SCORER_SYS
print(QUALITY_SCORER_SYS)"

echo
echo "=== 2. get_scorer_sys_override ==="
venv/bin/python3 - << 'PYEOF'
import ast
src = open("core/quality.py", encoding="utf-8").read()
L = src.splitlines()
for n in ast.walk(ast.parse(src)):
    if isinstance(n, ast.FunctionDef) and n.name == "get_scorer_sys_override":
        print("\n".join(L[n.lineno-1:min(n.end_lineno, n.lineno+60)]))
PYEOF

echo
echo "=== 3. run.py: prag AUTO-RETRO ==="
sed -n '76,104p' run.py

echo
echo "=== 4. Test hipoteze po grupama ocjena ==="
venv/bin/python3 - << 'PYEOF'
import os, re, sys, json, glob, statistics as st
sys.path.insert(0, ".")
from core.quality import _izracunaj_heuristicki_score as heur, _ekstrahuj_cist_tekst as cist
CK = os.environ["CK"]
sc = {k: float(v) for k, v in json.load(open(CK + "/quality_scores.json", encoding="utf-8")).items()
      if isinstance(v, (int, float))}
qa = json.load(open(CK + "/quality_accuracy.json", encoding="utf-8"))
sha = lambda t: re.sub(r"<!--\s*chunk_sha[^>]*-->\s*\n?", "", t)
tag = re.compile(r"<[^>]+>")
PROM = {"part0189.html_blok_2","part0192.html_blok_6","part0192.html_blok_8","part0235.html_blok_0","part0244.html_blok_0"}
rows = []
for k, s in sc.items():
    p = f"{CK}/{k}.chk"
    if not os.path.exists(p) or k in PROM or s <= 1.0: continue
    if qa.get(k, {}).get("accuracy_derived", 10) < 10: continue
    t = sha(open(p, encoding="utf-8", errors="replace").read())
    try:
        h = heur(t)[0]
        pocetak = cist(t)[:900]
    except Exception as e:
        continue
    nq = sum(pocetak.count(c) for c in ('„', '"', '“', '”'))
    dash = len(re.findall(r"<p[^>]*>\s*[\u2014\u2013]", t))
    rows.append((k, s, h, (s - 0.25*h) / 0.75, nq >= 2, dash >= 1))
print(f"blokova u analizi: {len(rows)}")
def grupa(naziv, f):
    r = [x for x in rows if f(x[1])]
    if not r: print(f"  {naziv}: nema"); return
    print(f"  {naziv:<10} n={len(r):<4} heur={st.mean(x[2] for x in r):.2f}  "
          f"izvedeni AI={st.mean(x[3] for x in r):.2f} (min {min(x[3] for x in r):.1f}, max {max(x[3] for x in r):.1f})  "
          f"dijalog u navodnicima(900zn)={sum(x[4] for x in r)/len(r):.0%}  crtice={sum(x[5] for x in r)/len(r):.0%}")
grupa("== 6.3", lambda s: abs(s-6.3) < .01)
grupa("6.7-7.3", lambda s: 6.6 < s < 7.4)
grupa("== 8.3", lambda s: abs(s-8.3) < .01)
grupa("== 9.8", lambda s: abs(s-9.8) < .01)
grupa("ostalo", lambda s: not any(abs(s-v) < .01 for v in (6.3, 8.3, 9.8)) and not 6.6 < s < 7.4)
dr = [x for x in rows if x[4]]
bn = [x for x in rows if not x[4]]
print(f"\n  svi blokovi s navodnicima u prvih 900 zn: n={len(dr)}, prosjek ocjene {st.mean(x[1] for x in dr):.2f}")
print(f"  svi blokovi BEZ navodnika u prvih 900 zn: n={len(bn)}, prosjek ocjene {st.mean(x[1] for x in bn):.2f}")
if len(dr) and len(bn):
    print(f"  udio 6.3 medju s navodnicima: {sum(abs(x[1]-6.3)<.01 for x in dr)/len(dr):.0%} | medju bez: {sum(abs(x[1]-6.3)<.01 for x in bn)/len(bn):.0%}")
PYEOF
} 2>&1 | tee "$LOG"

bash tools/out.sh "$LOG"
