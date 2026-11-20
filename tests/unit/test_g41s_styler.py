"""G41s: styler ne gradi EPUB kad .chk blokovi poglavlja imaju rupu u indeksima."""
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
TXT = "<p>Rijec " + "rijec " * 60 + "kraj.</p>"


def _epub(path: Path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", CONT)
        z.writestr("content.opf", OPF)
        z.writestr("ch1.xhtml", CH)


def _skr(base: Path, ime: str, idx):
    ck = base / ("_skr_" + ime) / "checkpoints"
    ck.mkdir(parents=True)
    for i in idx:
        (ck / f"ch1.xhtml_blok_{i}.chk").write_text(TXT, encoding="utf-8")


def _run(tmp_path, monkeypatch, idx):
    import config.settings as cfg
    monkeypatch.setattr(cfg, "CHECKPOINT_BASE_DIR", tmp_path / "cp")
    _skr(tmp_path / "cp", "abcdefghij_knjiga", idx)
    from epub.styler import run_epub_styler
    ep = tmp_path / "abcdefghij_knjiga.epub"
    _epub(ep)
    out = tmp_path / "out.epub"
    return run_epub_styler(ep, output_path=out), out


def test_rupa_ne_pravi_epub(tmp_path, monkeypatch):
    monkeypatch.delenv("BOOKLYFI_FINALIZE_OTVORENO", raising=False)
    res, out = _run(tmp_path, monkeypatch, [0, 2])
    assert res["ok"] is False and "G41" in res["error"], res
    assert not out.exists()


def test_uzastopni_prolazi(tmp_path, monkeypatch):
    monkeypatch.delenv("BOOKLYFI_FINALIZE_OTVORENO", raising=False)
    res, out = _run(tmp_path, monkeypatch, [0, 1])
    assert res["ok"] is True, res


def test_otvoreno_dopusta_rupu(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKLYFI_FINALIZE_OTVORENO", "1")
    res, out = _run(tmp_path, monkeypatch, [0, 2])
    assert res["ok"] is True, res
