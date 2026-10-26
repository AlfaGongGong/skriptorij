#!/usr/bin/env python3
import sys, zipfile
from pathlib import Path
from bs4 import BeautifulSoup
sys.path.insert(0, "/root/skriptorij")
from epub.styler import _ukloni_sve, _normalizuj, _dijalog, _dodaj_dropcap

SRC = Path("/storage/emulated/0/Download/Joe_Abercrombie_The_Trouble_With_Peace_PREVEDENO.epub")
if not SRC.exists():
    print(f"NEMA: {SRC}"); sys.exit(2)
with zipfile.ZipFile(SRC) as z:
    files = {n: z.read(n) for n in z.namelist()}

def prvi_p(soup):
    body = soup.body
    if not body: return None
    h1 = body.find("h1")
    return h1.find_next("p") if h1 else body.find("p")

kandidati = []
for n, b in files.items():
    if not n.endswith((".xhtml", ".html")): continue
    soup = BeautifulSoup(b.decode("utf-8", "replace"), "html.parser")
    pp = prvi_p(soup)
    if not pp: continue
    t = pp.get_text(" ", strip=True)
    if not t or t[0] == chr(34): continue
    if len(t) < 200 or not t[0].isalpha(): continue
    kandidati.append((n, b.decode("utf-8", "replace")))
    if len(kandidati) >= 10: break

if not kandidati:
    print("NEMA kandidata"); sys.exit(2)

uspjeh = 0
for i, (n, html) in enumerate(kandidati, 1):
    soup = BeautifulSoup(html, "html.parser")
    _ukloni_sve(soup); _normalizuj(soup); _dijalog(soup)
    rez = _dodaj_dropcap(soup)
    pp = prvi_p(soup)
    img = pp.find("img", class_="booklyfi-dropcap") if pp else None
    span = pp.find("span", style=True) if pp else None
    ok = bool(rez and img and span)
    if ok: uspjeh += 1
    print(f"  {i:>2}. {'OK  ' if ok else 'FAIL'} [{n}] rez={rez} img={bool(img)} span={bool(span)}")

print(f"\nREZULTAT: {uspjeh}/{len(kandidati)}")
sys.exit(0 if uspjeh == len(kandidati) else 1)
