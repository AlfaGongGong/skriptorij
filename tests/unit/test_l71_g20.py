"""L71/G20: styler je fail-closed kad se .chk ne moze spojiti (nema EPUB-a od EN izvora)."""
import zipfile
from pathlib import Path

OPF = (
    '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="2.0" '
    'unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
    '<dc:title>Test</dc:title><dc:creator>Autor</dc:creator>'
    '<dc:identifier id="id">x1</dc:identifier><dc:language>en</dc:language></metadata>'
    '<manifest><item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/></manifest>'
    '<spine><itemref idref="c1"/></spine></package>'
)
CONT = (
    '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    '<rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'
)
CH = "<html><body><h1>One</h1><p>" + "word " * 80 + "</p></body></html>"


def _epub(path: Path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", CONT)
        z.writestr("content.opf", OPF)
        z.writestr("ch1.xhtml", CH)


def _skr(base: Path, ime: str, sadrzaj="<p>Rijec " + "rijec " * 60 + "kraj.</p>"):
    ck = base / ("_skr_" + ime) / "checkpoints"
    ck.mkdir(parents=True)
    (ck / "ch1.xhtml_blok_0.chk").write_text(sadrzaj, encoding="utf-8")


def _run(tmp_path, monkeypatch):
    import config.settings as cfg
    monkeypatch.setattr(cfg, "CHECKPOINT_BASE_DIR", tmp_path / "cp")
    from epub.styler import run_epub_styler
    ep = tmp_path / "abcdefghij_knjiga.epub"
    _epub(ep)
    out = tmp_path / "out.epub"
    return run_epub_styler(ep, output_path=out), out


def test_nejedinstven_skr_ne_pravi_epub(tmp_path, monkeypatch):
    _skr(tmp_path / "cp", "abcdefghij_knjiga_a")
    _skr(tmp_path / "cp", "abcdefghij_knjiga_b")
    res, out = _run(tmp_path, monkeypatch)
    assert res["ok"] is False and "G20" in res["error"], res
    assert not out.exists()


def test_jedinstven_skr_prolazi(tmp_path, monkeypatch):
    _skr(tmp_path / "cp", "abcdefghij_knjiga")
    res, out = _run(tmp_path, monkeypatch)
    assert res["ok"] is True, res
    assert out.exists()


def test_bez_skr_ostaje_ok(tmp_path, monkeypatch):
    (tmp_path / "cp").mkdir()
    res, out = _run(tmp_path, monkeypatch)
    assert res["ok"] is True, res
