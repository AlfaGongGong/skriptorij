#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
import zipfile
import shutil
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString

SRC = Path("/storage/emulated/0/Books/MoonReader/STYLED/Joe_Abercrombie_The_Age_of_Madness_Trilogy_PREVEDENO_STYLED.epub")
TMP = SRC.with_name(SRC.name + ".tmp")
BAK = SRC.with_name(SRC.stem + "_bak2.epub")

EXACT_FIXES = {
    "text/part0077.html": [("Sharp Ends: Stories from the World of the First Law", "Oštri krajevi: Priče iz svijeta Prvog zakona")],
    "text/part0231.html": [
        ('— It was bad, then, was it?" upita ga.', '— Bilo je loše, onda, zar ne?" upita ga.'),
        ('— Da. I’m not a child any more. Ma might have a blind spot when it comes to you, always wanting to believe the best, but I know where your talents lie."', '— Da. Nisam više dijete. Mama možda ima slijepu pjegu kada si ti u pitanju, uvijek želi vjerovati najboljem, ali ja znam gdje leže tvoji talenti."')
    ],
    "text/part0085.html": [("Uz mračne, sumorne zagrljaje", "Uz mračne, sumorne zagrljaje.")],
    "text/part0133.html": [("[[NEPREVEDENO: prekinut prevod]]", "[...]")],
    "text/part0235.html": [('<div class="galley-rw', '')],
    "text/part0084.html": [("The Trouble With Peace Početak čitanjaSadržaj", "Sadržaj")],
    "text/part0004.html": [("Za Loua, uz turobne, mračne zagrljaje", "Za Loua, uz turobne, mračne zagrljaje.")],
}

def fix_html(html_bytes: bytes, fname: str) -> bytes:
    html = html_bytes.decode("utf-8", "replace")
    
    if fname in EXACT_FIXES:
        for old, new in EXACT_FIXES[fname]:
            html = html.replace(old, new)
            
    if fname == "text/part0137.html":
        html = '<html><head><title>Poglavlje</title></head><body><h1>POGLAVLJE</h1><p>[Ovo poglavlje nije prevedeno]</p></body></html>'
        return html.encode("utf-8")

    soup = BeautifulSoup(html, "html.parser")
    
    # Faza D2: Ciscenje navodnika u dijalozima
    for p in soup.find_all("p"):
        txt = p.get_text()
        if txt.strip().startswith("—"):
            # Obrisi sve ASCII navodnike " unutar dijaloga
            for child in p.children:
                if isinstance(child, NavigableString) and '"' in child:
                    child.replace_with(child.replace('"', ''))

    return str(soup).encode("utf-8")

def main():
    print(f"📖 Otvaram: {SRC.name}")
    if not SRC.exists():
        print("❌ Nema fajla."); return
        
    print(f"💾 Pravim backup: {BAK.name}")
    shutil.copy2(SRC, BAK)
    
    if TMP.exists():
        TMP.unlink()
        
    with zipfile.ZipFile(SRC, 'r') as zin:
        with zipfile.ZipFile(TMP, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename.endswith(('.html', '.xhtml')):
                    data = fix_html(data, item.filename)
                zout.writestr(item, data)
                
    TMP.replace(SRC)
    print(f"✅ Zavrseno. Original prepisan.")
    print(f"📦 Velicina: {SRC.stat().st_size / 1024 / 1024:.1f} MB")

if __name__ == "__main__":
    main()
