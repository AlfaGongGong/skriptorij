#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Epub Surgery — direktne popravke finalnog EPUB-a.
Rešava: LEK-SKRIPTA, LEK-TAG, INT-SPLIT, TIP-NAVOD, STIL-STYLE, JEZ-DUPW.
Ne dira: pipeline, ne troši API.
"""
import re
import zipfile
import shutil
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString, Tag

SRC = Path("/storage/emulated/0/Books/MoonReader/STYLED/Joe_Abercrombie_The_Age_of_Madness_Trilogy_PREVEDENO_STYLED.epub")
OUT = SRC.with_name(SRC.stem + "_FIXED.epub")

# Faza A: Precizne zamene
EXACT_FIXES = {
    "text/part0113.html": [("Zار", "Zar")],
    "text/part0114.html": [("zрити", "zriti")],
    "text/part0149.html": [("Zار", "Zar")],
    "text/part0207.html": [("isпустиo", "ispustio")],
    "text/part0236.html": [("Zار", "Zar")],
    "text/part0235.html": [('<div class="galley-rw', '<div')],
    "text/part0004.html": [("Za Loua,uz turobne, mračnezagrljaje", "Za Loua, uz turobne, mračne zagrljaje")],
    "text/part0084.html": [("The Trouble With Peace Početak čitanjaSadržaj", "Sadržaj")],
    "text/part0025.html": [("Covjek", "Čovjek")],
}

def fix_html(html_bytes: bytes, fname: str) -> bytes:
    html = html_bytes.decode("utf-8", "replace")
    
    # 1. Faza A: Exact string replacements
    if fname in EXACT_FIXES:
        for old, new in EXACT_FIXES[fname]:
            html = html.replace(old, new)
            
    # 2. Faza B: part0137 (LLM smeće)
    if fname == "text/part0137.html":
        html = '<html><head><title>Poglavlje</title></head><body><h1>POGLAVLJE</h1><p>[Ovo poglavlje nije prevedeno]</p></body></html>'
        return html.encode("utf-8")

    soup = BeautifulSoup(html, "html.parser")
    
    # 3. Faza E: Ciscenje klase i style (osim booklyfi)
    for tag in soup.find_all(True):
        if tag.name in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "span", "section"):
            # Obrisi style atribute osim ako je dropcap
            if "style" in tag.attrs:
                if "booklyfi-dropcap" not in tag.get("class", []) and "font-size:1px" not in tag["style"]:
                    del tag["style"]
            # Obrisi class atribute osim ako je booklyfi
            if "class" in tag.attrs:
                if not any(c.startswith("booklyfi-") for c in tag["class"]):
                    del tag["class"]
                    
    # 4. Faza C + D: Spajanje pasusa i navodnici
    for p in soup.find_all("p"):
        txt = p.get_text()
        
        # Faza D: —" na kraju u —
        if txt.startswith("—"):
            for child in p.children:
                if isinstance(child, NavigableString) and '—"' in child:
                    child.replace_with(child.replace('—"', '—'))
                elif isinstance(child, NavigableString) and '"' in child and child.strip().endswith('"'):
                    # Ako je zadnji karakter ", a pocetak je —
                    child.replace_with(child.rstrip('"'))

    # Faza C: spajanje odsecenih pasusa (obradjujemo listu unazad da ne poremetimo iteraciju)
    for p in list(soup.find_all("p"))[::-1]:
        if not p.parent:
            continue
        nxt = p.find_next_sibling()
        if not nxt or nxt.name != "p":
            continue
        
        txt = p.get_text().strip()
        txt_nxt = nxt.get_text().strip()
        
        # Ako trenutni p nema zavrsnu interpunkciju i sledeci pocinje malim slovom
        if txt and not txt[-1] in ".!?…—\"'" and txt_nxt and txt_nxt[0].islower():
            # Spoji ih
            p.append(" " + txt_nxt)
            nxt.decompose()
            
    # 5. Faza E: Duple reci (Veliko Veliko)
    for child in soup.find_all(string=True):
        if child.parent.name in ("script", "style", "title"):
            continue
        orig = str(child)
        # Regex za ponovljenu rec
        new = re.sub(r'\b(\w+)\s+\1\b', r'\1', orig, flags=re.IGNORECASE)
        if new != orig:
            child.replace_with(new)

    return str(soup).encode("utf-8")

def main():
    print(f"📖 Otvaram: {SRC.name}")
    if not SRC.exists():
        print("❌ Nema fajla."); return
        
    if OUT.exists():
        OUT.unlink()
        
    shutil.copy2(SRC, OUT) # Backup
    
    with zipfile.ZipFile(SRC, 'r') as zin:
        with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename.endswith(('.html', '.xhtml')):
                    data = fix_html(data, item.filename)
                zout.writestr(item, data)
                
    print(f"✅ Snimljeno: {OUT.name}")
    print(f"📦 Velicina: {OUT.stat().st_size / 1024 / 1024:.1f} MB")

if __name__ == "__main__":
    main()
