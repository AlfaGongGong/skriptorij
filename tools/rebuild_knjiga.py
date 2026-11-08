#!/usr/bin/env python3
"""rebuild_knjiga: P2.6e - slaganje EPUB-a iz .chk (generate_ncx -> finalize -> styler) za bilo koju knjigu.
Upotreba: rebuild_knjiga.py <izvorni_epub> [knjiga]
[knjiga]: engine izvodi work_dir (_skr_<ime>) iz imena izvornog fajla, pa se izvor kopira
u privremeni <knjiga>.epub (nuzno kad se izvor zove drukcije od _skr_ foldera).
Zadnji redak ispisa: STYLED=<putanja>. Kod 0 = uspjeh.
Isto kao heredoc u tools/booklyfi_rebuild_gate.sh, ali parametrizirano (taj skript ostaje netaknut).
"""
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
os.chdir(REPO)
_TMP = []
sys.path.insert(0, str(REPO))


def main(argv):
    if len(argv) < 2:
        print("Upotreba: rebuild_knjiga.py <izvorni_epub> [knjiga]")
        return 1
    book = Path(argv[1])
    if not book.is_file():
        print(f"STOP: nema {book}")
        return 1
    if len(argv) > 2 and argv[2].strip():
        tmpd = Path(tempfile.mkdtemp(prefix="rebuild_"))
        _TMP.append(tmpd)
        kopija = tmpd / (argv[2].strip() + ".epub")
        shutil.copy2(book, kopija)
        print(f"Izvor kopiran kao {kopija.name} (work_dir po imenu knjige)")
        book = kopija
    try:
        from core.engine import SkriptorijAllInOne
        from epub.manager import EpubStylerManager
        ss, sc = {}, {}
        e = SkriptorijAllInOne(str(book), "V10_TURBO", ss, sc)
        if not getattr(e, "html_files", None):
            e.html_files = sorted((Path(e.work_dir) / "text").glob("*.html"))
        print(f"HTML fajlova u work_dir: {len(e.html_files)}")
        e.generate_ncx()
        e.finalize()
        of = ss.get("output_file")
        u = Path(of) if of else Path(e.out_path)
        if not u.is_absolute():
            from config.settings import OUTPUT_DIR
            u = Path(OUTPUT_DIR) / u
        if not u.is_file():
            print("STOP: finalize nije napravio EPUB:", u)
            return 1
        print(f"Medjukorak: {u} ({u.stat().st_size} B)")
        r = EpubStylerManager(epub_path=u, log_callback=lambda m, a="info": None).stilizuj()
        print(f"Stilizacija ok={r.get('ok')}, poglavlja={r.get('chapters')}")
        s = Path(r.get("epub_path", "") or "")
        if not s.is_file():
            print("STOP: stilizacija nije napravila EPUB.")
            return 1
        print(f"STYLED={s}")
        return 0
    except Exception as ex:
        print(f"Rebuild greska: {ex!r}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    rc = main(sys.argv)
    for _d in _TMP:
        shutil.rmtree(_d, ignore_errors=True)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(rc)
