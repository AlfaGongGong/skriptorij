#!/usr/bin/env python3
"""Dijagnostika: zasto 11253 ASCII " ostaje posle Fix 1+2."""
import sys, re, zipfile
from pathlib import Path
from collections import Counter
sys.path.insert(0, "/root/skriptorij")
from bs4 import BeautifulSoup
from epub.styler import _ukloni_sve, _normalizuj, _dijalog

SRC = Path("/storage/emulated/0/Download/_TEST_FIX.epub")
if not SRC.exists():
    print("NEMA _TEST_FIX.epub — pokreni prvo test_fix_navodnici.py"); sys.exit(1)

with zipfile.ZipFile(SRC) as z:
    files = {n: z.read(n) for n in z.namelist()}

# Uzmi tekst svih html fajlova (vec obradjenih)
primeri = []
ukupno_parova = 0
ukupno_neparnih_redova = 0
duzine = Counter()

for n, b in files.items():
    if not n.endswith((".xhtml", ".html")): continue
    soup = BeautifulSoup(b.decode("utf-8", "replace"), "html.parser")
    for node in soup.find_all(string=True):
        if node.parent and node.parent.name in ("script", "style"): continue
        s = str(node)
        if chr(34) not in s: continue
        # Broj navodnika u ovom stringu
        n_count = s.count(chr(34))
        # Parovi u ovom stringu
        pairs = re.findall(r'"([^"\n]{1,300})"', s)
        for p in pairs:
            duzine[len(p)] += 1
        # Ostatak posle uklanjanja parova
        ostatak = re.sub(r'"[^"\n]{1,300}"', '', s)
        ostalo_count = ostatak.count(chr(34))
        if ostalo_count > 0:
            ukupno_neparnih_redova += 1
            if len(primeri) < 15:
                primeri.append({
                    "fajl": n,
                    "ukupno": n_count,
                    "parova": len(pairs),
                    "ostalo": ostalo_count,
                    "tekst": s[:250].replace("\n", "\\n"),
                })

print(f"\n=== SAZETAK ===")
print(f"Stringova sa ostalim \"': {ukupno_neparnih_redova}")
print(f"\n=== DUZINE PAROVA (posle Fix 2) ===")
if duzine:
    print(f"  min={min(duzine)}, max={max(duzine)}, ukupno={sum(duzine.values())}")
    print(f"  hist: ", sorted(duzine.items())[:5], "...", sorted(duzine.items())[-5:])

print(f"\n=== PRVIH 15 PRIMERA (stringovi sa ostalim \") ===")
for i, p in enumerate(primeri, 1):
    print(f"\n--- {i}. {p['fajl']} (uk={p['ukupno']}, par={p['parova']}, ost={p['ostalo']}) ---")
    print(f"  {p['tekst']}")

# Koliko navodnika je u stringovima sa NEparnim brojem
print(f"\n=== PAR/NEPAR ANALIZA ===")
parno = 0; neparno = 0; parno_chars = 0; neparno_chars = 0
for n, b in files.items():
    if not n.endswith((".xhtml", ".html")): continue
    soup = BeautifulSoup(b.decode("utf-8", "replace"), "html.parser")
    for node in soup.find_all(string=True):
        s = str(node)
        c = s.count(chr(34))
        if c == 0: continue
        if c % 2 == 0:
            parno += 1; parno_chars += c
        else:
            neparno += 1; neparno_chars += c
print(f"  Stringova sa PARNIM brojem \": {parno} (ukupno \": {parno_chars})")
print(f"  Stringova sa NEPARNIM brojem \": {neparno} (ukupno \": {neparno_chars})")
