#!/usr/bin/env python3
"""Konacna provjera: split tekst/attr/XML + rucna verifikacija 3 primjera."""
import sys, re, zipfile
from pathlib import Path
sys.path.insert(0, "/root/skriptorij")
from bs4 import BeautifulSoup

NOVI  = Path("/storage/emulated/0/Download/_TEST_FIX.epub")
STARI = Path("/storage/emulated/0/Download/Joe_Abercrombie_The_Trouble_With_Peace_PREVEDENO.epub")

def split_epub(p):
    with zipfile.ZipFile(p) as z:
        files = {n: z.read(n) for n in z.namelist()}
    tekst = attr = 0
    for n, b in files.items():
        if not n.endswith((".xhtml", ".html")): continue
        html = b.decode("utf-8", "replace")
        soup = BeautifulSoup(html, "html.parser")
        for t in soup(["script", "style"]): t.decompose()
        tekst += sum(str(s).count(chr(34)) for s in soup.find_all(string=True))
        for tag in soup.find_all(True):
            for v in (tag.attrs or {}).values():
                s = " ".join(v) if isinstance(v, list) else str(v)
                attr += s.count(chr(34))
    return tekst, attr

print("=== SPLIT: tekst vs atributi ===")
tp, ap = split_epub(STARI)
tn, an = split_epub(NOVI)
print(f"  PRIJE :  tekst={tp:>6}  attr={ap:>5}")
print(f"  POSLIJE: tekst={tn:>6}  attr={an:>5}")
if tn < 500:
    print(f"  ✅ CILJ POSTIGNUT u tekstu: {tn} < 500")
else:
    print(f"  ❌ tekst {tn} >= 500 — treba jos")

# Rucna verifikacija — trazi po rijecima BEZ navodnika
print("\n=== RUCNO: 3 primjera iz proslog testa ===")
primjeri_kljuc = [
    "Silovao je pralju",
    "N adam se da nitko nema",
    "Šteta",
]
with zipfile.ZipFile(STARI) as z:
    stari_88 = z.read("text/part0088.html").decode("utf-8", "replace")
with zipfile.ZipFile(NOVI) as z:
    novi_88 = z.read("text/part0088.html").decode("utf-8", "replace")

soup_s = BeautifulSoup(stari_88, "html.parser")
soup_n = BeautifulSoup(novi_88, "html.parser")
tekst_s = soup_s.get_text(" ", strip=True)
tekst_n = soup_n.get_text(" ", strip=True)

for kljuc in primjeri_kljuc:
    # Ocisti navodnike iz kljuca za pretragu
    kljuc_cist = kljuc.replace(chr(34), "")
    idx_s = tekst_s.replace(chr(34), "").find(kljuc_cist)
    idx_n = tekst_n.find(kljuc_cist)
    print(f"\n  Trazim: '{kljuc_cist}'")
    if idx_s >= 0 and idx_n >= 0:
        print(f"    PRIJE  (bez nav.): ...{tekst_s.replace(chr(34),'')[max(0,idx_s-5):idx_s+80]}...")
        print(f"    POSLIJE         : ...{tekst_n[max(0,idx_n-5):idx_n+80]}...")
        print(f"    ✅ rijecima sacuvano")
    else:
        print(f"    ❌ NIJE NADJEN (prije={idx_s>=0}, poslije={idx_n>=0})")
