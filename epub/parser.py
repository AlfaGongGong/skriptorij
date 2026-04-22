# epub/parser.py
import re
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString

def _ocisti_epub_html(html: str) -> str:
    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all(True):
            for node in list(tag.children):
                if isinstance(node, NavigableString):
                    cleaned = re.sub(r"^[\n\r\t\v]+", "", str(node))
                    if cleaned != str(node):
                        node.replace_with(NavigableString(cleaned))
        return str(soup)
    except:
        return html

def _ukloni_inline_stilove(html_fajlovi: list, log_fn=None) -> int:
    modificirano = 0
    for fajl in html_fajlovi:
        try:
            original = fajl.read_text("utf-8", errors="ignore")
            if "style=" not in original: continue
            soup = BeautifulSoup(original, "html.parser")
            izmijenjeno = False
            for tag in soup.find_all(True):
                if tag.get("style"):
                    del tag["style"]
                    izmijenjeno = True
            if izmijenjeno:
                fajl.write_text(str(soup), encoding="utf-8")
                modificirano += 1
        except: pass
    if modificirano and log_fn:
        log_fn(f"🎨 Inline stilovi očišćeni u {modificirano} HTML fajl(ov)a.", "tech")
    return modificirano

def _zamijeni_epub_css(html_fajlovi: list, work_dir, log_fn=None) -> int:
    # pojednostavljeno
    return 0
