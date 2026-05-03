

# epub/packager.py
import shutil
import zipfile
from pathlib import Path
from bs4 import BeautifulSoup


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
# Dropcap & TOC
# ─────────────────────────────────────────────────────────────────────────────

def apply_dropcap_and_toc(self, soup, html_file, samo_dropcap=False):
    """Injectira CSS i puni TOC listu za NCX navigaciju."""
    from epub.styling import _inject_epub_global_css
    _inject_epub_global_css(soup)

    if samo_dropcap:
        return

    # Dropcap na prvom paragrafu
    first_p = soup.find("p")
    if first_p and first_p.get_text(strip=True):
        tekst = first_p.get_text(strip=True)
        if tekst and len(tekst) > 1:
            first_char = tekst[0]
            rest = str(first_p)
            if '<span class="dropcap"' not in rest:
                original_html = str(first_p)
                new_html = original_html.replace(
                    first_char,
                    f'<span class="dropcap">{first_char}</span>',
                    1,
                )
                from bs4 import BeautifulSoup as _BS
                first_p.replace_with(_BS(new_html, "html.parser"))

    # Puni toc_entries za NCX
    rel_path = html_file.relative_to(self.work_dir)
    title = None
    for tag in ["h1", "h2", "h3"]:
        h = soup.find(tag)
        if h and h.get_text(strip=True):
            title = h.get_text(strip=True)[:60]
            break
    if not title:
        title = (
            html_file.stem.replace("chapter", "Poglavlje ")
            .replace("_", " ")
            .title()
        )

    href = str(rel_path).replace("\\", "/")
    if not any(e[1] == href for e in self.toc_entries):
        self.toc_entries.append((title, href))


# ─────────────────────────────────────────────────────────────────────────────
# NCX generator
# ─────────────────────────────────────────────────────────────────────────────

def generate_ncx(self):
    """Minimalni NCX generator za EPUB navigaciju."""
    ncx_path = self.work_dir / "toc.ncx"

    nav_points = ""
    for i, (title, href) in enumerate(self.toc_entries, 1):
        safe_title = (
            title.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
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

def finalize(self):
    """
    1. Pakuje finalni EPUB u INPUT_DIR (kao i dosad).
    2. Kopira ga u OUTPUT_DIR (/storage/emulated/0/Books/MoonReader/booklyfi).
    3. Upisuje stvarnu putanju u shared_stats["output_file"].
    4. Briše (LIVE) privremeni fajl.
    """
    output_dir = _get_output_dir()

    # ── 1. Pakuj EPUB ────────────────────────────────────────────────────────
    # out_path je definiran u engine.__init__ kao INPUT_DIR / PREVEDENO_xxx.epub
    try:
        with zipfile.ZipFile(self.out_path, "w", zipfile.ZIP_DEFLATED) as z:
            for f in self.work_dir.rglob("*"):
                if f.is_file() and "checkpoints" not in f.parts:
                    z.write(f, f.relative_to(self.work_dir))
        self.log(f"📦 EPUB spakovan: {self.out_path.name}", "tech")
    except Exception as e:
        self.log(f"❌ Pakovanje EPUB-a palo: {e}", "error")
        raise

    # ── 2. Kopiraj u MoonReader direktorij ──────────────────────────────────
    moon_path = output_dir / self.out_path.name
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(self.out_path), str(moon_path))
        final_path = moon_path
        self.log(
            f"📱 EPUB kopiran u MoonReader: {moon_path}",
            "system",
        )
    except Exception as e:
        # Fallback: ostaje na INPUT_DIR putanji
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



