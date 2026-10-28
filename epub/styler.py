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
img.booklyfi-dropcap { float:left; display:block;
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

    # F0.39: Obrisi SVE ostale klase i inline stilove (osim za dropcap/TTS)
    for tag in soup.find_all(True):
        if tag.name in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "span", "section"):
            # Style
            if "style" in tag.attrs:
                style_val = tag["style"]
                if "font-size:1px" not in style_val and "booklyfi-dropcap" not in tag.get("class", []):
                    del tag["style"]
            # Class
            if "class" in tag.attrs:
                cls = tag["class"]
                if not any(c.startswith("booklyfi-") for c in cls) and "booklyfi-dropcap" not in cls:
                    del tag["class"]

    # FIX 2026-10-26: unwrap <section> i div.galley-rw (sirovi lektura HTML iz .chk)
    for sec in soup.find_all("section"):
        sec.unwrap()
    for _g in soup.find_all(class_="galley-rw"):
        _g.unwrap()


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


def _ukloni_duplikate_p(soup: BeautifulSoup) -> int:
    """Ukloni <p> ciji je pocetak prefix ili identican drugom <p>. Zadrzava duzi."""
    import re as _re

    def norm(t):
        t = _re.sub(r"^[\u2014\u2013\-\s]+", "", t.strip())
        return _re.sub(r"\s+", " ", t).lower()

    ps = soup.find_all("p")
    to_remove = []
    for i, p1 in enumerate(ps):
        t1 = p1.get_text(strip=True)
        if len(t1) < 30:
            continue
        n1 = norm(t1)
        for p2 in ps[i+1:]:
            t2 = p2.get_text(strip=True)
            if len(t2) < 30:
                continue
            n2 = norm(t2)
            mn = min(len(n1), len(n2))
            if mn < 60:
                continue
            if n1[:mn] == n2[:mn]:
                to_remove.append(p2 if len(t1) > len(t2) else p1)
                break
    for el in set(to_remove):
        if el.parent is not None:
            el.decompose()
    return len(to_remove)


def _skrati_overlap(prethodni, sljedeci, min_rijeci=15):
    """Ako kraj prethodnog = pocetak sljedeceg, skrati sljedeci za taj overlap.
    Vraca (skraceni_tekst, broj_uklonjenih_rijeci).
    Radi nad cistim tekstom (bez HTML)."""
    import re as _re
    def _words(t):
        return _re.sub(r"<[^>]+>", " ", t).split()
    w1 = _words(prethodni)
    w2 = _words(sljedeci) if False else _words(sljedeci)
    mn = min(len(w1), len(w2), 500)
    for L in range(mn, min_rijeci - 1, -1):
        if w1[-L:] == w2[:L]:
            # Skrati sljedeci za L rijeci; vrati ostatak
            return " ".join(w2[L:]), L
    return sljedeci, 0


def _je_duplikat(t1, t2, threshold=0.7):
    """Fuzzy match: 70%+ zajednickih rijeci (duzine >3)."""
    import re as _re
    w1 = set(w.lower() for w in _re.findall(r"\w+", t1) if len(w) > 3)
    w2 = set(w.lower() for w in _re.findall(r"\w+", t2) if len(w) > 3)
    if not w1 or not w2:
        return False
    return len(w1 & w2) / min(len(w1), len(w2)) >= threshold


def _spoji_blokove(delovi):
    """Spoji blokove sa separatorom kad se spajaju dvije rijeci (alfanum na obje strane)."""
    if not delovi:
        return ""
    result = delovi[0]
    for b in delovi[1:]:
        if not b:
            continue
        last = result.rstrip()[-1] if result.rstrip() else ""
        first = b.lstrip()[0] if b.lstrip() else ""
        if last.isalnum() and first.isalnum():
            result += "\n"
        result += b
    return result



def _razdvoji_dijalog_p(soup: BeautifulSoup) -> int:
    """Razdvoji <p> sa 3+ replika (em-crtica posle .!?…) u zasebne <p>."""
    import re as _re

    changes = 0
    for p in list(soup.find_all("p")):
        text = p.get_text()
        if len(text) < 200 or text.count("\u2014") < 3:
            continue
        parts = _re.split(r"(?<=[.!?\u2026])\s*(?=\u2014\s)", text.strip())
        if len(parts) <= 1:
            continue
        parent = p.parent
        if parent is None:
            continue
        idx = list(parent.children).index(p) if p in parent.children else -1
        if idx < 0:
            continue
        p.clear()
        p.append(parts[0])
        insert_at = idx + 1
        for part in parts[1:]:
            new_p = soup.new_tag("p")
            new_p.append(part.strip())
            parent.insert(insert_at, new_p)
            insert_at += 1
        changes += 1
    return changes


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
                logger.exception("[C1_http] styler.py:320 Exception")
    return "Nepoznat_autor", "Nepoznat_naslov"


def _san(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|]', "", s.strip())
    return re.sub(r"\s+", "_", s)


def _ime(c: str, t: str) -> str:
    return f"{_san(c)}_{_san(t)}_PREVEDENO_STYLED.epub"


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
            logger.exception("[C1_kriticno] styler.py:426 Exception")

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
            logger.exception("[C1_kriticno] styler.py:449 Exception")
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

    # FIX 2026-10-26: Dropcap ide SAMO u prvi <p> posle <h1>.
    # Ako je taj <p> dijalog (— " „), PRESKOČI dropcap za celo poglavlje
    # (ne idi dalje — inače završi na pola stranice).
    body = soup.find("body")
    if not body:
        return False

    # F0.11: nadji prvi <p> sa >=60c teksta (preskoci kratke naslove prica)
    prvi_p = None
    h1 = body.find("h1")
    if h1:
        for kandidat in h1.find_all_next("p"):
            t = kandidat.get_text(strip=True)
            if len(t) >= 60 and not t.isdigit():
                prvi_p = kandidat
                break
    if prvi_p is None:
        for kandidat in body.find_all("p"):
            t = kandidat.get_text(strip=True)
            if len(t) >= 60 and not t.isdigit():
                prvi_p = kandidat
                break

    if prvi_p is None:
        return False

    prvi_tekst = prvi_p.get_text(strip=True)
    prvi_char = prvi_tekst[0] if prvi_tekst else ""
    dijalog_chars = ("—", "–", "-", "‒", "―", '"', "„", '"', '"', "«", "'")

    if prvi_char in dijalog_chars:
        # F0.11: dijalog na pocetku — velika crtica umesto slova
        if prvi_char in ("—", "–", "‒", "―"):
            crtica = prvi_char
        else:
            crtica = "—"
        img_html = (
            '<span class="booklyfi-crtica" '
            'style="float:left;display:block;'
            'font-size:4em;line-height:0.8;'
            'margin:0.1em 0.05em 0 0;padding:0;">'
            + crtica
            + '</span>'
        )
        cls = prvi_p.get("class") or []
        if isinstance(cls, str):
            cls = cls.split()
        crtica_tag = BeautifulSoup(img_html, "html.parser").find("span")
        prvi_p.insert(0, crtica_tag)
        prvi_p["class"] = list(cls) + ["booklyfi-prvi"]
        return True

    # Primeni dropcap SAMO na prvi_p
    for p in [prvi_p]:
        cls = p.get("class") or []
        if isinstance(cls, str):
            cls = cls.split()
        if "booklyfi-naslov" in cls or "booklyfi-prvi" in cls:
            continue

        text = p.get_text(strip=True)
        if len(text) < 60 or text.isdigit():
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
            'style="float:left;display:block;'
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


# def _ekstrahuj_zajednicke_slike(files: dict) -> list[str]:
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

    # FIX 2026-10-26: TOC naslov moze biti "Pitanja\nPoradili su mu na ruci…"
    # — spojen naslov + prva recenica iz .chk. Uzmi samo prvu liniju kao naslov
    # i ukloni je iz prvog <p> da dropcap ne uzme slovo iz naslova.
    if naslov and "\n" in naslov:
        prva = naslov.split("\n")[0].strip()
        if prva and len(prva) < 60:
            for _p in body.find_all("p"):
                if _p.find(True):
                    continue
                _t = _p.get_text()
                if _t.lstrip().startswith(prva):
                    _rest = _t.lstrip()[len(prva):].lstrip("\n\r \t")
                    if _rest:
                        _p.clear()
                        _p.append(_rest)
                        naslov = prva
                    break

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

        # F0.17: ako je prvi <p> posle h1 identican naslovu, obrisi ga
        _prvi_p = h1.find_next("p")
        if _prvi_p and _prvi_p.get_text(strip=True) == h1.get_text(strip=True):
            _prvi_p.decompose()
        return

    if body.find("h1"):
        return

    if len(body.get_text(strip=True)) < 400:
        return

    # F0.36: Stroga validacija <title> taga
    _naslov_fallback = None
    _title_tag = soup.find("title")
    if _title_tag:
        _t = _title_tag.get_text(strip=True)
        if _t and len(_t) <= 60 and len(_t.split()) <= 10 and not _t.endswith("…") and not _t.endswith("."):
            if _t.lower() not in ("navigation", "cover", "toc")                and _t not in ("A Little Hatred", "The Trouble With Peace", "The Wisdom of Crowds"):
                _naslov_fallback = _t

    h1 = soup.new_tag("h1")
    h1["class"] = "booklyfi-naslov"
    h1.string = _naslov_fallback or ("POGLAVLJE %d" % broj)
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
        # F0.37: Stroga validacija naslova (ne smije biti recenica)
        INVALID_TITLES = {"A Little Hatred", "The Trouble With Peace", "The Wisdom of Crowds",
                          "A Little Hatred: Book One of The Age of Madness",
                          "The Age of Madness Trilogy"}
        def _is_valid_title(t):
            if not t: return False
            t = t.strip()
            if len(t) > 60 or len(t.split()) > 10: return False
            if t.endswith("…") or t.endswith("."): return False
            if t in INVALID_TITLES: return False
            if GENERIC_RX.match(t): return False
            if book_title and book_title.strip().lower() in t.lower(): return False
            if t.lower().startswith(("za ", "posveta", "uvod", "predgovor")): return False
            return True

        if _is_valid_title(toc_naslov):
            return toc_naslov.strip()

        try:
            s = BeautifulSoup(hb, "html.parser")
            for tag in ("h1", "h2", "h3"):
                h = s.find(tag)
                if h:
                    t = h.get_text(strip=True)
                    if _is_valid_title(t):
                        return t
            tt = s.find("title")
            if tt:
                t = tt.get_text(strip=True)
                if _is_valid_title(t):
                    return t
            # F0.33: Ne uzimaj prvi pasus kao naslov.
            pass
        except Exception:
            logger.exception("[C1_http] styler.py:1448 Exception")
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
            # FIX 2026-10-26: Calibre "Navigation" stub nije poglavlje
            if title == "navigation":
                return False, "navigation stub", None, False
            if imgs >= 1 and tlen < 30:
                return False, "samo-slika", None, False
            if imgs >= 1 and tlen < 100:
                return False, "cover-slicica", None, False

            if "table of contents" in title or "inhaltsverzeichnis" in title:
                return False, "toc(title)", None, False

            # F0.12: skip frontmatter po h1 tekstu (Calibre stavlja ime knjige u title)
            _h1 = s.find("h1")
            if _h1 is not None:
                _h1_low = _h1.get_text(strip=True).lower()
                _h1_skip = (
                    "navigation",
                    "autor:",
                    "autor :",
                    "o autoru",
                    "sadržaj",
                    "sadrzaj",
                    "table of contents",
                    "naslovna",
                )
                if any(m in _h1_low for m in _h1_skip):
                    return False, "frontmatter(h1)", None, False
            if (
                ("sadrzaj" in tlow or "sadr\u017eaj" in tlow)
                and ("naslovnica" in tlow or "naslovna stranica" in tlow)
                and "autorska prava" in tlow
            ):
                return False, "toc(kombinacija)", None, False

            # F0.10: copyright/marketing filter samo za KRATKE fajlove bez <h1> POGLAVLJE
            _h1 = s.find("h1")
            _has_chapter_h1 = _h1 is not None and "poglavlje" in _h1.get_text(strip=True).lower()
            _je_dugacak = tlen > 5000

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
            if not (_has_chapter_h1 or _je_dugacak):
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
                logger.exception("[C1_http] styler.py:1581 Exception")
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
            logger.debug("[C3_fallback] styler.py:1601 Exception")
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
    # FIX 2026-10-26: PRE obrade HTML-a, spoji .chk u HTML.
    # Time se izbegava da originalni HTML (galley-rw, navodnici)
    # pregazi .chk sadržaj.
    try:
        from epub.packager import _spoji_chk_u_html
        class _TmpEngine:
            pass
        _eng = _TmpEngine()
        _eng.work_dir = Path(STYLED_OUTPUT_DIR).parent / "_tmp_styler_work"
        # Ne koristimo _spoji_chk_u_html jer on radi na engine.work_dir
        # Umesto toga, direktno spojimo .chk u files dict
        import re as _re_s
        from pathlib import Path as _P_s
        from config.settings import CHECKPOINT_BASE_DIR as _CPB_s

        _epub_stem = Path(str(epub_path)).stem
        _epub_stem = _re_s.sub(
            r"^(?:PREVEDENO_)+", "", _epub_stem, flags=_re_s.IGNORECASE
        )
        _epub_stem = _re_s.sub(
            r"(?:_PREVEDENO|_STYLED)+$", "", _epub_stem, flags=_re_s.IGNORECASE
        )
        _svi_sa_chk = [
            _k
            for _k in _CPB_s.glob("_skr_*")
            if (_k / "checkpoints").exists()
            and any((_k / "checkpoints").glob("*.chk"))
        ]
        _exact = _CPB_s / ("_skr_" + _epub_stem)
        _skr = None
        if _exact in _svi_sa_chk:
            _skr = _exact
        else:
            _kandidati = []
            for _k in _svi_sa_chk:
                _k_name = _k.name[len("_skr_") :]
                if _k_name in _epub_stem or _epub_stem in _k_name:
                    _kandidati.append(_k)
                elif (
                    len(_k_name) >= 20
                    and len(_epub_stem) >= 20
                    and (
                        _k_name[:20] == _epub_stem[:20]
                        or _k_name[-20:] == _epub_stem[-20:]
                    )
                ):
                    _kandidati.append(_k)
            if len(_kandidati) == 1:
                _skr = _kandidati[0]
            else:
                _skr = None
                _imena = (
                    ", ".join(_k.name for _k in _kandidati)
                    if _kandidati
                    else "(nema)"
                )
                _log(
                    "   -> _skr_ nije jedinstven za "
                    + _epub_stem
                    + " ("
                    + str(len(_kandidati))
                    + ": "
                    + _imena
                    + "), .chk se ne spaja",
                    "warning",
                )

        if _skr:
            _ckpt = _skr / "checkpoints"
            _chk_po_fajlu = {}
            for _f in _ckpt.glob("*.chk"):
                if _f.stem.endswith((".prevod", ".lektura")): continue
                _m = _re_s.match(r"(.+?)_blok_(\d+)$", _f.stem)
                if not _m: continue
                _chk_po_fajlu.setdefault(_m.group(1), {})[int(_m.group(2))] = _f

            def _ocisti_chk(t):
                t = _re_s.sub(r"<!--\s*chunk_sha[^>]*-->\s*\n?", "", t)
                if t.strip().startswith("{"):
                    try:
                        import json as _j
                        d = _j.loads(t)
                        for k in ("finalno_polirano", "korektura", "tekst", "translated"):
                            if k in d and isinstance(d[k], str): return d[k]
                    except: pass
                return t

            _spojeno = 0
            for _html_name, _blokovi in _chk_po_fajlu.items():
                if _html_name not in files:
                    # Nađi po basename
                    _found = None
                    for _k2 in files:
                        if _k2.endswith(_html_name) or _html_name.endswith(_k2.split("/")[-1]):
                            _found = _k2; break
                    if not _found: continue
                    _html_name = _found

                try:
                    _soup = BeautifulSoup(files[_html_name].decode("utf-8", "replace"), "html.parser")
                except: continue
                _body = _soup.body
                if not _body: continue

                _delovi = [_ocisti_chk(_blokovi[i].read_text("utf-8", errors="ignore")).strip() for i in sorted(_blokovi.keys())]
                _delovi = [d for d in _delovi if d]
                if not _delovi: continue

                # F0.7+F0.8: obrisi duplikate (plain vs HTML, HTML vs HTML)
                _za_brisanje = set()
                _parovi = [(i, t) for i, t in enumerate(_delovi)]
                for _i1, _t1 in _parovi:
                    if _i1 in _za_brisanje: continue
                    _je_plain1 = "<p" not in _t1
                    for _i2, _t2 in _parovi:
                        if _i1 >= _i2: continue
                        if _i2 in _za_brisanje: continue
                        _je_plain2 = "<p" not in _t2
                        # plain vs HTML: 70%+ threshold
                        # HTML vs HTML: 90%+ threshold (stroze)
                        if _je_plain1 and _je_plain2:
                            _th = 0.7
                        elif _je_plain1 or _je_plain2:
                            _th = 0.7
                        else:
                            _th = 0.90
                        if not _je_duplikat(_t1, _t2, _th):
                            continue
                        _w1 = len(_t1.split())
                        _w2 = len(_t2.split())
                        # Obrisi kraci
                        if _w1 >= _w2:
                            _za_brisanje.add(_i2)
                            print(f"  [dup] {_html_name}: obrisan blok_{_i2} ({'plain' if _je_plain2 else 'HTML'}, {_w2}w) — duplikat blok_{_i1} ({_w1}w, {_th*100:.0f}%)")
                        else:
                            _za_brisanje.add(_i1)
                            print(f"  [dup] {_html_name}: obrisan blok_{_i1} ({'plain' if _je_plain1 else 'HTML'}, {_w1}w) — duplikat blok_{_i2} ({_w2}w, {_th*100:.0f}%)")
                        break
                if _za_brisanje:
                    _delovi = [t for i, t in enumerate(_delovi) if i not in _za_brisanje]
                    if not _delovi: continue

                # F0.6: skrati overlap izmedju susjednih blokova
                _delovi_dedup = [_delovi[0]]
                for _sl in _delovi[1:]:
                    _sk, _n = _skrati_overlap(_delovi_dedup[-1], _sl)
                    if _n > 0:
                        print(f"  [overlap] {_html_name}: skraceno {_n} rijeci")
                    if _sk.strip():
                        _delovi_dedup.append(_sk)
                _delovi = _delovi_dedup

                # F0.18b: ako zadnji blok ima >=50 rijeci teksta i zavrsava bez interpunkcije = prekinut
                if _delovi:
                    from bs4 import BeautifulSoup as _BS_f018
                    _zadnji_html = _delovi[-1]
                    _zadnji_tekst = _BS_f018(_zadnji_html, "html.parser").get_text(strip=True)
                    if (
                        _zadnji_tekst
                        and _zadnji_tekst[-1] not in '.!?"\u201c\u201d\u201e\u2014\u2026)\u203a\u00bb:;'
                        and len(_zadnji_tekst.split()) >= 50
                    ):
                        _delovi[-1] = _zadnji_html + '\n<p>[[NEPREVEDENO: prekinut prevod]]</p>'
                        _log("   -> PREKINUT: " + _html_name + " (" + str(len(_zadnji_tekst.split())) + "w) zavrsava sa " + repr(_zadnji_tekst[-40:]), "warning")

                _body.clear()
                # F0.13b: wrap po bloku PRIJE spajanja (sprecava pogled."Zadovoljstvo)
                _delovi_wrapped = []
                for _t in _delovi:
                    if "<p" in _t.lower():
                        _delovi_wrapped.append(_t)
                    else:
                        _paras = [x.strip() for x in _t.split("\n\n") if x.strip()]
                        _delovi_wrapped.append("".join("<p>" + x + "</p>" for x in _paras))
                _joined = _spoji_blokove(_delovi_wrapped)
                _ns = BeautifulSoup(_joined, "html.parser")
                _src = _ns.body or _ns
                for _c in list(_src.children):
                    _body.append(_c.extract())
                files[_html_name] = str(_soup).encode("utf-8")
                _spojeno += 1
    except Exception as _e:
        print(f"  ⚠ _spoji_chk_u_html greška: {_e}")

    for p in poglavlja:
        soup = BeautifulSoup(
            files[p["full_path"]].decode("utf-8", errors="replace"), "html.parser"
        )
        _ukloni_sve(soup)
        _normalizuj(soup)
        _dijalog(soup)
        _ukloni_duplikate_p(soup)
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
#     _shared_images = _ekstrahuj_zajednicke_slike(files)
    _shared_images = []  # FIX F0.1: funkcija obrisana, dedup onemogucen (inline base64)
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


