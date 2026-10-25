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

from bs4 import BeautifulSoup

_PNG_CACHE: dict[str, str] = {}


logger = logging.getLogger(__name__)


STYLED_OUTPUT_DIR = "/storage/emulated/0/Books/MoonReader/STYLED"


ORNAMENTS_DIR = "/storage/emulated/0/Books/MoonReader/ornaments_small_size"


CENTER_ORNAMENT_PNG = "center_ornament.png"


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


CSS = """
body { background:#FDF6E3; color:#3E2723; font-family:Georgia,serif;
       font-size:1em; line-height:1.6; margin:0 5%; padding:0; }
p { margin:0; padding:0; text-indent:1.8em; font-size:1em; line-height:1.6; }
p.booklyfi-prvi { text-indent:0; margin-top:0.5em; margin-bottom:0.3em; }
p.booklyfi-dijalog { margin:0.3em 0; padding-left:1.5em; text-indent:-1em; }
h1.booklyfi-naslov { color:#5D4037; text-align:center;
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
        new = re.sub(r"\b([A-ZŠĐČĆŽ])\1+([a-zšđčćž])", r"\1\2", orig)
        if new != orig:
            text_node.replace_with(new)


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


def _dodaj_vijenac(soup: BeautifulSoup) -> None:
    b64 = _png_b64(CENTER_ORNAMENT_PNG)
    body = soup.find("body")
    if not body:
        return
    if b64:
        html = (
            f'<img class="booklyfi-vijenac" '
            f'src="data:image/png;base64,{b64}" '
            f'style="display:block;width:70%;height:auto;'
            f'margin:0.5em auto 0.8em auto;" />'
        )
    else:
        html = '<p class="booklyfi-vijenac" style="text-align:center;">— ✠ —</p>'
    orn = BeautifulSoup(html, "html.parser").find(["img", "p"])
    body.insert(0, copy.deepcopy(orn))


SKIP_FNAME = (
    "cover",
    "titlepage",
    "title_page",
    "copyright",
    "colophon",
    "toc",
    "contents",
    "nav",
    "impressum",
    "about",
    "acknowledg",
    "dedication",
    "epigraph",
    "foreword",
    "preface",
    "introduction",
)


SKIP_FIRST_P = (
    "naslov izvornika",
    "autorska prava",
    "copyright",
    "sadržaj",
    "uvod",
    "predgovor",
    "posveta",
    "zahvala",
    "bilješka",
    "napomena",
    "izvorni naslov",
    "izvorno izdanje",
    "originalno izdanje",
)


_DEBUG_JE_POGLAVLJE = False  # isključeno


def _read(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist()}


def _write(path: Path, files: dict[str, bytes]) -> None:
    tmp_fd, tmp = tempfile.mkstemp(suffix=".epub.tmp", dir=path.parent)
    try:
        with zipfile.ZipFile(tmp, "w") as z:
            if "mimetype" in files:
                z.writestr(
                    zipfile.ZipInfo("mimetype"),
                    files["mimetype"],
                    compress_type=zipfile.ZIP_STORED,
                )
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


SKIP_TITLES = (
    "sadržaj",
    "sadrzaj",
    "table of contents",
    "contents",
    "toc",
    "impresum",
    "copyright",
    "autorska prava",
    "sva prava",
    "naslovna",
    "title page",
    "cover",
    "korice",
    "kazalo",
    "index",
)


def _je_poglavlje(html_bytes, full_path):
    def _dbg(r):
        if _DEBUG_JE_POGLAVLJE:
            logger.info("[styler] _je_poglavlje ODBIJEN %s: %s", full_path, r)

    if len(html_bytes) < 2000:
        _dbg("prekratak HTML")
        return False

    basename = Path(full_path).name.lower()
    if any(s in basename for s in SKIP_FNAME):
        _dbg("basename: " + basename)
        return False

    try:
        soup = BeautifulSoup(
            html_bytes.decode("utf-8", errors="replace"), "html.parser"
        )
    except Exception as e:
        _dbg("BS: " + str(e))
        return False

    text = soup.get_text(strip=True)
    if len(text) < 500:
        _dbg("prekratak tekst")
        return False

    title = ""
    for tag in ("h1", "h2", "h3", "title"):
        t = soup.find(tag)
        if t and t.get_text(strip=True):
            title = t.get_text(strip=True)
            break

    tl = title.lower().strip()
    for skip in SKIP_TITLES:
        if tl == skip or tl.startswith((skip + " ", skip + ":")):
            return False

    fp = soup.find("p")
    if fp:
        fpl = fp.get_text(strip=True).lower()[:100]
        for skip in SKIP_FIRST_P:
            if fpl.startswith(skip):
                _dbg("first_p: " + fpl)
                return False

    return True


def _izvuci_toc_mapu(files, opf_dir):
    mapa = {}
    for n in files:
        if not n.lower().endswith((".html", ".xhtml", ".htm")):
            continue
        try:
            s = BeautifulSoup(files[n], "html.parser")
            nav = s.find("nav", attrs={"epub:type": "toc"})
            if not nav:
                continue
            for a in nav.find_all("a"):
                nas = a.get_text(strip=True)
                href = a.get("href", "").split("#")[0]
                if nas and href:
                    if opf_dir and not href.startswith(opf_dir):
                        href = (
                            (opf_dir + "/" + href)
                            if not href.startswith("/")
                            else href.lstrip("/")
                        )
                    mapa[href] = nas
            if mapa:
                return mapa
        except Exception:
            pass

    ncx = next((n for n in files if n.lower().endswith(".ncx")), None)
    if ncx:
        try:
            soup = BeautifulSoup(files[ncx], "xml")
            for nav in soup.find_all("navPoint"):
                lab = nav.find("navLabel")
                con = nav.find("content")
                if lab and con:
                    nas = lab.get_text(strip=True)
                    s2 = con.get("src", "").split("#")[0]
                    if nas and s2:
                        if opf_dir and not s2.startswith(opf_dir):
                            s2 = (
                                (opf_dir + "/" + s2)
                                if not s2.startswith("/")
                                else s2.lstrip("/")
                            )
                        mapa[s2] = nas
            if mapa:
                return mapa
        except Exception:
            pass
    return mapa


def _dodaj_naslov(soup, broj, naslov=None):
    body = soup.find("body")
    if not body:
        return

    nasao_tekst = False
    for child in list(body.children):
        if not hasattr(child, "name"):
            continue
        if child.name in ("h1", "h2", "h3"):
            if not nasao_tekst:
                child.decompose()
            continue
        if child.name == "p" and len(child.get_text(strip=True)) > 50:
            nasao_tekst = True
            break

    h1 = soup.new_tag("h1")
    h1["class"] = "booklyfi-naslov"
    h1.string = naslov if naslov else ("POGLAVLJE %d" % broj)

    insert_pos = 0
    for i, child in enumerate(body.children):
        cls = child.get("class") if hasattr(child, "get") else None
        if cls:
            if isinstance(cls, str):
                cls = cls.split()
            if "booklyfi-vijenac" in cls:
                insert_pos = i + 1
                continue
        break
    body.insert(insert_pos, h1)


def _dodaj_dropcap(soup):
    from bs4 import NavigableString

    for p in soup.find_all("p"):
        cls = p.get("class") or []
        if isinstance(cls, str):
            cls = cls.split()
        if "booklyfi-naslov" in cls or "booklyfi-prvi" in cls:
            continue

        text = p.get_text(strip=True)
        if len(text) < 60 or text.isdigit():
            continue
        if text[0] in ("—", "–", "-", "‒", "―"):
            continue
        if text[0] in ('"', "„", '"', '"', "«", "'"):
            continue

        prvo = None
        cvor = None
        for desc in p.descendants:
            if not isinstance(desc, NavigableString):
                continue
            s = str(desc)
            for i, ch in enumerate(s):
                if ch.isalpha():
                    prvo = ch.upper()
                    cvor = (desc, i)
                    break
            if prvo:
                break

        if not prvo:
            continue

        fname = DROPCAP_MAP.get(prvo)
        if not fname:
            continue
        b64 = _png_b64(fname)
        if not b64:
            continue

        desc_node, idx = cvor
        s_orig = str(desc_node)
        desc_node.replace_with(NavigableString(s_orig[:idx] + s_orig[idx + 1 :]))

        img_html = (
            '<img class="booklyfi-dropcap" '
            'src="data:image/png;base64,' + b64 + '" '
            'style="float:left;display:inline;'
            "width:4em;height:auto;max-width:none;"
            "margin:0.1em 0.15em 0 0;padding:0;"
            'vertical-align:top;" />'
        )
        skriveno_html = (
            '<span style="font-size:1px;color:transparent;line-height:0;">'
            + prvo
            + "</span>"
        )
        img_tag = BeautifulSoup(img_html, "html.parser").find("img")
        skriveno_tag = BeautifulSoup(skriveno_html, "html.parser").find("span")

        p.insert(0, skriveno_tag)
        p.insert(0, img_tag)
        p["class"] = list(cls) + ["booklyfi-prvi"]
        return True

    return False


def _ekstrahuj_zajednicke_slike(files: dict) -> list[str]:
    """
    2026-10-24 B7: dedup inline base64 slike u zajednicke PNG/JPG fajlove.
    Zamena src="data:image/png;base64,XXX" sa relativnim putem do PNG-a.
    Vraca listu novih putanja (za OPF manifest).
    """
    import base64 as _b64_b7
    import hashlib as _hl_b7
    import os as _os_b7

    RX = re.compile(r"data:image/(png|jpeg|jpg);base64,([A-Za-z0-9+/=]+)")
    EXT_MAP = {"png": "png", "jpeg": "jpg", "jpg": "jpg"}

    unique: dict[str, bytes] = {}
    b64_hash_ext: dict[str, tuple] = {}

    for name, data in files.items():
        if not name.endswith((".xhtml", ".html", ".htm")):
            continue
        try:
            text = data.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            continue
        for m in RX.finditer(text):
            fmt = m.group(1).lower()
            b64 = m.group(2)
            if b64 in b64_hash_ext:
                continue
            try:
                raw = _b64_b7.b64decode(b64, validate=False)
            except Exception:
                continue
            h = _hl_b7.sha256(raw).hexdigest()[:16]
            ext = EXT_MAP.get(fmt, "png")
            unique[h] = raw
            b64_hash_ext[b64] = (h, ext)

    if not unique:
        return []

    new_paths: list[str] = []
    for h, raw in unique.items():
        ext = next((e for (hh, e) in b64_hash_ext.values() if hh == h), "png")
        path = f"images/booklyfi-shared-{h}.{ext}"
        if path not in files:
            files[path] = raw
            new_paths.append(path)

    for name in list(files.keys()):
        if not name.endswith((".xhtml", ".html", ".htm")):
            continue
        try:
            text = files[name].decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            continue
        dirname = _os_b7.path.dirname(name) or "."

        def _repl(m, _dirname=dirname):
            b64 = m.group(2)
            h, ext = b64_hash_ext[b64]
            png_path = f"images/booklyfi-shared-{h}.{ext}"
            return _os_b7.path.relpath(png_path, _dirname)

        new_text = RX.sub(_repl, text)
        if new_text != text:
            files[name] = new_text.encode("utf-8")

    return new_paths


def run_epub_styler(
    epub_path, output_path=None, fleet=None, log_callback=None, options=None
):
    import datetime as _dt
    import html as _html
    import re as _re

    epub_path = Path(epub_path)

    def _log(msg, atype="info"):
        logger.info("[styler] %s", msg)
        if log_callback:
            log_callback(msg, atype)

    def _esc(s):
        return _html.escape(str(s or ""), quote=True)

    def _page(title, body_html):
        css = (
            "body{background:#FDF6E3;color:#3E2723;font-family:Georgia,serif;"
            "margin:0 8%;padding:3em 0;line-height:1.7;font-size:1em;}"
            "h1,h2{color:#5D4037;}h1{text-align:center;font-size:1.5em;}"
            "hr{border:none;border-top:1px solid #8B6914;width:40%;margin:2em auto;}"
            "ul{list-style:none;padding:0;}"
            "li{padding:0.4em 0;border-bottom:1px dotted #8B6914;}"
            "a{color:#3E2723;text-decoration:none;}"
        )
        return (
            '<?xml version="1.0" encoding="utf-8"?>'
            "<!DOCTYPE html>"
            '<html xmlns="http://www.w3.org/1999/xhtml" lang="hr">'
            '<head><meta charset="utf-8"/><title>' + _esc(title) + "</title>"
            "<style>" + css + "</style></head><body>" + body_html + "</body></html>"
        )

    GENERIC_RX = _re.compile(
        r"^(?:part\s*\d+|chapter\s*\d+|ch\.?\s*\d+|"
        r"poglavlje\s*\d+|odjeljak\s*\d+|section\s*\d+|"
        r"book\s*\d+|knjiga\s*\d+)$",
        _re.I,
    )

    def _naslov_iz(hb, toc_naslov, book_title):
        if toc_naslov and not GENERIC_RX.match(toc_naslov.strip()):
            return toc_naslov
        try:
            s = BeautifulSoup(hb, "html.parser")
            for tag in ("h1", "h2", "h3"):
                h = s.find(tag)
                if h:
                    t = h.get_text(strip=True)
                    if t and 0 < len(t) < 120:
                        return t
            tt = s.find("title")
            if tt:
                t = tt.get_text(strip=True)
                if t and 0 < len(t) < 120:
                    if not book_title or t.lower() != book_title.lower():
                        return t
        except Exception:
            pass
        return None

    def _classify(hb, href, toc_naslov, book_title, cover_hrefs):
        try:
            s = BeautifulSoup(hb, "html.parser")
            for tag in s(["script", "style"]):
                tag.decompose()
            tt = s.find("title")
            title = (tt.get_text(strip=True) if tt else "").lower()
            imgs = len(s.find_all(["img", "svg", "image"]))
            text = s.get_text(" ", strip=True)
            tlen = len(text)
            tlow = text[:1200].lower()
            href_base = href.rsplit("/", 1)[-1]

            if href in cover_hrefs or href_base in cover_hrefs:
                return False, "cover(opf)", None
            if title == "cover":
                return False, "cover(title)", None
            if imgs >= 1 and tlen < 30:
                return False, "samo-slika", None

            cpy = (
                "\u00a9",
                "copyright",
                "sva prava",
                "all rights",
                "autorska prava",
                "isbn",
                "published by",
                "first published",
                "originally published",
            )
            if any(m in tlow for m in cpy):
                return False, "copyright", None

            mk = (
                "discovery page",
                "about this book",
                "discover more",
                "otkrijte svoje",
            )
            if any(m in title or m in tlow for m in mk):
                return False, "marketing", None

            if "table of contents" in title or "inhaltsverzeichnis" in title:
                return False, "toc(title)", None
            if (
                ("sadrzaj" in tlow or "sadr\u017eaj" in tlow)
                and ("naslovnica" in tlow or "naslovna stranica" in tlow)
                and "autorska prava" in tlow
            ):
                return False, "toc(kombinacija)", None

            return True, "ok", _naslov_iz(hb, toc_naslov, book_title)
        except Exception as e:
            return False, "greska:" + str(e), None

    try:
        files = _read(epub_path)
    except Exception as e:
        return {"ok": False, "error": "Citanje: " + str(e)}

    opf_path = next((n for n in files if n.endswith(".opf")), None)
    if not opf_path:
        return {"ok": False, "error": "Nema OPF"}

    opf_soup = BeautifulSoup(files[opf_path], "xml")
    spine = opf_soup.find("spine")
    manifest = opf_soup.find("manifest")
    if not spine or not manifest:
        return {"ok": False, "error": "Nema spine/manifest"}

    opf_dir = str(Path(opf_path).parent)
    if opf_dir == ".":
        opf_dir = ""

    cover_hrefs = set()
    for it in manifest.find_all("item"):
        if "cover-image" in (it.get("properties") or ""):
            cover_hrefs.add(it.get("href", ""))
            cover_hrefs.add(it.get("id", ""))
    for meta in opf_soup.find_all("meta", attrs={"name": "cover"}):
        cid = meta.get("content")
        if cid:
            for it in manifest.find_all("item"):
                if it.get("id") == cid:
                    cover_hrefs.add(it.get("href", ""))
    guide = opf_soup.find("guide")
    if guide:
        for ref in guide.find_all("reference", attrs={"type": "cover"}):
            h = ref.get("href", "").split("#")[0]
            if h:
                cover_hrefs.add(h)

    toc_mapa = _izvuci_toc_mapu(files, opf_dir)
    _log("   -> TOC mapa: %d naslova" % len(toc_mapa), "tech")

    creator, book_title = _meta(files)
    book_uid = "booklyfi"
    dc_lang = "hr"
    for n, d in files.items():
        if n.endswith(".opf"):
            try:
                osoup = BeautifulSoup(d, "xml")
                u = osoup.find("dc:identifier")
                if u:
                    book_uid = u.get_text(strip=True)
                lg = osoup.find("dc:language")
                if lg:
                    dc_lang = lg.get_text(strip=True) or "hr"
            except Exception:
                pass
            break

    for n in list(files.keys()):
        low = n.lower()
        if not low.endswith((".html", ".xhtml", ".htm", ".ncx")):
            continue
        if "booklyfi_" in low:
            continue
        if low.endswith(".ncx"):
            del files[n]
            _log("   -> Obrisan NCX: " + n, "tech")
            continue
        try:
            s = BeautifulSoup(files[n], "html.parser")
            if s.find("nav", attrs={"epub:type": "toc"}):
                del files[n]
                _log("   -> Obrisan NAV TOC: " + n, "tech")
                continue
        except Exception:
            pass
        if any(kw in low for kw in ("toc", "sadrzaj", "contents", "nav.")):
            del files[n]
            _log("   -> Obrisan stari TOC: " + n, "tech")

    id_to_href = {}
    for it in manifest.find_all("item"):
        href = it.get("href", "")
        if href.lower().endswith((".html", ".xhtml", ".htm")):
            id_to_href[it.get("id", "")] = href

    poglavlja = []
    for itemref in spine.find_all("itemref"):
        href = id_to_href.get(itemref.get("idref", ""), "")
        if not href:
            continue
        full = (opf_dir + "/" + href) if opf_dir else href
        hb = files.get(full) or files.get(href)
        if not hb:
            continue
        toc_naslov = toc_mapa.get(href) or toc_mapa.get(full)
        keep, razlog, finalni = _classify(hb, href, toc_naslov, book_title, cover_hrefs)
        if not keep:
            _log("   -> Skip (%s): %s" % (razlog, href), "tech")
            continue
        poglavlja.append(
            {
                "href": href,
                "full_path": full,
                "order": len(poglavlja) + 1,
                "naslov": finalni,
            }
        )

    _log("   -> %d poglavlja" % len(poglavlja), "tech")

    dropcaps = 0
    for p in poglavlja:
        soup = BeautifulSoup(
            files[p["full_path"]].decode("utf-8", errors="replace"), "html.parser"
        )
        _ukloni_sve(soup)
        _normalizuj(soup)
        _dijalog(soup)
        _dodaj_vijenac(soup)
        if p.get("naslov"):
            _dodaj_naslov(soup, p["order"], naslov=p["naslov"])
        else:
            _dodaj_naslov(soup, p["order"])
        if _dodaj_dropcap(soup):
            dropcaps += 1
        head = soup.find("head")
        if not head:
            head = soup.new_tag("head")
            parent = soup.html if soup.html else soup
            parent.insert(0, head)
        st = soup.new_tag("style", type="text/css")
        st.string = CSS
        head.append(st)
        files[p["full_path"]] = str(soup).encode("utf-8")

    _log("   -> %d dropcapa" % dropcaps, "tech")

    nas_path = (
        (opf_dir + "/booklyfi_001_naslovna.xhtml")
        if opf_dir
        else "booklyfi_001_naslovna.xhtml"
    )
    imp_path = (
        (opf_dir + "/booklyfi_002_impresum.xhtml")
        if opf_dir
        else "booklyfi_002_impresum.xhtml"
    )
    year = _dt.datetime.now().year
    nas_body = (
        '<div style="text-align:center;padding:3em 5% 0;">'
        '<p style="font-size:0.85em;letter-spacing:0.3em;color:#8B6914;">BOOKLYFI IZDANJE</p>'
        '<hr/><h1 style="font-size:2.4em;">' + _esc(book_title) + "</h1>"
        '<hr/><p style="font-size:1.3em;margin-top:3em;">' + _esc(creator) + "</p>"
        '<p style="font-size:0.9em;color:#8B6914;margin-top:5em;">Booklyfi &#183; '
        + str(year)
        + "</p></div>"
    )
    imp_body = (
        '<h1 style="text-align:center;">IMPRESUM</h1>'
        "<p><b>Naslov:</b> " + _esc(book_title) + "</p>"
        "<p><b>Autor:</b> " + _esc(creator) + "</p>"
        "<p><b>ID:</b> " + _esc(book_uid) + "</p>"
        "<p><b>Izdanje:</b> Booklyfi digitalno izdanje, " + str(year) + ".</p>"
        "<p><b>Format:</b> EPUB 3</p><p>Sva prava zadrzana.</p>"
    )
    files[nas_path] = _page("Naslovna", nas_body).encode("utf-8")
    files[imp_path] = _page("Impresum", imp_body).encode("utf-8")

    ncx_path = (opf_dir + "/toc.ncx") if opf_dir else "toc.ncx"
    nps = []
    for p in poglavlja:
        nas = p.get("naslov") or ("POGLAVLJE %d" % p["order"])
        nps.append(
            '<navPoint id="np-%d" playOrder="%d"><navLabel><text>%s</text></navLabel>'
            '<content src="%s"/></navPoint>'
            % (p["order"], p["order"], _esc(nas), _esc(p["href"]))
        )
    files[ncx_path] = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
        '<head><meta name="dtb:uid" content="' + _esc(book_uid) + '"/>'
        '<meta name="dtb:depth" content="1"/></head>'
        "<docTitle><text>" + _esc(book_title) + "</text></docTitle>"
        "<navMap>" + "".join(nps) + "</navMap></ncx>"
    ).encode("utf-8")

    nav_path = (opf_dir + "/nav.xhtml") if opf_dir else "nav.xhtml"
    nav_its = []
    for p in poglavlja:
        nas = p.get("naslov") or ("POGLAVLJE %d" % p["order"])
        nav_its.append('<li><a href="%s">%s</a></li>' % (_esc(p["href"]), _esc(nas)))
    first_href = poglavlja[0]["href"] if poglavlja else Path(nas_path).name
    nav_body = (
        '<nav epub:type="toc" id="toc"><h1>Sadržaj</h1><ol>'
        + "".join(nav_its)
        + "</ol></nav>"
        '<nav epub:type="landmarks" hidden="hidden"><h2>Orijentiri</h2><ol>'
        '<li><a epub:type="titlepage" href="'
        + _esc(Path(nas_path).name)
        + '">Naslovna</a></li>'
        '<li><a epub:type="copyright-page" href="'
        + _esc(Path(imp_path).name)
        + '">Impresum</a></li>'
        '<li><a epub:type="bodymatter" href="' + _esc(first_href) + '">Početak</a></li>'
        "</ol></nav>"
    )
    files[nav_path] = (
        '<?xml version="1.0" encoding="utf-8"?>'
        "<!DOCTYPE html>"
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
        'lang="' + _esc(dc_lang) + '">'
        '<head><meta charset="utf-8"/><title>Sadržaj</title></head>'
        "<body>" + nav_body + "</body></html>"
    ).encode("utf-8")

    opf_soup = BeautifulSoup(files[opf_path], "xml")
    mtag = opf_soup.find("manifest")
    stag = opf_soup.find("spine")
    existing = set(files.keys())
    for it in list(mtag.find_all("item")):
        href = it.get("href", "")
        fh = (opf_dir + "/" + href) if opf_dir else href
        if fh not in existing and href not in existing:
            it.decompose()
    gd = opf_soup.find("guide")
    if gd:
        for ref in list(gd.find_all("reference")):
            h = ref.get("href", "").split("#")[0]
            fh = (opf_dir + "/" + h) if opf_dir else h
            if fh not in existing and h not in existing:
                ref.decompose()

    for iid, path, mt in (
        ("booklyfi-naslovna", nas_path, "application/xhtml+xml"),
        ("booklyfi-impresum", imp_path, "application/xhtml+xml"),
        ("ncx", ncx_path, "application/x-dtbncx+xml"),
    ):
        for old in mtag.find_all("item", id=iid):
            old.decompose()
        ni = opf_soup.new_tag("item")
        ni["id"] = iid
        ni["href"] = Path(path).name
        ni["media-type"] = mt
        mtag.append(ni)
    for old in mtag.find_all("item", id="nav"):
        old.decompose()
    ni = opf_soup.new_tag("item")
    ni["id"] = "nav"
    ni["href"] = Path(nav_path).name
    ni["media-type"] = "application/xhtml+xml"
    ni["properties"] = "nav"
    mtag.append(ni)

    if not opf_soup.find("meta", attrs={"property": "dcterms:modified"}):
        now = _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        meta = opf_soup.new_tag("meta")
        meta["property"] = "dcterms:modified"
        meta.string = now
        md = opf_soup.find("metadata")
        if md:
            md.append(meta)

    orig_ids = [ir.get("idref") for ir in stag.find_all("itemref")]
    for ir in stag.find_all("itemref"):
        ir.decompose()
    for iid in ("booklyfi-naslovna", "booklyfi-impresum"):
        ir = opf_soup.new_tag("itemref")
        ir["idref"] = iid
        stag.append(ir)
    for iid in orig_ids:
        if iid in ("booklyfi-naslovna", "booklyfi-impresum", "nav", "ncx"):
            continue
        ir = opf_soup.new_tag("itemref")
        ir["idref"] = iid
        stag.append(ir)
    if not stag.get("toc"):
        stag["toc"] = "ncx"
    files[opf_path] = str(opf_soup).encode("utf-8")

    if output_path:
        out = Path(output_path)
    else:
        od = Path(STYLED_OUTPUT_DIR)
        od.mkdir(parents=True, exist_ok=True)
        out = od / _ime(creator, book_title)
    _write(out, files)

    return {
        "ok": True,
        "epub_path": str(out),
        "chapters": len(poglavlja),
        "dropcaps_added": dropcaps,
        "toc_created": True,
        "error": None,
    }


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


# ═══════════════════════════════════════════════════════════════════════════
# V7 OVERRIDES — popravke za posvetu, discovery, h1 duplikate, \uFFFC
# ═══════════════════════════════════════════════════════════════════════════


def _ocisti_fffc(soup):
    """Ukloni \ufffc (object replacement) iz svih tekstualnih čvorova."""
    for tn in soup.find_all(string=True):
        s = str(tn)
        if "\ufffc" in s:
            tn.replace_with(s.replace("\ufffc", ""))
    return soup


def _dodaj_naslov(soup, broj, naslov=None):
    """Nova verzija: cuva originalni h1 ako nema eksplicitnog naslova,
    brise sve h1 ako ima, ne dodaje POGLAVLJE N za kratka tijela."""
    body = soup.find("body")
    if not body:
        return

    if naslov:
        for h in body.find_all("h1"):
            h.decompose()
        h1 = soup.new_tag("h1")
        h1["class"] = "booklyfi-naslov"
        h1.string = naslov
        insert_pos = 0
        for i, child in enumerate(body.children):
            cls = child.get("class") if hasattr(child, "get") else None
            if cls:
                if isinstance(cls, str):
                    cls = cls.split()
                if "booklyfi-vijenac" in cls:
                    insert_pos = i + 1
                    continue
            break
        body.insert(insert_pos, h1)
        return

    if body.find("h1"):
        return

    if len(body.get_text(strip=True)) < 400:
        return

    h1 = soup.new_tag("h1")
    h1["class"] = "booklyfi-naslov"
    h1.string = "POGLAVLJE %d" % broj
    insert_pos = 0
    for i, child in enumerate(body.children):
        cls = child.get("class") if hasattr(child, "get") else None
        if cls:
            if isinstance(cls, str):
                cls = cls.split()
            if "booklyfi-vijenac" in cls:
                insert_pos = i + 1
                continue
        break
    body.insert(insert_pos, h1)


def run_epub_styler(
    epub_path, output_path=None, fleet=None, log_callback=None, options=None
):
    import datetime as _dt
    import html as _html
    import re as _re

    epub_path = Path(epub_path)

    def _log(msg, atype="info"):
        logger.info("[styler] %s", msg)
        if log_callback:
            log_callback(msg, atype)

    def _esc(s):
        return _html.escape(str(s or ""), quote=True)

    def _page(title, body_html):
        css = (
            "body{background:#FDF6E3;color:#3E2723;font-family:Georgia,serif;"
            "margin:0 8%;padding:3em 0;line-height:1.7;font-size:1em;}"
            "h1,h2{color:#5D4037;}h1{text-align:center;font-size:1.5em;}"
            "hr{border:none;border-top:1px solid #8B6914;width:40%;margin:2em auto;}"
            "ul{list-style:none;padding:0;}"
            "li{padding:0.4em 0;border-bottom:1px dotted #8B6914;}"
            "a{color:#3E2723;text-decoration:none;}"
        )
        return (
            '<?xml version="1.0" encoding="utf-8"?>'
            "<!DOCTYPE html>"
            '<html xmlns="http://www.w3.org/1999/xhtml" lang="hr">'
            '<head><meta charset="utf-8"/><title>' + _esc(title) + "</title>"
            "<style>" + css + "</style></head><body>" + body_html + "</body></html>"
        )

    GENERIC_RX = _re.compile(
        r"^(?:part\s*\d+|chapter\s*\d+|ch\.?\s*\d+|"
        r"poglavlje\s*\d+|odjeljak\s*\d+|section\s*\d+|"
        r"book\s*\d+|knjiga\s*\d+)$",
        _re.I,
    )

    DEDICATION_STARTS = (
        "za ",
        "za\u00a0",
        "posve",
        "dedicat",
        "in memory",
        "u sje\u0107anje",
        "u spomen",
        "for ",
    )

    def _je_posveta(tlow, tlen):
        if tlen > 400:
            return False
        s = tlow.strip()
        for pfx in DEDICATION_STARTS:
            if s.startswith(pfx):
                return True
        return False

    def _naslov_iz(hb, toc_naslov, book_title):
        # Preskoči toc_naslov ako sadrži ime knjige (Calibre stavlja isto za sve)
        if (
            toc_naslov
            and not GENERIC_RX.match(toc_naslov.strip())
            and not (
                book_title and book_title.strip().lower() in toc_naslov.strip().lower()
            )
        ):
            return toc_naslov
        try:
            s = BeautifulSoup(hb, "html.parser")
            for tag in ("h1", "h2", "h3"):
                h = s.find(tag)
                if h:
                    t = h.get_text(strip=True)
                    if t and 0 < len(t) < 120:
                        return t
            tt = s.find("title")
            if tt:
                t = tt.get_text(strip=True)
                if t and 0 < len(t) < 120:
                    if not (book_title and book_title.strip().lower() in t.lower()):
                        return t
            first_p = s.find("p")
            if first_p:
                t = first_p.get_text(strip=True)
                if t and 0 < len(t) < 80:
                    tu = t.upper()
                    if t == tu or any(
                        kw in tu for kw in ("DIO", "KNJIGA", "PART", "BOOK")
                    ):
                        return t
        except Exception:
            pass
        return None

    def _classify(hb, href, toc_naslov, book_title, cover_hrefs):
        try:
            s = BeautifulSoup(hb, "html.parser")
            for tag in s(["script", "style"]):
                tag.decompose()
            tt = s.find("title")
            title = (tt.get_text(strip=True) if tt else "").lower()
            imgs = len(s.find_all(["img", "svg", "image"]))
            text = s.get_text(" ", strip=True).replace("\ufffc", "")
            tlen = len(text)
            tlow = text[:1200].lower()
            href_base = href.rsplit("/", 1)[-1]

            if tlen < 10 and imgs == 0:
                return False, "prazan", None, False

            if href in cover_hrefs or href_base in cover_hrefs:
                return False, "cover(opf)", None, False
            if title == "cover":
                return False, "cover(title)", None, False
            if imgs >= 1 and tlen < 30:
                return False, "samo-slika", None, False
            if imgs >= 1 and tlen < 100:
                return False, "cover-slicica", None, False

            if "table of contents" in title or "inhaltsverzeichnis" in title:
                return False, "toc(title)", None, False
            if (
                ("sadrzaj" in tlow or "sadr\u017eaj" in tlow)
                and ("naslovnica" in tlow or "naslovna stranica" in tlow)
                and "autorska prava" in tlow
            ):
                return False, "toc(kombinacija)", None, False

            cpy = (
                "\u00a9",
                "copyright",
                "sva prava",
                "all rights",
                "autorska prava",
                "isbn",
                "published by",
                "first published",
                "originally published",
            )
            if any(m in tlow for m in cpy):
                return False, "copyright", None, False

            mk = (
                "discovery page",
                "about this book",
                "discover more",
                "otkrijte svoje",
                "istra\u017eite darivanja",
                "istra\u017eite svoje",
                "pretpreglede",
                "dodirnite ovdje",
                "tap here",
                "vi\u0161e informacija",
                "saznajte vi\u0161e",
                "preporuke knjiga",
                "noviteti",
            )
            if any(m in title or m in tlow for m in mk):
                return False, "marketing", None, False

            if _je_posveta(tlow, tlen):
                return True, "posveta", None, True

            return True, "ok", _naslov_iz(hb, toc_naslov, book_title), False
        except Exception as e:
            return False, "greska:" + str(e), None, False

    try:
        files = _read(epub_path)
    except Exception as e:
        return {"ok": False, "error": "Citanje: " + str(e)}

    opf_path = next((n for n in files if n.endswith(".opf")), None)
    if not opf_path:
        return {"ok": False, "error": "Nema OPF"}

    opf_soup = BeautifulSoup(files[opf_path], "xml")
    spine = opf_soup.find("spine")
    manifest = opf_soup.find("manifest")
    if not spine or not manifest:
        return {"ok": False, "error": "Nema spine/manifest"}

    opf_dir = str(Path(opf_path).parent)
    if opf_dir == ".":
        opf_dir = ""

    cover_hrefs = set()
    for it in manifest.find_all("item"):
        if "cover-image" in (it.get("properties") or ""):
            cover_hrefs.add(it.get("href", ""))
            cover_hrefs.add(it.get("id", ""))
    for meta in opf_soup.find_all("meta", attrs={"name": "cover"}):
        cid = meta.get("content")
        if cid:
            for it in manifest.find_all("item"):
                if it.get("id") == cid:
                    cover_hrefs.add(it.get("href", ""))
    guide = opf_soup.find("guide")
    if guide:
        for ref in guide.find_all("reference", attrs={"type": "cover"}):
            h = ref.get("href", "").split("#")[0]
            if h:
                cover_hrefs.add(h)

    toc_mapa = _izvuci_toc_mapu(files, opf_dir)
    _log("   -> TOC mapa: %d naslova" % len(toc_mapa), "tech")

    creator, book_title = _meta(files)
    book_uid = "booklyfi"
    dc_lang = "hr"
    for n, d in files.items():
        if n.endswith(".opf"):
            try:
                osoup = BeautifulSoup(d, "xml")
                u = osoup.find("dc:identifier")
                if u:
                    book_uid = u.get_text(strip=True)
                lg = osoup.find("dc:language")
                if lg:
                    dc_lang = lg.get_text(strip=True) or "hr"
            except Exception:
                pass
            break

    for n in list(files.keys()):
        low = n.lower()
        if not low.endswith((".html", ".xhtml", ".htm", ".ncx")):
            continue
        if "booklyfi_" in low:
            continue
        if low.endswith(".ncx"):
            del files[n]
            _log("   -> Obrisan NCX: " + n, "tech")
            continue
        try:
            s = BeautifulSoup(files[n], "html.parser")
            if s.find("nav", attrs={"epub:type": "toc"}):
                del files[n]
                _log("   -> Obrisan NAV TOC: " + n, "tech")
                continue
        except Exception:
            pass
        if any(kw in low for kw in ("toc", "sadrzaj", "contents", "nav.")):
            del files[n]
            _log("   -> Obrisan stari TOC: " + n, "tech")

    id_to_href = {}
    for it in manifest.find_all("item"):
        href = it.get("href", "")
        if href.lower().endswith((".html", ".xhtml", ".htm")):
            id_to_href[it.get("id", "")] = href

    poglavlja = []
    skip_hrefs = set()

    for itemref in spine.find_all("itemref"):
        href = id_to_href.get(itemref.get("idref", ""), "")
        if not href:
            continue
        full = (opf_dir + "/" + href) if opf_dir else href
        hb = files.get(full) or files.get(href)
        if not hb:
            continue
        toc_naslov = toc_mapa.get(href) or toc_mapa.get(full)
        keep, razlog, finalni, no_heading = _classify(
            hb, href, toc_naslov, book_title, cover_hrefs
        )
        if not keep:
            _log("   -> Skip (%s): %s" % (razlog, href), "tech")
            skip_hrefs.add(href)
            skip_hrefs.add(full)
            continue
        poglavlja.append(
            {
                "href": href,
                "full_path": full,
                "order": len(poglavlja) + 1,
                "naslov": finalni,
                "no_heading": no_heading,
            }
        )

    _log("   -> %d poglavlja" % len(poglavlja), "tech")

    for h in skip_hrefs:
        if h in files and not h.lower().endswith(
            (".jpg", ".jpeg", ".png", ".gif", ".svg", ".css", ".ttf", ".otf", ".woff")
        ):
            del files[h]
            _log("   -> Obrisan iz EPUB-a: " + h, "tech")

    dropcaps = 0
    for p in poglavlja:
        soup = BeautifulSoup(
            files[p["full_path"]].decode("utf-8", errors="replace"), "html.parser"
        )
        _ukloni_sve(soup)
        _normalizuj(soup)
        _dijalog(soup)
        _dodaj_vijenac(soup)
        _ocisti_fffc(soup)
        if p.get("no_heading"):
            pass
        elif p.get("naslov"):
            _dodaj_naslov(soup, p["order"], naslov=p["naslov"])
        else:
            _dodaj_naslov(soup, p["order"])
        p["_ima_h1"] = bool(soup.find("h1"))
        if _dodaj_dropcap(soup):
            dropcaps += 1
        head = soup.find("head")
        if not head:
            head = soup.new_tag("head")
            parent = soup.html if soup.html else soup
            parent.insert(0, head)
        st = soup.new_tag("style", type="text/css")
        st.string = CSS
        head.append(st)
        files[p["full_path"]] = str(soup).encode("utf-8")

    _log("   -> %d dropcapa" % dropcaps, "tech")

    nas_path = (
        (opf_dir + "/booklyfi_001_naslovna.xhtml")
        if opf_dir
        else "booklyfi_001_naslovna.xhtml"
    )
    imp_path = (
        (opf_dir + "/booklyfi_002_impresum.xhtml")
        if opf_dir
        else "booklyfi_002_impresum.xhtml"
    )
    year = _dt.datetime.now().year
    nas_body = (
        '<div style="text-align:center;padding:3em 5% 0;">'
        '<p style="font-size:0.85em;letter-spacing:0.3em;color:#8B6914;">BOOKLYFI IZDANJE</p>'
        '<hr/><h1 style="font-size:2.4em;">' + _esc(book_title) + "</h1>"
        '<hr/><p style="font-size:1.3em;margin-top:3em;">' + _esc(creator) + "</p>"
        '<p style="font-size:0.9em;color:#8B6914;margin-top:5em;">Booklyfi &#183; '
        + str(year)
        + "</p></div>"
    )
    imp_body = (
        '<h1 style="text-align:center;">IMPRESUM</h1>'
        "<p><b>Naslov:</b> " + _esc(book_title) + "</p>"
        "<p><b>Autor:</b> " + _esc(creator) + "</p>"
        "<p><b>ID:</b> " + _esc(book_uid) + "</p>"
        "<p><b>Izdanje:</b> Booklyfi digitalno izdanje, " + str(year) + ".</p>"
        "<p><b>Format:</b> EPUB 3</p><p>Sva prava zadrzana.</p>"
    )
    files[nas_path] = _page("Naslovna", nas_body).encode("utf-8")
    files[imp_path] = _page("Impresum", imp_body).encode("utf-8")

    ncx_path = (opf_dir + "/toc.ncx") if opf_dir else "toc.ncx"
    nps = []
    for p in poglavlja:
        if not p.get("_ima_h1"):
            continue  # nema h1 u EPUB-u -> nema u TOC-u
        nas = p.get("naslov") or ("POGLAVLJE %d" % p["order"])
        nps.append(
            '<navPoint id="np-%d" playOrder="%d"><navLabel><text>%s</text></navLabel>'
            '<content src="%s"/></navPoint>'
            % (p["order"], p["order"], _esc(nas), _esc(p["href"]))
        )
    files[ncx_path] = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
        '<head><meta name="dtb:uid" content="' + _esc(book_uid) + '"/>'
        '<meta name="dtb:depth" content="1"/></head>'
        "<docTitle><text>" + _esc(book_title) + "</text></docTitle>"
        "<navMap>" + "".join(nps) + "</navMap></ncx>"
    ).encode("utf-8")

    nav_path = (opf_dir + "/nav.xhtml") if opf_dir else "nav.xhtml"
    nav_its = []
    for p in poglavlja:
        if not p.get("_ima_h1"):
            continue  # nema h1 u EPUB-u -> nema u TOC-u
        nas = p.get("naslov") or ("POGLAVLJE %d" % p["order"])
        nav_its.append('<li><a href="%s">%s</a></li>' % (_esc(p["href"]), _esc(nas)))
    first_href = poglavlja[0]["href"] if poglavlja else Path(nas_path).name
    nav_body = (
        '<nav epub:type="toc" id="toc"><h1>Sadržaj</h1><ol>'
        + "".join(nav_its)
        + "</ol></nav>"
        '<nav epub:type="landmarks" hidden="hidden"><h2>Orijentiri</h2><ol>'
        '<li><a epub:type="titlepage" href="'
        + _esc(Path(nas_path).name)
        + '">Naslovna</a></li>'
        '<li><a epub:type="copyright-page" href="'
        + _esc(Path(imp_path).name)
        + '">Impresum</a></li>'
        '<li><a epub:type="bodymatter" href="' + _esc(first_href) + '">Početak</a></li>'
        "</ol></nav>"
    )
    files[nav_path] = (
        '<?xml version="1.0" encoding="utf-8"?>'
        "<!DOCTYPE html>"
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
        'lang="' + _esc(dc_lang) + '">'
        '<head><meta charset="utf-8"/><title>Sadržaj</title></head>'
        "<body>" + nav_body + "</body></html>"
    ).encode("utf-8")

    opf_soup = BeautifulSoup(files[opf_path], "xml")
    mtag = opf_soup.find("manifest")
    stag = opf_soup.find("spine")
    existing = set(files.keys())

    for it in list(mtag.find_all("item")):
        href = it.get("href", "")
        fh = (opf_dir + "/" + href) if opf_dir else href
        if fh not in existing and href not in existing:
            it.decompose()

    gd = opf_soup.find("guide")
    if gd:
        for ref in list(gd.find_all("reference")):
            h = ref.get("href", "").split("#")[0]
            fh = (opf_dir + "/" + h) if opf_dir else h
            if fh not in existing and h not in existing:
                ref.decompose()

    for iid, path, mt in (
        ("booklyfi-naslovna", nas_path, "application/xhtml+xml"),
        ("booklyfi-impresum", imp_path, "application/xhtml+xml"),
        ("ncx", ncx_path, "application/x-dtbncx+xml"),
    ):
        for old in mtag.find_all("item", id=iid):
            old.decompose()
        ni = opf_soup.new_tag("item")
        ni["id"] = iid
        ni["href"] = Path(path).name
        ni["media-type"] = mt
        mtag.append(ni)
    for old in mtag.find_all("item", id="nav"):
        old.decompose()
    ni = opf_soup.new_tag("item")
    ni["id"] = "nav"
    ni["href"] = Path(nav_path).name
    ni["media-type"] = "application/xhtml+xml"
    ni["properties"] = "nav"
    mtag.append(ni)

    if not opf_soup.find("meta", attrs={"property": "dcterms:modified"}):
        now = _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        meta = opf_soup.new_tag("meta")
        meta["property"] = "dcterms:modified"
        meta.string = now
        md = opf_soup.find("metadata")
        if md:
            md.append(meta)

    kept_hrefs = {p["href"] for p in poglavlja}
    orig_ids = []
    for ir in stag.find_all("itemref"):
        iid = ir.get("idref", "")
        href = id_to_href.get(iid, "")
        if href and href in kept_hrefs:
            orig_ids.append(iid)

    for ir in stag.find_all("itemref"):
        ir.decompose()
    # 2026-10-24 B7: dedup base64 slike u zajednicke PNG pre OPF build
    _shared_images = _ekstrahuj_zajednicke_slike(files)
    if _shared_images:
        _log("   -> %d zajednickih slika (dedup base64)" % len(_shared_images), "tech")

    # 2026-10-24 B7: dodaj manifest items za zajednicke slike
    if _shared_images:
        for _png_path in _shared_images:
            _ext = _png_path.rsplit(".", 1)[-1].lower()
            _hash_part = (
                _png_path.rsplit("/", 1)[-1]
                .replace("booklyfi-shared-", "")
                .rsplit(".", 1)[0]
            )
            ni = opf_soup.new_tag("item")
            ni["id"] = "booklyfi-shared-" + _hash_part
            ni["href"] = _png_path
            ni["media-type"] = "image/jpeg" if _ext in ("jpg", "jpeg") else "image/png"
            mtag.append(ni)

    for iid in ("booklyfi-naslovna", "booklyfi-impresum", "nav"):
        ir = opf_soup.new_tag("itemref")
        ir["idref"] = iid
        stag.append(ir)
    for iid in orig_ids:
        if iid in ("booklyfi-naslovna", "booklyfi-impresum", "nav", "ncx"):
            continue
        ir = opf_soup.new_tag("itemref")
        ir["idref"] = iid
        stag.append(ir)
    if not stag.get("toc"):
        stag["toc"] = "ncx"
    files[opf_path] = str(opf_soup).encode("utf-8")

    if output_path:
        out = Path(output_path)
    else:
        od = Path(STYLED_OUTPUT_DIR)
        od.mkdir(parents=True, exist_ok=True)
        out = od / _ime(creator, book_title)
    _write(out, files)

    return {
        "ok": True,
        "epub_path": str(out),
        "chapters": len(poglavlja),
        "dropcaps_added": dropcaps,
        "toc_created": True,
        "error": None,
    }
