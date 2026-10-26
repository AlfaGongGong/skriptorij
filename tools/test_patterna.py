#!/usr/bin/env python3
"""Test novih patterna na 20 stvarnih pasusa PRIJE primene."""
import sys, re, zipfile
from pathlib import Path
sys.path.insert(0, "/root/skriptorij")
from bs4 import BeautifulSoup

SRC = Path("/storage/emulated/0/Download/Joe_Abercrombie_The_Trouble_With_Peace_PREVEDENO.epub")
if not SRC.exists():
    print("NEMA EPUB"); sys.exit(1)

# ── NOVI PREDLOZENI PATTERNI (redoslijed je kljucan) ──
PATTERNS = [
    # 1) " na pocetku reda (dijalog) → — 
    (r'(?m)^(\s*)"(?=\S)', r'\1— '),
    # 2) " posle . ! ? … : (dijalog u nastavku) → — 
    (r'(?<=[.!?…:] )"(?=\S)', r'— '),
    # 3) " posle : na kraju pasusa (dijalog) → — 
    (r'(?<=:) "(?=\S)', r'— '),
    # 4) ZATVARAJUCI ": " posle teksta prije , ; : . ! ? → obrisi "
    (r'(?<=[a-zA-ZčćšžđČĆŠŽĐ.!?…])"(?=\s*[,;:.!?])', ''),
    # 5) ZATVARAJUCI " na kraju pasusa posle teksta → obrisi
    (r'(?<=[a-zA-ZčćšžđČĆŠŽĐ.!?…])"\s*$', ''),
    # 6) OTVARAJUCI " posle , ; : u naraciji (npr. ", reče on, "nastavak) → obrisi "
    (r'(?<=[,;:])\s*"(?=[A-Za-zČĆŠŽĐčćšžđ])', ' '),
    # 7) "citat" gde su OBA u tekstu bez interpunkcije izmedju (pravi par) → — citat
    #    Uslov: prvi " nije posle interpunkcije, drugi " nije prije interpunkcije
    #    Ovo je najrizicniji — zato ga testiramo
    (r'(?<![,;:!?.\s])"([^"\n]{3,200})"(?![,;:!?.])', r'— \1'),
]

def primeni(t):
    n = 0
    for pat, repl in PATTERNS:
        t, k = re.subn(pat, repl, t)
        n += k
    return t, n

# Uzmi 20 pasusa sa dijalogom
pasusi = []
with zipfile.ZipFile(SRC) as z:
    for n in z.namelist():
        if not n.endswith((".xhtml", ".html")): continue
        if len(pasusi) >= 20: break
        soup = BeautifulSoup(z.read(n).decode("utf-8", "replace"), "html.parser")
        for p in soup.find_all("p"):
            t = p.get_text(" ", strip=True)
            if chr(34) in t and 10 < len(t.split()) < 80:
                pasusi.append((n, t))
                if len(pasusi) >= 20: break

print(f"Testiram {len(pasusi)} pasusa\n")
print("=" * 80)
for i, (n, t) in enumerate(pasusi, 1):
    novo, k = primeni(t)
    print(f"\n{i:>2}. [{n}]  ({k} zamjena)")
    print(f"   PRIJE : {t}")
    print(f"   POSLIJE: {novo}")
    # Detektuj probleme
    problemi = []
    if "— ," in novo or "—," in novo: problemi.append("em-crtica ispred zapete")
    if "— ." in novo or "—." in novo: problemi.append("em-crtica ispred tacke")
    if '""' in novo: problemi.append("dvostruki navodnik")
    if novo.count(chr(34)) > 0 and novo.count(chr(34)) % 2 != 0:
        problemi.append(f"neparan broj navodnika ({novo.count(chr(34))})")
    if problemi:
        print(f"   ⚠️  {', '.join(problemi)}")

print("\n" + "=" * 80)
print("\nAko su primeri OK — reci 'da', pa primenjujem na ceo EPUB.")
print("Ako neki prave probleme — reci Koji, i popravljam pattern.")
