import logging
logger = logging.getLogger(__name__)
import contextlib
import re

# epub/packager.py
import shutil
import zipfile
from pathlib import Path

# Uvezi zaštitu za container.xml
try:
    from epub.styler import _osiguraj_container_xml
except ImportError:
    _osiguraj_container_xml = None

# ─────────────────────────────────────────────────────────────────────────────
# Pomoćna: efektivni OUTPUT_DIR (s fallbackom)
# ─────────────────────────────────────────────────────────────────────────────


def _get_output_dir() -> Path:
    """
    Vraća OUTPUT_DIR iz settings-a.
    Ako Android putanja nije dostupna, vraća INPUT_DIR kao fallback.
    """
    try:
        from config.settings import OUTPUT_DIR

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        return OUTPUT_DIR
    except Exception:
        try:
            from config.settings import INPUT_DIR

            return INPUT_DIR
        except Exception:
            return Path("data")


# ─────────────────────────────────────────────────────────────────────────────
# Live EPUB (u toku obrade)
# ─────────────────────────────────────────────────────────────────────────────


def buildlive_epub(self):
    """Gradi privremeni live EPUB u INPUT_DIR za pregled u toku obrade."""
    try:
        from config.settings import INPUT_DIR

        live_dir = Path(INPUT_DIR)
    except Exception:
        live_dir = self.book_path.parent

    live_epub = live_dir / f"(LIVE)_{self.clean_book_name}.epub"
    try:
        with zipfile.ZipFile(live_epub, "w", zipfile.ZIP_DEFLATED) as z:
            for f in self.work_dir.rglob("*"):
                if f.is_file() and "checkpoints" not in f.parts:
                    z.write(f, f.relative_to(self.work_dir))
    except Exception as e:
        self.log(f"⚠️ Live EPUB greška: {e}", "warning")


# ─────────────────────────────────────────────────────────────────────────────
# Osnovni CSS & TOC
# ─────────────────────────────────────────────────────────────────────────────


def apply_dropcap_and_toc(self, soup, html_file, samo_dropcap=False):
    """
    Injectira osnovni CSS i puni TOC listu za NCX navigaciju.

    FIX 2026-09-27 v2: Deterministički TOC bez AI.
    Prioritet naslova:
      1. <h1> / <h2> / <h3> iz HTML-a (originalni naslov poglavlja)
      2. Prva rečenica iz prvog <p> s >= 20 znakova
      3. Filename (zadnji fallback)

    Parametar samo_dropcap se ignoriše (dropcap radi Stil tab).
    """
    from epub.styling import _inject_epub_global_css

    _inject_epub_global_css(soup)

    rel_path = html_file.relative_to(self.work_dir)
    title = None

    # ── 1. Traži <h1>/<h2>/<h3> ──────────────────────────────────────────
    for tag in ["h1", "h2", "h3"]:
        h = soup.find(tag)
        if h and h.get_text(strip=True):
            title = h.get_text(strip=True)[:60]
            break

    # ── 2. Prva rečenica iz prvog <p> ─────────────────────────────────────
    if not title:
        first_p = soup.find("p")
        if first_p:
            para = first_p.get_text(strip=True)
            if len(para) >= 20:
                # Prva rečenica (do . ! ?)
                m_sent = re.match(r"^([^.!?]{10,90})[.!?]", para)
                if m_sent:
                    candidate = m_sent.group(1).strip()
                    # Očisti vodeće navodnike/crtice
                    candidate = candidate.lstrip('"\u201e\u201c\u2018\u2019\u2014-– ')
                    if len(candidate) >= 5:
                        title = candidate + "\u2026"
                if not title:
                    # Nema točke — uzmi prvih 60 znakova
                    title = para[:60].strip()
                    if len(para) > 60:
                        title += "\u2026"

    # ── 3. Fallback na filename ──────────────────────────────────────────
    if not title:
        title = (
            html_file.stem.replace("chapter", "Poglavlje ").replace("_", " ").title()
        )

    href = str(rel_path).replace("\\", "/")
    if not any(e[1] == href for e in self.toc_entries):
        self.toc_entries.append((title, href))


def generate_ncx(self):
    """Minimalni NCX generator za EPUB navigaciju."""
    ncx_path = self.work_dir / "toc.ncx"

    nav_points = ""
    for i, (title, href) in enumerate(self.toc_entries, 1):
        safe_title = (
            title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        nav_points += (
            f'    <navPoint id="nav{i}" playOrder="{i}">\n'
            f"      <navLabel><text>{safe_title}</text></navLabel>\n"
            f'      <content src="{href}"/>\n'
            f"    </navPoint>\n"
        )

    book_title = self.book_context.get("title", self.clean_book_name)

    ncx_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{self.clean_book_name}"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>{book_title}</text></docTitle>
  <navMap>
{nav_points}  </navMap>
</ncx>"""

    ncx_path.write_text(ncx_content, encoding="utf-8")
    self.log(
        f"📑 NCX navigacija generirana ({len(self.toc_entries)} poglavlja)",
        "tech",
    )


# ─────────────────────────────────────────────────────────────────────────────
# FINALIZE — pakuje EPUB i kopira u MoonReader
# ─────────────────────────────────────────────────────────────────────────────


# ═══════════════════════════════════════════════════════════════════════
# FINALNI FIXEVI — dropcap, ornament, CSS, TOC, atributi
# ═══════════════════════════════════════════════════════════════════════


def _finaliziraj_fix_epub(self):
    """
    Primijeni sve fixeve na EPUB prije finalnog pakovanja:
      - Dropcap (dodaj ako fali)
      - Ornament (dodaj ako fali)
      - CSS spajanje u styles.css
      - TOC NCX regeneracija s HR naslovima
      - Obrisi root toc.ncx
      - Ocisti stare spanove
      - Popravi pokvarene atribute
    """
    import re as _re

    from bs4 import BeautifulSoup as _BS

    work_dir = self.work_dir
    if not work_dir.exists():
        return

    # Nadji OPF i images dir
    opf = next(work_dir.rglob("*.opf"), None)
    base_dir = opf.parent if opf else work_dir

    # 1. Ocisti atribute + stari spanovi + dropcap + ornament
    for ext in ("*.xhtml", "*.html", "*.htm"):
        for f in work_dir.rglob(ext):
            try:
                html = f.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue

            # Ocisti „ iz HTML atributa
            def _clean_tag(m):
                tag = m.group(0)
                if "„" in tag or "“" in tag or "”" in tag:
                    tag = tag.replace("„", "").replace("“", "").replace("”", "")
                return tag

            html = _re.sub(r"<[^>]+>", _clean_tag, html)

            soup = _BS(html, "html.parser")

            # Obrisi stare spanove bez stila
            for span in soup.find_all("span"):
                if span.get("style"):
                    continue
                t = span.get_text(strip=True)
                if len(t) == 1 and t.isalpha():
                    span.decompose()

            # Fix pokvareni src
            for el in soup.find_all(True):
                if "src" in el.attrs:
                    src = el.attrs["src"]
                    if isinstance(src, str):
                        novi = src.rstrip("/\"'")
                        m = _re.search(
                            r"\.(png|jpg|jpeg|gif|webp|svg)", novi, _re.IGNORECASE
                        )
                        if m:
                            novi = novi[: m.end()]
                        if novi != src and novi:
                            el.attrs["src"] = novi

            out = str(soup)
            if not out.startswith("<?xml"):
                out = '<?xml version="1.0" encoding="utf-8"?>\n' + out
            f.write_text(out, encoding="utf-8")

    # 2. CSS spajanje
    css_blokovi = set()
    for ext in ("*.xhtml", "*.html", "*.htm"):
        for f in work_dir.rglob(ext):
            try:
                html = f.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            soup = _BS(html, "html.parser")
            for style in soup.find_all("style"):
                if style.string:
                    css_blokovi.add(style.string.strip())

    if css_blokovi:
        css_path = base_dir / "styles.css"
        css_path.write_text("\n\n".join(sorted(css_blokovi)), encoding="utf-8")

        for f in work_dir.rglob("*"):
            if f.suffix.lower() not in (".xhtml", ".html", ".htm"):
                continue
            try:
                html = f.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            soup = _BS(html, "html.parser")
            head = soup.find("head")
            if head is None:
                continue
            ima_stil = False
            for style in head.find_all("style"):
                style.decompose()
                ima_stil = True
            if not ima_stil:
                continue
            try:
                rel = f.relative_to(base_dir)
                depth = len(rel.parts) - 1
                rel_href = ("../" * depth) + "styles.css"
            except Exception:
                rel_href = "styles.css"
            link = soup.new_tag(
                "link", rel="stylesheet", type="text/css", href=rel_href
            )
            head.append(link)
            out = str(soup)
            if not out.startswith("<?xml"):
                out = '<?xml version="1.0" encoding="utf-8"?>\n' + out
            f.write_text(out, encoding="utf-8")

    # 3. TOC NCX regeneracija
    ncx_path = None
    for f in work_dir.rglob("*.ncx"):
        if "OEBPS" in str(f):
            ncx_path = f
            break
    if ncx_path is None:
        for f in work_dir.rglob("*.ncx"):
            ncx_path = f
            break

    toc_xhtml = next(work_dir.rglob("toc.xhtml"), None)
    if ncx_path and toc_xhtml:
        try:
            href_map = {}
            soup = _BS(toc_xhtml.read_text(encoding="utf-8"), "html.parser")
            for a in soup.find_all("a"):
                h = (a.get("href") or "").strip().lstrip("./")
                t = a.get_text(strip=True)
                if h and t:
                    href_map[h] = t

            ncx_text = ncx_path.read_text(encoding="utf-8")
            text_iter = list(_re.finditer(r"<text>([^<]*)</text>", ncx_text))
            content_iter = list(_re.finditer(r'<content[^>]*src="([^"]+)"', ncx_text))
            zamjene = []
            for tm in text_iter:
                stari = tm.group(1)
                src = None
                for cm in content_iter:
                    if cm.start() > tm.start():
                        src = cm.group(1).strip().lstrip("./").split("/")[-1]
                        break
                if src and src in href_map:
                    novi = href_map[src]
                    if stari != novi:
                        zamjene.append((tm.start(1), tm.end(1), novi))

            if zamjene:
                novi_ncx = ncx_text
                for start, end, novi in reversed(zamjene):
                    novi_ncx = novi_ncx[:start] + novi + novi_ncx[end:]
                ncx_path.write_text(novi_ncx, encoding="utf-8")
        except Exception:
            logger.exception("[C1_kriticno] packager.py:336 Exception")

    # 4. Obrisi root toc.ncx
    oebps_ncx = work_dir / "OEBPS" / "toc.ncx"
    root_ncx = work_dir / "toc.ncx"
    if oebps_ncx.exists() and root_ncx.exists():
        root_ncx.unlink()

    # Tipografija na tekstualnim čvorovima (ne regex na HTML-u)
    try:
        from core.tipografija import normaliziraj_soup as _tip_n
        from bs4 import BeautifulSoup as _BS_typo, NavigableString as _NS_typo
        n_typo = 0
        for _f in list(work_dir.rglob("*.xhtml")) + list(work_dir.rglob("*.html")):
            try:
                _raw = _f.read_text(encoding="utf-8")
                _soup = _BS_typo(_raw, "html.parser")
                _changed = _tip_n(_soup) > 0
                if _changed:
                    _f.write_text(str(_soup), encoding="utf-8")
                    n_typo += 1
            except Exception:
                pass
        if n_typo:
            self.log(f"Tipografija: {n_typo} fajlova", "tech")
    except Exception as _e:
        self.log(f"Tipografija greška: {_e}", "warning")

    self.log("Finalni fixevi primijenjeni", "tech")


def _spoji_chk_u_files_dict(files: dict, checkpoint_dir: Path) -> int:
    """
    FIX 2026-10-26: Spoji .chk u files dict U MEMORIJI (ne na disk).
    Za razliku od _spoji_chk_u_html koji menja fajlove na disku,
    ova funkcija menja files dict direktno — bez disk I/O.

    Koristi se u run_epub_styler gde radimo sa files dict, ne sa diskom.
    """
    import re as _re_sd
    from bs4 import BeautifulSoup as _BS_sd

    checkpoint_dir = Path(checkpoint_dir)
    if not checkpoint_dir.exists():
        return 0

    chks = {}
    for f in checkpoint_dir.glob("*.chk"):
        if f.stem.endswith((".prevod", ".lektura")):
            continue
        m = _re_sd.match(r"(.+?)_blok_(\d+)$", f.stem)
        if not m:
            continue
        chks.setdefault(m.group(1), {})[int(m.group(2))] = f

    if not chks:
        return 0

    def _ocisti(t):
        t = _re_sd.sub(r"<!--\s*chunk_sha[^>]*-->\s*\n?", "", t)
        if t.strip().startswith("{"):
            try:
                import json as _j
                d = _j.loads(t)
                for k in ("finalno_polirano", "korektura", "tekst", "translated"):
                    if k in d and isinstance(d[k], str):
                        return d[k]
            except Exception:
                logger.warning("[C2_parse] packager.py:384 Exception")
        return t

    zamenjeno = 0
    # Mapiraj basename -> puni kljuc u files dict
    basename_to_key = {}
    for k in files.keys():
        if isinstance(k, str) and k.endswith((".html", ".xhtml", ".htm")):
            basename_to_key[k.split("/")[-1]] = k

    for html_name, blokovi in chks.items():
        # html_name je npr "part0082.html"
        key = basename_to_key.get(html_name)
        if key is None:
            continue

        try:
            soup = _BS_sd(files[key].decode("utf-8", "replace"), "html.parser")
        except Exception:
            continue
        body = soup.body
        if not body:
            continue

        delovi = []
        for i in sorted(blokovi.keys()):
            raw = _ocisti(blokovi[i].read_text("utf-8", errors="ignore")).strip()
            if not raw:
                continue

            # FIX 2026-10-26: Očisti .chk pre ubacivanja u files dict.
            # .chk ima sirovi HTML (galley-rw, section, h1, a, navodnici).
            try:
                _tmp = _BS_sd(raw, "html.parser")

                # Skini klase
                for el in _tmp.find_all(True):
                    if el.get("class"):
                        klase = el.get("class") or []
                        if isinstance(klase, str):
                            klase = klase.split()
                        nove = [
                            k for k in klase
                            if not any(x in k.lower() for x in (
                                "dc1_", "galley", "drop_capital",
                                "toc-", "chapter", "page-", "bt1_", "bt2_",
                                "copyright-", "part-",
                            ))
                        ]
                        if nove:
                            el["class"] = nove
                        else:
                            del el["class"]

                # Skini <a>
                for a in _tmp.find_all("a"):
                    a.unwrap()

                # Skini <section>, <div>, <span>
                for tag in _tmp.find_all(["section", "div", "span"]):
                    # Očuvaj dropcap span
                    style = str(tag.get("style", ""))
                    if tag.name == "span" and ("font-size:1px" in style or "color:transparent" in style):
                        continue
                    tag.unwrap()

                # Skini <h1>-<h6> (naslov je već u originalnom HTML-u)
                for h in _tmp.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
                    h.decompose()

                # Dijalog: navodnici → em-crtica
                try:
                    from core.tipografija import normaliziraj_soup as _tip_n
                    _tip_n(_tmp)
                except Exception:
                    logger.exception("[tipografija] packager")

                raw = str(_tmp.body) if _tmp.body else str(_tmp)
                if raw.startswith("<body>"):
                    raw = raw[6:]
                if raw.endswith("</body>"):
                    raw = raw[:-7]
                raw = raw.strip()
            except Exception:
                logger.exception("[C1_http] packager.py:477 Exception")

            if raw:
                delovi.append(raw)

        if not delovi:
            continue

        body.clear()
        ns = _BS_sd("".join(delovi), "html.parser")
        src_soup = ns.body or ns
        for c in list(src_soup.children):
            body.append(c.extract())

        files[key] = str(soup).encode("utf-8")
        zamenjeno += 1

    return zamenjeno


def _spoji_chk_u_html(engine):
    """
    FIX 2026-10-26: Spoji .chk blokove u HTML fajlove u work_dir PRE
    pakovanja EPUB-a.

    Uzrok problema: process_single_file_worker ažurira HTML iz final_parts,
    ali kad su svi blokovi cache hit, može se desiti da se HTML ne ažurira
    sinhrono sa .chk → finalize() pakuje HTML od PREVOD-a (837k) umesto
    lekturiranog (.chk, 918k). Gubitak 81k.

    Rešenje: pre pakovanja, za svaki HTML koji ima .chk u checkpoint_dir,
    spoji sve .chk blokove (sortirano po blok_idx) i prepiši <body>.

    Idempotentno — ne menja ništa ako su .chk već spojeni u HTML.
    """
    import re as _re_sk
    from pathlib import Path as _P

    from bs4 import BeautifulSoup as _BS

    work_dir = _P(engine.work_dir)
    checkpoint_dir = _P(engine.checkpoint_dir)

    # FIX 2026-10-26: Fallback na stariji _skr_ folder — i za work_dir i za
    # checkpoint_dir iz ISTOG foldera.
    # Kad output postane Joe_Abercrombie_..._PREVEDENO.epub, clean_book_name
    # postane Joe_Abercrombie_The_Trouble_With_Peace, ali i .chk i HTML su
    # u _skr_The_Trouble_With_Peace (od pre output-rename faze).
    from config.settings import CHECKPOINT_BASE_DIR as _CPB

    def _nadji_skr_folder():
        """Vrati _skr_ folder koji ima i .chk i text/ HTML."""
        # 1. Trenutni — mora imati .chk I text/ HTML
        ckpt = checkpoint_dir
        txt = work_dir / "text"
        if ckpt.exists() and any(ckpt.glob("*.chk")) and txt.exists() and any(txt.glob("*.html")):
            return work_dir

        # 2. Fuzzy po prefixu imena
        name = engine.clean_book_name
        for kljuc_len in (30, 25, 20, 15, 10):
            kljuc = name[:kljuc_len]
            if len(kljuc) < 8:
                continue
            for k in _CPB.glob(f"_skr_*{kljuc}*"):
                ckpt_k = k / "checkpoints"
                txt_k = k / "text"
                if (ckpt_k.exists() and any(ckpt_k.glob("*.chk"))
                        and txt_k.exists() and any(txt_k.glob("*.html"))):
                    return k

        # 3. Fuzzy po sufiksu — skini prefikse
        parts = name.split("_")
        for i in range(len(parts) - 1):
            suffix = "_".join(parts[i:])
            if len(suffix) < 8:
                continue
            for k in _CPB.glob(f"_skr_*{suffix}*"):
                ckpt_k = k / "checkpoints"
                txt_k = k / "text"
                if (ckpt_k.exists() and any(ckpt_k.glob("*.chk"))
                        and txt_k.exists() and any(txt_k.glob("*.html"))):
                    return k

        return None

    pravi_skr = _nadji_skr_folder()
    if pravi_skr is None:
        engine.log("⚠ _spoji_chk_u_html: nema _skr_ sa .chk + text/", "warning")
        return 0

    stvarni_work_dir = pravi_skr
    stvarni_chk_dir = pravi_skr / "checkpoints"

    if stvarni_work_dir != work_dir or stvarni_chk_dir != checkpoint_dir:
        engine.log(
            f"🔍 _spoji_chk_u_html: koristim _skr_{pravi_skr.name[5:]}",
            "tech",
        )

    # Skupi .chk po HTML fajlu
    chks = {}
    for f in stvarni_chk_dir.glob("*.chk"):
        if f.stem.endswith((".prevod", ".lektura")):
            continue
        m = _re_sk.match(r"(.+?)_blok_(\d+)$", f.stem)
        if not m:
            continue
        chks.setdefault(m.group(1), {})[int(m.group(2))] = f

    if not chks:
        return 0

    def _ocisti_chk(t):
        t = _re_sk.sub(r"<!--\s*chunk_sha[^>]*-->\s*\n?", "", t)
        if t.strip().startswith("{"):
            try:
                import json as _j
                d = _j.loads(t)
                for k in ("finalno_polirano", "korektura", "tekst", "translated"):
                    if k in d and isinstance(d[k], str):
                        return d[k]
            except Exception:
                logger.warning("[C2_parse] packager.py:600 Exception")
        return t

    zamenjeno = 0
    for html_name, blokovi in chks.items():
        src = stvarni_work_dir / "text" / html_name
        if not src.exists():
            # Pokušaj rekurzivno
            found = list(stvarni_work_dir.rglob(html_name))
            if not found:
                continue
            src = found[0]

        try:
            soup = _BS(src.read_text("utf-8", errors="ignore"), "html.parser")
        except Exception:
            continue

        body = soup.body
        if not body:
            continue

        delovi = []
        for i in sorted(blokovi.keys()):
            raw = _ocisti_chk(blokovi[i].read_text("utf-8", errors="ignore")).strip()
            if not raw:
                continue

            # FIX 2026-10-26: Očisti .chk pre ubacivanja u HTML.
            # .chk može imati sirovi HTML iz lekture:
            #   - <div class="galley-rw">, <span class="dc1_drop_capital_">
            #   - <a> tagove, <section> tagove
            #   - ASCII navodnike "..." u dijalogu (treba → —)
            # Redosled: strip → normalizuj → dijalog
            try:
                from bs4 import BeautifulSoup as _BS_C
                _tmp_soup = _BS_C(raw, "html.parser")

                # 1. Skini stare klase (dc1_drop_capital_, galley-rw, itd.)
                for el in _tmp_soup.find_all(True):
                    if el.get("class"):
                        klase = el.get("class") or []
                        if isinstance(klase, str):
                            klase = klase.split()
                        nove = [
                            k for k in klase
                            if not any(x in k.lower() for x in (
                                "dc1_", "galley", "drop_capital",
                                "toc-", "chapter", "page-", "bt1_", "bt2_",
                            ))
                        ]
                        if nove:
                            el["class"] = nove
                        else:
                            del el["class"]
                    # Skini id koji je Calibre-ov anchor
                    if el.get("id") and el.name in ("h1", "h2", "h3", "a", "section"):
                        if any(x in str(el.get("id")).lower() for x in (
                            "chapter", "toc-", "page-", "1737",
                        )):
                            del el["id"]

                # 2. Skini <a> tagove koji su samo navigacioni (bez href ili href u istoj knjizi)
                for a in _tmp_soup.find_all("a"):
                    href = a.get("href", "")
                    if not href or href.startswith("#") or "part0" in href or "toc-" in href:
                        a.unwrap()

                # 3. Skini <section> (unwrap)
                for sec in _tmp_soup.find_all("section"):
                    sec.unwrap()

                # 4. Skini <div> sa tekstom → unwrap, sa decom → unwrap
                for div in _tmp_soup.find_all("div"):
                    div.unwrap()

                # 5. Skini <span> sa decom → unwrap (dc1_drop_capital)
                for span in _tmp_soup.find_all("span"):
                    span.unwrap()

                # 6. Dijalog: ASCII "..." → —
                try:
                    from core.tipografija import normaliziraj_soup as _tip_n
                    _tip_n(_tmp_soup)
                except Exception:
                    logger.exception("[tipografija] packager")

                # 7. Skini <h1>/<h2>/<h3> iz .chk sadržaja (naslov je već u originalnom HTML-u)
                for h in _tmp_soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
                    h.decompose()

                raw = str(_tmp_soup.body) if _tmp_soup.body else str(_tmp_soup)
                # Skini <body> wrapper ako postoji
                if raw.startswith("<body>"):
                    raw = raw[6:]
                if raw.endswith("</body>"):
                    raw = raw[:-7]
                raw = raw.strip()
            except Exception as _ce:
                engine.log(f"⚠ čišćenje .chk palo: {_ce}", "warning")
                # Fallback: koristi original
                pass

            if raw:
                delovi.append(raw)

        if not delovi:
            # Nema .chk za ovaj fajl (paratekst) — samo ocisti HTML
            try:
                for el in soup.find_all(True):
                    if el.get("class"):
                        klase = el.get("class") or []
                        if isinstance(klase, str):
                            klase = klase.split()
                        nove = [
                            k for k in klase
                            if not any(x in k.lower() for x in (
                                "dc1_", "galley", "drop_capital",
                                "toc-", "chapter", "page-", "bt1_", "bt2_",
                            ))
                        ]
                        if nove:
                            el["class"] = nove
                        else:
                            del el["class"]
                for a in soup.find_all("a"):
                    href = a.get("href", "")
                    if not href or href.startswith("#") or "part0" in href or "toc-" in href:
                        a.unwrap()
                for sec in soup.find_all("section"):
                    sec.unwrap()
                for div in soup.find_all("div"):
                    div.unwrap()
                for span in soup.find_all("span"):
                    span.unwrap()
                # Dijalog i na fajlovima bez .chk
                try:
                    from core.tipografija import normaliziraj_soup as _tip_n
                    _tip_n(soup)
                except Exception:
                    logger.exception("[tipografija] packager")
                src.write_text(str(soup), encoding="utf-8")
                zamenjeno += 1
            except Exception:
                logger.exception("[C1_kriticno] packager.py:762 Exception")
            continue

        body.clear()
        ns = _BS("".join(delovi), "html.parser")
        src_soup = ns.body or ns
        for c in list(src_soup.children):
            body.append(c.extract())

        # FINALNO CISCENJE — posle ubacivanja .chk u body
        # Ukloni sve sto je ostalo (galley-rw, dc1_, navodnike)
        try:
            for el in soup.find_all(True):
                if el.get("class"):
                    klase = el.get("class") or []
                    if isinstance(klase, str):
                        klase = klase.split()
                    nove = [
                        k for k in klase
                        if not any(x in k.lower() for x in (
                            "dc1_", "galley", "drop_capital",
                            "toc-", "chapter", "page-", "bt1_", "bt2_",
                        ))
                    ]
                    if nove:
                        el["class"] = nove
                    else:
                        del el["class"]
            for div in soup.find_all("div"):
                div.unwrap()
            for span in soup.find_all("span"):
                # Očuvaj dropcap span (font-size:1px) i sliku
                style = str(span.get("style", ""))
                if "font-size:1px" in style or "color:transparent" in style:
                    continue
                span.unwrap()
            # Dijalog posle ubacivanja (finalni prolaz)
            try:
                from core.tipografija import normaliziraj_soup as _tip_n
                _tip_n(soup)
            except Exception:
                logger.exception("[tipografija] packager")
        except Exception:
            logger.exception("[C1_http] packager.py:814 Exception")

        src.write_text(str(soup), encoding="utf-8")
        zamenjeno += 1

    return zamenjeno


def finalize(self):
    """
    1. Pakuje finalni EPUB u INPUT_DIR (kao i dosad).
    2. Kopira ga u OUTPUT_DIR (/storage/emulated/0/Books/MoonReader/booklyfi).
    3. Upisuje stvarnu putanju u shared_stats["output_file"].
    4. Briše (LIVE) privremeni fajl.
    """
    output_dir = _get_output_dir()

    # ── 1. Pakuj EPUB ────────────────────────────────────────────────────────
    # Zaštita: provjeri container.xml prije pakovanja
    if _osiguraj_container_xml is not None:
        # Skupi sve fajlove iz work_dir
        _tmp_files = {}
        for _f in self.work_dir.rglob("*"):
            if _f.is_file() and "checkpoints" not in _f.parts:
                _rel = _f.relative_to(self.work_dir).as_posix()
                _tmp_files[_rel] = _f.read_bytes()
        if _osiguraj_container_xml(_tmp_files):
            self.log("🔧 container.xml regeneriran", "warning")
            # Zapiši natrag
            for _rel, _data in _tmp_files.items():
                _f2 = self.work_dir / _rel
                _f2.write_bytes(_data)

    # Finalni fixevi (dropcap, ornament, CSS, TOC)
    try:
        _finaliziraj_fix_epub(self)
    except Exception as _e:
        self.log("Finalni fixevi greska: " + str(_e), "warning")

    try:
        # ─── BooklyFi Metadata Standardizacija ───

        try:
            import shutil as _sh
            from datetime import datetime as _dt
            from zipfile import ZipFile as _ZipF

            from core.metadata import standardizuj_metapodatke

            # Učitaj sve fajlove iz upravo snimljenog EPUB-a

            with _ZipF(self.out_path) as _z:
                _files = {n: _z.read(n) for n in _z.namelist() if not n.endswith("/")}

            # Nađi OPF

            _opf = next((n for n in _files if n.endswith(".opf")), None)

            if _opf:
                # Prikupi kontekst

                _translated_at = None

                _stylized_at = _dt.now().isoformat(timespec="seconds")

                _quality_score = None

                _glossary_id = None

                # Iz shared_stats — quality score

                try:
                    _ss = getattr(self, "shared_stats", None)

                    if _ss:
                        _qs = _ss.get("quality_scores", {})

                        if _qs:
                            _vals = [
                                v for v in _qs.values() if isinstance(v, (int, float))
                            ]

                            if _vals:
                                _quality_score = sum(_vals) / len(_vals)

                        _mode = _ss.get("knjiga_mode")

                        if _mode:
                            # Ako je prevođeno — postavi translated_at

                            _translated_at = _dt.now().isoformat(timespec="seconds")

                except Exception:
                    logger.exception("[C1_http] packager.py:907 Exception")

                # Glossary ID

                try:
                    _glosar_path = (
                        self.checkpoint_dir.parent / "data" / "kanon" / "knjige"
                    )

                    _knjiga_id = getattr(self, "clean_book_name", "")

                    if _knjiga_id and (_glosar_path / f"{_knjiga_id}.json").exists():
                        _glossary_id = _knjiga_id

                except Exception:
                    logger.exception("[C1_kriticno] packager.py:922 Exception")

                # Standardizuj

                _stats = standardizuj_metapodatke(
                    files=_files,
                    opf_path=_opf,
                    epub_path=str(self.out_path),
                    translated_at=_translated_at,
                    stylized_at=_stylized_at,
                    glossary_id=_glossary_id,
                    quality_score=_quality_score,
                    pipeline_version=getattr(self, "model_name", "V10_TURBO"),
                )

                if _stats.get("ok"):
                    # Ponovo snimi EPUB sa ažuriranim OPF-om

                    _tmp = str(self.out_path) + ".meta.tmp"

                    with _ZipF(_tmp, "w") as _z:
                        if "mimetype" in _files:
                            _z.writestr(
                                "mimetype", _files["mimetype"], compress_type=0
                            )  # ZIP_STORED

                        for _n, _d in _files.items():
                            if _n == "mimetype":
                                continue

                            _z.writestr(_n, _d)

                    _sh.move(_tmp, str(self.out_path))

                    self.log(
                        f"📋 Metadata standardizovani ({_stats['booklyfi_meta_added']} booklyfi polja)",
                        "tech",
                    )

        except Exception as _me:
            with contextlib.suppress(Exception):
                self.log(f"⚠ Metadata greška: {_me}", "warning")


        # FIX 2026-10-26: Spoji .chk u HTML pre pakovanja.
        # Garantuje da EPUB sadrži lekturirani tekst, ne HTML od PREVOD-a.
        try:
            _spojeno = _spoji_chk_u_html(self)
            if _spojeno > 0:
                self.log(
                    f"🔗 Spojeno {_spojeno} HTML fajlova iz .chk prije pakovanja",
                    "tech",
                )
        except Exception as _e:
            self.log(f"⚠ Spajanje .chk u HTML palo: {_e}", "warning")

        # FIX 2026-10-26: Streaming pakovanje sa minimalnom memorijom.
        # compresslevel=1 (3x manje memorije), mimetype prvi bez kompresije.
        with zipfile.ZipFile(
            self.out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=1
        ) as z:
            mimetype = self.work_dir / "mimetype"
            if mimetype.exists():
                z.write(mimetype, "mimetype", compress_type=zipfile.ZIP_STORED)
            for f in self.work_dir.rglob("*"):
                if not f.is_file():
                    continue
                if "checkpoints" in f.parts:
                    continue
                if f.name == "mimetype":
                    continue
                z.write(f, f.relative_to(self.work_dir))
        self.log(f"📦 EPUB spakovan: {self.out_path.name}", "tech")
    except Exception as e:
        self.log(f"❌ Pakovanje EPUB-a palo: {e}", "error")
        raise

    # ── 2. Kopiraj u MoonReader direktorij ──────────────────────────────────
    moon_path = output_dir / self.out_path.name
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        if self.out_path.resolve() == moon_path.resolve():
            final_path = moon_path
            self.log(
                f"📱 EPUB već u MoonReader: {moon_path}",
                "system",
            )
        else:
            shutil.copy2(str(self.out_path), str(moon_path))
            final_path = moon_path
            self.log(
                f"📱 EPUB kopiran u MoonReader: {moon_path}",
                "system",
            )
    except Exception as e:
        self.log(
            f"⚠️ Kopiranje u MoonReader nije uspjelo ({e}). "
            f"EPUB dostupan na: {self.out_path}",
            "warning",
        )
        final_path = self.out_path

    # ── 3. Upisi putanju u shared_stats ─────────────────────────────────────
    self.shared_stats["output_file"] = str(final_path)
    self.shared_stats["output_dir"] = str(output_dir)
    self.shared_stats["status"] = "ZAVRŠENO"

    self.log(
        f"✅ Knjiga završena! Putanja: {final_path}",
        "system",
    )

    # ── 4. Obriši (LIVE) privremeni fajl ────────────────────────────────────
    try:
        from config.settings import INPUT_DIR

        live_epub = Path(INPUT_DIR) / f"(LIVE)_{self.clean_book_name}.epub"
    except Exception:
        live_epub = self.book_path.parent / f"(LIVE)_{self.clean_book_name}.epub"

    try:
        if live_epub.exists():
            live_epub.unlink()
            self.log("🗑️ Live preview fajl obrisan.", "tech")
    except Exception:
        pass