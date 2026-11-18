"""L58 DIO 3: smoke test epub/packager.py finalize() + tools/epub_gate.py na mini EPUB-u.

Radni direktorij knjige (work_dir) sa zadanim EPUB-om i prevedenim .chk blokom ->
finalize() -> valjan zip -> gate(). Bez mreze, sve u tmp_path (OUTPUT_DIR se zamjenjuje).
"""
import sys
import zipfile
from pathlib import Path

import pytest

from tests.unit.test_l58_smoke import engine  # noqa: F401

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.epub_gate import gate  # noqa: E402

CONTAINER = (
    '<?xml version="1.0"?><container version="1.0" '
    'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
    '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
    "</rootfiles></container>"
)
OPF = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id">'
    '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
    "<dc:title>Mala knjiga</dc:title><dc:language>hr</dc:language>"
    '<dc:creator>Pisac</dc:creator><dc:identifier id="id">urn:test:1</dc:identifier>'
    "</metadata><manifest>"
    '<item id="ch1" href="chapter001.html" media-type="application/xhtml+xml"/>'
    '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
    '</manifest><spine toc="ncx"><itemref idref="ch1"/></spine></package>'
)
NCX = (
    '<?xml version="1.0"?><ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
    '<head><meta name="dtb:uid" content="urn:test:1"/></head><docTitle><text>Mala knjiga</text></docTitle>'
    '<navMap><navPoint id="n1" playOrder="1"><navLabel><text>Prvo poglavlje</text></navLabel>'
    '<content src="chapter001.html"/></navPoint></navMap></ncx>'
)
HR_TIJELO = (
    "<p>Starac je polako hodao cestom, a vjetar mu je hladno puhao u lice. "
    "Nije vidio brata godinama i nije znao što će mu reći.</p>"
)


def _html(tijelo):
    return (
        '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Prvo</title></head>'
        f"<body><h1>Prvo poglavlje</h1>{tijelo}</body></html>"
    )


@pytest.fixture
def knjiga(engine, tmp_path, monkeypatch):  # noqa: F811
    import epub.packager as pk

    izlaz = tmp_path / "izlaz"
    monkeypatch.setattr(pk, "_get_output_dir", lambda: izlaz)
    import config.settings as cs

    monkeypatch.setattr(cs, "INPUT_DIR", tmp_path / "ulaz")  # finalize brise (LIVE)_ kopiju
    engine.out_path = tmp_path / "Pisac_Mala_knjiga_PREVEDENO.epub"
    w = Path(engine.work_dir)
    (w / "META-INF").mkdir(parents=True, exist_ok=True)
    (w / "OEBPS").mkdir(parents=True, exist_ok=True)
    (w / "mimetype").write_text("application/epub+zip", encoding="ascii")
    (w / "META-INF" / "container.xml").write_text(CONTAINER, encoding="utf-8")
    (w / "OEBPS" / "content.opf").write_text(OPF, encoding="utf-8")
    (w / "OEBPS" / "toc.ncx").write_text(NCX, encoding="utf-8")
    (w / "OEBPS" / "chapter001.html").write_text(_html(HR_TIJELO), encoding="utf-8")
    return engine


def test_finalize_pakira_valjan_epub_koji_prolazi_gate(knjiga):
    knjiga.finalize()
    out = Path(knjiga.out_path)
    assert out.exists()
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None
        imena = z.namelist()
        assert imena[0] == "mimetype"
        assert z.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
        assert "META-INF/container.xml" in imena
        sadrzaj = "\n".join(
            z.read(n).decode("utf-8", "ignore") for n in imena if n.endswith("html")
        )
    assert "Starac" in sadrzaj
    assert not any("checkpoints" in n for n in imena)
    assert knjiga.shared_stats.get("status") == "ZAVRŠENO"
    ok, nalazi = gate(str(out), forbid=())
    fail = [n for n in nalazi if n[0] == "FAIL"]
    assert ok and not fail, f"gate FAIL: {fail}"


def test_gate_odbija_epub_s_markerom_neprevedeno(knjiga):
    p = Path(knjiga.work_dir) / "OEBPS" / "chapter001.html"
    p.write_text(_html("<p>[[NEPREVEDENO: blok 0]]</p>"), encoding="utf-8")
    knjiga.finalize()
    ok, nalazi = gate(str(knjiga.out_path), forbid=())
    assert not ok
    assert any("placeholder" in n[1] for n in nalazi if n[0] == "FAIL")


def test_end_to_end_prijevod_pa_pakiranje_pa_gate(knjiga, monkeypatch):
    """Cijeli lanac: EN poglavlje -> worker (lazni provider) -> finalize -> gate."""
    import asyncio
    import socket

    import core.kalkovi.dinamicki_detektor as dd
    import processing.parallel as par
    from tests.unit.test_l58_smoke import HR_PREVOD, _lazni

    monkeypatch.setattr(dd, "CLASSLA_DOSTUPAN", False)
    monkeypatch.setattr(par, "_RETRY_PAUZA", 0)
    _init0 = par.AdaptiveParallelism.__init__

    def _init(self, engine):
        _init0(self, engine)
        self._human_delay = (0.0, 0.0)

    monkeypatch.setattr(par.AdaptiveParallelism, "__init__", _init)

    def _zabrani(self, *a, **k):
        raise OSError("L58: mreza zabranjena u testu")

    monkeypatch.setattr(socket.socket, "connect", _zabrani)

    knjiga.fleet.get_total_active_keys = lambda: 2
    knjiga.fleet.keys = lambda: []
    knjiga.buildlive_epub = lambda *a, **k: None
    p = Path(knjiga.work_dir) / "OEBPS" / "chapter001.html"
    p.write_text(
        _html(
            "<p>The old man walked slowly down the road, and the wind was cold against "
            "his face. He had not seen his brother for many years, and he did not know "
            "what he would say.</p>"
        ),
        encoding="utf-8",
    )
    _lazni(knjiga, lambda u, pr: (HR_PREVOD, "LAZNI"))
    asyncio.run(knjiga.process_single_file_worker(p))
    knjiga.finalize()
    with zipfile.ZipFile(knjiga.out_path) as z:
        tekst = "\n".join(
            z.read(n).decode("utf-8", "ignore") for n in z.namelist() if n.endswith("html")
        )
    assert "Starac" in tekst
    assert "The old man" not in tekst
    ok, nalazi = gate(str(knjiga.out_path), forbid=())
    fail = [n for n in nalazi if n[0] == "FAIL"]
    assert ok and not fail, f"gate FAIL: {fail}"
