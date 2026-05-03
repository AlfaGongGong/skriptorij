

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
    except Exception:
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


# ─────────────────────────────────────────────────────────────────────────────
# EpubParser — čita EPUB zip i vraća poglavlja za preview
# ─────────────────────────────────────────────────────────────────────────────
import zipfile
import os

class EpubParser:
    """
    Minimalni EPUB parser za live preview.
    Čita spine redoslijed iz OPF-a, parsira svaki HTML dokument
    i vraća listu poglavlja s naslovom, HTML sadržajem i plain textom.
    """

    def __init__(self, epub_path: str):
        self.epub_path = str(epub_path)
        self._chapters = None

    # ── Javni API ─────────────────────────────────────────────────────────────

    def get_chapters(self) -> list:
        """
        Vraća listu dict-ova:
          { title, html, text, partial, idx }
        """
        if self._chapters is not None:
            return self._chapters
        try:
            self._chapters = self._parse()
        except Exception as e:
            self._chapters = []
        return self._chapters

    # ── Interni parseri ───────────────────────────────────────────────────────

    def _parse(self) -> list:
        chapters = []
        with zipfile.ZipFile(self.epub_path, "r") as zf:
            names = zf.namelist()

            # 1. Pronađi OPF (content.opf ili META-INF/container.xml → rootfile)
            opf_path = self._find_opf(zf, names)

            if opf_path:
                spine_items = self._parse_opf_spine(zf, opf_path)
            else:
                # Fallback: uzmi sve HTML fajlove abecednim redom
                spine_items = sorted(
                    n for n in names
                    if n.lower().endswith((".html", ".xhtml", ".htm"))
                    and not n.startswith("__")
                )

            opf_dir = "/".join(opf_path.split("/")[:-1]) if opf_path else ""

            for idx, item_href in enumerate(spine_items):
                # Normaliziraj putanju unutar zipa
                full_path = (opf_dir + "/" + item_href).lstrip("/") if opf_dir else item_href

                # Provjeri alternativu ako puna putanja ne postoji
                if full_path not in names:
                    # Pokušaj direktno
                    if item_href in names:
                        full_path = item_href
                    else:
                        continue

                try:
                    raw = zf.read(full_path).decode("utf-8", errors="replace")
                except Exception:
                    continue

                title, html_body, plain = self._extract_content(raw, idx)
                if not plain.strip():
                    continue  # Preskoči prazna poglavlja

                chapters.append({
                    "idx":     idx,
                    "title":   title,
                    "html":    html_body,
                    "text":    plain[:500],   # Kratki preview teksta
                    "partial": False,
                })

        return chapters

    def _find_opf(self, zf, names) -> str:
        """Pronađi putanju do OPF fajla."""
        # Direktno
        for n in names:
            if n.endswith(".opf"):
                return n
        # Preko container.xml
        if "META-INF/container.xml" in names:
            try:
                container_xml = zf.read("META-INF/container.xml").decode("utf-8", errors="replace")
                soup = BeautifulSoup(container_xml, "html.parser")
                rf = soup.find("rootfile")
                if rf and rf.get("full-path"):
                    return rf["full-path"]
            except Exception:
                pass
        return ""

    def _parse_opf_spine(self, zf, opf_path: str) -> list:
        """Parsira OPF i vraća href-ove po spine redoslijedu."""
        try:
            opf_raw = zf.read(opf_path).decode("utf-8", errors="replace")
            soup = BeautifulSoup(opf_raw, "html.parser")

            # Manifest: id → href
            manifest = {}
            for item in soup.find_all("item"):
                item_id   = item.get("id", "")
                item_href = item.get("href", "")
                media     = item.get("media-type", "")
                if "html" in media or item_href.endswith((".html", ".xhtml", ".htm")):
                    manifest[item_id] = item_href

            # Spine: idref redoslijed
            spine_hrefs = []
            for itemref in soup.find_all("itemref"):
                idref = itemref.get("idref", "")
                if idref in manifest:
                    spine_hrefs.append(manifest[idref])

            return spine_hrefs if spine_hrefs else list(manifest.values())
        except Exception:
            return []

    def _extract_content(self, raw_html: str, idx: int):
        """Vraća (title, body_html, plain_text) iz HTML stringa."""
        try:
            soup = BeautifulSoup(raw_html, "html.parser")

            # Naslov: <title>, h1, h2 — kojegod nađe
            title = ""
            title_tag = soup.find("title")
            if title_tag:
                title = title_tag.get_text(strip=True)
            if not title:
                for htag in ("h1", "h2", "h3"):
                    h = soup.find(htag)
                    if h:
                        title = h.get_text(strip=True)
                        break
            if not title:
                title = f"Poglavlje {idx + 1}"

            # Body HTML — samo sadržaj <body> taga
            body = soup.find("body")
            body_html = str(body) if body else str(soup)

            # Plain text (za provjeru je li prazan)
            plain = soup.get_text(separator=" ", strip=True)

            return title, body_html, plain

        except Exception:
            return f"Poglavlje {idx + 1}", raw_html, raw_html[:200]

