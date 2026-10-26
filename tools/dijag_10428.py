#!/usr/bin/env python3
"""Sta je 10428 navodnika sto nisu tekst ni atribut."""
import sys, re, zipfile
from pathlib import Path
sys.path.insert(0, "/root/skriptorij")
from bs4 import BeautifulSoup

SRC = Path("/storage/emulated/0/Download/_TEST_FIX.epub")
with zipfile.ZipFile(SRC) as z:
    files = {n: z.read(n) for n in z.namelist()}

def count_outside_text_attr(html: str) -> dict:
    """Razbij: komentari, script, style, XML decl, ostalo."""
    out = {"komentar": 0, "script": 0, "style": 0,
           "xml_decl": 0, "doctype": 0, "ostalo": 0}
    # Ukloni tekst i atribute preko BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    # Komentari (BeautifulSoup ih cuva kao Comment)
    from bs4 import Comment
    for c in soup.find_all(string=lambda t: isinstance(t, Comment)):
        out["komentar"] += str(c).count(chr(34))

    # Script i style
    for tag in soup.find_all(["script", "style"]):
        txt = tag.string or ""
        out[tag.name] += str(txt).count(chr(34))
        # Ukloni iz dalje analize
        tag.decompose()

    # XML decl i doctype iz originala (prije BeautifulSoup)
    for m in re.finditer(r"<\?xml[^?]*\?>", html):
        out["xml_decl"] += m.group(0).count(chr(34))
    for m in re.finditer(r"<!DOCTYPE[^>]*>", html, re.IGNORECASE):
        out["doctype"] += m.group(0).count(chr(34))

    # Ostalo: prebroj sve " u originalu, oduzmi poznato
    raw = html.count(chr(34))
    tekst = sum(str(n).count(chr(34)) for n in soup.find_all(string=True))
    attr = 0
    for tag in soup.find_all(True):
        for v in (tag.attrs or {}).values():
            s = " ".join(v) if isinstance(v, list) else str(v)
            attr += s.count(chr(34))
    poznato = out["komentar"] + out["script"] + out["style"] + \
              out["xml_decl"] + out["doctype"] + tekst + attr
    out["ostalo"] = raw - poznato
    out["_raw"] = raw
    out["_tekst"] = tekst
    out["_attr"] = attr
    return out

total = {}
top_fajlovi = []
for n, b in files.items():
    if not n.endswith((".xhtml", ".html")): continue
    d = count_outside_text_attr(b.decode("utf-8", "replace"))
    for k, v in d.items():
        total[k] = total.get(k, 0) + v
    if d["_raw"]:
        top_fajlovi.append((d["_raw"], n, d))

print("=== GLOBALNA RAZBUKA ===")
for k in ["komentar", "script", "style", "xml_decl", "doctype", "ostalo"]:
    print(f"  {k:12s}: {total.get(k, 0):>6}")
print(f"  {'_raw':12s}: {total.get('_raw', 0):>6}")
print(f"  {'_tekst':12s}: {total.get('_tekst', 0):>6}  <-- cilj <500")
print(f"  {'_attr':12s}: {total.get('_attr', 0):>6}")

print()
print("=== TOP 5 FAJLOVA po broju \" u raw ===")
top_fajlovi.sort(reverse=True)
for raw, n, d in top_fajlovi[:5]:
    print(f"\n  {n}: raw={raw}")
    print(f"    komentar={d['komentar']}, script={d['script']}, "
          f"style={d['style']}, xml={d['xml_decl']}, "
          f"doctype={d['doctype']}, ostalo={d['ostalo']}")
    print(f"    _tekst={d['_tekst']}, _attr={d['_attr']}")
    # Pokazi prvih 3 pojave "
    with zipfile.ZipFile(SRC) as z:
        html = z.read(n).decode("utf-8", "replace")
    idx = 0
    for i in range(3):
        idx = html.find(chr(34), idx)
        if idx < 0: break
        print(f"    ctx: ...{html[max(0,idx-60):idx+30]}...")
        idx += 1
