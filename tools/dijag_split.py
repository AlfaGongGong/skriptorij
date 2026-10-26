#!/usr/bin/env python3
"""Razdvaja ASCII " na tekst (NavigableString) vs atribute (tag.attrs)."""
import sys, re, zipfile
from pathlib import Path
sys.path.insert(0, "/root/skriptorij")
from bs4 import BeautifulSoup

SRC = Path("/storage/emulated/0/Download/_TEST_FIX.epub")
with zipfile.ZipFile(SRC) as z:
    files = {n: z.read(n) for n in z.namelist()}

tekst_count = 0
attr_count = 0
primjeri_tekst = []
primjeri_attr = {}
raw_count = 0

for n, b in files.items():
    if not n.endswith((".xhtml", ".html")): continue
    raw = b.decode("utf-8", "replace")
    raw_count += raw.count(chr(34))

    soup = BeautifulSoup(raw, "html.parser")

    # Tekst
    for node in soup.find_all(string=True):
        c = str(node).count(chr(34))
        if c:
            tekst_count += c
            if len(primjeri_tekst) < 10:
                primjeri_tekst.append((n, str(node)[:200].replace("\n","\\n")))

    # Atributi — grupisi po tag.name
    for tag in soup.find_all(True):
        if tag.attrs is None: continue
        for k, v in tag.attrs.items():
            if isinstance(v, list):
                s = " ".join(str(x) for x in v)
            else:
                s = str(v)
            c = s.count(chr(34))
            if c:
                attr_count += c
                primjeri_attr[tag.name] = primjeri_attr.get(tag.name, 0) + c

print(f"=== UKUPNO u fajlovima (grep-style): {raw_count} ===")
print(f"=== U TEKSTU (NavigableString):     {tekst_count} ===")
print(f"=== U ATRIBUTIMA:                   {attr_count} ===")
print(f"=== RAZLIKA (raw - tekst - attr):   {raw_count - tekst_count - attr_count} ===")
print(f"    (razlika = XML/DOCTYPE/comments/script/style)")
print()

print("=== ATRIBUTI po tagu (top 15) ===")
for k, v in sorted(primjeri_attr.items(), key=lambda x: -x[1])[:15]:
    print(f"  <{k}>: {v}")

print()
print("=== PRIMJERI U TEKSTU (ako ih ima) ===")
for i, (n, s) in enumerate(primjeri_tekst, 1):
    print(f"  {i}. [{n}] {s}")
