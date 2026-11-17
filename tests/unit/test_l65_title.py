import base64
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bs4 import BeautifulSoup
import epub.styler as S

LONG = "Ovo je dugacak odlomak koji pocinje pravim tekstom poglavlja i ima vise od sezdeset znakova da bi dropcap mogao na njega. " * 4
PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


def _epub(path, naslov, dokumenti):
    ch = lambda b: ('<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>%s</title></head><body>%s</body></html>' % (naslov, b)).encode()
    man = "".join('<item id="d%d" href="d%d.xhtml" media-type="application/xhtml+xml"/>' % (i, i) for i in range(len(dokumenti)))
    spine = "".join('<itemref idref="d%d"/>' % i for i in range(len(dokumenti)))
    opf = ('<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>%s</dc:title><dc:creator>Autor</dc:creator><dc:language>hr</dc:language><dc:identifier id="id">x1</dc:identifier></metadata><manifest>%s<item id="img" href="img.png" media-type="image/png"/></manifest><spine>%s</spine></package>' % (naslov, man, spine)).encode()
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", b"application/epub+zip", zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", b'<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        z.writestr("OEBPS/img.png", base64.b64decode(PNG))
        z.writestr("OEBPS/content.opf", opf)
        for i, b in enumerate(dokumenti):
            z.writestr("OEBPS/d%d.xhtml" % i, ch(b))


def _h1(out):
    r = {}
    with zipfile.ZipFile(out) as z:
        for n in z.namelist():
            if n.endswith((".xhtml", ".html")) and "booklyfi_" not in n:
                h = BeautifulSoup(z.read(n), "html.parser").find("h1")
                r[n.rsplit("/", 1)[-1]] = h.get_text() if h else None
    return r


@pytest.mark.parametrize("naslov", [
    "Kralj trnja",
    "Kralj trnja: Druga knjiga Slomljenog Carstva",
    "Kralj trnja: Druga knjiga Slomljenog Carstva (hrvatsko izdanje)",
    "King of Thorns: Book Two of the Broken Empire",
])
def test_broj_slika_s_dugackim_naslovom(tmp_path, naslov):
    dok = [
        '<h1>5</h1><img src="img.png"/>',
        "<p>Dan vjen\u010danja</p><p>%s</p><p>%s</p>" % (LONG, LONG),
        '<h1>6</h1><img src="img.png"/>',
        "<p>%s</p><p>%s</p>" % (LONG, LONG),
        '<p>XIV.</p><img src="img.png"/>',
        "<p>Otvori kutiju</p><p>%s</p><p>%s</p>" % (LONG, LONG),
    ]
    src, out = tmp_path / "in.epub", tmp_path / "out.epub"
    _epub(src, naslov, dok)
    res = S.run_epub_styler(str(src), output_path=str(out))
    assert res.get("ok") is True, res
    h = _h1(out)
    assert h.get("d1.xhtml") == "POGLAVLJE 5 \u2013 Dan vjen\u010danja", h
    assert h.get("d3.xhtml") == "POGLAVLJE 6", h
    assert h.get("d5.xhtml") == "POGLAVLJE XIV \u2013 Otvori kutiju", h


def test_dokument_s_tekstom_i_slikom_ostaje_poglavlje(tmp_path):
    dok = ['<p>%s</p><img src="img.png"/><p>%s</p>' % (LONG, LONG)]
    src, out = tmp_path / "in.epub", tmp_path / "out.epub"
    _epub(src, "Kralj trnja: Druga knjiga Slomljenog Carstva", dok)
    res = S.run_epub_styler(str(src), output_path=str(out))
    assert res.get("ok") is True, res
    assert "d0.xhtml" in _h1(out)
