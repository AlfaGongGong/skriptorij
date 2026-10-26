#!/usr/bin/env python3
"""Standalone test Fix 1 + Fix 2 na EPUB-u. Bez fleet-a, bez UI-a."""
import sys, zipfile
from pathlib import Path
sys.path.insert(0, "/root/skriptorij")
from bs4 import BeautifulSoup
from epub.styler import _ukloni_sve, _normalizuj, _dijalog

SRC = Path("/storage/emulated/0/Download/Joe_Abercrombie_The_Trouble_With_Peace_PREVEDENO.epub")
OUT = Path("/storage/emulated/0/Download/_TEST_FIX.epub")

KEYS = ["galley-rw", "<section>", 'ASCII "', "„", '"', "—"]
def cnt(txt):
    return {
        "galley-rw": txt.count("galley-rw"),
        "<section>": txt.count("<section"),
        'ASCII "':   txt.count(chr(34)),
        "„":         txt.count(chr(0x201E)),
        '"':         txt.count(chr(0x201C)),
        "—":         txt.count(chr(0x2014)),
    }

def total(files):
    agg = {k: 0 for k in KEYS}
    for n, b in files.items():
        if not n.endswith((".xhtml", ".html")): continue
        for k, v in cnt(b.decode("utf-8", "replace")).items():
            agg[k] += v
    return agg

def pprint(label, d):
    print(label)
    for k in KEYS:
        print(f"  {k:12s}: {d[k]:>6}")

print(f"SRC: {SRC}")
if not SRC.exists():
    print("NEMA fajla — STOP"); sys.exit(1)

with zipfile.ZipFile(SRC) as z:
    files = {n: z.read(n) for n in z.namelist()}

pprint("PRIJE:", total(files))

ok = 0; fail = 0
for n in list(files):
    if not n.endswith((".xhtml", ".html")): continue
    try:
        soup = BeautifulSoup(files[n].decode("utf-8", "replace"), "html.parser")
        _ukloni_sve(soup)
        _normalizuj(soup)
        _dijalog(soup)
        files[n] = str(soup).encode("utf-8")
        ok += 1
    except Exception as e:
        print(f"  FAIL {n}: {type(e).__name__}: {e}")
        fail += 1
print(f"\nObradjeno: {ok}, palo: {fail}")

pprint("POSLIJE:", total(files))

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for n, b in files.items():
        z.writestr(n, b)
print(f"\nSnimljeno: {OUT}")
