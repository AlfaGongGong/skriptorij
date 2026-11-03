#!/bin/bash
# TWOC: jedan prolaz — 7 neprevedenih, Adua, ASCII navodnici, preskoceni dijelovi, retry mehanizam
cd /root/skriptorij || exit 1
clear
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/twoc_rest_$TS.log"
export CK="/storage/emulated/0/booklyfi_checkpoints/_skr_The_Wisdom_of_Crowds/checkpoints"
export EPUB_DIR="/storage/emulated/0/Books/MoonReader/STYLED"
export SRC_EPUB="/storage/emulated/0/Download/The_Wisdom_of_Crowds.epub"

{
echo "=== HEAD: $(git rev-parse --short HEAD) | T1 fajlovi ==="
git status --short --untracked-files=no
git log --oneline -6

venv/bin/python3 << 'PYEOF'
import os, re, glob, json, zipfile
from collections import Counter

CK, ED, SRC = os.environ["CK"], os.environ["EPUB_DIR"], os.environ["SRC_EPUB"]
sha = lambda t: re.sub(r"<!--\s*chunk_sha[^>]*-->\s*\n?", "", t)
plain = lambda t: re.sub(r"<[^>]+>", " ", t)
ep = sorted(glob.glob(ED + "/*Wisdom*PREVEDENO_STYLED.epub"), key=os.path.getmtime)[-1]
z = zipfile.ZipFile(ep)
htm = {os.path.basename(n): z.read(n).decode("utf-8", "replace")
       for n in z.namelist() if n.lower().endswith((".xhtml", ".html", ".htm"))}

print("\n=== 1. Neprevedeni blokovi (.prevod.chk bez finalnog) ===")
pv = sorted(os.path.basename(p)[:-len(".prevod.chk")] for p in glob.glob(CK + "/*.prevod.chk"))
fin = {os.path.basename(p)[:-4] for p in glob.glob(CK + "/*.chk") if not p.endswith((".prevod.chk", ".lektura.chk"))}
nema = [b for b in pv if b not in fin]
print("  blokovi:", nema)
sc = json.load(open(CK + "/quality_scores.json"))
print("  ocjene:", {b: sc.get(b) for b in nema})
for b in nema[:3]:
    t = sha(open(f"{CK}/{b}.prevod.chk", encoding="utf-8", errors="replace").read())
    print(f"  --- {b}.prevod.chk ({len(t)} zn): {plain(t).strip()[:160]!r}")

print("\n=== 2. NEPREVEDENO u EPUB-u ===")
for n, t in htm.items():
    for m in re.finditer("NEPREVEDENO", t):
        print(f"  {n}: ...{plain(t[max(0,m.start()-60):m.end()+80]).strip()[:140]!r}")
        break

print("\n=== 3. Adua: oblici u HR vs EN ===")
hr = " ".join(plain(sha(open(p, encoding="utf-8", errors="replace").read()))
              for p in glob.glob(CK + "/*.chk") if not p.endswith((".prevod.chk", ".lektura.chk")))
print("  HR oblici Adu*:", Counter(re.findall(r"(?<!\w)Adu\w*", hr)).most_common(8))
print("  HR Ad* (nepoznata transliteracija):", Counter(re.findall(r"(?<!\w)Ad[uv]\w*", hr)).most_common(6))

print("\n=== 4. ASCII navodnici ===")
nh = sum(1 for t in htm.values() if '"' in plain(t).replace("&quot;", ""))
print(f"  EPUB dijelova sa ASCII \" u tekstu: {nh}/{len(htm)}")
tot = Counter()
for t in htm.values():
    p = plain(t)
    tot["ascii"] += p.count('"'); tot["„"] += p.count("„"); tot["“"] += p.count("“"); tot["”"] += p.count("”")
print("  ukupno znakova u EPUB-u:", dict(tot))
for b in ("part0174.html_blok_1",):
    t = plain(sha(open(f"{CK}/{b}.chk", encoding="utf-8").read()))
    i = t.find('"')
    print(f"  chk {b}: ...{t[max(0,i-50):i+70].strip()!r}")
p = plain(htm.get("part0174.html", ""))
i = p.find('"')
print(f"  EPUB part0174: ASCII poz {i}; primjer: {p[max(0,i-50):i+70].strip()!r}" if i >= 0
      else "  EPUB part0174: nema ASCII navodnika (stilizator ih mijenja)")

print("\n=== 5. Izvornik bez checkpointa i dijelovi koji fale u EPUB-u ===")
zs = zipfile.ZipFile(SRC)
src = {os.path.basename(n): plain(zs.read(n).decode("utf-8", "replace"))
       for n in zs.namelist() if n.lower().endswith((".xhtml", ".html", ".htm"))}
for n in ("part0170.html", "part0246.html"):
    print(f"  {n}: {len(src.get(n,'').split())} rijeci | u EPUB-u: {n in htm} | pocetak: {' '.join(src.get(n,'').split())[:140]!r}")
fale = sorted(set(src) - set(htm))
print(f"  dijelovi izvornika koji fale u EPUB-u ({len(fale)}):")
for n in fale:
    print(f"    {n}: {len(src[n].split())} rijeci: {' '.join(src[n].split())[:80]!r}")

print("\n=== 6. Accuracy: blokovi s kodovima ===")
qa = json.load(open(CK + "/quality_accuracy.json"))
for k, v in qa.items():
    if v.get("kodovi"):
        print(f"  {k}: kodovi={v['kodovi']} derived={v.get('accuracy_derived')} ocjena={sc.get(k)}")
try:
    print("  human_review:", json.dumps(json.load(open(CK + "/human_review.json")), ensure_ascii=False)[:300])
except Exception: pass
PYEOF

echo
echo "=== 7. Mehanizam za ponovni prevod ciljanih blokova ==="
grep -n "def .*retro\|def .*retry\|def .*ciljan\|def .*ponovo\|def .*resume" processing/retro.py processing/pipeline.py core/engine.py | head -20
grep -n "route(.*\(retro\|retry\|resume\|restart\|ponov\|start\)" api/routes/*.py | head -15
} 2>&1 | tee "$LOG"

bash tools/out.sh "$LOG"
