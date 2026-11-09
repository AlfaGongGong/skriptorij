import zipfile

from epub.ocisti import ocisti_epub


def _epub(p):
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("OEBPS/a.xhtml", '<html><body><p id="x">T<img src="indent.jpg"/><a href="#nema">link</a><a href="b.xhtml#y">ok</a><a href="b.xhtml#nema">mrtav</a><img src="s.png"/></p></body></html>')
        z.writestr("OEBPS/b.xhtml", '<html><body><p id="y">B</p></body></html>')
        z.writestr("OEBPS/s.png", b"x")


def test_ocisti(tmp_path):
    p = tmp_path / "t.epub"
    _epub(p)
    assert ocisti_epub(p, dry=True) == {"img": 1, "link": 2, "datoteka": 1}
    r = ocisti_epub(p)
    assert r["img"] == 1 and r["link"] == 2
    h = zipfile.ZipFile(p).read("OEBPS/a.xhtml").decode()
    assert "indent.jpg" not in h and "#nema" not in h and 'href="b.xhtml#y"' in h and "s.png" in h
    assert zipfile.ZipFile(p).namelist()[0] == "mimetype"
    assert ocisti_epub(p)["datoteka"] == 0
