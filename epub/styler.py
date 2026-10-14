"""epub/styler.py — BOOKLYFI STYLER v2 (konačna verzija)
===========================================================================
JEDINSTVENI FORMAT ZA SVE KNJIGE.

PRAVILA:
  1. Obriši SVE staro (css, klase, dropcap, ornament, sadržaj, toc, ncx)
  2. Normalizuj HTML (div→p, h4-h6→h3, font→unwrap, deduplikacija AA→A)
  3. Detektuj STVARNA poglavlja (isključi uvod/o autoru/impresum/sadržaj)
  4. Za svako poglavlje: vijenac → POGLAVLJE N → dropcap
  5. Dropcap: 4em, pokriva 3+ reda, prvo slovo nevidljivo ali u tekstu
  6. Novi toc.ncx i toc.xhtml — SAMO stvarna poglavlja
  7. Svi TOC-ovi i ncx-ovi iz EPUB-a se brišu, pravi se jedan
===========================================================================
"""
from __future__ import annotations

import base64
import copy
import logging
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString

logger = logging.getLogger(__name__)

STYLED_OUTPUT_DIR = "/storage/emulated/0/Books/MoonReader/STYLED"
ORNAMENTS_DIR = "/storage/emulated/0/Books/MoonReader/ornaments_small_size"
CENTER_ORNAMENT_PNG = "center_ornament.png"


# ═══════════════════════════════════════════════════════════════════════════
# 1. PNG SISTEM
# ═══════════════════════════════════════════════════════════════════════════

_PNG_CACHE: dict[str, str] = {}


def _png_b64(fname: str) -> str:
    if fname in _PNG_CACHE:
        return _PNG_CACHE[fname]
    path = os.path.join(ORNAMENTS_DIR, fname)
    if os.path.exists(path):
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
            _PNG_CACHE[fname] = b64
            return b64
    return ""


def _scan_dropcaps() -> dict[str, str]:
    m = {}
    if not os.path.isdir(ORNAMENTS_DIR):
        return m
    for fname in sorted(os.listdir(ORNAMENTS_DIR)):
        if not fname.lower().endswith(".png"):
            continue
        stem = fname[:-4]
        if len(stem) in (1, 2) and stem.isalpha():
            m.setdefault(stem.upper(), fname)
    return m


DROPCAP_MAP = _scan_dropcaps()


# ═══════════════════════════════════════════════════════════════════════════
# 2. CSS — JEDAN STIL
# ═══════════════════════════════════════════════════════════════════════════

CSS = """
body { background:#F5F0E8; color:#2C1810; font-family:Georgia,serif;
       font-size:1em; line-height:1.6; margin:0 5%; padding:0; }
p { margin:0; padding:0; text-indent:1.8em; font-size:1em; line-height:1.6; }
p.booklyfi-prvi { text-indent:0; margin-top:0.5em; margin-bottom:0.3em; }
p.booklyfi-dijalog { margin:0.3em 0; padding-left:1.5em; text-indent:-1em; }
h1.booklyfi-naslov { color:#8B0000; text-align:center;
    font-size:1.8em; font-weight:600; letter-spacing:0.05em;
    margin:0.5em 0 0.8em 0; line-height:1.3; text-indent:0; }
img.booklyfi-vijenac { display:block; width:70%; height:auto;
    margin:0.5em auto 0.8em auto; }
img.booklyfi-dropcap { float:left; display:inline;
    width:4em; height:auto; max-width:none;
    margin:0.1em 0.15em 0 0; padding:0; vertical-align:top; }
em, i { font-style:italic; }
strong, b { font-weight:700; }
"""


# ═══════════════════════════════════════════════════════════════════════════
# 3. BRISANJE SVE STARE STILIZACIJE
# ═══════════════════════════════════════════════════════════════════════════

def _ukloni_sve(soup: BeautifulSoup) -> None:
    # Style/link
    for style in soup.find_all("style"):
        style.decompose()
    for link in soup.find_all("link"):
        rel = link.get("rel") or []
        if isinstance(rel, str):
            rel = [rel]
        if "stylesheet" in [r.lower() for r in rel]:
            link.decompose()

    # Ornamenti
    for tag in soup.find_all("img", class_="booklyfi-vijenac"):
        tag.decompose()
    for tag in soup.find_all("img", class_="booklyfi-ornament"):
        tag.decompose()
    for tag in soup.find_all("div", class_="booklyfi-ornament"):
        tag.decompose()
    for tag in soup.find_all("p", class_="booklyfi-vijenac"):
        tag.decompose()

    # Dropcapi
    for tag in soup.find_all("img", class_="booklyfi-dropcap"):
        tag.decompose()
    for tag in soup.find_all("span", class_="booklyfi-dropcap"):
        tag.decompose()

    # Skrivena slova — VRATI SLOVO U TEKST
    for span in soup.find_all("span", style=True):
        s = span.get("style") or ""
        if "font-size:1px" in s or "font-size: 1px" in s or "font-size:0" in s:
            slovo = span.get_text(strip=True)
            span.replace_with(slovo)

    # Klase booklyfi-*
    for el in soup.find_all(class_=True):
        classes = el.get("class") or []
        if isinstance(classes, str):
            classes = classes.split()
        new_c = [c for c in classes if not c.startswith("booklyfi-")]
        if new_c:
            el["class"] = new_c
        elif el.get("class") is not None:
            del el["class"]


# ═══════════════════════════════════════════════════════════════════════════
# 4. NORMALIZACIJA HTML-a
# ═══════════════════════════════════════════════════════════════════════════

def _normalizuj(soup: BeautifulSoup) -> None:
    # div → p
    for div in soup.find_all("div"):
        if div.find(["div", "p", "ul", "ol", "table"]):
            continue
        if not div.get_text(strip=True):
            continue
        div.name = "p"

    # h4-h6 → h3
    for h in soup.find_all(["h4", "h5", "h6"]):
        h.name = "h3"

    # font → unwrap
    for font in soup.find_all("font"):
        font.unwrap()

    # center → p
    for c in soup.find_all("center"):
        p_new = soup.new_tag("p")
        for child in list(c.children):
            p_new.append(child)
        c.replace_with(p_new)

    # table layout → p
    for table in soup.find_all("table"):
        if len(table.find_all("tr")) <= 1:
            p_new = soup.new_tag("p")
            p_new.string = table.get_text(" ", strip=True)
            table.replace_with(p_new)

    # span bez stila → unwrap
    for span in soup.find_all("span"):
        if not span.get("style"):
            span.unwrap()

    # b→strong, i→em
    for b in soup.find_all("b"):
        b.name = "strong"
    for i in soup.find_all("i"):
        i.name = "em"

    # u,s,strike → unwrap
    for tag in soup.find_all(["u", "s", "strike", "del", "ins"]):
        tag.unwrap()

    # Deduplikacija: AAutorska → Autorska
    for text_node in soup.find_all(string=True):
        if text_node.parent and text_node.parent.name in ("script", "style"):
            continue
        orig = str(text_node)
        new = re.sub(r'\b([A-ZŠĐČĆŽ])\1+([a-zšđčćž])', r'\1\2', orig)
        if new != orig:
            text_node.replace_with(new)


# ═══════════════════════════════════════════════════════════════════════════
# 5. DIJALOG
# ═══════════════════════════════════════════════════════════════════════════

def _dijalog(soup: BeautifulSoup) -> int:
    try:
        from core.kalkovi.dijalog import DIJALOG_TIPOGRAFIJA
    except Exception:
        return 0
    n = 0
    for node in soup.find_all(string=True):
        if node.parent and node.parent.name in ("script", "style"):
            continue
        orig = str(node)
        new = orig
        for pattern, repl in DIJALOG_TIPOGRAFIJA:
            new = re.sub(pattern, repl, new)
        if new != orig:
            node.replace_with(new)
            n += 1
    return n


# ═══════════════════════════════════════════════════════════════════════════
# 6. VIJENAC
# ═══════════════════════════════════════════════════════════════════════════

def _dodaj_vijenac(soup: BeautifulSoup) -> None:
    b64 = _png_b64(CENTER_ORNAMENT_PNG)
    body = soup.find("body")
    if not body:
        return
    if b64:
        html = (f'<img class="booklyfi-vijenac" '
                f'src="data:image/png;base64,{b64}" '
                f'style="display:block;width:70%;height:auto;'
                f'margin:0.5em auto 0.8em auto;" />')
    else:
        html = '<p class="booklyfi-vijenac" style="text-align:center;">— ✠ —</p>'
    orn = BeautifulSoup(html, "html.parser").find(["img", "p"])
    body.insert(0, copy.deepcopy(orn))


# ═══════════════════════════════════════════════════════════════════════════
# 7. NASLOV
# ═══════════════════════════════════════════════════════════════════════════

def _dodaj_naslov(soup: BeautifulSoup, broj: int) -> None:
    body = soup.find("body")
    if not body:
        return
    # Obriši sve h1-h3 (stari naslovi)
    for h in soup.find_all(["h1", "h2", "h3"]):
        h.decompose()
    h1 = soup.new_tag("h1")
    h1["class"] = "booklyfi-naslov"
    h1.string = f"POGLAVLJE {broj}"
    # Ubaci poslije vijenca (ako postoji), inače na početak
    insert_pos = 0
    for i, child in enumerate(body.children):
        classes = child.get("class") if hasattr(child, "get") else None
        if classes:
            if isinstance(classes, str):
                classes = classes.split()
            if "booklyfi-vijenac" in classes:
                insert_pos = i + 1
                continue
        break
    body.insert(insert_pos, h1)


# ═══════════════════════════════════════════════════════════════════════════
# 8. DROPCAP — 4em, 3+ reda, prvo slovo nevidljivo u tekstu
# ═══════════════════════════════════════════════════════════════════════════

def _dodaj_dropcap(soup: BeautifulSoup) -> bool:
    for p in soup.find_all("p"):
        # Preskoči naslove
        classes = p.get("class") or []
        if isinstance(classes, str):
            classes = classes.split()
        if "booklyfi-naslov" in classes:
            continue

        text = p.get_text(strip=True)
        if len(text) < 60:
            continue
        if text.isdigit():
            continue
        if text[0] in ("—", "–", "-", "‒", "―"):
            continue
        if text[0] in ('"', '„', '“', '«', "'"):
            continue

        # Prvo slovo
        first_char = None
        for content in p.contents:
            if isinstance(content, NavigableString):
                s = str(content).strip()
                if s:
                    first_char = s[0].upper()
                break
            elif hasattr(content, "get_text"):
                t = content.get_text(strip=True)
                if t:
                    first_char = t[0].upper()
                break

        if not first_char or not first_char.isalpha():
            continue

        fname = DROPCAP_MAP.get(first_char)
        if not fname:
            continue
        b64 = _png_b64(fname)
        if not b64:
            continue

        img_html = (
            f'<img class="booklyfi-dropcap" '
            f'src="data:image/png;base64,{b64}" '
            f'style="float:left;display:inline;'
            f'width:4em;height:auto;max-width:none;'
            f'margin:0.1em 0.15em 0 0;padding:0;'
            f'vertical-align:top;" />'
        )

        novi_html = f'<p class="booklyfi-prvi">{img_html}'
        novi_html += f'<span style="font-size:1px;color:transparent;line-height:0;">{first_char}</span>'

        skip = True
        for content in list(p.contents):
            if isinstance(content, NavigableString):
                s = str(content)
                if skip:
                    stripped = s.lstrip()
                    lead = len(s) - len(stripped)
                    s = s[:lead] + stripped[1:]
                    skip = False
                novi_html += s
            else:
                novi_html += str(content)

        novi_html += "</p>"
        novi_p = BeautifulSoup(novi_html, "html.parser").find("p")
        if novi_p:
            p.replace_with(novi_p)
            return True

    return False


# ═══════════════════════════════════════════════════════════════════════════
# 9. DETEKCIJA STVARNIH POGLAVLJA
# ═══════════════════════════════════════════════════════════════════════════

SKIP_FNAME = (
    "cover", "titlepage", "title_page", "copyright",
    "colophon", "toc", "contents", "nav",
    "impressum", "about", "acknowledg", "dedication",
    "epigraph", "foreword", "preface", "introduction",
)

SKIP_TITLES = (
    "sadržaj", "sadrzaj", "table of contents", "contents", "toc",
    "impresum", "copyright", "autorska prava", "sva prava",
    "naslovna", "title page", "cover", "korice",
    "uvod", "uvodne informacije", "uvodna", "predgovor",
    "prolog", "foreword", "preface", "introduction",
    "epilog", "pogovor", "afterword", "epilogue",
    "o autoru", "o piscu", "o knjizi", "o izdanju", "about",
    "bilješka", "biljeska", "napomena", "note",
    "posveta", "dedication", "zahvala", "zahvale",
    "izjave zahvalnosti", "acknowledgments",
    "kazalo", "dodatak", "appendix", "index", "glossary",
    "prolaznost života", "prolaznost zivota",
)

SKIP_FIRST_P = (
    "naslov izvornika", "autorska prava", "copyright",
    "sadržaj", "uvod", "predgovor", "posveta",
    "zahvala", "bilješka", "napomena", "izvorni naslov",
    "izvorno izdanje", "originalno izdanje",
)


def _je_poglavlje(html_bytes: bytes, full_path: str) -> bool:
    # Veličina
    if len(html_bytes) < 8000:
        return False

    # Ime fajla
    fname_low = full_path.lower()
    if any(s in fname_low for s in SKIP_FNAME):
        return False

    # Sadržaj
    try:
        soup = BeautifulSoup(html_bytes.decode("utf-8", errors="replace"), "html.parser")
    except Exception:
        return False

    text = soup.get_text(strip=True)
    if len(text) < 5000:
        return False

    # Naslov
    title = ""
    for tag in ["h1", "h2", "h3", "title"]:
        t = soup.find(tag)
        if t:
            txt = t.get_text(strip=True)
            if txt:
                title = txt
                break

    title_low = title.lower().strip()
    for skip in SKIP_TITLES:
        if title_low == skip or title_low.startswith(skip + " ") or title_low.startswith(skip + ":"):
            return False

    # Prvi <p>
    first_p = soup.find("p")
    if first_p:
        fp_low = first_p.get_text(strip=True).lower()[:100]
        for skip in SKIP_FIRST_P:
            if fp_low.startswith(skip):
                return False

    return True


# ═══════════════════════════════════════════════════════════════════════════
# 10. EPUB I/O
# ═══════════════════════════════════════════════════════════════════════════

def _read(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist()}


def _write(path: Path, files: dict[str, bytes]) -> None:
    tmp_fd, tmp = tempfile.mkstemp(suffix=".epub.tmp", dir=path.parent)
    try:
        with zipfile.ZipFile(tmp, "w") as z:
            if "mimetype" in files:
                z.writestr(zipfile.ZipInfo("mimetype"), files["mimetype"],
                           compress_type=zipfile.ZIP_STORED)
        with zipfile.ZipFile(tmp, "a", zipfile.ZIP_DEFLATED) as z:
            for n, d in files.items():
                if n == "mimetype":
                    continue
                z.writestr(n, d)
        os.close(tmp_fd)
        shutil.move(tmp, str(path))
    except Exception:
        try:
            os.close(tmp_fd)
            os.unlink(tmp)
        except Exception:
            pass
        raise


def _meta(files: dict) -> tuple[str, str]:
    for n, d in files.items():
        if n.endswith(".opf"):
            try:
                s = BeautifulSoup(d, "xml")
                t = s.find("dc:title")
                c = s.find("dc:creator")
                return (
                    c.get_text(strip=True) if c else "Nepoznat_autor",
                    t.get_text(strip=True) if t else "Nepoznat_naslov",
                )
            except Exception:
                pass
    return "Nepoznat_autor", "Nepoznat_naslov"


def _san(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|]', "", s.strip())
    return re.sub(r"\s+", "_", s)


def _ime(c: str, t: str) -> str:
    return f"{_san(c)}_-_{_san(t)}_PREVEDENO_STYLED.epub"


# ═══════════════════════════════════════════════════════════════════════════
# 11. GLAVNA
# ═══════════════════════════════════════════════════════════════════════════

def run_epub_styler(epub_path, output_path=None, fleet=None,
                    log_callback=None, options=None) -> dict:
    epub_path = Path(epub_path)

    def _log(msg, atype="info"):
        logger.info("[styler] %s", msg)
        if log_callback:
            log_callback(msg, atype)

    # ── BOOKLYFI STRANICE (nested — bez NameError) ──
    def _napravi_naslovnu(creator, title):
        import datetime
        year = datetime.datetime.now().year
        css = ("body{background:#F5F0E8;color:#2C1810;font-family:Georgia,serif;"
               "margin:0;padding:3em 5% 2em 5%;text-align:center;}"
               ".booklyfi-label{font-size:0.85em;letter-spacing:0.3em;"
               "color:#8B6914;text-transform:uppercase;margin-bottom:4em;}"
               ".title{font-size:2.4em;font-weight:700;color:#8B0000;"
               "letter-spacing:0.05em;line-height:1.2;margin:2em 0 0.5em 0;}"
               ".author{font-size:1.3em;color:#2C1810;letter-spacing:0.08em;"
               "margin-top:3em;}"
               ".publisher{font-size:0.9em;color:#8B6914;letter-spacing:0.15em;"
               "margin-top:5em;text-transform:uppercase;}"
               ".rule{border:none;border-top:1px solid #8B6914;width:40%;"
               "margin:2em auto;opacity:0.5;}")
        return ('<?xml version="1.0" encoding="utf-8"?>'
                '<!DOCTYPE html>'
                '<html xmlns="http://www.w3.org/1999/xhtml" lang="hr">'
                f'<head><meta charset="utf-8"/><title>Naslovna</title>'
                f'<style>{css}</style></head>'
                '<body>'
                '<div class="booklyfi-label">Booklyfi izdanje</div>'
                '<hr class="rule"/>'
                f'<h1 class="title">{title}</h1>'
                '<hr class="rule"/>'
                f'<p class="author">{creator}</p>'
                f'<div class="publisher">Booklyfi &middot; {year}</div>'
                '</body></html>')

    def _napravi_impresum(creator, title, uid=""):
        import datetime
        year = datetime.datetime.now().year
        uid_line = f'<p><span class="label">ID:</span> {uid}</p>' if uid else ''
        css = ("body{background:#F5F0E8;color:#2C1810;font-family:Georgia,serif;"
               "margin:0 8%;padding:3em 0 2em 0;line-height:1.7;font-size:0.95em;}"
               "h1{color:#8B0000;text-align:center;font-size:1.3em;"
               "letter-spacing:0.15em;margin-bottom:2em;}"
               "h2{color:#5C3A1E;font-size:1em;letter-spacing:0.1em;"
               "margin-top:1.5em;margin-bottom:0.5em;font-style:italic;}"
               "p{margin:0.4em 0;text-indent:0;}"
               ".meta{margin-bottom:2em;}"
               ".meta .label{color:#8B6914;font-size:0.85em;"
               "letter-spacing:0.08em;text-transform:uppercase;}"
               ".booklyfi-block{margin-top:3em;padding-top:1.5em;"
               "border-top:1px solid #8B6914;color:#5C3A1E;font-size:0.9em;}"
               ".center{text-align:center;color:#8B6914;letter-spacing:0.2em;"
               "margin:2em 0;}")
        return ('<?xml version="1.0" encoding="utf-8"?>'
                '<!DOCTYPE html>'
                '<html xmlns="http://www.w3.org/1999/xhtml" lang="hr">'
                f'<head><meta charset="utf-8"/><title>Impresum</title>'
                f'<style>{css}</style></head>'
                '<body>'
                '<h1>IMPRESUM</h1>'
                '<div class="meta">'
                f'<p><span class="label">Naslov:</span> {title}</p>'
                f'<p><span class="label">Autor:</span> {creator}</p>'
                f'<p><span class="label">Izdanje:</span> Booklyfi digitalno izdanje, {year}.</p>'
                f'{uid_line}'
                '</div>'
                '<div class="center">- - -</div>'
                '<h2>O ovom izdanju</h2>'
                '<p>Ovo izdanje pripremljeno je kroz <strong>Booklyfi</strong> '
                'pipeline za pripremu digitalnih izdanja knjizevnih djela. '
                'Tekst je prosao kroz automatsku lekturu, korekturu i '
                'tipografsku obradu.</p>'
                '<h2>Autorska prava</h2>'
                '<p>Sva prava zadrzana. Nijedan dio ove knjige ne smije se '
                'reproducirati, pohranjivati u sustavu za pretrazivanje ili '
                'prenositi u bilo kojem obliku bez prethodnog pisanog '
                'dopustenja nositelja prava.</p>'
                '<p>Digitalno izdanje pripremljeno za osobnu upotrebu.</p>'
                '<h2>Tehnicki podaci</h2>'
                '<p><span class="label">Format:</span> EPUB 3</p>'
                '<p><span class="label">Pismo:</span> Latinica (ijekavica)</p>'
                '<p><span class="label">Tipografija:</span> Georgia, EB Garamond</p>'
                '<div class="booklyfi-block">'
                '<p style="text-align:center;letter-spacing:0.15em;">BOOKLYFI</p>'
                f'<p style="text-align:center;font-size:0.85em;">Digitalna izdanja &middot; {year}</p>'
                '</div>'
                '</body></html>')

    result = {"ok": False, "epub_path": "", "chapters": 0,
              "dropcaps_added": 0, "toc_created": False, "error": None}

    if not epub_path.exists():
        result["error"] = f"Ne postoji: {epub_path}"
        return result

    _log(f"📖 {epub_path.name}", "system")

    try:
        files = _read(epub_path)
    except Exception as e:
        result["error"] = f"Čitanje: {e}"
        return result

    # Izlaz
    if output_path:
        out = Path(output_path)
    else:
        c, t = _meta(files)
        od = Path(STYLED_OUTPUT_DIR)
        od.mkdir(parents=True, exist_ok=True)
        out = od / _ime(c, t)

    # Nađi OPF
    opf_path = next((n for n in files if n.endswith(".opf")), None)
    if not opf_path:
        result["error"] = "Nema OPF"
        return result

    opf_soup = BeautifulSoup(files[opf_path], "xml")
    spine = opf_soup.find("spine")
    manifest = opf_soup.find("manifest")
    if not spine or not manifest:
        result["error"] = "Nema spine/manifest"
        return result

    id_to_href = {}
    for it in manifest.find_all("item"):
        iid = it.get("id", "")
        href = it.get("href", "")
        if href.lower().endswith((".html", ".xhtml", ".htm")):
            id_to_href[iid] = href

    opf_dir = str(Path(opf_path).parent)
    if opf_dir == ".":
        opf_dir = ""

    # Nađi poglavlja
    poglavlja = []
    for itemref in spine.find_all("itemref"):
        iid = itemref.get("idref", "")
        href = id_to_href.get(iid, "")
        if not href:
            continue
        full = f"{opf_dir}/{href}" if opf_dir else href
        hb = files.get(full) or files.get(href)
        if not hb:
            continue
        if _je_poglavlje(hb, full):
            poglavlja.append({
                "href": href, "full_path": full,
                "order": len(poglavlja) + 1,
            })

    _log(f"   → {len(poglavlja)} stvarnih poglavlja", "tech")

    # ── BOOKLYFI STRANICE (naslovna + impresum) ──
    creator_name, book_title = _meta(files)
    book_uid = "booklyfi"
    for n, d in files.items():
        if n.endswith(".opf"):
            try:
                s = BeautifulSoup(d, "xml")
                u = s.find("dc:identifier")
                if u:
                    book_uid = u.get_text(strip=True)
            except Exception:
                pass
            break

    naslovna_path = f"{opf_dir}/booklyfi_001_naslovna.xhtml" if opf_dir else "booklyfi_001_naslovna.xhtml"
    impresum_path = f"{opf_dir}/booklyfi_002_impresum.xhtml" if opf_dir else "booklyfi_002_impresum.xhtml"

    files[naslovna_path] = _napravi_naslovnu(creator_name, book_title).encode("utf-8")
    files[impresum_path] = _napravi_impresum(creator_name, book_title, book_uid).encode("utf-8")

    # Dodaj u OPF manifest
    opf_str_tmp = files[opf_path].decode("utf-8", errors="replace")
    naslovna_href = Path(naslovna_path).name
    impresum_href = Path(impresum_path).name
    opf_str_tmp = opf_str_tmp.replace(
        "</manifest>",
        f'<item id="booklyfi-naslovna" href="{naslovna_href}" media-type="application/xhtml+xml"/>'
        f'<item id="booklyfi-impresum" href="{impresum_href}" media-type="application/xhtml+xml"/>'
        "</manifest>"
    )
    # Dodaj na početak spine-a
    opf_str_tmp = re.sub(
        r'(<spine[^>]*>)',
        r'\1<itemref idref="booklyfi-naslovna"/><itemref idref="booklyfi-impresum"/>',
        opf_str_tmp,
        count=1,
    )
    files[opf_path] = opf_str_tmp.encode("utf-8")
    _log(f"   → Booklyfi naslovna + impresum dodani", "tech")

    # Obrada poglavlja
    dropcaps = 0
    for p in poglavlja:
        full = p["full_path"]
        soup = BeautifulSoup(files[full].decode("utf-8", errors="replace"), "html.parser")

        _ukloni_sve(soup)
        _normalizuj(soup)
        _dijalog(soup)
        _dodaj_vijenac(soup)
        _dodaj_naslov(soup, p["order"])
        if _dodaj_dropcap(soup):
            dropcaps += 1

        # CSS
        head = soup.find("head")
        if not head:
            head = soup.new_tag("head")
            if soup.html:
                soup.html.insert(0, head)
            else:
                soup.insert(0, head)
        st = soup.new_tag("style", type="text/css")
        st.string = CSS
        head.append(st)

        files[full] = str(soup).encode("utf-8")

    _log(f"   → {dropcaps} dropcapa", "tech")

    # ── OBRIŠI SVE HTML FAJLOVE KOJI NISU POGLAVLJA ──
    # ZADRŽI: poglavlja + booklyfi_* (naslovna, impresum, toc) + cover
    poglavlja_paths = {p["full_path"] for p in poglavlja}
    for n in list(files.keys()):
        low = n.lower()
        if not low.endswith((".html", ".xhtml", ".htm")):
            continue
        if n in poglavlja_paths:
            continue
        # Zadrži booklyfi_* (naslovna, impresum, toc)
        if "booklyfi_" in low:
            continue
        # Zadrži cover
        if "cover" in low:
            continue
        # Obriši front/back matter HTML
        del files[n]

    # ── OBRIŠI SVE STARE TOC/NCX
    for n in list(files.keys()):
        low = n.lower()
        if low.endswith(".ncx"):
            del files[n]
            continue
        if low.endswith((".html", ".xhtml", ".htm")):
            if "toc" in low or "sadrzaj" in low or "contents" in low:
                content = files[n].decode("utf-8", errors="replace")[:3000].lower()
                if "<nav" in content or "toc" in low:
                    del files[n]

    # Novi NCX
    book_title = "Knjiga"
    book_uid = "booklyfi"
    for n, d in files.items():
        if n.endswith(".opf"):
            s = BeautifulSoup(d, "xml")
            t = s.find("dc:title")
            if t:
                book_title = t.get_text(strip=True)
            u = s.find("dc:identifier")
            if u:
                book_uid = u.get_text(strip=True)
            break

    ncx_path = f"{opf_dir}/toc.ncx" if opf_dir else "toc.ncx"
    navpoints = "\n".join(
        f'  <navPoint id="np-{p["order"]}" playOrder="{p["order"]}">'
        f'<navLabel><text>POGLAVLJE {p["order"]}</text></navLabel>'
        f'<content src="{p["href"]}"/></navPoint>'
        for p in poglavlja
    )
    files[ncx_path] = f'''<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
<head><meta name="dtb:uid" content="{book_uid}"/><meta name="dtb:depth" content="1"/></head>
<docTitle><text>{book_title}</text></docTitle>
<navMap>
{navpoints}
</navMap>
</ncx>'''.encode("utf-8")

    # Novi TOC HTML
    toc_path = f"{opf_dir}/booklyfi_toc.xhtml" if opf_dir else "booklyfi_toc.xhtml"
    items = "\n".join(
        f'<li><a href="{p["href"]}">POGLAVLJE {p["order"]}</a></li>'
        for p in poglavlja
    )
    files[toc_path] = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="hr">
<head><meta charset="utf-8"/><title>Sadržaj</title>
<style>body{{background:#F5F0E8;color:#2C1810;font-family:Georgia,serif;margin:0 8%;padding:2em 0;}}
h1{{text-align:center;color:#8B0000;}}ul{{list-style:none;padding:0;}}
li{{padding:0.4em 0;border-bottom:1px dotted #8B6914;}}
a{{color:#2C1810;text-decoration:none;}}</style></head>
<body><h1>Sadržaj</h1><ul>
{items}
</ul></body></html>'''.encode("utf-8")

    # Ažuriraj OPF
    opf_str = files[opf_path].decode("utf-8", errors="replace")

    # Ukloni iz manifesta sve iteme koji referenciraju obrisane fajlove
    sve_u_epub = set(files.keys())
    def _ukloni_item(match):
        href = match.group(1)
        # Ako fajl ne postoji u files, ukloni item
        for n in files:
            if n.endswith(href) or href.endswith(Path(n).name):
                return match.group(0)  # zadrži
        return ''  # ukloni

    # Jednostavnije: prođi kroz manifest i ukloni iteme čiji href ne postoji
    manifest_soup = BeautifulSoup(opf_str, "xml")
    manifest_el = manifest_soup.find("manifest")
    if manifest_el:
        for item in manifest_el.find_all("item"):
            href = item.get("href", "")
            # Provjeri da li postoji u files
            if opf_dir:
                full_href = f"{opf_dir}/{href}"
            else:
                full_href = href
            if full_href not in files and href not in files:
                item.decompose()
        # Ukloni iz spine-a itemref koji referenciraju nepostojeće iteme
        spine_el = manifest_soup.find("spine")
        if spine_el:
            valid_ids = {it.get("id") for it in manifest_el.find_all("item")}
            for itemref in spine_el.find_all("itemref"):
                iid = itemref.get("idref")
                if iid and iid not in valid_ids and iid != "booklyfi-toc":
                    itemref.decompose()
        opf_str = str(manifest_soup)
    # Ukloni stare (ali NE booklyfi-naslovna/impresum)
    opf_str = re.sub(r'<item[^>]*id="(?:booklyfi-toc|ncx|toc)"[^>]*/>', '', opf_str, flags=re.I)
    opf_str = re.sub(r'<itemref[^>]*idref="(?:booklyfi-toc|toc)"[^>]*/>', '', opf_str, flags=re.I)
    # Dodaj nove
    opf_str = opf_str.replace("</manifest>",
        f'<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
        f'<item id="booklyfi-toc" href="booklyfi_toc.xhtml" media-type="application/xhtml+xml"/>'
        "</manifest>")
    opf_str = re.sub(r'(<spine[^>]*>)', r'\1<itemref idref="booklyfi-toc"/>', opf_str, count=1)
    if 'toc="ncx"' not in opf_str[:2000]:
        opf_str = re.sub(r'<spine(?![^>]*\btoc=)', '<spine toc="ncx"', opf_str, count=1)
    files[opf_path] = opf_str.encode("utf-8")

    # Snimi
    _log("💾 Snimam...", "tech")
    _write(out, files)

    result.update({
        "ok": True, "epub_path": str(out),
        "chapters": len(poglavlja),
        "dropcaps_added": dropcaps,
        "toc_created": True,
    })
    _log(f"✅ {out.name} ({len(poglavlja)} pogl, {dropcaps} dropcap)", "success")
    return result


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if len(sys.argv) < 2:
        print("Upotreba: python -m epub.styler <knjiga.epub> [izlaz.epub]")
        sys.exit(1)
    res = run_epub_styler(
        sys.argv[1],
        output_path=sys.argv[2] if len(sys.argv) > 2 else None,
        log_callback=lambda m, t="info": print(f"  {m}"),
    )
    print(f"\n{'✅ OK' if res['ok'] else '❌ ' + str(res['error'])}")
    if res["ok"]:
        print(f"   EPUB:      {res['epub_path']}")
        print(f"   Poglavlja: {res['chapters']}")
        print(f"   Dropcaps:  {res['dropcaps_added']}")
