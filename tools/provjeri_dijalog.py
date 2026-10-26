#!/usr/bin/env python3
"""Da li je Fix 2/3 sacuvao dijalog ili ga obrisao."""
import sys, zipfile
from pathlib import Path
sys.path.insert(0, "/root/skriptorij")
from bs4 import BeautifulSoup

PRIJE = Path("/storage/emulated/0/Download/Joe_Abercrombie_The_Trouble_With_Peace_PREVEDENO.epub")
POSLIJE = Path("/storage/emulated/0/Download/_TEST_FIX.epub")

def tekst_epuba(p):
    with zipfile.ZipFile(p) as z:
        files = {n: z.read(n) for n in z.namelist()}
    svi = {}
    for n, b in files.items():
        if not n.endswith((".xhtml", ".html")): continue
        soup = BeautifulSoup(b.decode("utf-8", "replace"), "html.parser")
        for t in soup(["script", "style"]): t.decompose()
        svi[n] = soup.get_text(" ", strip=True)
    return svi

print("Ucitavam PRIJE...", flush=True)
prije = tekst_epuba(PRIJE)
print("Ucitavam POSLIJE...", flush=True)
poslije = tekst_epuba(POSLIJE)

print("\n=== UKUPNO RIJECI U TEKSTU ===")
def rijeci(d):
    return sum(len(t.split()) for t in d.values())
rp, rq = rijeci(prije), rijeci(poslije)
print(f"  PRIJE : {rp:>8}")
print(f"  POSLIJE: {rq:>8}")
print(f"  RAZLIKA: {rq - rp:>+8}  ({(rq-rp)/rp*100:+.2f}%)")
if abs(rq - rp) / rp < 0.01:
    print("  ✅ Sadrzaj sacuvan (razlika <1%)")
elif rq < rp:
    print(f"  ❌ IZGUBLJENO {rp - rq} rijeci — REGRESIJA")
else:
    print(f"  ⚠️  Dobijeno {rq - rp} rijeci (neobicno)")

# Primjeri pasusa sa dijalogom — iz fajlova koji su imali navodnike
print("\n=== PRIMJERI PASUSA SA DIJALOGOM (prije → poslije) ===")
primjeri_uzeti = 0
for n in sorted(prije):
    if primjeri_uzeti >= 5: break
    tp = prije[n]; tq = poslije.get(n, "")
    # Nadji pasus u originalu koji ima " i bar 20 rijeci
    with zipfile.ZipFile(PRIJE) as z:
        soup = BeautifulSoup(z.read(n).decode("utf-8", "replace"), "html.parser")
    for p in soup.find_all(["p"]):
        txt = p.get_text(" ", strip=True)
        if chr(34) not in txt: continue
        if len(txt.split()) < 10: continue
        # Nadji odgovarajuci pasus u poslije (po prvih 5 rijeci)
        prvih5 = " ".join(txt.split()[:5])
        with zipfile.ZipFile(POSLIJE) as z:
            soup2 = BeautifulSoup(z.read(n).decode("utf-8", "replace"), "html.parser")
        match = None
        for p2 in soup2.find_all(["p"]):
            t2 = p2.get_text(" ", strip=True)
            if t2.startswith(prvih5[:30]) or prvih5[:30] in t2:
                match = t2; break
        print(f"\n--- {n} ---")
        print(f"PRIJE  : {txt[:220]}")
        print(f"POSLIJE: {match[:220] if match else '(NIJE NADJEN!)'}")
        primjeri_uzeti += 1
        if primjeri_uzeti >= 5: break
