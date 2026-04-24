# epub/packager.py
import zipfile
import random
from pathlib import Path
from bs4 import BeautifulSoup

def buildlive_epub(self):
    live_epub = self.book_path.parent / f"(LIVE)_{self.clean_book_name}.epub"
    with zipfile.ZipFile(live_epub, "w", zipfile.ZIP_DEFLATED) as z:
        for f in self.work_dir.rglob("*"):
            if f.is_file() and "checkpoints" not in f.parts:
                z.write(f, f.relative_to(self.work_dir))

def apply_dropcap_and_toc(self, soup, html_file, samo_dropcap=False):
    # pojednostavljeno – samo CSS inject
    from epub.styling import _inject_epub_global_css
    _inject_epub_global_css(soup)
    # ... ostatak dropcap logike (preuzeti iz starog koda) ...

def generate_ncx(self):
    # preuzeti iz starog koda
    pass

def finalize(self):
    with zipfile.ZipFile(self.out_path, "w") as z:
        for f in self.work_dir.rglob("*"):
            if f.is_file() and "checkpoints" not in f.parts:
                z.write(f, f.relative_to(self.work_dir))
    self.log(f"📖 EPUB: {self.out_path.name}", "system")
