import zipfile
from pathlib import Path

import pytest

from core import epub_popravci as EP

CSS = """body { color: red }
@font-face {
    font-family: "A";
    src: url(OEBPS/Styles/styles/XXXXXXXXXXXXXXXX);
}
@font-face {
    font-family: "B";
    src: url(OEBPS/Fonts/ok.otf);
}
@font-face { font-family: "C"; src: url(OEBPS/Fonts/nema.woff), url(OEBPS/Fonts/ok.otf); }
"""


def _epub(tmp_path, html_id, guide_frag, css=CSS):
    p = tmp_path / "t.epub"
    opf = ('<package><manifest/><guide><reference href="OEBPS/Text/p.html'
           + (f"#{guide_frag}" if guide_frag else "") + '" title="C" type="toc"/></guide></package>')
    with zipfile.ZipFile(p, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), b"application/epub+zip")
        z.writestr("content.opf", opf)
        z.writestr("page_styles.css", css)
        z.writestr("OEBPS/Fonts/ok.otf", b"font")
        z.writestr("OEBPS/Text/p.html", f'<html><body id="{html_id}"><p>x</p></body></html>')
    return p


def _citaj(p, ime):
    with zipfile.ZipFile(p) as z:
        return z.read(ime).decode("utf-8")


def test_css_uklanja_samo_mrtve_font_face(tmp_path):
    p = _epub(tmp_path, "a1", "a1")
    st = EP.popravi(p)
    css = _citaj(p, "page_styles.css")
    assert st["font_face_uklonjeno"] == 1
    assert "XXXXXXXXXXXXXXXX" not in css and "ok.otf" in css and "body { color: red }" in css
    assert 'font-family: "C"' in css  # ima bar jedan postojeci url


def test_guide_fragment_ostaje_ako_postoji(tmp_path):
    p = _epub(tmp_path, "abc", "abc")
    st = EP.popravi(p)
    assert 'p.html#abc"' in _citaj(p, "content.opf")
    assert st["guide_fragment_popravljen"] == 0 and st["guide_fragment_skinut"] == 0


def test_guide_fragment_prepravlja_na_x_prefiks(tmp_path):
    p = _epub(tmp_path, "x1T140-abc", "1T140-abc")
    st = EP.popravi(p)
    assert 'p.html#x1T140-abc"' in _citaj(p, "content.opf")
    assert st["guide_fragment_popravljen"] == 1


def test_guide_fragment_skida_ako_nema_ni_jedan(tmp_path):
    p = _epub(tmp_path, "nesto", "nema-ga")
    st = EP.popravi(p)
    opf = _citaj(p, "content.opf")
    assert 'href="OEBPS/Text/p.html"' in opf and "#" not in opf
    assert st["guide_fragment_skinut"] == 1


def test_idempotentno_i_mimetype_prvi(tmp_path):
    p = _epub(tmp_path, "x1T", "1T")
    EP.popravi(p)
    st2 = EP.popravi(p)
    assert st2 == {"font_face_uklonjeno": 0, "guide_fragment_popravljen": 0, "guide_fragment_skinut": 0}
    with zipfile.ZipFile(p) as z:
        i0 = z.infolist()[0]
        assert i0.filename == "mimetype" and i0.compress_type == zipfile.ZIP_STORED
        assert z.testzip() is None


def test_izlazni_fajl_ulaz_netaknut(tmp_path):
    p = _epub(tmp_path, "x1T", "1T")
    prije = p.read_bytes()
    out = tmp_path / "out.epub"
    EP.popravi(p, out)
    assert p.read_bytes() == prije and out.exists() and "#x1T" in _citaj(out, "content.opf")


def test_zavrsi_poziva_popravke_prije_provjere():
    s = (Path(__file__).resolve().parent.parent / "core" / "zavrsi.py").read_text("utf-8")
    assert s.count("epub_popravci.popravi(styled)") == 1
    assert s.index("epub_popravci.popravi(styled)") < s.index('upd(korak="provjera")')
