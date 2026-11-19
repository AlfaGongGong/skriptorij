"""L71/G20 DIO 2: stilizator odbija knjigu koja je ostala engleska, propusta hrvatsku."""
from core.jezik_epub import dokument_je_engleski, ocijeni_knjigu

EN = ("<p>" + "She was not sure that they would have been there when the old man "
      "came into the house, but he had her with him and the others. " * 12 + "</p>")
HR = ("<p>" + "Nije bila sigurna hoće li stari čovjek doći u kuću, ali je on "
      "doveo djevojku sa sobom i ostale ljude iz sela. " * 12 + "</p>")


def test_engleski_i_hrvatski_dokument():
    assert dokument_je_engleski(EN) is True
    assert dokument_je_engleski(HR) is False


def test_kratki_dokument_se_ne_ocjenjuje():
    assert dokument_je_engleski("<p>The and was for with his they.</p>") is False


def test_hrvatska_knjiga_prolazi():
    ok, _, st = ocijeni_knjigu([("a%d.html" % i, HR) for i in range(6)])
    assert ok and st["engleskih"] == 0


def test_engleska_knjiga_pada():
    ok, msg, _ = ocijeni_knjigu([("a%d.html" % i, EN) for i in range(6)])
    assert not ok and "engleskih dokumenata 6 od 6" in msg


def test_mjesovita_knjiga_ispod_praga_prolazi():
    docs = [("h%d.html" % i, HR) for i in range(9)] + [("e.html", EN)]
    assert ocijeni_knjigu(docs)[0] is True


def test_styler_odbija_en_izvor_bez_chk(tmp_path, monkeypatch):
    import zipfile
    import config.settings as cfg
    monkeypatch.setattr(cfg, "CHECKPOINT_BASE_DIR", tmp_path / "cp")
    (tmp_path / "cp").mkdir()
    from tests.unit import test_l71_g20 as t
    from epub.styler import run_epub_styler
    ep = tmp_path / "abcdefghij_knjiga.epub"
    with zipfile.ZipFile(ep, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", t.CONT)
        z.writestr("content.opf", t.OPF)
        z.writestr("ch1.xhtml", "<html><body><h1>One</h1>" + EN + "</body></html>")
    out = tmp_path / "out.epub"
    res = run_epub_styler(ep, output_path=out)
    assert res["ok"] is False and "G20" in res["error"] and not out.exists(), res
