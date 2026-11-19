"""G26: impresum s dijakriticima, dc:language hr/bs u izlazu stilizatora, gate odbija pogresan jezik."""
import base64
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bs4 import BeautifulSoup
import epub.styler as S
from tools.epub_gate import gate

LONG = "Ovo je dugacak odlomak koji pocinje pravim tekstom poglavlja i ima vise od sezdeset znakova da bi dropcap mogao na njega. " * 4
PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


def _epub(path, lang):
    ch = lambda b: ('<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>T</title></head><body>%s</body></html>' % b).encode()
    opf = ('<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Kralj trnja</dc:title><dc:creator>Autor</dc:creator><dc:language>%s</dc:language><dc:identifier id="id">x1</dc:identifier></metadata><manifest><item id="d0" href="d0.xhtml" media-type="application/xhtml+xml"/><item id="img" href="img.png" media-type="image/png"/></manifest><spine><itemref idref="d0"/></spine></package>' % lang).encode()
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", b"application/epub+zip", zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", b'<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        z.writestr("OEBPS/img.png", base64.b64decode(PNG))
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/d0.xhtml", ch("<p>%s</p><p>%s</p>" % (LONG, LONG)))


def _stiliziraj(tmp_path, lang):
    src, out = tmp_path / "in.epub", tmp_path / "out.epub"
    _epub(src, lang)
    res = S.run_epub_styler(str(src), output_path=str(out))
    assert res.get("ok") is True, res
    return out


def _opf_lang(out):
    with zipfile.ZipFile(out) as z:
        n = [x for x in z.namelist() if x.endswith(".opf")][0]
        return BeautifulSoup(z.read(n), "xml").find("dc:language").get_text(strip=True)


def test_en_postaje_hr(tmp_path):
    assert _opf_lang(_stiliziraj(tmp_path, "en")) == "hr"


def test_hr_i_bs_ostaju(tmp_path):
    assert _opf_lang(_stiliziraj(tmp_path, "hr")) == "hr"
    d = tmp_path / "b"
    d.mkdir()
    assert _opf_lang(_stiliziraj(d, "bs")) == "bs"


def test_impresum_dijakritici(tmp_path):
    out = _stiliziraj(tmp_path, "hr")
    with zipfile.ZipFile(out) as z:
        n = [x for x in z.namelist() if x.endswith("booklyfi_002_impresum.xhtml")][0]
        t = z.read(n).decode("utf-8")
    assert "Sva prava pridržana." in t and "zadrzana" not in t
    assert "izvorno djelo" in t


def test_gate_odbija_en_jezik(tmp_path):
    out = _stiliziraj(tmp_path, "hr")
    lose = tmp_path / "lose.epub"
    with zipfile.ZipFile(out) as zi, zipfile.ZipFile(lose, "w") as zo:
        for it in zi.infolist():
            d = zi.read(it.filename)
            if it.filename.endswith(".opf"):
                d = re.sub(rb"<dc:language[^>]*>[^<]*</dc:language>", b"<dc:language>en</dc:language>", d)
            zo.writestr(it, d, compress_type=it.compress_type)
    ok, nalazi = gate(str(lose), forbid=())
    assert any("dc:language nije hr/bs" in str(n) for n in nalazi)
    ok2, nalazi2 = gate(str(out), forbid=())
    assert not any("dc:language nije hr/bs" in str(n) for n in nalazi2)
