#!/usr/bin/env python3
"""Da li _dodaj_dropcap radi posle fixa orphan navodnika."""
import sys, re, zipfile
from pathlib import Path
from bs4 import BeautifulSoup
sys.path.insert(0, "/root/skriptorij")
from epub.styler import _ukloni_sve, _normalizuj, _dijalog, _dodaj_dropcap

SRC = Path("/storage/emulated/0/Download/Joe_Abercrombie_The_Trouble_With_Peace_PREVEDENO.epub")
if not SRC.exists():
    print(f"NEMA: {SRC}"); sys.exit(1)

with zipfile.ZipFile(SRC) as z:
    files = {n: z.read(n) for n in z.namelist()}

def prvi_p(soup):
    body = soup.body
    if not body: return None
    h1 = body.find("h1")
    return h1.find_next("p") if h1 else body.find("p")

# Kandidati: prvi p u body ima "X  pattern (orphan quote + slovo + razmak)
kandidati = []
for n, b in files.items():
    if not n.endswith((".xhtml", ".html")): continue
    soup = BeautifulSoup(b.decode("utf-8", "replace"), "html.parser")
    pp = prvi_p(soup)
    if not pp: continue
    t = pp.get_text(" ", strip=True)
    if re.match(r'^"[A-ZČĆŠŽĐ]\s', t):
        kandidati.append((n, b.decode("utf-8", "replace"), t))
    if len(kandidati) >= 5: break

print(f"Kandidata sa orphan quote na prvom pasusu: {len(kandidati)}\n")

for i, (n, html, t_orig) in enumerate(kandidati, 1):
    print(f"\n{'='*70}")
    print(f"{i}. [{n}]")
    print(f"ORIGINAL: {t_orig[:150]}")

    soup = BeautifulSoup(html, "html.parser")
    pp_orig = prvi_p(soup)
    if pp_orig:
        orig_img = pp_orig.find("img", class_="booklyfi-dropcap")
        orig_span = pp_orig.find("span", style=True)
        print(f"  orig img:  {'DA' if orig_img else 'NE'}")
        print(f"  orig span: {'DA' if orig_span else 'NE'}")
        if orig_span:
            print(f"  span tekst: {orig_span.get_text(strip=True)!r}")

    _ukloni_sve(soup)
    pp = prvi_p(soup)
    t1 = pp.get_text(" ", strip=True)[:120] if pp else "?"
    print(f"  +_ukloni_sve:    {t1}")

    _normalizuj(soup)
    pp = prvi_p(soup)
    t2 = pp.get_text(" ", strip=True)[:120] if pp else "?"
    print(f"  +_normalizuj:    {t2}")

    _dijalog(soup)
    pp = prvi_p(soup)
    t3 = pp.get_text(" ", strip=True)[:120] if pp else "?"
    print(f"  +_dijalog:       {t3}")

    if pp:
        prvi = pp.get_text(strip=True)[:1]
        klas = "DIJALOG→preskok" if prvi in ('—','–','-','"','"','"','«',"'") else "NARACIJA→dropcap"
        print(f"  Klasifikacija:   {prvi!r} → {klas}")

    rez = _dodaj_dropcap(soup)
    print(f"  +_dodaj_dropcap: vratio={rez}")

    pp = prvi_p(soup)
    if pp:
        fin_img = pp.find("img", class_="booklyfi-dropcap")
        fin_span = pp.find("span", style=True)
        tf = pp.get_text(" ", strip=True)
        print(f"  FINALNI:         {tf[:150]}")
        print(f"  fin img:  {'DA' if fin_img else 'NE'}")
        print(f"  fin span: {'DA' if fin_span else 'NE'}")
        if fin_span:
            print(f"  fin span tekst: {fin_span.get_text(strip=True)!r}")
