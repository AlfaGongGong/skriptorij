import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bs4 import BeautifulSoup
import epub.styler as S

LONG = "Ovo je dugacak odlomak koji pocinje pravim tekstom poglavlja i ima vise od sezdeset znakova da bi dropcap mogao na njega. " * 4


def test_broj_iz_samo_slike():
    f = S._broj_iz_samo_slike
    assert f(b'<html><head><title>x</title></head><body><h1>12</h1><img src="a.png"/></body></html>') == "12"
    assert f(b'<html><body><h1>Chapter 7</h1><img src="a.png"/></body></html>') == "7"
    assert f(b'<html><body><p>XIV.</p><img src="a.png"/></body></html>') == "XIV"
    assert f(b'<html><body><img src="a.png"/></body></html>') is None
    assert f(b'<html><body><p>Prolog</p><img src="a.png"/></body></html>') is None


def _soup(h1):
    return BeautifulSoup('<html><body><h1 class="booklyfi-naslov">%s</h1><p>%s</p></body></html>' % (h1, LONG), "html.parser")


def test_primjena_naslov():
    s = _soup("Obmana")
    r = S._primijeni_broj_prethodnog(s, "12", "Obmana", 5)
    assert r == "POGLAVLJE 12 \u2013 Obmana" and s.find("h1").get_text() == r


def test_primjena_redni_fallback():
    s = _soup("POGLAVLJE 5")
    assert S._primijeni_broj_prethodnog(s, "12", "POGLAVLJE 5", 5) == "POGLAVLJE 12"


def test_primjena_ne_dira_postojeci_broj():
    for h in ("POGLAVLJE 12 \u2013 Obmana", "POGLAVLJE 9", "9"):
        s = _soup(h)
        assert S._primijeni_broj_prethodnog(s, "12", h, 5) == h
        assert s.find("h1").get_text() == h


def _mini_epub(path, cover_png):
    ch = lambda t, b: ('<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>%s</title></head><body>%s</body></html>' % (t, b)).encode()
    files = {
        "mimetype": b"application/epub+zip",
        "META-INF/container.xml": b'<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
        "OEBPS/img.png": cover_png,
        "OEBPS/content.opf": b'<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Test Knjiga</dc:title><dc:creator>Autor</dc:creator><dc:language>hr</dc:language><dc:identifier id="id">x1</dc:identifier></metadata><manifest><item id="a" href="a.xhtml" media-type="application/xhtml+xml"/><item id="b" href="b.xhtml" media-type="application/xhtml+xml"/><item id="c" href="c.xhtml" media-type="application/xhtml+xml"/><item id="d" href="d.xhtml" media-type="application/xhtml+xml"/><item id="img" href="img.png" media-type="image/png"/></manifest><spine><itemref idref="a"/><itemref idref="b"/><itemref idref="c"/><itemref idref="d"/></spine></package>',
        "OEBPS/a.xhtml": ch("Test Knjiga", '<h1>1</h1><img src="img.png"/>'),
        "OEBPS/b.xhtml": ch("Test Knjiga", "<p>Obmana</p><p>%s</p><p>%s</p>" % (LONG, LONG)),
        "OEBPS/c.xhtml": ch("Test Knjiga", '<h1>2</h1><img src="img.png"/>'),
        "OEBPS/d.xhtml": ch("Test Knjiga", "<p>%s</p><p>%s</p>" % (LONG, LONG)),
    }
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", files.pop("mimetype"), zipfile.ZIP_STORED)
        for n, d in files.items():
            z.writestr(n, d)


def test_integracija_styler(tmp_path):
    import base64
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
    src, out = tmp_path / "in.epub", tmp_path / "out.epub"
    _mini_epub(src, png)
    res = S.run_epub_styler(str(src), output_path=str(out))
    assert res.get("ok") is True, res
    with zipfile.ZipFile(out) as z:
        h1 = {}
        for n in z.namelist():
            if n.endswith((".xhtml", ".html")) and "booklyfi_" not in n:
                sp = BeautifulSoup(z.read(n), "html.parser")
                h = sp.find("h1")
                h1[n.rsplit("/", 1)[-1]] = h.get_text() if h else None
    assert h1.get("b.xhtml") == "POGLAVLJE 1 \u2013 Obmana", h1
    assert h1.get("d.xhtml") == "POGLAVLJE 2", h1


def test_toc_hr_mapa_broj_i_naslov():
    toc = (
        '<html><body>'
        '<p><a href="CR%21X_split_005.html#a"> Zahvale</a></p>'
        '<p><a href="CR%21X_split_008.html#b"> Prolog</a></p>'
        '<p><a href="CR%21X_split_010.html#c"> 1: Dan vjen\u010danja</a></p>'
        '<p><a href="CR%21X_split_012.html#d"> 2: Obmana</a></p>'
        '<p><a href="CR%21X_split_014.html#e"> 3: Kutija</a></p>'
        '</body></html>'
    ).encode("utf-8")
    files = {"OEBPS/CR!X_split_007.html": toc, "OEBPS/a.html": b"<html><body><p>nema</p></body></html>"}
    m = S._toc_hr_mapa(files)
    assert m["CR!X_split_010.html"] == ("1", "Dan vjen\u010danja")
    assert m["CR!X_split_012.html"] == ("2", "Obmana")
    assert m["CR!X_split_008.html"] == (None, "Prolog")


def test_toc_hr_mapa_premalo_stavki():
    toc = b'<html><body><p><a href="a.html">1: Prvo</a></p><p><a href="b.html">Kraj</a></p></body></html>'
    assert S._toc_hr_mapa({"t.html": toc}) == {}


def test_hrvatski_toc_naslov_ostaje():
    s = BeautifulSoup('<html><body><p>%s</p></body></html>' % (LONG * 3), "html.parser")
    r = S._dodaj_naslov(s, 5, naslov="POGLAVLJE 1 \u2013 Dan vjen\u010danja", knjiga="Kralj trnja")
    assert r == "POGLAVLJE 1 \u2013 Dan vjen\u010danja"
